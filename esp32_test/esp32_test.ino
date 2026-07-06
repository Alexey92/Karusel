/*
 * DIAGNOSTIC TOOL для ESP32
 * Проверяет: WiFi, DHCP, DNS, доступность серверов
 * Версия: 1.0
 */

#include <WiFi.h>
#include <HTTPClient.h>
#include <WiFiClient.h>

// ═══════════════════════════════════════════════════════
// НАСТРОЙКИ ДЛЯ ТЕСТА
// ═══════════════════════════════════════════════════════

const char* WIFI_SSID = "SmartVend";
const char* WIFI_PASSWORD = "12345678";
// const char* WIFI_SSID = "iPhone (Алекс)";
// const char* WIFI_PASSWORD = "qwerty777";

// Тестовые серверы
const char* SERVER_IP = "194.186.104.79";  // Ваш сервер
const int SERVER_PORT = 80;                 // Изменен на 80
const char* SERVER_URL = "http://194.186.104.79:80/api/event";

// Для теста DNS
const char* TEST_DOMAIN = "ya.ru";
const char* TEST_URL = "http://ya.ru";

// ═══════════════════════════════════════════════════════
// ГЛОБАЛЬНЫЕ ПЕРЕМЕННЫЕ
// ═══════════════════════════════════════════════════════

unsigned long last_test = 0;
int test_counter = 0;

// ═══════════════════════════════════════════════════════
// SETUP
// ═══════════════════════════════════════════════════════

void setup() {
    Serial.begin(115200);
    delay(1000);
    
    Serial.println("\n\n");
    Serial.println("╔═══════════════════════════════════════════╗");
    Serial.println("║      ESP32 DIAGNOSTIC TOOL v1.0         ║");
    Serial.println("╚═══════════════════════════════════════════╝");
    Serial.println();
    
    // Подключение к WiFi
    Serial.printf("[1] Подключение к WiFi: %s\n", WIFI_SSID);
    WiFi.mode(WIFI_STA);
    WiFi.begin(WIFI_SSID, WIFI_PASSWORD);
    
    int attempts = 0;
    while (WiFi.status() != WL_CONNECTED && attempts < 30) {
        delay(1000);
        Serial.print(".");
        attempts++;
    }
    Serial.println();
    
    if (WiFi.status() == WL_CONNECTED) {
        Serial.println("[OK] WiFi подключен!");
        printNetworkInfo();
    } else {
        Serial.println("[ERROR] Не удалось подключиться к WiFi!");
        Serial.println("Проверьте SSID и пароль");
    }
    
    Serial.println("\n═══════════════════════════════════════════");
    Serial.println("Начинаю полную диагностику...");
    Serial.println("═══════════════════════════════════════════\n");
    
    // Сразу запускаем полную диагностику
    runFullDiagnostic();
}

// ═══════════════════════════════════════════════════════
// LOOP
// ═══════════════════════════════════════════════════════

void loop() {
    // Проверяем WiFi каждые 30 секунд
    if (millis() - last_test > 30000) {
        last_test = millis();
        test_counter++;
        
        Serial.printf("\n--- ТЕСТ #%d ---\n", test_counter);
        
        if (WiFi.status() == WL_CONNECTED) {
            runQuickDiagnostic();
        } else {
            Serial.println("[ERROR] WiFi отключен!");
            Serial.println("Попытка переподключения...");
            WiFi.reconnect();
        }
    }
    
    delay(1000);
}

// ═══════════════════════════════════════════════════════
// ФУНКЦИИ ДИАГНОСТИКИ
// ═══════════════════════════════════════════════════════

void printNetworkInfo() {
    Serial.println("\n--- СЕТЕВАЯ ИНФОРМАЦИЯ ---");
    Serial.printf("IP адрес:    %s\n", WiFi.localIP().toString().c_str());
    Serial.printf("Маска:       %s\n", WiFi.subnetMask().toString().c_str());
    Serial.printf("Шлюз:        %s\n", WiFi.gatewayIP().toString().c_str());
    Serial.printf("DNS:         %s\n", WiFi.dnsIP().toString().c_str());
    Serial.printf("RSSI:        %d dBm\n", WiFi.RSSI());
    Serial.printf("MAC адрес:   %s\n", WiFi.macAddress().c_str());
    Serial.printf("Канал:       %d\n", WiFi.channel());
    Serial.println("---------------------------\n");
}

void runFullDiagnostic() {
    if (WiFi.status() != WL_CONNECTED) {
        Serial.println("[SKIP] WiFi не подключен, диагностика невозможна");
        return;
    }
    
    // 1. Проверка соединения со шлюзом
    Serial.println("[1] Проверка шлюза...");
    IPAddress gateway = WiFi.gatewayIP();
    if (pingHost(gateway, 3000)) {
        Serial.printf("[OK] Шлюз %s доступен\n", gateway.toString().c_str());
    } else {
        Serial.printf("[ERROR] Шлюз %s НЕ ДОСТУПЕН!\n", gateway.toString().c_str());
    }
    
    // 2. Проверка DNS
    Serial.println("\n[2] Проверка DNS (ya.ru)...");
    IPAddress dnsTest = resolveDNS(TEST_DOMAIN);
    if (dnsTest.toString() != "0.0.0.0") {
        Serial.printf("[OK] DNS работает: %s -> %s\n", TEST_DOMAIN, dnsTest.toString().c_str());
    } else {
        Serial.printf("[ERROR] DNS не может разрешить %s!\n", TEST_DOMAIN);
    }
    
    // 3. Проверка интернета через ya.ru
    Serial.println("\n[3] Проверка интернета (ya.ru)...");
    if (checkInternet(TEST_URL)) {
        Serial.println("[OK] Интернет доступен (ya.ru)");
    } else {
        Serial.println("[ERROR] Интернет НЕ ДОСТУПЕН!");
    }
    
    // 4. Проверка вашего сервера (TCP)
    Serial.println("\n[4] Проверка TCP соединения с сервером...");
    if (checkTCPServer(SERVER_IP, SERVER_PORT)) {
        Serial.printf("[OK] Сервер %s:%d доступен (TCP)\n", SERVER_IP, SERVER_PORT);
    } else {
        Serial.printf("[ERROR] Сервер %s:%d НЕ ДОСТУПЕН (TCP)!\n", SERVER_IP, SERVER_PORT);
    }
    
    // 5. Проверка HTTP запроса
    Serial.println("\n[5] Проверка HTTP запроса...");
    testHTTP();
    
    // 6. Проверка ping до сервера
    Serial.println("\n[6] Проверка ICMP ping...");
    if (pingHost(IPAddress(194, 186, 104, 79), 3000)) {
        Serial.println("[OK] Сервер отвечает на ping");
    } else {
        Serial.println("[WARN] Сервер не отвечает на ping (может быть заблокирован)");
    }
    
    Serial.println("\n═══════════════════════════════════════════");
    Serial.println("ДИАГНОСТИКА ЗАВЕРШЕНА");
    Serial.println("═══════════════════════════════════════════\n");
}

void runQuickDiagnostic() {
    // Быстрая проверка основных параметров
    Serial.printf("RSSI: %d dBm | ", WiFi.RSSI());
    
    // Проверка интернета
    if (checkInternet(TEST_URL)) {
        Serial.print("Интернет: OK | ");
    } else {
        Serial.print("Интернет: FAIL | ");
    }
    
    // Проверка сервера
    if (checkTCPServer(SERVER_IP, SERVER_PORT)) {
        Serial.printf("Сервер: OK (%s:%d)\n", SERVER_IP, SERVER_PORT);
    } else {
        Serial.printf("Сервер: FAIL (%s:%d)\n", SERVER_IP, SERVER_PORT);
    }
}

// ═══════════════════════════════════════════════════════
// ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ
// ═══════════════════════════════════════════════════════

bool pingHost(IPAddress ip, unsigned long timeout) {
    WiFiClient client;
    unsigned long start = millis();
    
    // Пытаемся соединиться с хостом
    if (client.connect(ip, 80)) {
        client.stop();
        return true;
    }
    
    // Если не получилось, пробуем еще раз через 100мс
    delay(100);
    if (client.connect(ip, 80)) {
        client.stop();
        return true;
    }
    
    return false;
}

IPAddress resolveDNS(const char* domain) {
    IPAddress ip;
    if (WiFi.hostByName(domain, ip)) {
        return ip;
    }
    return IPAddress(0, 0, 0, 0);
}

bool checkInternet(const char* url) {
    HTTPClient http;
    http.begin(url);
    http.setTimeout(3000);
    
    int httpCode = http.GET();
    http.end();
    
    return (httpCode > 0);
}

bool checkTCPServer(const char* host, int port) {
    WiFiClient client;
    if (client.connect(host, port)) {
        client.stop();
        return true;
    }
    return false;
}

void testHTTP() {
    HTTPClient http;
    http.begin(SERVER_URL);
    http.addHeader("Content-Type", "application/json");
    http.setTimeout(5000);
    
    // Тестовый запрос
    String jsonBody = "{\"machine_id\":100,\"location_id\":1,\"api_key\":\"EawbxVBa7azu65LNdfCOzXzB\",\"event_type\":\"play\"}";
    
    Serial.printf("[TEST] Отправка на %s\n", SERVER_URL);
    Serial.printf("[TEST] Тело: %s\n", jsonBody.c_str());
    
    unsigned long start = millis();
    int httpCode = http.POST(jsonBody);
    unsigned long duration = millis() - start;
    
    Serial.printf("[HTTP] Код: %d, время: %lu мс\n", httpCode, duration);
    
    if (httpCode > 0) {
        String response = http.getString();
        Serial.printf("[RESPONSE] %s\n", response.c_str());
        
        if (httpCode == 200) {
            Serial.println("[OK] HTTP запрос успешен!");
        } else {
            Serial.printf("[ERROR] HTTP ошибка: %d\n", httpCode);
        }
    } else {
        // Расшифровка ошибок
        Serial.printf("[ERROR] HTTP ошибка: %d\n", httpCode);
        switch(httpCode) {
            case -1: Serial.println("  -> Таймаут соединения"); break;
            case -2: Serial.println("  -> Не удалось подключиться"); break;
            case -3: Serial.println("  -> Ошибка отправки"); break;
            case -4: Serial.println("  -> Ошибка получения"); break;
            case -5: Serial.println("  -> Ошибка SSL/TLS"); break;
            case -6: Serial.println("  -> Ошибка парсинга URL"); break;
            default: Serial.println("  -> Неизвестная ошибка");
        }
    }
    
    http.end();
}

// ═══════════════════════════════════════════════════════
// ДОПОЛНИТЕЛЬНАЯ ФУНКЦИЯ ДЛЯ АНАЛИЗА
// ═══════════════════════════════════════════════════════

void printDiagnosticSummary() {
    Serial.println("\n═══════════════════════════════════════════");
    Serial.println("КРАТКИЙ ОТЧЕТ:");
    Serial.println("═══════════════════════════════════════════");
    
    if (WiFi.status() != WL_CONNECTED) {
        Serial.println("❌ WiFi НЕ ПОДКЛЮЧЕН");
        return;
    }
    
    Serial.println("✅ WiFi подключен");
    Serial.printf("   IP: %s\n", WiFi.localIP().toString().c_str());
    Serial.printf("   RSSI: %d dBm\n", WiFi.RSSI());
    
    // Проверка шлюза
    if (pingHost(WiFi.gatewayIP(), 2000)) {
        Serial.println("✅ Шлюз доступен");
    } else {
        Serial.println("❌ Шлюз НЕ ДОСТУПЕН!");
    }
    
    // Проверка DNS
    IPAddress dnsTest = resolveDNS("google.com");
    if (dnsTest.toString() != "0.0.0.0") {
        Serial.printf("✅ DNS работает: google.com -> %s\n", dnsTest.toString().c_str());
    } else {
        Serial.println("❌ DNS НЕ РАБОТАЕТ!");
    }
    
    // Проверка интернета
    if (checkInternet("http://google.com")) {
        Serial.println("✅ Интернет доступен");
    } else {
        Serial.println("❌ Интернет НЕ ДОСТУПЕН!");
    }
    
    // Проверка сервера
    if (checkTCPServer(SERVER_IP, SERVER_PORT)) {
        Serial.printf("✅ Сервер %s:%d доступен\n", SERVER_IP, SERVER_PORT);
    } else {
        Serial.printf("❌ Сервер %s:%d НЕ ДОСТУПЕН!\n", SERVER_IP, SERVER_PORT);
    }
    
    Serial.println("═══════════════════════════════════════════\n");
}