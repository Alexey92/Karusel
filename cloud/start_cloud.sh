#!/bin/bash
# Запуск облачного сервера KARUSEL

echo "=== KARUSEL Cloud ==="
echo "Проверяю PostgreSQL..."

# Проверка, запущен ли PostgreSQL
if pg_isready -q; then
    echo "PostgreSQL уже запущен."
else
    echo "Запускаю PostgreSQL..."
    open -a Postgres
    sleep 5
    echo "PostgreSQL запущен."
fi

# Запуск сервера
cd ~/Documents/karusel/cloud
echo "Запускаю облачный сервер..."
python3.12 main.py