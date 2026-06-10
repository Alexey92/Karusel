"""
Pydantic-модели для валидации данных.
"""
from pydantic import BaseModel, Field
from typing import Optional


class EventRequest(BaseModel):
    machine_id: int = Field(..., ge=1)
    event_type: str = Field(default="win", pattern="^(win|jackpot|play)$")


class EventResponse(BaseModel):
    status: str = "ok"
    event_id: int
    machine_id: int
    machine_name: str
    location_id: int
    location_name: str
    event_type: str
    timestamp: str


class PublicStatsResponse(BaseModel):
    wins_24h: int
    total_wins: int
    last_win: Optional[dict] = None
    jackpot_current: int
    jackpot_threshold: int


class LoginRequest(BaseModel):
    username: str
    password: str


class LoginResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"


class MachineStats(BaseModel):
    machine_id: int
    machine_name: str = ""
    location_id: Optional[int] = None
    location_name: str = ""
    wins_hour: int
    wins_today: int
    wins_24h: int
    wins_total: int
    plays_total: int = 0
    last_win: Optional[str] = None
    jackpot_config: Optional[dict] = None
    wins_period: int = 0
    plays_period: int = 0


class EventHistoryItem(BaseModel):
    id: int
    machine_id: int
    machine_name: str
    location_id: int
    location_name: str
    event_type: str
    timestamp: str


class JackpotConfigResponse(BaseModel):
    id: int
    location_id: int
    win_count_for_jackpot: int
    current_win_count: int


class JackpotThresholdRequest(BaseModel):
    win_count: int = Field(..., ge=1, le=10000)


class JackpotCounterRequest(BaseModel):
    count: int = Field(..., ge=0, le=10000)


class ChangePasswordRequest(BaseModel):
    old_password: str = Field(..., min_length=1)
    new_password: str = Field(..., min_length=4)


class LocationCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=100)


class LocationUpdate(BaseModel):
    name: str = Field(..., min_length=1, max_length=100)


class MachineCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=100)


class LocationResponse(BaseModel):
    id: int
    name: str
    machine_count: Optional[int] = 0
    
    
class MachineUpdate(BaseModel):
    local_id: Optional[int] = Field(None, ge=1)
    name: Optional[str] = Field(None, min_length=1, max_length=100)