"""
KARUSEL — сервер системы учёта выигрышей.
Запуск: python main.py
"""
import uvicorn
from fastapi import FastAPI, HTTPException, Request, Depends, Query
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from contextlib import asynccontextmanager
import os

from database import (
    init_db, add_event, get_public_stats,
    get_user, update_admin_password,
    get_locations, create_location, update_location, delete_location,
    get_machines, create_machine, delete_machine, get_machine_stats, get_all_machines_stats,
    get_events_history, get_total_events_count,
    increment_jackpot, set_jackpot_threshold, reset_jackpot, set_jackpot_counter
)
from models import (
    EventRequest, EventResponse, PublicStatsResponse,
    LoginRequest, LoginResponse, MachineStats, EventHistoryItem,
    JackpotConfigResponse, JackpotThresholdRequest, JackpotCounterRequest,
    ChangePasswordRequest, LocationCreate, LocationUpdate, MachineCreate, LocationResponse
)
from auth import hash_password, verify_password, create_access_token, get_current_user


BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
STATIC_DIR = os.path.join(BASE_DIR, "static")
TEMPLATES_DIR = os.path.join(BASE_DIR, "templates")

ADMIN_USERNAME = "admin"
ADMIN_DEFAULT_PASSWORD = "admin123"


async def setup_admin_password():
    user = await get_user(ADMIN_USERNAME)
    if user and user["password_hash"] == "placeholder_hash_will_be_replaced":
        hashed = hash_password(ADMIN_DEFAULT_PASSWORD)
        await update_admin_password(ADMIN_USERNAME, hashed)
        print(f"[AUTH] Установлен пароль администратора: {ADMIN_DEFAULT_PASSWORD}")


@asynccontextmanager
async def lifespan(app: FastAPI):
    print("=" * 50)
    print("[SERVER] Запуск сервера KARUSEL...")
    await init_db()
    await setup_admin_password()
    print("[SERVER] Сервер готов к работе.")
    print("=" * 50)
    yield
    print("[SERVER] Сервер остановлен.")


app = FastAPI(
    title="KARUSEL Win Tracker",
    version="2.0.0",
    lifespan=lifespan,
)

app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")
templates = Jinja2Templates(directory=TEMPLATES_DIR)


# ─── Публичные эндпоинты ───────────────────────────────────────

@app.get("/")
async def root():
    return {"status": "ok", "server": "KARUSEL Win Tracker", "version": "2.0.0"}


@app.get("/screen")
async def screen(request: Request):
    return templates.TemplateResponse("screen.html", {"request": request})


@app.post("/api/event", response_model=EventResponse)
async def receive_event(event: EventRequest):
    try:
        jackpot_result = await increment_jackpot(event.machine_id)
        actual_event_type = event.event_type
        if jackpot_result["jackpot_triggered"]:
            actual_event_type = "jackpot"

        result = await add_event(event.machine_id, actual_event_type)
        response = EventResponse(**result)
        if jackpot_result["jackpot_triggered"]:
            response.event_type = "jackpot"

        return response
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Ошибка сервера: {str(e)}")


@app.get("/api/public-stats", response_model=PublicStatsResponse)
async def public_stats(location_id: int = Query(None)):
    try:
        stats = await get_public_stats(location_id)
        return PublicStatsResponse(**stats)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Ошибка сервера: {str(e)}")


@app.get("/api/screen-data")
async def screen_data(location_id: int = Query(None)):
    """Все данные для публичного экрана (три окна)."""
    try:
        stats = await get_public_stats(location_id)
        return stats
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Ошибка сервера: {str(e)}")


# ─── Авторизация ───────────────────────────────────────────────

@app.post("/api/login", response_model=LoginResponse)
async def login(login_data: LoginRequest):
    user = await get_user(login_data.username)
    if not user:
        raise HTTPException(status_code=401, detail="Неверный логин или пароль")
    if not verify_password(login_data.password, user["password_hash"]):
        raise HTTPException(status_code=401, detail="Неверный логин или пароль")
    token = create_access_token(login_data.username)
    return LoginResponse(access_token=token)


# ─── Админские эндпоинты ──────────────────────────────────────

@app.get("/admin")
async def admin_panel(request: Request):
    return templates.TemplateResponse("admin.html", {"request": request})


@app.get("/api/admin/locations")
async def admin_locations(username: str = Depends(get_current_user)):
    locations = await get_locations()
    result = []
    for loc in locations:
        machines = await get_machines(loc["id"])
        result.append({**loc, "machine_count": len(machines)})
    return result


@app.post("/api/admin/locations", response_model=LocationResponse)
async def admin_create_location(data: LocationCreate, username: str = Depends(get_current_user)):
    loc = await create_location(data.name)
    return {**loc, "machine_count": 0}


@app.put("/api/admin/locations/{location_id}", response_model=LocationResponse)
async def admin_update_location(location_id: int, data: LocationUpdate, username: str = Depends(get_current_user)):
    loc = await update_location(location_id, data.name)
    machines = await get_machines(location_id)
    return {**loc, "machine_count": len(machines)}


@app.delete("/api/admin/locations/{location_id}")
async def admin_delete_location(location_id: int, username: str = Depends(get_current_user)):
    await delete_location(location_id)
    return {"status": "ok"}


@app.get("/api/admin/locations/{location_id}/machines")
async def admin_location_machines(location_id: int, username: str = Depends(get_current_user)):
    return await get_machines(location_id)


@app.post("/api/admin/locations/{location_id}/machines")
async def admin_create_machine(location_id: int, data: MachineCreate, username: str = Depends(get_current_user)):
    return await create_machine(data.name, location_id)


@app.delete("/api/admin/machines/{machine_id}")
async def admin_delete_machine(machine_id: int, username: str = Depends(get_current_user)):
    await delete_machine(machine_id)
    return {"status": "ok"}


@app.get("/api/admin/stats/{machine_id}", response_model=MachineStats)
async def admin_machine_stats(machine_id: int, username: str = Depends(get_current_user)):
    stats = await get_machine_stats(machine_id)
    return MachineStats(**stats)


@app.get("/api/admin/stats")
async def admin_all_stats(username: str = Depends(get_current_user)):
    return await get_all_machines_stats()


@app.get("/api/admin/events")
async def admin_events(
    limit: int = 50,
    offset: int = 0,
    location_id: int = Query(None),
    username: str = Depends(get_current_user)
):
    events = await get_events_history(limit=limit, offset=offset, location_id=location_id)
    total = await get_total_events_count(location_id)
    return {"events": events, "total": total, "limit": limit, "offset": offset}


@app.get("/api/admin/check-auth")
async def check_auth(username: str = Depends(get_current_user)):
    return {"status": "ok", "username": username}


# ─── Управление главным призом (по адресу) ────────────────────

@app.get("/api/admin/jackpot/{location_id}", response_model=JackpotConfigResponse)
async def get_jackpot_config(location_id: int, username: str = Depends(get_current_user)):
    from database import get_db
    db = await get_db()
    row = await db.execute_fetchall("SELECT * FROM jackpot_config WHERE location_id = ?", (location_id,))
    await db.close()
    if not row:
        raise HTTPException(status_code=404)
    return JackpotConfigResponse(**dict(row[0]))


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
    if len(data.new_password) < 4:
        raise HTTPException(status_code=400, detail="Новый пароль должен быть не менее 4 символов")
    new_hash = hash_password(data.new_password)
    await update_admin_password(username, new_hash)
    return {"status": "ok", "message": "Пароль успешно изменён"}


# ─── Точка входа ────────────────────────────────────────────────
if __name__ == "__main__":
    uvicorn.run("main:app", host="0.0.0.0", port=5050, reload=True, log_level="info")