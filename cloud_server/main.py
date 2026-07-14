"""
KARUSEL Cloud — центральный сервер системы учёта выигрышей.
Запуск: cd cloud && python main.py
"""
import uvicorn
import secrets
import os
import sys
from fastapi import FastAPI, HTTPException, Request, Depends, Query
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from contextlib import asynccontextmanager
from pydantic import BaseModel
from datetime import datetime

# Добавляем server/ в путь для импорта auth.py
import importlib.util

auth_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "server", "auth.py")
spec = importlib.util.spec_from_file_location("auth", auth_path)
auth = importlib.util.module_from_spec(spec)
spec.loader.exec_module(auth)

hash_password = auth.hash_password
verify_password = auth.verify_password
create_access_token = auth.create_access_token
get_current_user = auth.get_current_user


from database import (
    init_db, add_event, verify_api_key, find_or_create_machine,
    get_user, update_admin_password,
    get_locations, create_location, update_location, delete_location,
    get_machines, create_machine, update_machine, delete_machine,
    get_machine_stats, get_all_machines_stats,
    get_events_history, get_total_events_count,
    increment_jackpot, set_jackpot_threshold, reset_jackpot, set_jackpot_counter, get_pool
)
from models import (
    CloudEventRequest, EventResponse,
    LoginRequest, LoginResponse, MachineStats,
    JackpotConfigResponse, JackpotThresholdRequest, JackpotCounterRequest,
    ChangePasswordRequest, LocationCreate, LocationUpdate, MachineCreate, MachineUpdate, BulkEventRequest
)

# Пути к общим папкам
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
STATIC_DIR = os.path.join(BASE_DIR, "static")
TEMPLATES_DIR = os.path.join(BASE_DIR, "templates")

ADMIN_USERNAME = "admin"
ADMIN_DEFAULT_PASSWORD = "admin123"

class LogRequest(BaseModel):
    machine_id: int
    message: str    

async def setup_admin_password():
    user = await get_user(ADMIN_USERNAME)
    if user and user["password_hash"] == "placeholder_hash_will_be_replaced":
        hashed = hash_password(ADMIN_DEFAULT_PASSWORD)
        await update_admin_password(ADMIN_USERNAME, hashed)
        print(f"[AUTH] Установлен пароль администратора: {ADMIN_DEFAULT_PASSWORD}")

def log(msg):
    print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] {msg}")

@asynccontextmanager
async def lifespan(app: FastAPI):
    print("=" * 50)
    print("[CLOUD] Запуск облачного сервера KARUSEL...")
    await init_db()
    await setup_admin_password()
    print("[CLOUD] Сервер готов.")
    print("=" * 50)
    yield
    print("[CLOUD] Сервер остановлен.")

app = FastAPI(title="KARUSEL Cloud", version="1.0.0", lifespan=lifespan)

app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")
app.mount("/firmware", StaticFiles(directory=os.path.join(BASE_DIR, "cloud_server", "firmware")), name="firmware")
templates = Jinja2Templates(directory=TEMPLATES_DIR)

# ─── Приём событий от локальных серверов ──────────────────────
@app.post("/api/event", response_model=EventResponse)
async def receive_cloud_event(event: CloudEventRequest):
    if not await verify_api_key(event.location_id, event.api_key):
        raise HTTPException(status_code=403, detail="Неверный api_key")

    try:
        # Найти или создать автомат по local_id
        cloud_machine_id = await find_or_create_machine(event.location_id, event.machine_id)

        actual_event_type = event.event_type
        if actual_event_type in ("win", "jackpot"):
            jackpot_result = await increment_jackpot(cloud_machine_id)
            if jackpot_result["jackpot_triggered"]:
                actual_event_type = "jackpot"

        result = await add_event(cloud_machine_id, event.location_id, actual_event_type, event.local_event_id)

        if result.get("status") == "duplicate":
            return EventResponse(
                event_id=result["id"],
                machine_id=cloud_machine_id,
                machine_name="",
                location_id=event.location_id,
                location_name="",
                event_type=actual_event_type,
                timestamp="",
                status="duplicate"
            )

        response = EventResponse(**result)
        if actual_event_type == "jackpot":
            response.event_type = "jackpot"

        return response
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Ошибка: {str(e)}")
        
        
        
@app.post("/api/bulk-event")
async def receive_bulk_event(event: BulkEventRequest):
    if not await verify_api_key(event.location_id, event.api_key):
        raise HTTPException(status_code=403, detail="Неверный api_key")

    try:
        cloud_machine_id = await find_or_create_machine(event.location_id, event.machine_id)

        p = await get_pool()
        
        async with p.acquire() as conn:
            prev_wins = await conn.fetchval(
                "SELECT COUNT(*) FROM events WHERE machine_id = $1 AND event_type != 'play'",
                cloud_machine_id
            ) or 0
            prev_plays = await conn.fetchval(
                "SELECT COUNT(*) FROM events WHERE machine_id = $1 AND event_type = 'play'",
                cloud_machine_id
            ) or 0

            new_wins = max(0, event.total_wins - prev_wins)
            new_plays = max(0, event.total_plays - prev_plays)

            for _ in range(new_wins):
                await add_event(cloud_machine_id, event.location_id, "win")
                await increment_jackpot(cloud_machine_id)
            for _ in range(new_plays):
                await add_event(cloud_machine_id, event.location_id, "play")
                
            await conn.execute("UPDATE machines SET last_seen = NOW() WHERE id = $1", cloud_machine_id)
                
        return {
            "status": "ok",
            "new_wins": new_wins,
            "new_plays": new_plays,
            "total_wins": event.total_wins,
            "total_plays": event.total_plays
        }

    except Exception as e:
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"Ошибка: {str(e)}")        
        
@app.get("/api/get-counts")
async def get_counts(machine_id: int, location_id: int, api_key: str):
    if not await verify_api_key(location_id, api_key):
        raise HTTPException(status_code=403, detail="Неверный api_key")
    
    cloud_machine_id = await find_or_create_machine(location_id, machine_id)
    
    p = await get_pool()
    async with p.acquire() as conn:
        total_wins = await conn.fetchval(
            "SELECT COUNT(*) FROM events WHERE machine_id = $1 AND event_type != 'play'",
            cloud_machine_id
        ) or 0
        total_plays = await conn.fetchval(
            "SELECT COUNT(*) FROM events WHERE machine_id = $1 AND event_type = 'play'",
            cloud_machine_id
        ) or 0
    
    return {"total_wins": total_wins, "total_plays": total_plays}
    
    
@app.post("/api/log")
async def receive_log(log: LogRequest):
    print(f"[ESP:{log.machine_id}] {log.message}")
    return {"status": "ok"}
# ─── Авторизация ─────────────────────────────────────────────

@app.post("/api/login", response_model=LoginResponse)
async def login(login_data: LoginRequest):
    user = await get_user(login_data.username)
    if not user:
        raise HTTPException(status_code=401, detail="Неверный логин или пароль")
    if not verify_password(login_data.password, user["password_hash"]):
        raise HTTPException(status_code=401, detail="Неверный логин или пароль")
    return LoginResponse(access_token=create_access_token(login_data.username))

# ─── Админка ────────────────────────────────────────────────
@app.get("/admin")
async def admin_panel(request: Request):
    return templates.TemplateResponse("admin.html", {"request": request, "is_cloud": True})

@app.get("/api/admin/locations")
async def admin_locations(username: str = Depends(get_current_user)):
    locations = await get_locations()
    result = []
    for loc in locations:
        machines = await get_machines(loc["id"])
        result.append({**loc, "machine_count": len(machines)})
    return result
    
@app.get("/api/admin/stats")
async def admin_all_stats(
    from_date: str = Query(None),
    to_date: str = Query(None),
    username: str = Depends(get_current_user)
):
    return await get_all_machines_stats(from_date, to_date)

@app.post("/api/admin/locations")
async def admin_create_location(data: LocationCreate, username: str = Depends(get_current_user)):
    api_key = secrets.token_urlsafe(32)
    loc = await create_location(data.name, api_key)
    return {**loc, "machine_count": 0}

@app.put("/api/admin/locations/{location_id}")
async def admin_update_location(location_id: int, data: LocationUpdate, username: str = Depends(get_current_user)):
    await update_location(location_id, data.name)
    machines = await get_machines(location_id)
    return {"id": location_id, "name": data.name, "machine_count": len(machines)}
    
@app.put("/api/admin/machines/{machine_id}")
async def admin_update_machine(machine_id: int, data: MachineUpdate, username: str = Depends(get_current_user)):
    await update_machine(machine_id, data.local_id, data.name)
    return {"status": "ok"}

@app.delete("/api/admin/locations/{location_id}")
async def admin_delete_location(location_id: int, username: str = Depends(get_current_user)):
    await delete_location(location_id)
    return {"status": "ok"}

@app.get("/api/admin/locations/{location_id}/machines")
async def admin_location_machines(location_id: int, username: str = Depends(get_current_user)):
    return await get_machines(location_id)

@app.post("/api/admin/locations/{location_id}/machines")
async def admin_create_machine(location_id: int, data: MachineCreate, username: str = Depends(get_current_user)):
    return await create_machine(data.local_id, data.name, location_id)

@app.delete("/api/admin/machines/{machine_id}")
async def admin_delete_machine(machine_id: int, username: str = Depends(get_current_user)):
    await delete_machine(machine_id)
    return {"status": "ok"}

@app.get("/api/admin/stats/{machine_id}", response_model=MachineStats)
async def admin_machine_stats(machine_id: int, username: str = Depends(get_current_user)):
    stats = await get_machine_stats(machine_id)
    return MachineStats(**stats)


@app.get("/api/admin/events")
async def admin_events(limit: int = 50, offset: int = 0, location_id: int = Query(None), username: str = Depends(get_current_user)):
    events = await get_events_history(limit, offset, location_id)
    total = await get_total_events_count(location_id)
    return {"events": events, "total": total, "limit": limit, "offset": offset}

@app.get("/api/admin/check-auth")
async def check_auth(username: str = Depends(get_current_user)):
    return {"status": "ok", "username": username}

@app.get("/api/admin/jackpot/{location_id}", response_model=JackpotConfigResponse)
async def get_jackpot_config(location_id: int, username: str = Depends(get_current_user)):
    from database import get_pool
    p = await get_pool()
    async with p.acquire() as conn:
        row = await conn.fetchrow("SELECT * FROM jackpot_config WHERE location_id = $1", location_id)
    if not row:
        raise HTTPException(status_code=404)
    return JackpotConfigResponse(**dict(row))

@app.put("/api/admin/jackpot/{location_id}/threshold")
async def update_jackpot_threshold(location_id: int, data: JackpotThresholdRequest, username: str = Depends(get_current_user)):
    result = await set_jackpot_threshold(location_id, data.win_count)
    return {"status": "ok", "config": result}

@app.post("/api/admin/jackpot/{location_id}/reset")
async def reset_jackpot_counter(location_id: int, username: str = Depends(get_current_user)):
    result = await reset_jackpot(location_id)
    return {"status": "ok", "config": result}

@app.put("/api/admin/jackpot/{location_id}/counter")
async def set_jackpot_counter_value(location_id: int, data: JackpotCounterRequest, username: str = Depends(get_current_user)):
    result = await set_jackpot_counter(location_id, data.count)
    return {"status": "ok", "config": result}

@app.put("/api/admin/change-password")
async def change_password(data: ChangePasswordRequest, username: str = Depends(get_current_user)):
    user = await get_user(username)
    if not user:
        raise HTTPException(status_code=404)
    if not verify_password(data.old_password, user["password_hash"]):
        raise HTTPException(status_code=400, detail="Неверный старый пароль")
    new_hash = hash_password(data.new_password)
    await update_admin_password(username, new_hash)
    return {"status": "ok", "message": "Пароль изменён"}

if __name__ == "__main__":
    uvicorn.run("main:app", host="0.0.0.0", port=80, reload=True,, log_level="info")
