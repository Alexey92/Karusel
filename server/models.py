"""
Pydantic-модели для валидации данных.
"""
from pydantic import BaseModel, Field
from typing import Optional


class EventRequest(BaseModel):
    """Запрос от ESP32 при выигрыше."""
    machine_id: int = Field(..., ge=1, le=10, description="ID аппарата (1-10)")
    event_type: str = Field(default="win", pattern="^(win|jackpot)$", description="Тип события: win или jackpot")


class EventResponse(BaseModel):
    """Ответ сервера на успешное добавление события."""
    status: str = "ok"
    event_id: int
    machine_id: int
    machine_name: str
    event_type: str
    timestamp: str


class PublicStatsResponse(BaseModel):
    """Статистика для публичного экрана."""
    wins_24h: int
    last_win: Optional[dict] = None


class LoginRequest(BaseModel):
    """Запрос на вход."""
    username: str
    password: str


class LoginResponse(BaseModel):
    """Ответ с токеном."""
    access_token: str
    token_type: str = "bearer"


class MachineStats(BaseModel):
    """Статистика по одному аппарату."""
    machine_id: int
    wins_hour: int
    wins_today: int
    wins_24h: int
    wins_total: int
    last_win: Optional[str] = None
    jackpot_config: Optional[dict] = None


class EventHistoryItem(BaseModel):
    """Одна запись в истории."""
    id: int
    machine_id: int
    machine_name: str
    event_type: str
    timestamp: str


class JackpotConfigResponse(BaseModel):
    """Настройки главного приза."""
    id: int
    machine_id: int
    win_count_for_jackpot: int
    current_win_count: int


class JackpotThresholdRequest(BaseModel):
    """Запрос на изменение порога джекпота."""
    win_count: int = Field(..., ge=1, le=10000, description="Количество выигрышей до джекпота")


class JackpotCounterRequest(BaseModel):
    """Запрос на ручную установку счётчика."""
    count: int = Field(..., ge=0, le=10000, description="Текущее значение счётчика")
	
class ChangePasswordRequest(BaseModel):
    """Запрос на смену пароля."""
    old_password: str = Field(..., min_length=1, description="Старый пароль")
    new_password: str = Field(..., min_length=4, description="Новый пароль (мин. 4 символа)")