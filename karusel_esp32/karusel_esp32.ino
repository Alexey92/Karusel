/*
 * KARUSEL — прошивка для ESP32
 * 
 * Назначение:
 *   - Ловит импульс выигрыша с игрового автомата (пин GPIO)
 *   - Отправляет HTTP POST на сервер
 *   - При обрыве WiFi сохраняет события в память и отправляет при восстановлении
 * 
 * Настройка перед прошивкой (строки 30-40):
 *   1. WIFI_SSID — имя WiFi сети
 *   2. WIFI_PASSWORD — пароль WiFi
 *   3. SERVER_URL — адрес сервера (статический IP мини-ПК)
 *   4. MACHINE_ID — уникальный ID аппарата (1-10)
 *   5. WIN_PIN — пин GPIO, на который приходит импульс выигрыша
 */

#include <WiFi.h>
#include <HTTPClient.h>
#include <Preferences.h>
#include <ArduinoJson.h>

// ═══════════════════════════════════════════════════════
// НАСТРОЙКИ (менять здесь)
// ═══════════════════════════════════════════════════════

const char* WIFI_SSID = "karusel-net";         // Имя WiFi сети
const char* WIFI_PASSWORD = "karusel2026";      // Пароль WiFi
const char* SERVER_URL = "http://192.168.1.100:5050/api/event";  // URL сервера
const int MACHINE_ID = 1;                       // ID этого автомата (1-10)
const int WIN_PIN = 13;                         // Пин GPIO для сигнала выигрыша

// ═══════════════════════════════════════════════════════
// КОНСТАНТЫ
// ═══════════════════════════════════════════════════════

const unsigned long DEBOUNCE_MS = 200;          // Защита от дребезга (мс)
const unsigned long WIFI_RETRY_MS = 10000;      // Пауза между попытками WiFi (мс)
const int MAX_STORED_EVENTS = 100;              // Максимум событий в офлайн-буфере
const char* PREFS_NAMESPACE = "karusel";        // Пространство в NVS памяти
const char* PREFS_KEY = "events";               // Ключ для хранения событий

// ═══════════════════════════════════════════════════════
// ГЛОБАЛЬНЫЕ ПЕРЕМЕННЫЕ
// ═══════════════════════════════════════════════════════

Preferences prefs;                              // Энергонезависимая память (NVS)
volatile bool win_detected = false;             // Флаг: обнаружен импульс
unsigned long last_win_time = 0;                // Время последнего импульса
unsigned long last_wifi_attempt = 0;            // Время последней попытки WiFi
int pending_events = 0;                         // Количество неотправленных событий

// Структура для хранения события
struct StoredEvent {
  unsigned long timestamp;
  bool sent;
};

// ═══════════════════════════════════════════════════════
// ПРЕРЫВАНИЕ (вызывается при импульсе на пине)
// ═══════════════════════════════════════════════════════

void IRAM_ATTR onWinSignal() {
  // Простая защита от шума — проверяем уровень сигнала
  if (digitalRead(WIN_PIN) == HIGH) {
    win_detected = true;
  }
}

// ═══════════════════════════════════════════════════════
// SETUP (запуск один раз при включении)
// ═══════════════════════════════════════════════════════

void setup() {
  Serial.begin(115200);
  delay(1000);
  
  Serial.println("╔════════════════════════════════╗");
  Serial.println("║  KARUSEL ESP32 TRACKER v1.0   ║");
  Serial.println("╚════════════════════════════════╝");
  Serial.printf("Аппарат ID: %d\n", MACHINE_ID);
  Serial.printf("Пин сигнала: GPIO%d\n", WIN_PIN);
  Serial.printf("Сервер: %s\n", SERVER_URL);

  // Настраиваем пин выигрыша
  pinMode(WIN_PIN, INPUT_PULLDOWN);  // Подтяжка к земле (сигнал = HIGH при выигрыше)
  attachInterrupt(digitalPinToInterrupt(WIN_PIN), onWinSignal, RISING);

  // Встроенный светодиод — индикатор WiFi
  pinMode(LED_BUILTIN, OUTPUT);
  digitalWrite(LED_BUILTIN, LOW);

  // Подключаем WiFi
  connectWiFi();

  // Загружаем неотправленные события из памяти
  loadStoredEvents();
  Serial.printf("Неотправленных событий в буфере: %d\n", pending_events);
}

// ═══════════════════════════════════════════════════════
// LOOP (основной цикл)
// ═══════════════════════════════════════════════════════

void loop() {
  // ── Переподключение WiFi при обрыве ──
  if (WiFi.status() != WL_CONNECTED) {
    digitalWrite(LED_BUILTIN, LOW);  // Светодиод выключен = нет сети
    if (millis() - last_wifi_attempt > WIFI_RETRY_MS) {
      Serial.println("[WiFi] Попытка переподключения...");
      connectWiFi();
      last_wifi_attempt = millis();
    }
    delay(100);
    return;
  }

  digitalWrite(LED_BUILTIN, HIGH);  // Светодиод горит = сеть есть

  // ── Сначала отправляем накопленные события ──
  if (pending_events > 0) {
    sendStoredEvents();
  }

  // ── Обработка нового импульса ──
  if (win_detected) {
    win_detected = false;

    // Защита от дребезга
    unsigned long now = millis();
    if (now - last_win_time < DEBOUNCE_MS) {
      return;
    }
    last_win_time = now;

    // Проверяем сигнал напрямую (дополнительная защита)
    if (digitalRead(WIN_PIN) == HIGH) {
      Serial.println("[WIN] Обнаружен выигрыш!");
      sendWinEvent();
    }
  }

  delay(10);  // Маленькая задержка, чтобы не молотить процессор
}

// ═══════════════════════════════════════════════════════
// ПОДКЛЮЧЕНИЕ К WiFi
// ═══════════════════════════════════════════════════════

void connectWiFi() {
  Serial.printf("[WiFi] Подключаюсь к %s...\n", WIFI_SSID);
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
    Serial.printf("[WiFi] IP адрес: %s\n", WiFi.localIP().toString().c_str());
  } else {
    Serial.println("\n[WiFi] Не удалось подключиться. Буду пробовать позже.");
  }
}

// ═══════════════════════════════════════════════════════
// ОТПРАВКА СОБЫТИЯ НА СЕРВЕР
// ═══════════════════════════════════════════════════════

void sendWinEvent() {
  if (WiFi.status() != WL_CONNECTED) {
    // Нет сети — сохраняем событие локально
    storeEvent();
    return;
  }

  HTTPClient http;
  http.begin(SERVER_URL);
  http.addHeader("Content-Type", "application/json");

  // Формируем JSON
  StaticJsonDocument<128> doc;
  doc["machine_id"] = MACHINE_ID;
  doc["event_type"] = "win";

  String jsonBody;
  serializeJson(doc, jsonBody);

  // Отправляем POST
  int httpCode = http.POST(jsonBody);

  if (httpCode == 200) {
    String response = http.getString();
    Serial.printf("[HTTP] OK (код %d): %s\n", httpCode, response.c_str());
  } else {
    Serial.printf("[HTTP] Ошибка (код %d): %s\n", httpCode, http.errorToString(httpCode).c_str());
    // Ошибка отправки — сохраняем локально
    storeEvent();
  }

  http.end();
}

// ═══════════════════════════════════════════════════════
// ХРАНЕНИЕ СОБЫТИЙ (офлайн-буфер)
// ═══════════════════════════════════════════════════════

void storeEvent() {
  if (pending_events >= MAX_STORED_EVENTS) {
    Serial.println("[BUFFER] Буфер переполнен! Самое старое событие будет потеряно.");
    return;
  }

  // Сохраняем метку времени в NVS
  char key[16];
  snprintf(key, sizeof(key), "evt_%d", pending_events);
  
  unsigned long now = millis();
  prefs.begin(PREFS_NAMESPACE, false);
  prefs.putULong(key, now);
  prefs.end();

  pending_events++;
  Serial.printf("[BUFFER] Событие сохранено. Всего в буфере: %d\n", pending_events);
}

// ═══════════════════════════════════════════════════════

void loadStoredEvents() {
  prefs.begin(PREFS_NAMESPACE, true);
  pending_events = 0;
  
  // Считаем, сколько событий сохранено
  for (int i = 0; i < MAX_STORED_EVENTS; i++) {
    char key[16];
    snprintf(key, sizeof(key), "evt_%d", i);
    if (prefs.isKey(key)) {
      pending_events++;
    } else {
      break;
    }
  }
  prefs.end();
}

// ═══════════════════════════════════════════════════════

void sendStoredEvents() {
  if (pending_events == 0) return;

  Serial.printf("[BUFFER] Отправляю %d накопленных событий...\n", pending_events);
  
  prefs.begin(PREFS_NAMESPACE, false);
  
  int sent = 0;
  for (int i = 0; i < pending_events; i++) {
    char key[16];
    snprintf(key, sizeof(key), "evt_%d", i);
    
    unsigned long timestamp = prefs.getULong(key, 0);
    
    // Отправляем событие с сохранённой меткой времени
    HTTPClient http;
    http.begin(SERVER_URL);
    http.addHeader("Content-Type", "application/json");

    StaticJsonDocument<200> doc;
    doc["machine_id"] = MACHINE_ID;
    doc["event_type"] = "win";
    doc["timestamp"] = timestamp;  // Оригинальное время события

    String jsonBody;
    serializeJson(doc, jsonBody);

    int httpCode = http.POST(jsonBody);
    http.end();

    if (httpCode == 200) {
      prefs.remove(key);  // Удаляем отправленное событие
      sent++;
    } else {
      Serial.printf("[BUFFER] Не удалось отправить событие %d. Остановка.\n", i);
      break;  // Если не отправилось — пробуем позже
    }

    delay(100);  // Небольшая пауза между отправками
  }

  // Сдвигаем оставшиеся события
  compactStoredEvents();
  
  pending_events -= sent;
  prefs.end();
  
  Serial.printf("[BUFFER] Отправлено %d событий. Осталось: %d\n", sent, pending_events);
}

// ═══════════════════════════════════════════════════════

void compactStoredEvents() {
  // Сдвигаем оставшиеся ключи, чтобы не было пропусков
  int writeIdx = 0;
  for (int readIdx = 0; readIdx < MAX_STORED_EVENTS; readIdx++) {
    char readKey[16], writeKey[16];
    snprintf(readKey, sizeof(readKey), "evt_%d", readIdx);
    
    if (prefs.isKey(readKey)) {
      if (readIdx != writeIdx) {
        snprintf(writeKey, sizeof(writeKey), "evt_%d", writeIdx);
        unsigned long value = prefs.getULong(readKey, 0);
        prefs.putULong(writeKey, value);
        prefs.remove(readKey);
      }
      writeIdx++;
    }
  }
}