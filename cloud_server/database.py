"""
Работа с PostgreSQL (через asyncpg).
"""
import asyncpg
import os
from datetime import date


DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://karusel:karusel@localhost:5432/karusel")
pool = None

async def get_pool():
    global pool
    if pool is None:
        pool = await asyncpg.create_pool(DATABASE_URL, min_size=2, max_size=10)
    return pool

async def get_db():
    p = await get_pool()
    return await p.acquire()

async def release_db(conn):
    p = await get_pool()
    await p.release(conn)

async def init_db():
    p = await get_pool()
    async with p.acquire() as conn:
        with open(os.path.join(os.path.dirname(__file__), "schema.sql"), "r") as f:
            await conn.execute(f.read())
    print("[DB] База данных инициализирована.")

async def add_event(machine_id: int, location_id: int, event_type: str, local_event_id: int = None) -> dict:
    p = await get_pool()
    async with p.acquire() as conn:
        if local_event_id:
            existing = await conn.fetchrow(
                "SELECT id FROM events WHERE location_id = $1 AND local_event_id = $2",
                location_id, local_event_id
            )
            if existing:
                return {"status": "duplicate", "id": existing["id"]}

        row = await conn.fetchrow(
            "INSERT INTO events (machine_id, location_id, event_type, local_event_id) VALUES ($1, $2, $3, $4) RETURNING id, machine_id, location_id, event_type, timestamp",
            machine_id, location_id, event_type, local_event_id
        )

        machine = await conn.fetchrow("SELECT name FROM machines WHERE id = $1", machine_id)
        location = await conn.fetchrow("SELECT name FROM locations WHERE id = $1", location_id)

        return {
            "event_id": row["id"],
            "machine_id": row["machine_id"],
            "machine_name": machine["name"] if machine else f"Автомат №{machine_id}",
            "location_id": row["location_id"],
            "location_name": location["name"] if location else "",
            "event_type": row["event_type"],
            "timestamp": row["timestamp"].strftime("%Y-%m-%d %H:%M:%S"),
            "status": "ok"
        }

async def find_or_create_machine(location_id: int, local_id: int, name: str = None) -> int:
    """Найти автомат по location_id и local_id, если нет — создать."""
    p = await get_pool()
    async with p.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT id FROM machines WHERE location_id = $1 AND local_id = $2",
            location_id, local_id
        )
        if row:
            return row["id"]

        if not name:
            name = f"Автомат №{local_id}"

        row = await conn.fetchrow(
            "INSERT INTO machines (local_id, name, location_id) VALUES ($1, $2, $3) ON CONFLICT (location_id, local_id) DO UPDATE SET name = $2 RETURNING id",
            local_id, name, location_id
        )
        return row["id"]

async def verify_api_key(location_id: int, api_key: str) -> bool:
    p = await get_pool()
    async with p.acquire() as conn:
        row = await conn.fetchrow("SELECT api_key FROM locations WHERE id = $1", location_id)
        return row is not None and row["api_key"] == api_key

async def get_user(username: str) -> dict:
    p = await get_pool()
    async with p.acquire() as conn:
        row = await conn.fetchrow("SELECT * FROM users WHERE username = $1", username)
        return dict(row) if row else None

async def update_admin_password(username: str, password_hash: str):
    p = await get_pool()
    async with p.acquire() as conn:
        await conn.execute("UPDATE users SET password_hash = $1 WHERE username = $2", password_hash, username)

async def get_locations() -> list:
    p = await get_pool()
    async with p.acquire() as conn:
        rows = await conn.fetch("SELECT * FROM locations ORDER BY id")
        return [dict(r) for r in rows]

async def create_location(name: str, api_key: str) -> dict:
    p = await get_pool()
    async with p.acquire() as conn:
        row = await conn.fetchrow(
            "INSERT INTO locations (name, api_key) VALUES ($1, $2) RETURNING id, name, api_key",
            name, api_key
        )
        await conn.execute("INSERT INTO jackpot_config (location_id) VALUES ($1)", row["id"])
        return dict(row)

async def update_location(location_id: int, name: str):
    p = await get_pool()
    async with p.acquire() as conn:
        await conn.execute("UPDATE locations SET name = $1 WHERE id = $2", name, location_id)

async def delete_location(location_id: int):
    p = await get_pool()
    async with p.acquire() as conn:
        await conn.execute("DELETE FROM jackpot_config WHERE location_id = $1", location_id)
        await conn.execute("DELETE FROM events WHERE location_id = $1", location_id)
        await conn.execute("DELETE FROM machines WHERE location_id = $1", location_id)
        await conn.execute("DELETE FROM locations WHERE id = $1", location_id)

async def get_machines(location_id: int = None) -> list:
    p = await get_pool()
    async with p.acquire() as conn:
        if location_id:
            rows = await conn.fetch(
                "SELECT m.*, l.name as location_name FROM machines m JOIN locations l ON m.location_id = l.id WHERE m.location_id = $1 ORDER BY m.local_id",
                location_id
            )
        else:
            rows = await conn.fetch(
                "SELECT m.*, l.name as location_name FROM machines m JOIN locations l ON m.location_id = l.id ORDER BY m.id"
            )
        return [dict(r) for r in rows]

async def create_machine(local_id: int, name: str, location_id: int) -> dict:
    p = await get_pool()
    async with p.acquire() as conn:
        row = await conn.fetchrow(
            "INSERT INTO machines (local_id, name, location_id) VALUES ($1, $2, $3) ON CONFLICT (location_id, local_id) DO UPDATE SET name = $2 RETURNING id, local_id, name, location_id",
            local_id, name, location_id
        )
        return dict(row)

async def update_machine(machine_id: int, local_id: int = None, name: str = None):
    p = await get_pool()
    async with p.acquire() as conn:
        if local_id is not None and name is not None:
            await conn.execute(
                "UPDATE machines SET local_id = $1, name = $2 WHERE id = $3",
                local_id, name, machine_id
            )
        elif local_id is not None:
            await conn.execute(
                "UPDATE machines SET local_id = $1 WHERE id = $2",
                local_id, machine_id
            )
        elif name is not None:
            await conn.execute(
                "UPDATE machines SET name = $1 WHERE id = $2",
                name, machine_id
            )

async def delete_machine(machine_id: int):
    p = await get_pool()
    async with p.acquire() as conn:
        await conn.execute("DELETE FROM events WHERE machine_id = $1", machine_id)
        await conn.execute("DELETE FROM machines WHERE id = $1", machine_id)

async def get_machine_stats(machine_id: int, from_date: str = None, to_date: str = None) -> dict:
    if from_date:
        from_date = date.fromisoformat(from_date)
    if to_date:
        to_date = date.fromisoformat(to_date)
        
    p = await get_pool()
    async with p.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT m.name as machine_name, m.local_id, m.location_id, l.name as location_name FROM machines m JOIN locations l ON m.location_id = l.id WHERE m.id = $1",
            machine_id
        )
        if not row:
            return {}
        info = dict(row)

        wins_hour = await conn.fetchval("SELECT COUNT(*) FROM events WHERE machine_id = $1 AND event_type != 'play' AND timestamp >= NOW() - INTERVAL '1 hour'", machine_id)
        wins_today = await conn.fetchval("SELECT COUNT(*) FROM events WHERE machine_id = $1 AND event_type != 'play' AND date(timestamp) = CURRENT_DATE", machine_id)
        wins_24h = await conn.fetchval("SELECT COUNT(*) FROM events WHERE machine_id = $1 AND event_type != 'play' AND timestamp >= NOW() - INTERVAL '24 hours'", machine_id)
        wins_total = await conn.fetchval("SELECT COUNT(*) FROM events WHERE machine_id = $1 AND event_type != 'play'", machine_id)
        plays_total = await conn.fetchval("SELECT COUNT(*) FROM events WHERE machine_id = $1 AND event_type = 'play'", machine_id)
        
        wins_period = 0
        plays_period = 0
        if from_date and to_date:
            wins_period = await conn.fetchval(
                "SELECT COUNT(*) FROM events WHERE machine_id = $1 AND event_type != 'play' AND date(timestamp) BETWEEN $2 AND $3",
                machine_id, from_date, to_date
            ) or 0
            plays_period = await conn.fetchval(
                "SELECT COUNT(*) FROM events WHERE machine_id = $1 AND event_type = 'play' AND date(timestamp) BETWEEN $2 AND $3",
                machine_id, from_date, to_date
            ) or 0
        
        last_win = await conn.fetchval("SELECT timestamp FROM events WHERE machine_id = $1 AND event_type != 'play' ORDER BY timestamp DESC LIMIT 1", machine_id)
        jackpot = await conn.fetchrow("SELECT * FROM jackpot_config WHERE location_id = $1", info["location_id"])

        return {
            "machine_id": machine_id,
            "local_id": info["local_id"],
            "machine_name": info["machine_name"],
            "location_id": info["location_id"],
            "location_name": info["location_name"],
            "wins_hour": wins_hour or 0,
            "wins_today": wins_today or 0,
            "wins_24h": wins_24h or 0,
            "wins_total": wins_total or 0,
            "plays_total": plays_total or 0,
            "last_win": last_win.isoformat() if last_win else None,
            "jackpot_config": dict(jackpot) if jackpot else None,
            "wins_period": wins_period,
            "plays_period": plays_period
        }

async def get_all_machines_stats(from_date: str = None, to_date: str = None) -> list:
    if from_date:
        from_date = date.fromisoformat(from_date)
    if to_date:
        to_date = date.fromisoformat(to_date)
    
    machines = await get_machines()
    stats = []
    for m in machines:
        s = await get_machine_stats(m["id"], from_date, to_date)
        if s:
            stats.append(s)
    return stats

async def get_events_history(limit: int = 50, offset: int = 0, location_id: int = None) -> list:
    p = await get_pool()
    async with p.acquire() as conn:
        query = """
            SELECT e.id, e.machine_id, m.name as machine_name, e.location_id, l.name as location_name, e.event_type, e.timestamp
            FROM events e
            JOIN machines m ON e.machine_id = m.id
            JOIN locations l ON e.location_id = l.id
        """
        params = []
        if location_id:
            query += " WHERE e.location_id = $1"
            params.append(location_id)
        query += " ORDER BY e.timestamp DESC LIMIT $" + str(len(params)+1) + " OFFSET $" + str(len(params)+2)
        params.extend([limit, offset])
        rows = await conn.fetch(query, *params)
        return [dict(r) for r in rows]

async def get_total_events_count(location_id: int = None) -> int:
    p = await get_pool()
    async with p.acquire() as conn:
        if location_id:
            return await conn.fetchval("SELECT COUNT(*) FROM events WHERE location_id = $1", location_id)
        return await conn.fetchval("SELECT COUNT(*) FROM events")

async def increment_jackpot(machine_id: int) -> dict:
    p = await get_pool()
    async with p.acquire() as conn:
        location = await conn.fetchrow("SELECT location_id FROM machines WHERE id = $1", machine_id)
        if not location:
            return {"jackpot_triggered": False}

        config = await conn.fetchrow("SELECT * FROM jackpot_config WHERE location_id = $1", location["location_id"])
        current = config["current_win_count"] + 1
        threshold = config["win_count_for_jackpot"]
        triggered = False
        if current >= threshold:
            triggered = True
            current = 0

        await conn.execute("UPDATE jackpot_config SET current_win_count = $1 WHERE location_id = $2", current, location["location_id"])
        return {"jackpot_triggered": triggered, "threshold": threshold}

async def set_jackpot_threshold(location_id: int, win_count: int) -> dict:
    p = await get_pool()
    async with p.acquire() as conn:
        await conn.execute("UPDATE jackpot_config SET win_count_for_jackpot = $1 WHERE location_id = $2", win_count, location_id)
        row = await conn.fetchrow("SELECT * FROM jackpot_config WHERE location_id = $1", location_id)
        return dict(row)

async def reset_jackpot(location_id: int) -> dict:
    p = await get_pool()
    async with p.acquire() as conn:
        await conn.execute("UPDATE jackpot_config SET current_win_count = 0 WHERE location_id = $1", location_id)
        row = await conn.fetchrow("SELECT * FROM jackpot_config WHERE location_id = $1", location_id)
        return dict(row)

async def set_jackpot_counter(location_id: int, count: int) -> dict:
    p = await get_pool()
    async with p.acquire() as conn:
        threshold = await conn.fetchval("SELECT win_count_for_jackpot FROM jackpot_config WHERE location_id = $1", location_id)
        if count >= threshold:
            count = 0
        await conn.execute("UPDATE jackpot_config SET current_win_count = $1 WHERE location_id = $2", count, location_id)
        row = await conn.fetchrow("SELECT * FROM jackpot_config WHERE location_id = $1", location_id)
        return dict(row)