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
#include <Preferences.h>

Preferences prefs;

// ═══════════════════════════════════════════════════════
// НАСТРОЙКИ
// ═══════════════════════════════════════════════════════
const int MACHINE_ID = 100;
const int WIN_PIN = 13;
const int PLAY_PIN = 14;

//////////////////////////////////////////
const char* SERVER_URL = "http://194.186.104.79:80/api/bulk-event";
// const char* WIFI_SSID = "SmartVend";
// const char* WIFI_PASSWORD = "12345678";

const char* WIFI_SSID = "kv1313";
const char* WIFI_PASSWORD = "93985666";

// const char* WIFI_SSID = "iPhone (Алекс)";
// const char* WIFI_PASSWORD = "qwerty777";

const int LOCATION_ID = 1;  // ID адреса в облаке
const char* API_KEY = "EawbxVBa7azu65LNdfCOzXzB_BRo0Kp2YC_fuy4rfVg";
//////////////////////////////////////////

// ═══════════════════════════════════════════════════════
// КОНСТАНТЫ
// ═══════════════════════════════════════════════════════

const unsigned long POLL_INTERVAL_MS = 5000;
const unsigned long HTTP_TIMEOUT_MS = 3000;
const unsigned long WIFI_RETRY_MS = 10000;

// ═══════════════════════════════════════════════════════
// ГЛОБАЛЬНЫЕ ПЕРЕМЕННЫЕ
// ═══════════════════════════════════════════════════════
bool synced = false;  // true = счётчики синхронизированы с сервером

// Счётчики событий (инкрементируются в прерываниях)
volatile int win_counter = 0;
volatile int play_counter = 0;

// Загружается из NVS
int total_wins = 0;   
int total_plays = 0;

volatile int raw_win_counter = 0;
volatile int raw_play_counter = 0;


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
  delay(3000);

  prefs.begin("karusel", false);
  total_wins = prefs.getInt("total_wins", 0);
  total_plays = prefs.getInt("total_plays", 0);
  prefs.end();

  // Если счётчики нулевые — запрашиваем у сервера
  if (total_wins > 0 || total_plays > 0) {
        synced = true;  // Уже были данные в NVS — синхронизированы
    }


  Serial.printf("Восстановлено: wins=%d, plays=%d\n", total_wins, total_plays);

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
        WiFi.begin(WIFI_SSID, WIFI_PASSWORD);
        last_wifi_attempt = millis();
    }


    // Если не синхронизированы — пытаемся получить данные с сервера
    if (!synced && wifi_ok) {
        HTTPClient http;
        String syncUrl = "http://194.186.104.79:80/api/get-counts?"
            "machine_id=" + String(MACHINE_ID) +
            "&location_id=" + String(LOCATION_ID) +
            "&api_key=" + String(API_KEY);
        http.begin(syncUrl);

        
        int httpCode = http.GET();
        if (httpCode == 200) {
            String response = http.getString();
            int server_wins = 0, server_plays = 0;
            int idx = response.indexOf("\"total_wins\":");
            if (idx > 0) server_wins = response.substring(idx + 13).toInt();
            idx = response.indexOf("\"total_plays\":");
            if (idx > 0) server_plays = response.substring(idx + 14).toInt();
            
            total_wins += server_wins;
            total_plays += server_plays;
            win_counter = 0;
            play_counter = 0;
            synced = true;
            
            prefs.begin("karusel", false);
            prefs.putInt("total_wins", total_wins);
            prefs.putInt("total_plays", total_plays);
            prefs.end();
        }
        http.end();
    }

    if (millis() - last_poll_time >= POLL_INTERVAL_MS) {
        last_poll_time = millis();

        portDISABLE_INTERRUPTS();
        int wins = win_counter;
        int plays = play_counter;
        win_counter = 0;
        play_counter = 0;
        portENABLE_INTERRUPTS();

        total_wins += wins;
        total_plays += plays;

        // Сохраняем в NVS
        prefs.begin("karusel", false);
        prefs.putInt("total_wins", total_wins);
        prefs.putInt("total_plays", total_plays);
        prefs.end();

        if (wins > 0 || plays > 0) {
            Serial.printf("Новые: wins=%d, plays=%d | Всего: wins=%d, plays=%d\n", wins, plays, total_wins, total_plays);
        }

        if (synced && wifi_ok) {
            HTTPClient http;
            http.begin(SERVER_URL);
            http.addHeader("Content-Type", "application/json");
            http.setTimeout(HTTP_TIMEOUT_MS);

            String jsonBody = "{\"machine_id\":" + String(MACHINE_ID) +
                ",\"location_id\":" + String(LOCATION_ID) +
                ",\"api_key\":\"" + String(API_KEY) + "\"" +
                ",\"total_wins\":" + String(total_wins) +
                ",\"total_plays\":" + String(total_plays) + "}";

            unsigned long t0 = millis();
            int httpCode = http.POST(jsonBody);
            unsigned long t1 = millis();
            http.end();

            Serial.printf("[HTTP] Код: %d, время: %lu мс\n", httpCode, t1 - t0);

            if (httpCode == 200) {
                Serial.println("[OK] Отправлено.");
            } else {
                Serial.println("[ERR] Ошибка отправки.");
            }
        }
    }

    delay(10);
}

