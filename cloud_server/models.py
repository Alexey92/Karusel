from pydantic import BaseModel, Field
from typing import Optional

class CloudEventRequest(BaseModel):
    machine_id: int
    location_id: int
    api_key: str
    event_type: str = "win"
    timestamp: Optional[str] = None
    local_event_id: Optional[int] = None

class EventResponse(BaseModel):
    status: str = "ok"
    event_id: int
    machine_id: int
    machine_name: str
    location_id: int
    location_name: str
    event_type: str
    timestamp: str

class LoginRequest(BaseModel):
    username: str
    password: str

class LoginResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"

class MachineStats(BaseModel):
    machine_id: int
    local_id: int = 0
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
    local_id: int = Field(..., ge=1)
    name: str = Field(..., min_length=1, max_length=100)

class MachineUpdate(BaseModel):
    local_id: Optional[int] = Field(None, ge=1)
    name: Optional[str] = Field(None, min_length=1, max_length=100)