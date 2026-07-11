/*
 * KARUSEL — прошивка для ESP32 v6.0
 * 
 * Два сигнала: WIN (GPIO13) и PLAY (GPIO14).
 * Счётчики событий в прерываниях.
 * Раз в секунду отправка всех накопленных событий.
 * Буфер: две переменные, сохраняются в NVS (энергонезависимая память).
 * Нет статуса сервера — если не отправилось, пробуем через секунду снова.
 * При старте задержка 5 секунд (ожидание стабилизации питания).
 */

#include <WiFi.h>
#include <HTTPClient.h>

// ═══════════════════════════════════════════════════════
// НАСТРОЙКИ
// ═══════════════════════════════════════════════════════
const int MACHINE_ID = 3;
const int WIN_PIN = 13;
const int PLAY_PIN = 14;

//////////////////////////////////////////
const char* SERVER_URL = "http://194.186.104.79:80/api/event";
const char* WIFI_SSID = "SmartVend";
const char* WIFI_PASSWORD = "12345678";

// const char* WIFI_SSID = "kv1313";
// const char* WIFI_PASSWORD = "93985666";

// const char* WIFI_SSID = "iPhone (Алекс)";
// const char* WIFI_PASSWORD = "qwerty777";

const int LOCATION_ID = 1;  // ID адреса в облаке
const char* API_KEY = "EawbxVBa7azu65LNdfCOzXzB_BRo0Kp2YC_fuy4rfVg";
//////////////////////////////////////////

// ═══════════════════════════════════════════════════════
// КОНСТАНТЫ
// ═══════════════════════════════════════════════════════

const unsigned long POLL_INTERVAL_MS = 1000;
const unsigned long HTTP_TIMEOUT_MS = 3000;
const unsigned long WIFI_RETRY_MS = 10000;

// ═══════════════════════════════════════════════════════
// ГЛОБАЛЬНЫЕ ПЕРЕМЕННЫЕ
// ═══════════════════════════════════════════════════════

// Счётчики событий (инкрементируются в прерываниях)
volatile int win_counter = 0;
volatile int play_counter = 0;

volatile int raw_win_counter = 0;
volatile int raw_play_counter = 0;

// Неотправленные события (сохраняются в NVS)
int pending_wins = 0;
int pending_plays = 0;


// WiFi
unsigned long last_wifi_attempt = 0;
unsigned long last_poll_time = 0;

// ═══════════════════════════════════════════════════════
// ПРЕРЫВАНИЯ
// ═══════════════════════════════════════════════════════
void IRAM_ATTR onWin() {
  delayMicroseconds(50);  // Ждём 50 мкс, пока дребезг затухнет
  if (digitalRead(WIN_PIN) == LOW) {  // Пин всё ещё в LOW — реальный импульс
    win_counter++;
    raw_win_counter++;
  }
}

void IRAM_ATTR onPlay() {
  delayMicroseconds(50);
  if (digitalRead(PLAY_PIN) == LOW) {
    play_counter++;
    raw_play_counter++;
  }
}

// ═══════════════════════════════════════════════════════
// SETUP
// ═══════════════════════════════════════════════════════
void setup() {
  Serial.begin(115200);

  // Задержка для стабилизации питания
  Serial.println("\n......................");
  delay(2000);

  Serial.println("\n╔════════════════════════════════╗");
  Serial.println("║  KARUSEL ESP32 TRACKER v6.0    ║");
  Serial.println("╚════════════════════════════════╝");
  Serial.printf("ID: %d | WIN: GPIO%d | PLAY: GPIO%d\n", MACHINE_ID, WIN_PIN, PLAY_PIN);

  pinMode(WIN_PIN, INPUT_PULLUP);
  pinMode(PLAY_PIN, INPUT_PULLUP);
  pinMode(LED_BUILTIN, OUTPUT);
  digitalWrite(LED_BUILTIN, LOW);


  attachInterrupt(digitalPinToInterrupt(WIN_PIN), onWin, FALLING);
  attachInterrupt(digitalPinToInterrupt(PLAY_PIN), onPlay, FALLING);

  WiFi.mode(WIFI_STA);
  // WiFi.config(IPAddress(192, 168, 0, 200 + MACHINE_ID), IPAddress(192, 168, 0, 1), IPAddress(255, 255, 255, 0));
  WiFi.begin(WIFI_SSID, WIFI_PASSWORD);
  Serial.printf("[WiFi] Подключение к %s...\n", WIFI_SSID);
}

// ═══════════════════════════════════════════════════════
// LOOP
// ═══════════════════════════════════════════════════════

void loop() {
  // ── WiFi ──
  bool wifi_ok = (WiFi.status() == WL_CONNECTED);
  digitalWrite(LED_BUILTIN, wifi_ok ? HIGH : LOW);

  static bool was_connected = false;
  if (wifi_ok && !was_connected) {
      was_connected = true;
      Serial.printf("[WiFi] Подключено! IP: %s\n", WiFi.localIP().toString().c_str());
  }
  if (!wifi_ok) {
      was_connected = false;
  }

  if (!wifi_ok && (millis() - last_wifi_attempt > WIFI_RETRY_MS)) {
    Serial.println("[WiFi] Переподключение...");
    WiFi.begin(WIFI_SSID, WIFI_PASSWORD);
    last_wifi_attempt = millis();
  }

  // ── Отправка раз в секунду ──
  if (millis() - last_poll_time >= POLL_INTERVAL_MS) {
    last_poll_time = millis();

    //Serial.printf("raw: wins=%d, plays=%d\n", raw_win_counter, raw_play_counter);



    // Атомарное чтение и обнуление счётчиков
    portDISABLE_INTERRUPTS();
    int wins = win_counter;
    int plays = play_counter;
    win_counter = 0;
    play_counter = 0;
    portENABLE_INTERRUPTS();

    pending_wins += wins;
    pending_plays += plays;

    if (pending_wins > 0 || pending_plays > 0) {
      delay(2000);
      Serial.printf("Очередь: wins=%d, plays=%d\n", pending_wins, pending_plays);

      if (wifi_ok) {
        // Отправляем ТОЛЬКО ОДНО событие за раз!
        if (pending_wins > 0) {
          if (sendHTTP("win")) {
            pending_wins--; // Успешно отправили - уменьшаем очередь
            Serial.printf("[OK] Осталось win: %d\n", pending_wins);
          } else {
            Serial.println("[WIN] Ошибка, пробуем в следующую секунду");
            // НЕ уменьшаем pending_wins, просто выходим из итерации
          }
        } 
        else if (pending_plays > 0) { // Иначе, если нет win, отправляем play
          if (sendHTTP("play")) {
            pending_plays--;
            Serial.printf("[OK] Осталось play: %d\n", pending_plays);
          } else {
            Serial.println("[PLAY] Ошибка, пробуем в следующую секунду");
          }
        }

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

  //String jsonBody = "{\"machine_id\":" + String(MACHINE_ID) + ",\"event_type\":\"" + eventType + "\"}";
  String jsonBody = "{\"machine_id\":" + String(MACHINE_ID) + 
    ",\"location_id\":" + String(1) +
    ",\"api_key\":\"EawbxVBa7azu65LNdfCOzXzB_BRo0Kp2YC_fuy4rfVg\"" +
    ",\"event_type\":\"" + eventType + "\"}";


  unsigned long t0 = millis();
  int httpCode = http.POST(jsonBody);
  unsigned long t1 = millis();
  http.end();

  Serial.printf("[HTTP] Код: %d, время: %lu мс, тип: %s\n", httpCode, t1 - t0, eventType.c_str());

  return (httpCode == 200);
}
