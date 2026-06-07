"""
Отправка событий на облачный сервер.
"""
import httpx
import os
import asyncio
import aiosqlite

CLOUD_URL = os.getenv("KARUSEL_CLOUD_URL", "")
CLOUD_API_KEY = os.getenv("KARUSEL_CLOUD_KEY", "")
LOCATION_ID = int(os.getenv("KARUSEL_LOCATION_ID", "1"))
DB_PATH = os.path.join(os.path.dirname(__file__), "karusel.db")

async def sync_event_to_cloud(event: dict):
    if not CLOUD_URL or not CLOUD_API_KEY:
        return False

    async with httpx.AsyncClient(timeout=10) as client:
        try:
            resp = await client.post(
                CLOUD_URL,
                json={
                    "machine_id": event["machine_id"],
                    "location_id": LOCATION_ID,
                    "api_key": CLOUD_API_KEY,
                    "event_type": event["event_type"],
                    "local_event_id": event["event_id"]
                }
            )
            if resp.status_code == 200:
                print(f"[CLOUD] Событие {event['event_id']} отправлено.")
                return True
            else:
                print(f"[CLOUD] Ошибка {resp.status_code}: {resp.text}")
                await save_to_pending(event)  # ← добавить
                return False
        except Exception as e:
            print(f"[CLOUD] Ошибка соединения: {e}")
            await save_to_pending(event)  # ← добавить
            return False

async def save_to_pending(event: dict):
    """Сохранить неотправленное событие в pending_sync."""
    db = await aiosqlite.connect(DB_PATH)
    await db.execute(
        "INSERT INTO pending_sync (event_id, machine_id, event_type) VALUES (?, ?, ?)",
        (event["event_id"], event["machine_id"], event["event_type"])
    )
    await db.commit()
    await db.close()
    print(f"[CLOUD] Событие {event['event_id']} сохранено в pending_sync.")

async def sync_pending_events():
    """Фоновый процесс: отправляет неотправленные события каждые 30 секунд."""
    # Создаём таблицу для pending_sync, если её нет
    db = await aiosqlite.connect(DB_PATH)
    await db.execute(
        "CREATE TABLE IF NOT EXISTS pending_sync (id INTEGER PRIMARY KEY AUTOINCREMENT, event_id INTEGER, machine_id INTEGER, event_type TEXT)"
    )
    await db.commit()
    await db.close()

    while True:
        try:
            db = await aiosqlite.connect(DB_PATH)
            rows = await db.execute_fetchall("SELECT * FROM pending_sync ORDER BY id LIMIT 50")
            
            for row in rows:
                success = await sync_event_to_cloud({
                    "event_id": row["event_id"],
                    "machine_id": row["machine_id"],
                    "event_type": row["event_type"]
                })
                if success:
                    await db.execute("DELETE FROM pending_sync WHERE id = ?", (row["id"],))
                    await db.commit()
            
            await db.close()
        except Exception as e:
            print(f"[CLOUD] Ошибка в sync_pending: {e}")
        
        await asyncio.sleep(30)