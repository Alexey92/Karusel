"""
KARUSEL — сервер системы учёта выигрышей.
Запуск: python main.py
"""
import uvicorn
from fastapi import FastAPI, HTTPException, Request, Depends
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from contextlib import asynccontextmanager
import os

from database import (
    init_db, add_event, get_public_stats,
    get_user, update_admin_password,
    get_machines, get_machine_stats, get_all_machines_stats,
    get_events_history, get_total_events_count
)
from models import (
    EventRequest, EventResponse, PublicStatsResponse,
    LoginRequest, LoginResponse, MachineStats, EventHistoryItem
)
from auth import hash_password, verify_password, create_access_token, get_current_user


# ─── Пути ──────────────────────────────────────────────────────
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
STATIC_DIR = os.path.join(BASE_DIR, "static")
TEMPLATES_DIR = os.path.join(BASE_DIR, "templates")


# ─── Инициализация пароля админа ───────────────────────────────
ADMIN_USERNAME = "admin"
ADMIN_DEFAULT_PASSWORD = "admin123"


async def setup_admin_password():
    """Установить пароль администратора при первом запуске."""
    user = await get_user(ADMIN_USERNAME)
    if user and user["password_hash"] == "placeholder_hash_will_be_replaced":
        hashed = hash_password(ADMIN_DEFAULT_PASSWORD)
        await update_admin_password(ADMIN_USERNAME, hashed)
        print(f"[AUTH] Установлен пароль администратора: {ADMIN_DEFAULT_PASSWORD}")
        print("[AUTH] Не забудьте сменить пароль в настройках!")


# ─── Жизненный цикл ────────────────────────────────────────────
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


# ─── Приложение ────────────────────────────────────────────────
app = FastAPI(
    title="KARUSEL Win Tracker",
    description="Система учёта выигрышей для 10 игровых автоматов",
    version="1.0.0",
    lifespan=lifespan,
)

app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")
templates = Jinja2Templates(directory=TEMPLATES_DIR)


# ─── Публичные эндпоинты ───────────────────────────────────────

@app.get("/")
async def root():
    return {"status": "ok", "server": "KARUSEL Win Tracker", "version": "1.0.0"}


@app.get("/screen")
async def public_screen(request: Request):
    """Публичный экран."""
    return templates.TemplateResponse("public.html", {"request": request})


@app.post("/api/event", response_model=EventResponse)
async def receive_event(event: EventRequest):
    """Приём события от ESP32."""
    if event.machine_id < 1 or event.machine_id > 10:
        raise HTTPException(status_code=400, detail="machine_id должен быть от 1 до 10")
    try:
        result = await add_event(event.machine_id, event.event_type)
        return EventResponse(**result)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Ошибка сервера: {str(e)}")


@app.get("/api/public-stats", response_model=PublicStatsResponse)
async def public_stats():
    """Статистика для публичного экрана."""
    try:
        stats = await get_public_stats()
        return PublicStatsResponse(**stats)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Ошибка сервера: {str(e)}")


# ─── Авторизация ───────────────────────────────────────────────

@app.post("/api/login", response_model=LoginResponse)
async def login(login_data: LoginRequest):
    """Вход в админ-панель."""
    user = await get_user(login_data.username)
    if not user:
        raise HTTPException(status_code=401, detail="Неверный логин или пароль")

    if not verify_password(login_data.password, user["password_hash"]):
        raise HTTPException(status_code=401, detail="Неверный логин или пароль")

    token = create_access_token(login_data.username)
    print(f"[AUTH] Пользователь '{login_data.username}' вошёл в систему.")
    return LoginResponse(access_token=token)


# ─── Админские эндпоинты (защищены токеном) ────────────────────

@app.get("/admin")
async def admin_panel(request: Request):
    """Админ-панель (HTML-страница). Вход проверяется на стороне фронтенда."""
    return templates.TemplateResponse("admin.html", {"request": request})


@app.get("/api/admin/machines")
async def admin_machines(username: str = Depends(get_current_user)):
    """Список всех аппаратов."""
    return await get_machines()


@app.get("/api/admin/stats/{machine_id}", response_model=MachineStats)
async def admin_machine_stats(machine_id: int, username: str = Depends(get_current_user)):
    """Статистика по конкретному аппарату."""
    if machine_id < 1 or machine_id > 10:
        raise HTTPException(status_code=400, detail="machine_id должен быть от 1 до 10")
    stats = await get_machine_stats(machine_id)
    return MachineStats(**stats)


@app.get("/api/admin/stats")
async def admin_all_stats(username: str = Depends(get_current_user)):
    """Статистика по всем аппаратам."""
    return await get_all_machines_stats()


@app.get("/api/admin/events")
async def admin_events(
    limit: int = 50,
    offset: int = 0,
    username: str = Depends(get_current_user)
):
    """История выигрышей с пагинацией."""
    events = await get_events_history(limit=limit, offset=offset)
    total = await get_total_events_count()
    return {
        "events": events,
        "total": total,
        "limit": limit,
        "offset": offset
    }


@app.get("/api/admin/check-auth")
async def check_auth(username: str = Depends(get_current_user)):
    """Проверка токена (для фронтенда)."""
    return {"status": "ok", "username": username}


# ─── Точка входа ────────────────────────────────────────────────
if __name__ == "__main__":
    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=5050,
        reload=True,
        log_level="info"
    )