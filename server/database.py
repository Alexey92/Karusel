"""
Работа с SQLite базой данных.
Используем aiosqlite для асинхронной работы (не блокирует сервер).
"""
import aiosqlite
import os

# Путь к файлу базы данных (в папке server)
DB_PATH = os.path.join(os.path.dirname(__file__), "karusel.db")
SCHEMA_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), "schema.sql")


async def get_db():
    """Получить соединение с БД."""
    db = await aiosqlite.connect(DB_PATH)
    db.row_factory = aiosqlite.Row
    return db


async def init_db():
    """Инициализация базы данных: создание таблиц и тестовых данных."""
    if os.path.exists(DB_PATH):
        print(f"[DB] База данных уже существует: {DB_PATH}")
        return

    print("[DB] Создаю новую базу данных...")
    db = await aiosqlite.connect(DB_PATH)

    with open(SCHEMA_PATH, "r", encoding="utf-8") as f:
        schema = f.read()

    await db.executescript(schema)
    await db.commit()
    await db.close()
    print("[DB] База данных создана и заполнена тестовыми данными.")


async def add_event(machine_id: int, event_type: str = "win") -> dict:
    """Добавить событие выигрыша в БД."""
    db = await get_db()
    cursor = await db.execute(
        "INSERT INTO events (machine_id, event_type) VALUES (?, ?)",
        (machine_id, event_type)
    )
    await db.commit()
    event_id = cursor.lastrowid

    row = await db.execute_fetchall(
        """
        SELECT e.id as event_id, e.machine_id, m.name as machine_name, 
               m.location_id, l.name as location_name, e.event_type, e.timestamp
        FROM events e
        JOIN machines m ON e.machine_id = m.id
        JOIN locations l ON m.location_id = l.id
        WHERE e.id = ?
        """,
        (event_id,)
    )
    await db.close()

    event = dict(row[0])
    print(f"[EVENT] Выигрыш: {event['machine_name']} ({event['location_name']}), тип={event['event_type']}")
    return event


async def get_public_stats(location_id: int = None) -> dict:
    """Получить статистику для публичного экрана."""
    db = await get_db()

    query_24h = "SELECT COUNT(*) as count FROM events e JOIN machines m ON e.machine_id = m.id WHERE e.timestamp >= datetime('now', '-24 hours', 'localtime')"
    query_last = """
        SELECT e.timestamp, m.name as machine_name, l.name as location_name
        FROM events e
        JOIN machines m ON e.machine_id = m.id
        JOIN locations l ON m.location_id = l.id
    """
    params = []
    if location_id:
        query_24h += " AND m.location_id = ?"
        query_last += " WHERE m.location_id = ?"
        params.append(location_id)

    query_last += " ORDER BY e.timestamp DESC LIMIT 1"

    row_24h = await db.execute_fetchall(query_24h, tuple(params))
    wins_24h = row_24h[0]["count"]

    row_last = await db.execute_fetchall(query_last, tuple(params))
    last_win = dict(row_last[0]) if row_last else None

    # Всего выигрышей
    query_total = "SELECT COUNT(*) as count FROM events e JOIN machines m ON e.machine_id = m.id"
    total_params = tuple(params) if params else ()
    if location_id:
        query_total += " WHERE m.location_id = ?"
    row_total = await db.execute_fetchall(query_total, total_params)
    total_wins = row_total[0]["count"]

    # Джекпот (суммарный по адресу или общий)
    jackpot_query = "SELECT SUM(current_win_count) as current, SUM(win_count_for_jackpot) as threshold FROM jackpot_config"
    jackpot_params = ()
    if location_id:
        jackpot_query += " WHERE location_id = ?"
        jackpot_params = (location_id,)
    row_jackpot = await db.execute_fetchall(jackpot_query, jackpot_params)
    jackpot = dict(row_jackpot[0]) if row_jackpot else {"current": 0, "threshold": 0}

    await db.close()
    return {
        "wins_24h": wins_24h,
        "total_wins": total_wins,
        "last_win": last_win,
        "jackpot_current": jackpot["current"] or 0,
        "jackpot_threshold": jackpot["threshold"] or 0
    }


async def get_user(username: str) -> dict | None:
    """Получить пользователя по имени."""
    db = await get_db()
    row = await db.execute_fetchall(
        "SELECT * FROM users WHERE username = ?", (username,)
    )
    await db.close()
    return dict(row[0]) if row else None


async def update_admin_password(username: str, password_hash: str):
    """Обновить хеш пароля администратора."""
    db = await get_db()
    await db.execute(
        "UPDATE users SET password_hash = ? WHERE username = ?",
        (password_hash, username)
    )
    await db.commit()
    await db.close()
    print(f"[DB] Пароль пользователя '{username}' обновлён.")


async def get_locations() -> list:
    """Получить список всех адресов."""
    db = await get_db()
    rows = await db.execute_fetchall("SELECT * FROM locations ORDER BY id")
    await db.close()
    return [dict(row) for row in rows]


async def create_location(name: str) -> dict:
    """Создать новый адрес."""
    db = await get_db()
    cursor = await db.execute("INSERT INTO locations (name) VALUES (?)", (name,))
    await db.commit()
    loc_id = cursor.lastrowid

    # Создаём настройки джекпота для нового адреса
    await db.execute(
        "INSERT INTO jackpot_config (location_id, win_count_for_jackpot, current_win_count) VALUES (?, 100, 0)",
        (loc_id,)
    )
    await db.commit()
    await db.close()
    return {"id": loc_id, "name": name}


async def update_location(location_id: int, name: str) -> dict:
    """Обновить адрес."""
    db = await get_db()
    await db.execute("UPDATE locations SET name = ? WHERE id = ?", (name, location_id))
    await db.commit()
    await db.close()
    return {"id": location_id, "name": name}


async def delete_location(location_id: int):
    """Удалить адрес и все связанные автоматы и настройки."""
    db = await get_db()
    await db.execute("DELETE FROM jackpot_config WHERE location_id = ?", (location_id,))
    await db.execute("DELETE FROM events WHERE machine_id IN (SELECT id FROM machines WHERE location_id = ?)", (location_id,))
    await db.execute("DELETE FROM machines WHERE location_id = ?", (location_id,))
    await db.execute("DELETE FROM locations WHERE id = ?", (location_id,))
    await db.commit()
    await db.close()


async def get_machines(location_id: int = None) -> list:
    """Получить список аппаратов (всех или по адресу)."""
    db = await get_db()
    if location_id:
        rows = await db.execute_fetchall(
            "SELECT m.*, l.name as location_name FROM machines m JOIN locations l ON m.location_id = l.id WHERE m.location_id = ? ORDER BY m.id",
            (location_id,)
        )
    else:
        rows = await db.execute_fetchall(
            "SELECT m.*, l.name as location_name FROM machines m JOIN locations l ON m.location_id = l.id ORDER BY m.id"
        )
    await db.close()
    return [dict(row) for row in rows]


async def create_machine(name: str, location_id: int) -> dict:
    """Добавить автомат на адрес."""
    db = await get_db()
    cursor = await db.execute(
        "INSERT INTO machines (name, location_id) VALUES (?, ?)",
        (name, location_id)
    )
    await db.commit()
    machine_id = cursor.lastrowid
    await db.close()
    return {"id": machine_id, "name": name, "location_id": location_id}


async def delete_machine(machine_id: int):
    """Удалить автомат."""
    db = await get_db()
    await db.execute("DELETE FROM events WHERE machine_id = ?", (machine_id,))
    await db.execute("DELETE FROM machines WHERE id = ?", (machine_id,))
    await db.commit()
    await db.close()


async def get_machine_stats(machine_id: int) -> dict:
    """Получить подробную статистику по одному аппарату."""
    db = await get_db()

    row_hour = await db.execute_fetchall(
        "SELECT COUNT(*) as count FROM events WHERE machine_id = ? AND timestamp >= datetime('now', '-1 hours', 'localtime')",
        (machine_id,)
    )
    wins_hour = row_hour[0]["count"]

    row_today = await db.execute_fetchall(
        "SELECT COUNT(*) as count FROM events WHERE machine_id = ? AND date(timestamp, 'localtime') = date('now', 'localtime')",
        (machine_id,)
    )
    wins_today = row_today[0]["count"]

    row_24h = await db.execute_fetchall(
        "SELECT COUNT(*) as count FROM events WHERE machine_id = ? AND timestamp >= datetime('now', '-24 hours', 'localtime')",
        (machine_id,)
    )
    wins_24h = row_24h[0]["count"]

    row_total = await db.execute_fetchall(
        "SELECT COUNT(*) as count FROM events WHERE machine_id = ?",
        (machine_id,)
    )
    wins_total = row_total[0]["count"]

    row_last = await db.execute_fetchall(
        "SELECT timestamp FROM events WHERE machine_id = ? ORDER BY timestamp DESC LIMIT 1",
        (machine_id,)
    )
    last_win = row_last[0]["timestamp"] if row_last else None

    # Джекпот по адресу, к которому привязан автомат
    row_location = await db.execute_fetchall(
        "SELECT location_id FROM machines WHERE id = ?", (machine_id,)
    )
    location_id = dict(row_location[0])["location_id"] if row_location else None

    row_jackpot = await db.execute_fetchall(
        "SELECT * FROM jackpot_config WHERE location_id = ?",
        (location_id,)
    )
    jackpot = dict(row_jackpot[0]) if row_jackpot else None

    await db.close()
    return {
        "machine_id": machine_id,
        "location_id": location_id,
        "wins_hour": wins_hour,
        "wins_today": wins_today,
        "wins_24h": wins_24h,
        "wins_total": wins_total,
        "last_win": last_win,
        "jackpot_config": jackpot
    }


async def get_location_stats(location_id: int) -> dict:
    """Статистика по всем автоматам на адресе."""
    db = await get_db()
    machines = await db.execute_fetchall(
        "SELECT id FROM machines WHERE location_id = ?", (location_id,)
    )
    machine_ids = [dict(m)["id"] for m in machines]

    if not machine_ids:
        await db.close()
        return {"location_id": location_id, "machines": [], "jackpot_config": None}

    # Суммарная статистика
    placeholders = ",".join("?" * len(machine_ids))
    row_jackpot = await db.execute_fetchall(
        "SELECT * FROM jackpot_config WHERE location_id = ?", (location_id,)
    )
    jackpot = dict(row_jackpot[0]) if row_jackpot else None

    await db.close()
    return {
        "location_id": location_id,
        "machine_count": len(machine_ids),
        "jackpot_config": jackpot
    }


async def get_all_machines_stats() -> list:
    """Получить статистику по всем автоматам."""
    machines = await get_machines()
    stats = []
    for m in machines:
        s = await get_machine_stats(m["id"])
        stats.append(s)
    return stats


async def get_events_history(limit: int = 100, offset: int = 0, location_id: int = None) -> list:
    """Получить историю выигрышей (с пагинацией и фильтром по адресу)."""
    db = await get_db()
    query = """
        SELECT e.id, e.machine_id, m.name as machine_name, m.location_id, l.name as location_name, e.event_type, e.timestamp
        FROM events e
        JOIN machines m ON e.machine_id = m.id
        JOIN locations l ON m.location_id = l.id
    """
    params = []
    if location_id:
        query += " WHERE m.location_id = ?"
        params.append(location_id)
    query += " ORDER BY e.timestamp DESC LIMIT ? OFFSET ?"
    params.extend([limit, offset])

    rows = await db.execute_fetchall(query, tuple(params))
    await db.close()
    return [dict(row) for row in rows]


async def get_total_events_count(location_id: int = None) -> int:
    """Общее количество событий."""
    db = await get_db()
    query = "SELECT COUNT(*) as count FROM events e JOIN machines m ON e.machine_id = m.id"
    params = ()
    if location_id:
        query += " WHERE m.location_id = ?"
        params = (location_id,)
    row = await db.execute_fetchall(query, params)
    await db.close()
    return row[0]["count"]


async def increment_jackpot(machine_id: int) -> dict:
    """Увеличить счётчик главного приза для адреса, к которому привязан автомат."""
    db = await get_db()

    # Определяем location_id
    row = await db.execute_fetchall("SELECT location_id FROM machines WHERE id = ?", (machine_id,))
    if not row:
        await db.close()
        return {"jackpot_triggered": False, "current_win_count": 0, "win_count_for_jackpot": 0, "threshold": 0}

    location_id = dict(row[0])["location_id"]

    # Получаем текущие настройки джекпота для адреса
    row = await db.execute_fetchall(
        "SELECT * FROM jackpot_config WHERE location_id = ?",
        (location_id,)
    )
    config = dict(row[0])
    current = config["current_win_count"] + 1
    threshold = config["win_count_for_jackpot"]

    jackpot_triggered = False
    if current >= threshold:
        jackpot_triggered = True
        current = 0

    await db.execute(
        "UPDATE jackpot_config SET current_win_count = ? WHERE location_id = ?",
        (current, location_id)
    )
    await db.commit()

    row = await db.execute_fetchall(
        "SELECT * FROM jackpot_config WHERE location_id = ?",
        (location_id,)
    )
    await db.close()

    result = dict(row[0])
    result["jackpot_triggered"] = jackpot_triggered
    result["threshold"] = threshold

    if jackpot_triggered:
        print(f"[JACKPOT] 🎰 ГЛАВНЫЙ ПРИЗ на адресе {location_id}! Аппарат {machine_id}. Счётчик сброшен.")

    return result


async def set_jackpot_threshold(location_id: int, win_count: int) -> dict:
    """Установить порог главного приза для адреса."""
    db = await get_db()
    await db.execute(
        "UPDATE jackpot_config SET win_count_for_jackpot = ? WHERE location_id = ?",
        (win_count, location_id)
    )
    await db.commit()
    row = await db.execute_fetchall("SELECT * FROM jackpot_config WHERE location_id = ?", (location_id,))
    await db.close()
    return dict(row[0])


async def reset_jackpot(location_id: int) -> dict:
    """Сбросить счётчик главного приза для адреса."""
    db = await get_db()
    await db.execute(
        "UPDATE jackpot_config SET current_win_count = 0 WHERE location_id = ?",
        (location_id,)
    )
    await db.commit()
    row = await db.execute_fetchall("SELECT * FROM jackpot_config WHERE location_id = ?", (location_id,))
    await db.close()
    return dict(row[0])


async def set_jackpot_counter(location_id: int, count: int) -> dict:
    """Установить счётчик главного приза вручную."""
    db = await get_db()
    row = await db.execute_fetchall(
        "SELECT win_count_for_jackpot FROM jackpot_config WHERE location_id = ?",
        (location_id,)
    )
    threshold = dict(row[0])["win_count_for_jackpot"]

    if count >= threshold:
        count = 0

    await db.execute(
        "UPDATE jackpot_config SET current_win_count = ? WHERE location_id = ?",
        (count, location_id)
    )
    await db.commit()
    row = await db.execute_fetchall("SELECT * FROM jackpot_config WHERE location_id = ?", (location_id,))
    await db.close()
    return dict(row[0])