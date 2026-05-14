-- Таблица адресов (locations)
CREATE TABLE IF NOT EXISTS locations (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Таблица аппаратов (справочник)
CREATE TABLE IF NOT EXISTS machines (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    location_id INTEGER NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (location_id) REFERENCES locations(id)
);

-- Таблица событий выигрыша (основная)
CREATE TABLE IF NOT EXISTS events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    machine_id INTEGER NOT NULL,
    event_type TEXT NOT NULL DEFAULT 'win',  -- 'win' или 'jackpot'
    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (machine_id) REFERENCES machines(id)
);

-- Настройки главного приза для каждого адреса (location)
CREATE TABLE IF NOT EXISTS jackpot_config (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    location_id INTEGER UNIQUE NOT NULL,
    win_count_for_jackpot INTEGER NOT NULL DEFAULT 100,
    current_win_count INTEGER NOT NULL DEFAULT 0,
    FOREIGN KEY (location_id) REFERENCES locations(id)
);

-- Пользователи (для админки)
CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    username TEXT UNIQUE NOT NULL,
    password_hash TEXT NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Индексы для быстрых запросов
CREATE INDEX IF NOT EXISTS idx_events_machine ON events(machine_id);
CREATE INDEX IF NOT EXISTS idx_events_timestamp ON events(timestamp);
CREATE INDEX IF NOT EXISTS idx_events_type ON events(event_type);
CREATE INDEX IF NOT EXISTS idx_machines_location ON machines(location_id);

-- Тестовые данные: 2 адреса
INSERT OR IGNORE INTO locations (id, name) VALUES (1, 'Основной зал'), (2, 'Второй этаж');

-- Тестовые данные: 10 автоматов (5 на первом адресе, 5 на втором)
INSERT OR IGNORE INTO machines (id, name, location_id) VALUES
    (1, 'Автомат №1', 1),
    (2, 'Автомат №2', 1),
    (3, 'Автомат №3', 1),
    (4, 'Автомат №4', 1),
    (5, 'Автомат №5', 1),
    (6, 'Автомат №6', 2),
    (7, 'Автомат №7', 2),
    (8, 'Автомат №8', 2),
    (9, 'Автомат №9', 2),
    (10, 'Автомат №10', 2);

-- Настройки главного приза для каждого адреса (по умолчанию 100)
INSERT OR IGNORE INTO jackpot_config (location_id, win_count_for_jackpot, current_win_count)
VALUES (1, 100, 0), (2, 100, 0);

-- Администратор по умолчанию
INSERT OR IGNORE INTO users (username, password_hash) VALUES
    ('admin', 'placeholder_hash_will_be_replaced');