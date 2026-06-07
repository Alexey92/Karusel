/*
 * KARUSEL — прошивка для ESP32 v5.0
 * 
 * Два сигнала: WIN (GPIO13) и PLAY (GPIO14).
 * Прерывания выставляют флаги и отключаются (антидребезг).
 * Опрос раз в секунду, синхронный HTTP, таймаут 1.5 с.
 * После отправки прерывания включаются снова.
 * Буфер на LittleFS.
 */

#include <WiFi.h>
#include <HTTPClient.h>
#include <LittleFS.h>

// ═══════════════════════════════════════════════════════
// НАСТРОЙКИ
// ═══════════════════════════════════════════════════════

const char* WIFI_SSID = "karusel-net";
const char* WIFI_PASSWORD = "karusel2026";
const char* SERVER_URL = "http://192.168.1.100:5050/api/event";
const int MACHINE_ID = 1;
const int WIN_PIN = 2;
const int PLAY_PIN = 4;

// ═══════════════════════════════════════════════════════
// КОНСТАНТЫ
// ═══════════════════════════════════════════════════════

const unsigned long POLL_INTERVAL_MS = 1000;
const unsigned long HTTP_TIMEOUT_MS = 1500;
const unsigned long WIFI_RETRY_MS = 30000;
const unsigned long BUFFER_COOLDOWN_MS = 300;
const int MAX_STORED_EVENTS = 100;
const char* BUFFER_FILE = "/buffer.txt";

// ═══════════════════════════════════════════════════════
// ГЛОБАЛЬНЫЕ ПЕРЕМЕННЫЕ
// ═══════════════════════════════════════════════════════

volatile bool win_flag = false;
volatile bool play_flag = false;

unsigned long last_wifi_attempt = 0;
unsigned long last_poll_time = 0;

int pending_events = 0;
unsigned long last_buffer_attempt = 0;

// ═══════════════════════════════════════════════════════
// ПРЕРЫВАНИЯ
// ═══════════════════════════════════════════════════════

volatile unsigned long last_win_interrupt = 0;
volatile unsigned long last_play_interrupt = 0;

void IRAM_ATTR onWin() {
  unsigned long now = millis();
  if (now - last_win_interrupt < 300) return;
  last_win_interrupt = now;
  detachInterrupt(digitalPinToInterrupt(WIN_PIN));
  win_flag = true;
}

void IRAM_ATTR onPlay() {
  unsigned long now = millis();
  if (now - last_play_interrupt < 300) return;
  last_play_interrupt = now;
  detachInterrupt(digitalPinToInterrupt(PLAY_PIN));
  play_flag = true;
}

// ═══════════════════════════════════════════════════════
// SETUP
// ═══════════════════════════════════════════════════════

void setup() {
  Serial.begin(115200);
  delay(1000);

  Serial.println("\n╔════════════════════════════════╗");
  Serial.println("║  KARUSEL ESP32 TRACKER v5.0   ║");
  Serial.println("╚════════════════════════════════╝");
  Serial.printf("ID: %d | WIN: GPIO%d | PLAY: GPIO%d\n", MACHINE_ID, WIN_PIN, PLAY_PIN);

  pinMode(WIN_PIN, INPUT_PULLUP);
  pinMode(PLAY_PIN, INPUT_PULLUP);
  pinMode(LED_BUILTIN, OUTPUT);
  digitalWrite(LED_BUILTIN, LOW);

  attachInterrupt(digitalPinToInterrupt(WIN_PIN), onWin, FALLING);
  attachInterrupt(digitalPinToInterrupt(PLAY_PIN), onPlay, FALLING);

  if (!LittleFS.begin(true)) {
    Serial.println("[FS] Ошибка LittleFS!");
  }

  WiFi.mode(WIFI_STA);
  WiFi.begin(WIFI_SSID, WIFI_PASSWORD);
  Serial.printf("[WiFi] Подключение к %s...\n", WIFI_SSID);

  pending_events = countBufferedEvents();
  Serial.printf("[BUFFER] Событий: %d\n", pending_events);
}

// ═══════════════════════════════════════════════════════
// LOOP
// ═══════════════════════════════════════════════════════

bool server_alive = true;  // глобальная переменная

void loop() {

  // ── WiFi ──
  bool wifi_ok = (WiFi.status() == WL_CONNECTED);
  digitalWrite(LED_BUILTIN, wifi_ok ? HIGH : LOW);

  if (!wifi_ok && (millis() - last_wifi_attempt > WIFI_RETRY_MS)) {
    Serial.println("[WiFi] Переподключение...");
    WiFi.begin(WIFI_SSID, WIFI_PASSWORD);
    last_wifi_attempt = millis();
    server_alive = true;  // После переподключения пробуем снова
  }

  // ── Отправка буфера ──
  if (wifi_ok && pending_events > 0 && (millis() - last_buffer_attempt > BUFFER_COOLDOWN_MS)) {
    last_buffer_attempt = millis();
    if (!isBufferEmpty()) {
      if (sendHTTP(readFirstEventType())) {
        removeFirstBufferedEvent();
        pending_events--;
        Serial.printf("[BUFFER] Отправлено. Осталось: %d\n", pending_events);
        server_alive = true;
        // При успехе продолжаем быстро сливать буфер
      } else {
        server_alive = false;
        last_buffer_attempt = millis() + 30000 - BUFFER_COOLDOWN_MS;
        Serial.println("[BUFFER] Не удалось. Пауза 30 с.");
      }
    } else {
      pending_events = 0;
    }
  }

  // ── Опрос флагов (раз в секунду) ──
  if (millis() - last_poll_time >= POLL_INTERVAL_MS) {
    last_poll_time = millis();

    if (win_flag) {
      win_flag = false;
      Serial.println("[WIN] Обнаружен выигрыш!");

      if (!wifi_ok) {
        bufferEvent("win");
        Serial.println("[WIN] Нет WiFi, в буфер.");
        server_alive = false;
      } else if (server_alive) {
        if (!sendHTTP("win")) {
          bufferEvent("win");
          Serial.println("[WIN] Сервер недоступен, в буфер.");
          server_alive = false;
        }
      } else {
        bufferEvent("win");
        Serial.println("[WIN] Сервер мёртв, в буфер.");
      }
      attachInterrupt(digitalPinToInterrupt(WIN_PIN), onWin, FALLING);
    }

    if (play_flag) {
      play_flag = false;
      Serial.println("[PLAY] Обнаружена игра!");

      if (!wifi_ok) {
        bufferEvent("play");
        Serial.println("[PLAY] Нет WiFi, в буфер.");
        server_alive = false;
      } else if (server_alive) {
        if (!sendHTTP("play")) {
          bufferEvent("play");
          Serial.println("[PLAY] Сервер недоступен, в буфер.");
          server_alive = false;
        }
      } else {
        bufferEvent("play");
        Serial.println("[PLAY] Сервер мёртв, в буфер.");
      }
      attachInterrupt(digitalPinToInterrupt(PLAY_PIN), onPlay, FALLING);
    }
  }

  delay(10);
}

// ═══════════════════════════════════════════════════════
// HTTP (синхронный)
// ═══════════════════════════════════════════════════════

bool sendHTTP(String eventType) {
  HTTPClient http;
  http.begin(SERVER_URL);
  http.addHeader("Content-Type", "application/json");
  http.setTimeout(HTTP_TIMEOUT_MS);

  String jsonBody = "{\"machine_id\":" + String(MACHINE_ID) + ",\"event_type\":\"" + eventType + "\"}";

  unsigned long t0 = millis();
  int httpCode = http.POST(jsonBody);
  unsigned long t1 = millis();
  http.end();

  Serial.printf("[HTTP] Код: %d, время: %lu мс, тип: %s\n", httpCode, t1 - t0, eventType.c_str());

  return (httpCode == 200);
}

// ═══════════════════════════════════════════════════════
// БУФЕР (LittleFS)
// ═══════════════════════════════════════════════════════

bool isBufferEmpty() {
  File f = LittleFS.open(BUFFER_FILE, "r");
  if (!f) return true;
  bool empty = !f.available();
  f.close();
  return empty;
}

void bufferEvent(String eventType) {
  if (pending_events >= MAX_STORED_EVENTS) {
    Serial.println("[BUFFER] Переполнен!");
    removeFirstBufferedEvent();
    pending_events--;
  }
  File f = LittleFS.open(BUFFER_FILE, "a");
  if (!f) return;
  f.printf("%lu,%s\n", millis(), eventType.c_str());
  f.close();
  pending_events++;
  Serial.printf("[BUFFER] Сохранено (%s). Всего: %d\n", eventType.c_str(), pending_events);
}

int countBufferedEvents() {
  int count = 0;
  File f = LittleFS.open(BUFFER_FILE, "r");
  if (!f) return 0;
  while (f.available()) { f.readStringUntil('\n'); count++; }
  f.close();
  return count;
}

String readFirstEventType() {
  File f = LittleFS.open(BUFFER_FILE, "r");
  if (!f || !f.available()) return "win";
  String line = f.readStringUntil('\n');
  f.close();
  int comma = line.indexOf(',');
  if (comma > 0) return line.substring(comma + 1);
  return "win";
}

void removeFirstBufferedEvent() {
  File f = LittleFS.open(BUFFER_FILE, "r");
  if (!f) return;
  String content = f.readString();
  f.close();
  int firstNewLine = content.indexOf('\n');
  if (firstNewLine >= 0) {
    content = content.substring(firstNewLine + 1);
    f = LittleFS.open(BUFFER_FILE, "w");
    if (f) { f.print(content); f.close(); }
  }
}