"""
Авторизация: хеширование паролей и JWT-токены.
"""
import hashlib
import secrets
from datetime import datetime, timedelta
from jose import JWTError, jwt
from fastapi import HTTPException, Depends
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials

# Секретный ключ для подписи токенов (позже смените на свой)
SECRET_KEY = "karusel-super-secret-key-change-in-production-2026"
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_HOURS = 24  # токен живёт 24 часа

# Схема авторизации (Bearer Token)
security = HTTPBearer()


def hash_password(password: str) -> str:
    """
    Хешировать пароль для хранения в БД.
    Используем SHA-256 с солью (без bcrypt для совместимости).
    """
    salt = secrets.token_hex(16)
    salted = salt + password
    hash_bytes = hashlib.sha256(salted.encode('utf-8')).hexdigest()
    return f"{salt}${hash_bytes}"


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Проверить пароль."""
    try:
        salt, stored_hash = hashed_password.split('$', 1)
        salted = salt + plain_password
        new_hash = hashlib.sha256(salted.encode('utf-8')).hexdigest()
        return secrets.compare_digest(new_hash, stored_hash)
    except (ValueError, AttributeError):
        return False


def create_access_token(username: str) -> str:
    """Создать JWT-токен."""
    expire = datetime.utcnow() + timedelta(hours=ACCESS_TOKEN_EXPIRE_HOURS)
    to_encode = {"sub": username, "exp": expire}
    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)


async def get_current_user(credentials: HTTPAuthorizationCredentials = Depends(security)):
    """Проверить токен и вернуть имя пользователя."""
    token = credentials.credentials
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        username: str = payload.get("sub")
        if username is None:
            raise HTTPException(status_code=401, detail="Недействительный токен")
        return username
    except JWTError:
        raise HTTPException(status_code=401, detail="Недействительный или истёкший токен")