/*
 * KARUSEL — прошивка для ESP32 v3.2
 * 
 * HTTP-запросы в отдельном потоке FreeRTOS (не блокирует кнопку).
 * Исправления v3.2:
 * - Проверка на пустой буфер перед отправкой
 * - Защита от бесконечного цикла при рассинхронизации счётчика
 * - Синхронизация pending_events с файлом при обнаружении пустого буфера
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
const int MACHINE_ID = 3;
const int WIN_PIN = 13;

// ═══════════════════════════════════════════════════════
// КОНСТАНТЫ
// ═══════════════════════════════════════════════════════

const unsigned long DEBOUNCE_MS = 200;
const unsigned long WIFI_RETRY_MS = 30000;
const unsigned long BUFFER_COOLDOWN_MS = 200;
const int MAX_STORED_EVENTS = 100;
const char* BUFFER_FILE = "/buffer.txt";

// ═══════════════════════════════════════════════════════
// ГЛОБАЛЬНЫЕ ПЕРЕМЕННЫЕ
// ═══════════════════════════════════════════════════════

// Кнопка
unsigned long last_win_time = 0;
int last_button_state = HIGH;

// HTTP-задача
volatile bool http_busy = false;
volatile bool http_done = false;
volatile bool http_success = false;
volatile bool http_was_buffer = false;

// WiFi
unsigned long last_wifi_attempt = 0;

// Буфер
int pending_events = 0;
unsigned long last_buffer_attempt = 0;

// ═══════════════════════════════════════════════════════
// SETUP
// ═══════════════════════════════════════════════════════

void setup() {
  Serial.begin(115200);
  delay(1000);

  Serial.println("\n╔════════════════════════════════╗");
  Serial.println("║  KARUSEL ESP32 TRACKER v3.2   ║");
  Serial.println("╚════════════════════════════════╝");
  Serial.printf("Аппарат ID: %d | Пин: GPIO%d\n", MACHINE_ID, WIN_PIN);

  pinMode(WIN_PIN, INPUT_PULLUP);
  pinMode(LED_BUILTIN, OUTPUT);
  digitalWrite(LED_BUILTIN, LOW);

  if (!LittleFS.begin(true)) {
    Serial.println("[FS] Ошибка монтирования LittleFS!");
  }

  connectWiFi();

  pending_events = countBufferedEvents();
  Serial.printf("[BUFFER] Событий в буфере: %d\n", pending_events);
}

// ═══════════════════════════════════════════════════════
// ЗАДАЧА HTTP (выполняется в отдельном потоке)
// ═══════════════════════════════════════════════════════

void httpTask(void* parameter) {
  HTTPClient http;
  http.begin(SERVER_URL);
  http.addHeader("Content-Type", "application/json");

  String jsonBody = "{\"machine_id\":" + String(MACHINE_ID) + ",\"event_type\":\"win\"}";

  unsigned long t0 = millis();
  int httpCode = http.POST(jsonBody);
  unsigned long t1 = millis();
  http.end();

  Serial.printf("[HTTP] Код: %d, время: %lu мс\n", httpCode, t1 - t0);

  http_success = (httpCode == 200);
  http_done = true;

  vTaskDelete(NULL);
}

void startHTTP(bool isBuffer) {
  if (http_busy) return;

  // Для буфера: проверяем, что файл не пуст
  if (isBuffer && isBufferEmpty()) {
    Serial.println("[BUFFER] Файл пуст, отправка отменена. Синхронизация счётчика.");
    pending_events = 0;
    return;
  }

  http_busy = true;
  http_done = false;
  http_was_buffer = isBuffer;

  xTaskCreatePinnedToCore(
    httpTask,
    "HTTP_Task",
    8192,
    NULL,
    1,
    NULL,
    0
  );
}

// ═══════════════════════════════════════════════════════
// LOOP
// ═══════════════════════════════════════════════════════

void loop() {

  // ── 1. ОБРАБОТКА ЗАВЕРШЁННОГО HTTP ──
  if (http_busy && http_done) {
    http_busy = false;

    if (http_success) {
      if (http_was_buffer) {
        removeFirstBufferedEvent();
        pending_events--;
        Serial.printf("[BUFFER] Отправлено. Осталось: %d\n", pending_events);
      }
    } else {
      if (!http_was_buffer) {
        bufferEvent();
        Serial.println("[WIN] Сервер недоступен, событие в буфер.");
      }
    }
  }

  // ── 2. WiFi ──
  bool wifi_ok = (WiFi.status() == WL_CONNECTED);
  digitalWrite(LED_BUILTIN, wifi_ok ? HIGH : LOW);

  if (!wifi_ok && (millis() - last_wifi_attempt > WIFI_RETRY_MS)) {
    Serial.println("[WiFi] Попытка переподключения...");
    connectWiFi();
    last_wifi_attempt = millis();
  }

  // ── 3. Отправка буфера ──
  if (wifi_ok && pending_events > 0 && !http_busy &&
      (millis() - last_buffer_attempt > BUFFER_COOLDOWN_MS)) {
    last_buffer_attempt = millis();

    if (!isBufferEmpty()) {
      startHTTP(true);
    } else {
      Serial.println("[BUFFER] Файл пуст, сбрасываю счётчик.");
      pending_events = 0;
    }
  }

  // ── 4. Кнопка ──
  int button_state = digitalRead(WIN_PIN);

  if (button_state == LOW && last_button_state == HIGH) {
    unsigned long now = millis();
    if (now - last_win_time > DEBOUNCE_MS) {
      last_win_time = now;
      Serial.println("[WIN] Обнаружен выигрыш!");

      if (!wifi_ok) {
        bufferEvent();
        Serial.println("[WIN] Нет WiFi, событие в буфер.");
      } else if (http_busy) {
        bufferEvent();
        Serial.println("[WIN] HTTP занят, событие в буфер.");
      } else {
        startHTTP(false);
      }
    }
  }

  last_button_state = button_state;
  delay(10);
}

// ═══════════════════════════════════════════════════════
// WiFi
// ═══════════════════════════════════════════════════════

void connectWiFi() {
  WiFi.mode(WIFI_STA);
  WiFi.begin(WIFI_SSID, WIFI_PASSWORD);

  int attempts = 0;
  while (WiFi.status() != WL_CONNECTED && attempts < 20) {
    delay(500);
    Serial.print(".");
    attempts++;
  }

  if (WiFi.status() == WL_CONNECTED) {
    Serial.println("\n[WiFi] Подключено!");
    Serial.printf("[WiFi] IP: %s\n", WiFi.localIP().toString().c_str());
  } else {
    Serial.println("\n[WiFi] Не удалось подключиться.");
  }
}

// ═══════════════════════════════════════════════════════
// БУФЕР
// ═══════════════════════════════════════════════════════

bool isBufferEmpty() {
  File f = LittleFS.open(BUFFER_FILE, "r");
  if (!f) return true;
  bool empty = !f.available();
  f.close();
  return empty;
}

void bufferEvent() {
  if (pending_events >= MAX_STORED_EVENTS) {
    Serial.println("[BUFFER] Переполнен!");
    removeFirstBufferedEvent();
    pending_events--;
  }

  File f = LittleFS.open(BUFFER_FILE, "a");
  if (!f) return;
  f.println(millis());
  f.close();
  pending_events++;
  Serial.printf("[BUFFER] Сохранено. Всего: %d\n", pending_events);
}

int countBufferedEvents() {
  int count = 0;
  File f = LittleFS.open(BUFFER_FILE, "r");
  if (!f) return 0;
  while (f.available()) { f.readStringUntil('\n'); count++; }
  f.close();
  return count;
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