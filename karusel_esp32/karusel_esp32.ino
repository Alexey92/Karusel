/*
 * KARUSEL — прошивка для ESP32 v4.0
 * 
 * Поддержка двух сигналов: WIN (GPIO13) и PLAY (GPIO14).
 * HTTP-запросы в отдельном потоке FreeRTOS (не блокирует кнопки).
 * Минимальный интервал между отправками: 500 мс.
 * Буфер на LittleFS с указанием типа события.
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
const int WIN_PIN = 13;   // Сигнал "Выигрыш"
const int PLAY_PIN = 14;  // Сигнал "Игра"


struct HttpParams {
  String eventType;
};

// ═══════════════════════════════════════════════════════
// КОНСТАНТЫ
// ═══════════════════════════════════════════════════════

const unsigned long DEBOUNCE_MS = 200;
const unsigned long MIN_SEND_INTERVAL_MS = 500;  // Минимум между отправками
const unsigned long WIFI_RETRY_MS = 30000;
const unsigned long BUFFER_COOLDOWN_MS = 200;
const int MAX_STORED_EVENTS = 100;
const char* BUFFER_FILE = "/buffer.txt";

// ═══════════════════════════════════════════════════════
// ГЛОБАЛЬНЫЕ ПЕРЕМЕННЫЕ
// ═══════════════════════════════════════════════════════


// Кнопки
unsigned long last_win_time = 0;
unsigned long last_play_time = 0;
unsigned long last_send_time = 0;
int last_win_state = HIGH;
int last_play_state = HIGH;

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
  Serial.println("║  KARUSEL ESP32 TRACKER v4.0   ║");
  Serial.println("╚════════════════════════════════╝");
  Serial.printf("Аппарат ID: %d | WIN: GPIO%d | PLAY: GPIO%d\n", MACHINE_ID, WIN_PIN, PLAY_PIN);

  pinMode(WIN_PIN, INPUT_PULLUP);
  pinMode(PLAY_PIN, INPUT_PULLUP);
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
  HttpParams* params = (HttpParams*)parameter;
  String eventType = params->eventType;
  delete params;  // Освобождаем память

  HTTPClient http;
  http.begin(SERVER_URL);
  http.addHeader("Content-Type", "application/json");

  String jsonBody = "{\"machine_id\":" + String(MACHINE_ID) + ",\"event_type\":\"" + eventType + "\"}";

  unsigned long t0 = millis();
  int httpCode = http.POST(jsonBody);
  unsigned long t1 = millis();
  http.end();

  Serial.printf("[HTTP] Код: %d, время: %lu мс, тип: %s\n", httpCode, t1 - t0, eventType.c_str());

  http_success = (httpCode == 200);
  http_done = true;

  vTaskDelete(NULL);
}

void startHTTP(bool isBuffer, String eventType = "win") {
  if (http_busy) return;

  // Не создаём задачу, если WiFi мёртв
  if (WiFi.status() != WL_CONNECTED) {
    if (!isBuffer) {
      bufferEvent(eventType);
      Serial.printf("[%s] Нет WiFi, событие в буфер.\n", eventType.c_str());
    }
    return;
  }

  if (isBuffer && isBufferEmpty()) {
    pending_events = 0;
    return;
  }

  http_busy = true;
  http_done = false;
  http_was_buffer = isBuffer;

  HttpParams* params = new HttpParams;
  params->eventType = eventType;

  xTaskCreatePinnedToCore(httpTask, "HTTP_Task", 8192, params, 1, NULL, 0);
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
    } else if (!http_was_buffer) {
        // Тип события уже сохранён в буфер при старте (в startHTTP при недоступности WiFi),
        // а здесь мы просто логируем. bufferEvent не нужен, событие уже в буфере.
        Serial.println("[HTTP] Сервер недоступен, событие уже в буфере.");
      }
  }

  // ── 2. WiFi ──
  bool wifi_ok = (WiFi.status() == WL_CONNECTED);
  digitalWrite(LED_BUILTIN, wifi_ok ? HIGH : LOW);

  if (!wifi_ok && (millis() - last_wifi_attempt > WIFI_RETRY_MS)) {
    Serial.println("[WiFi] Попытка переподключения...");
    connectWiFi();  // Теперь это мгновенная функция
    last_wifi_attempt = millis();
  }

  // ── 3. Отправка буфера ──
  if (wifi_ok && pending_events > 0 && !http_busy &&
      (millis() - last_buffer_attempt > BUFFER_COOLDOWN_MS)) {
    last_buffer_attempt = millis();

    if (!isBufferEmpty()) {
      // Читаем тип события из файла
      String etype = readFirstEventType();
      startHTTP(true, etype);
    } else {
      pending_events = 0;
    }
  }

  // ── 4. Кнопка WIN ──
  int win_state = digitalRead(WIN_PIN);
  if (win_state == LOW && last_win_state == HIGH) {
    unsigned long now = millis();
    if (now - last_win_time > DEBOUNCE_MS && now - last_send_time > MIN_SEND_INTERVAL_MS) {
      last_win_time = now;
      last_send_time = now;
      Serial.println("[WIN] Обнаружен выигрыш!");

      if (http_busy) { 
        bufferEvent("win"); Serial.println("[WIN] HTTP занят, в буфер."); 
      }
      else { 
        startHTTP(false, "win"); 
      }
    }
  }
  last_win_state = win_state;

  // ── 5. Кнопка PLAY ──
  int play_state = digitalRead(PLAY_PIN);
  if (play_state == LOW && last_play_state == HIGH) {
    unsigned long now = millis();
    if (now - last_play_time > DEBOUNCE_MS && now - last_send_time > MIN_SEND_INTERVAL_MS) {
      last_play_time = now;
      last_send_time = now;
      Serial.println("[PLAY] Обнаружена игра!");

      if (http_busy) { 
        bufferEvent("play"); Serial.println("[PLAY] HTTP занят, в буфер."); 
      }
      else { 
        startHTTP(false, "play"); 
      }
    }
  }
  last_play_state = play_state;


  delay(10);
}

// ═══════════════════════════════════════════════════════
// WiFi
// ═══════════════════════════════════════════════════════

void connectWiFi() {
  // Не ждём подключения — просто запускаем процесс
  WiFi.mode(WIFI_STA);
  WiFi.begin(WIFI_SSID, WIFI_PASSWORD);
  Serial.printf("[WiFi] Подключение к %s запущено...\n", WIFI_SSID);
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