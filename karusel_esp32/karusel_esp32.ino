/*
 * KARUSEL — прошивка для ESP32 v6.0
 * 
 * Два сигнала: WIN (GPIO13) и PLAY (GPIO14).
 * Счётчики событий в прерываниях.
 * Раз в секунду отправка всех накопленных событий.
 * Буфер: две переменные, сохраняются в NVS (энергонезависимая память).
 * Нет статуса сервера — если не отправилось, пробуем через секунду снова.
 * При старте задержка 15 секунд (ожидание стабилизации питания).
 */

#include <WiFi.h>
#include <HTTPClient.h>
#include <Preferences.h>

// ═══════════════════════════════════════════════════════
// НАСТРОЙКИ
// ═══════════════════════════════════════════════════════

//const char* WIFI_SSID = "karusel-net";
//const char* WIFI_PASSWORD = "karusel2026";
//const char* SERVER_URL = "http://192.168.1.100:5050/api/event";
const int MACHINE_ID = 2;
const int WIN_PIN = 13;
const int PLAY_PIN = 14;

//////////////////////////////////////////
const char* SERVER_URL = "http://192.168.0.108:5050/api/event";
const char* WIFI_SSID = "kv1313";
const char* WIFI_PASSWORD = "93985666";

const int TEST_WIN_OUT = 33;
const int TEST_PLAY_OUT = 32;
//////////////////////////////////////////

// ═══════════════════════════════════════════════════════
// КОНСТАНТЫ
// ═══════════════════════════════════════════════════════

const unsigned long POLL_INTERVAL_MS = 1000;
const unsigned long HTTP_TIMEOUT_MS = 3000;
const unsigned long WIFI_RETRY_MS = 7000;

// ═══════════════════════════════════════════════════════
// ГЛОБАЛЬНЫЕ ПЕРЕМЕННЫЕ
// ═══════════════════════════════════════════════════════

// Счётчики событий (инкрементируются в прерываниях)
volatile int win_counter = 0;
volatile int play_counter = 0;

// Неотправленные события (сохраняются в NVS)
int pending_wins = 0;
int pending_plays = 0;

// NVS
Preferences prefs;

// WiFi
unsigned long last_wifi_attempt = 0;
unsigned long last_poll_time = 0;

// ═══════════════════════════════════════════════════════
// ПРЕРЫВАНИЯ
// ═══════════════════════════════════════════════════════

volatile unsigned long last_win_interrupt = 0;

void IRAM_ATTR onWin() {
  win_counter++;
}

void IRAM_ATTR onPlay() {
  play_counter++;
}

// ═══════════════════════════════════════════════════════
// SETUP
// ═══════════════════════════════════════════════════════

void setup() {
  Serial.begin(115200);

  // Задержка для стабилизации питания
  Serial.println("\n......................");
  delay(5000);

  Serial.println("\n╔════════════════════════════════╗");
  Serial.println("║  KARUSEL ESP32 TRACKER v6.0    ║");
  Serial.println("╚════════════════════════════════╝");
  Serial.printf("ID: %d | WIN: GPIO%d | PLAY: GPIO%d\n", MACHINE_ID, WIN_PIN, PLAY_PIN);

  pinMode(WIN_PIN, INPUT_PULLUP);
  pinMode(PLAY_PIN, INPUT_PULLUP);
  pinMode(LED_BUILTIN, OUTPUT);
  digitalWrite(LED_BUILTIN, LOW);

  // Тестовые сигналы
  pinMode(TEST_WIN_OUT, OUTPUT);
  pinMode(TEST_PLAY_OUT, OUTPUT);
  digitalWrite(TEST_WIN_OUT, HIGH);
  digitalWrite(TEST_PLAY_OUT, HIGH);

  attachInterrupt(digitalPinToInterrupt(WIN_PIN), onWin, FALLING);
  attachInterrupt(digitalPinToInterrupt(PLAY_PIN), onPlay, FALLING);

  // Восстанавливаем неотправленные события из NVS
  prefs.begin("karusel", false);
  pending_wins = prefs.getInt("pend_win", 0);
  pending_plays = prefs.getInt("pend_play", 0);
  prefs.end();
  Serial.printf("[NVS] Восстановлено: wins=%d, plays=%d\n", pending_wins, pending_plays);

  WiFi.mode(WIFI_STA);
  WiFi.begin(WIFI_SSID, WIFI_PASSWORD);
  Serial.printf("[WiFi] Подключение к %s...\n", WIFI_SSID);
}

// ═══════════════════════════════════════════════════════
// LOOP
// ═══════════════════════════════════════════════════════

void loop() {
  testSignals();

  // ── WiFi ──
  bool wifi_ok = (WiFi.status() == WL_CONNECTED);
  digitalWrite(LED_BUILTIN, wifi_ok ? HIGH : LOW);

  if (!wifi_ok && (millis() - last_wifi_attempt > WIFI_RETRY_MS)) {
    Serial.println("[WiFi] Переподключение...");
    WiFi.begin(WIFI_SSID, WIFI_PASSWORD);
    last_wifi_attempt = millis();
  }

  // ── Отправка раз в секунду ──
  if (millis() - last_poll_time >= POLL_INTERVAL_MS) {
    last_poll_time = millis();


    // Атомарное чтение и обнуление счётчиков
    portDISABLE_INTERRUPTS();
    int wins = win_counter;
    int plays = play_counter;
    win_counter = 0;
    play_counter = 0;
    portENABLE_INTERRUPTS();

    pending_wins += wins;
    pending_plays += plays;

    // Сохраняем в NVS
    prefs.begin("karusel", false);
    prefs.putInt("pend_win", pending_wins);
    prefs.putInt("pend_play", pending_plays);
    prefs.end();

    if (pending_wins > 0 || pending_plays > 0) {
    Serial.printf("Отправка: wins=%d, plays=%d\n", pending_wins, pending_plays);

      if (wifi_ok) {
        // Отправляем выигрыши
        while (pending_wins > 0) {
          if (sendHTTP("win")) {
            pending_wins--;
          } else {
            Serial.println("[WIN] Отправка не удалась, пробую позже.");
            break;
          }
        }

        // Отправляем игры
        while (pending_plays > 0) {
          if (sendHTTP("play")) {
            pending_plays--;
          } else {
            Serial.println("[PLAY] Отправка не удалась, пробую позже.");
            break;
          }
        }

        // Обновляем NVS после отправки
        prefs.begin("karusel", false);
        prefs.putInt("pend_win", pending_wins);
        prefs.putInt("pend_play", pending_plays);
        prefs.end();

        if (pending_wins == 0 && pending_plays == 0) {
          Serial.println("[OK] Все события отправлены.");
        }
      } else {
        Serial.printf("[WAIT] Нет WiFi. Накоплено: wins=%d, plays=%d\n", pending_wins, pending_plays);
      }
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
// ТЕСТОВАЯ ГЕНЕРАЦИЯ СИГНАЛОВ (для отладки)
// Подключить: D35 к D13, D34 к D14
// ═══════════════════════════════════════════════════════
void testSignals() {
  static unsigned long last_win_test = 0;
  static unsigned long last_play_test = 0;
  static int play_burst_count = 0;
  static bool play_burst_active = false;
  static bool win_pulse_active = false;
  static unsigned long win_pulse_start = 0;
  static bool play_pulse_low = false;
  static unsigned long play_pulse_start = 0;
  
  unsigned long now = millis();

  // Выигрыш: раз в 10 секунд, импульс LOW на 25 мс
  if (!win_pulse_active && (now - last_win_test >= 10000)) {
    win_pulse_active = true;
    win_pulse_start = now;
    digitalWrite(TEST_WIN_OUT, LOW);   // импульс в 0
    //Serial.println("[TEST] Импульс WIN (25 мс, LOW)");
  }
  if (win_pulse_active && (now - win_pulse_start >= 25)) {
    digitalWrite(TEST_WIN_OUT, HIGH);  // возвращаем 3.3В
    win_pulse_active = false;
    last_win_test = now;
  }

  // Игры: раз в 7 секунд, пачка из 4 импульсов LOW по 25 мс с интервалом 5 мс
  if (!play_burst_active && (now - last_play_test >= 7000)) {
    play_burst_active = true;
    play_burst_count = 0;
    last_play_test = now;
    //Serial.println("[TEST] Пачка PLAY: 4 импульса");
  }

  if (play_burst_active && play_burst_count < 4) {
    if (!play_pulse_low) {
      digitalWrite(TEST_PLAY_OUT, LOW);  // импульс в 0
      play_pulse_low = true;
      play_pulse_start = now;
    }
    if (play_pulse_low && (now - play_pulse_start >= 25)) {
      digitalWrite(TEST_PLAY_OUT, HIGH);  // возвращаем 3.3В
      play_pulse_low = false;
      play_burst_count++;
      //Serial.printf("[TEST]   PLAY импульс %d/4\n", play_burst_count);
    }
  }
  if (play_burst_count >= 4) {
    play_burst_active = false;
  }
}