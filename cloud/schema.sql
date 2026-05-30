-- Таблица объектов (адресов)
CREATE TABLE IF NOT EXISTS locations (
    id SERIAL PRIMARY KEY,
    name TEXT NOT NULL,
    api_key TEXT UNIQUE NOT NULL,
    created_at TIMESTAMP DEFAULT NOW()
);

-- Таблица автоматов
CREATE TABLE IF NOT EXISTS machines (
    id SERIAL PRIMARY KEY,
    name TEXT NOT NULL,
    location_id INTEGER REFERENCES locations(id),
    created_at TIMESTAMP DEFAULT NOW()
);

-- Таблица событий (глобальная)
CREATE TABLE IF NOT EXISTS events (
    id SERIAL PRIMARY KEY,
    machine_id INTEGER REFERENCES machines(id),
    location_id INTEGER REFERENCES locations(id),
    event_type TEXT NOT NULL DEFAULT 'win',
    timestamp TIMESTAMP DEFAULT NOW(),
    local_event_id INTEGER  -- ID события в локальной БД (для защиты от дублей)
);

-- Настройки джекпота для каждого объекта
CREATE TABLE IF NOT EXISTS jackpot_config (
    id SERIAL PRIMARY KEY,
    location_id INTEGER UNIQUE REFERENCES locations(id),
    win_count_for_jackpot INTEGER DEFAULT 100,
    current_win_count INTEGER DEFAULT 0
);

-- Пользователи (админы)
CREATE TABLE IF NOT EXISTS users (
    id SERIAL PRIMARY KEY,
    username TEXT UNIQUE NOT NULL,
    password_hash TEXT NOT NULL,
    created_at TIMESTAMP DEFAULT NOW()
);

-- Индексы
CREATE INDEX IF NOT EXISTS idx_events_machine ON events(machine_id);
CREATE INDEX IF NOT EXISTS idx_events_location ON events(location_id);
CREATE INDEX IF NOT EXISTS idx_events_timestamp ON events(timestamp);
CREATE INDEX IF NOT EXISTS idx_events_type ON events(event_type);

-- Администратор по умолчанию (пароль: admin123)
INSERT INTO users (username, password_hash)
VALUES ('admin', 'placeholder_hash_will_be_replaced')
ON CONFLICT (username) DO NOTHING;