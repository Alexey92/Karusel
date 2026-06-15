@echo off
chcp 65001 >nul

echo === Установка KARUSEL ===

:: Скачивание Python
echo Скачиваю Python 3.12...
powershell -Command "Invoke-WebRequest -Uri 'https://www.python.org/ftp/python/3.12.8/python-3.12.8-amd64.exe' -OutFile '%TEMP%\python-install.exe'"
echo Устанавливаю Python (ждите 2-3 минуты)...
%TEMP%\python-install.exe /quiet InstallAllUsers=1 PrependPath=1 Include_test=0
echo Python установлен.

:: Обновление PATH
set PATH=C:\Program Files\Python312;C:\Program Files\Python312\Scripts;%PATH%

:: Клонирование проекта из GitHub (без авторизации)
echo Скачиваю проект с GitHub...
if not exist C:\karusel mkdir C:\karusel
powershell -Command "Invoke-WebRequest -Uri 'https://github.com/Alexey92/Karusel/archive/refs/heads/main.zip' -OutFile '%TEMP%\karusel.zip'"
powershell -Command "Expand-Archive -Path '%TEMP%\karusel.zip' -DestinationPath '%TEMP%\karusel_temp' -Force"
xcopy /E /Y "%TEMP%\karusel_temp\Karusel-main\*" "C:\karusel\"
rmdir /S /Q "%TEMP%\karusel_temp"
del "%TEMP%\karusel.zip"
echo Проект скачан в C:\karusel

:: Установка зависимостей Python
echo Устанавливаю зависимости Python...
cd /d C:\karusel\server
python -m pip install -r requirements.txt
echo Зависимости установлены.

echo === Установка завершена ===
echo Теперь настройте start_server.bat и запустите сервер.
pause