#!/bin/bash
PORT=/dev/cu.usbserial-1470
BAUD=115200
ADDR=0x10000
BIN=karusel_esp32/build/esp32.esp32.esp32doit-devkit-v1/karusel_esp32.ino.bin

killall screen 2>/dev/null
sleep 0.5
esptool --chip esp32 --port $PORT --baud $BAUD write-flash $ADDR $BIN
sleep 1
screen $PORT 115200