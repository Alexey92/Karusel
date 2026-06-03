-- Таблица адресов
CREATE TABLE IF NOT EXISTS locations (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Таблица аппаратов
CREATE TABLE IF NOT EXISTS machines (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    location_id INTEGER NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (location_id) REFERENCES locations(id)
);

-- Таблица событий
CREATE TABLE IF NOT EXISTS events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    machine_id INTEGER NOT NULL,
    event_type TEXT NOT NULL DEFAULT 'win',
    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (machine_id) REFERENCES machines(id)
);

-- Настройки главного приза
CREATE TABLE IF NOT EXISTS jackpot_config (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    location_id INTEGER UNIQUE NOT NULL,
    win_count_for_jackpot INTEGER NOT NULL DEFAULT 100,
    current_win_count INTEGER NOT NULL DEFAULT 0,
    FOREIGN KEY (location_id) REFERENCES locations(id)
);

-- Пользователи
CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    username TEXT UNIQUE NOT NULL,
    password_hash TEXT NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Индексы
CREATE INDEX IF NOT EXISTS idx_events_machine ON events(machine_id);
CREATE INDEX IF NOT EXISTS idx_events_timestamp ON events(timestamp);
CREATE INDEX IF NOT EXISTS idx_events_type ON events(event_type);
CREATE INDEX IF NOT EXISTS idx_machines_location ON machines(location_id);

-- Администратор по умолчанию
INSERT OR IGNORE INTO users (username, password_hash) VALUES ('admin', 'placeholder_hash_will_be_replaced');