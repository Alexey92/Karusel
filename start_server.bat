@echo off
set KARUSEL_CLOUD_URL=http://192.168.0.149:5050/api/event
set KARUSEL_CLOUD_KEY=hsD031z6OKV4Wlx3snP5xQUsvQFpPB0DZsogPkaJLB0
set KARUSEL_LOCATION_ID=1
cd /d C:\karusel\server
python main.py
pause