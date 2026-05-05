-- Таблица аппаратов (справочник)
CREATE TABLE IF NOT EXISTS machines (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,                  -- например "Автомат №1"
    location TEXT DEFAULT '',            -- где стоит
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Таблица событий выигрыша (основная)
CREATE TABLE IF NOT EXISTS events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    machine_id INTEGER NOT NULL,
    event_type TEXT NOT NULL DEFAULT 'win',  -- 'win' или 'jackpot'
    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (machine_id) REFERENCES machines(id)
);

-- Настройки главного приза для каждого аппарата
CREATE TABLE IF NOT EXISTS jackpot_config (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    machine_id INTEGER UNIQUE NOT NULL,
    win_count_for_jackpot INTEGER NOT NULL DEFAULT 100,  -- сколько выигрышей до главного приза
    current_win_count INTEGER NOT NULL DEFAULT 0,        -- текущий счётчик
    FOREIGN KEY (machine_id) REFERENCES machines(id)
);

-- Пользователи (для админки)
CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    username TEXT UNIQUE NOT NULL,
    password_hash TEXT NOT NULL,          -- храним хеш, не пароль
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Индексы для быстрых запросов
CREATE INDEX IF NOT EXISTS idx_events_machine ON events(machine_id);
CREATE INDEX IF NOT EXISTS idx_events_timestamp ON events(timestamp);
CREATE INDEX IF NOT EXISTS idx_events_type ON events(event_type);

-- Заполняем 10 автоматов (тестовые данные)
INSERT OR IGNORE INTO machines (id, name) VALUES
    (1, 'Автомат №1'), (2, 'Автомат №2'), (3, 'Автомат №3'),
    (4, 'Автомат №4'), (5, 'Автомат №5'), (6, 'Автомат №6'),
    (7, 'Автомат №7'), (8, 'Автомат №8'), (9, 'Автомат №9'),
    (10, 'Автомат №10');

-- Настройки главного приза для всех (по умолчанию 100)
INSERT OR IGNORE INTO jackpot_config (machine_id, win_count_for_jackpot, current_win_count)
SELECT id, 100, 0 FROM machines WHERE id BETWEEN 1 AND 10;

-- Администратор по умолчанию (пароль: admin123)
-- Позже сменим на нормальный хеш через Python
INSERT OR IGNORE INTO users (username, password_hash) VALUES
    ('admin', 'placeholder_hash_will_be_replaced');