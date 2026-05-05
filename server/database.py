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
        SELECT e.id as event_id, e.machine_id, m.name as machine_name, e.event_type, e.timestamp
        FROM events e
        JOIN machines m ON e.machine_id = m.id
        WHERE e.id = ?
        """,
        (event_id,)
    )
    await db.close()

    event = dict(row[0])
    print(f"[EVENT] Новый выигрыш: аппарат={event['machine_name']}, тип={event['event_type']}, время={event['timestamp']}")
    return event


async def get_public_stats() -> dict:
    """Получить статистику для публичного экрана."""
    db = await get_db()

    row_24h = await db.execute_fetchall(
        "SELECT COUNT(*) as count FROM events WHERE timestamp >= datetime('now', '-24 hours', 'localtime')"
    )
    wins_24h = row_24h[0]["count"]

    row_last = await db.execute_fetchall(
        """
        SELECT e.timestamp, m.name as machine_name
        FROM events e
        JOIN machines m ON e.machine_id = m.id
        ORDER BY e.timestamp DESC
        LIMIT 1
        """
    )
    last_win = dict(row_last[0]) if row_last else None

    await db.close()
    return {"wins_24h": wins_24h, "last_win": last_win}


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


async def get_machines() -> list:
    """Получить список всех аппаратов."""
    db = await get_db()
    rows = await db.execute_fetchall("SELECT * FROM machines ORDER BY id")
    await db.close()
    return [dict(row) for row in rows]


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

    row_jackpot = await db.execute_fetchall(
        "SELECT * FROM jackpot_config WHERE machine_id = ?",
        (machine_id,)
    )
    jackpot = dict(row_jackpot[0]) if row_jackpot else None

    await db.close()
    return {
        "machine_id": machine_id,
        "wins_hour": wins_hour,
        "wins_today": wins_today,
        "wins_24h": wins_24h,
        "wins_total": wins_total,
        "last_win": last_win,
        "jackpot_config": jackpot
    }


async def get_all_machines_stats() -> list:
    """Получить статистику по всем аппаратам сразу."""
    stats = []
    for machine_id in range(1, 11):
        s = await get_machine_stats(machine_id)
        stats.append(s)
    return stats


async def get_events_history(limit: int = 100, offset: int = 0) -> list:
    """Получить историю выигрышей (с пагинацией)."""
    db = await get_db()
    rows = await db.execute_fetchall(
        """
        SELECT e.id, e.machine_id, m.name as machine_name, e.event_type, e.timestamp
        FROM events e
        JOIN machines m ON e.machine_id = m.id
        ORDER BY e.timestamp DESC
        LIMIT ? OFFSET ?
        """,
        (limit, offset)
    )
    await db.close()
    return [dict(row) for row in rows]


async def get_total_events_count() -> int:
    """Общее количество событий (для пагинации)."""
    db = await get_db()
    row = await db.execute_fetchall("SELECT COUNT(*) as count FROM events")
    await db.close()
    return row[0]["count"]