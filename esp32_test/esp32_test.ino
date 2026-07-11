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


// ═══════════════════════════════════════════════════════
// НАСТРОЙКИ
// ═══════════════════════════════════════════════════════
const int WIN_PIN = 13;
const int PLAY_PIN = 14;




// ═══════════════════════════════════════════════════════
// SETUP
// ═══════════════════════════════════════════════════════
void setup() {
  Serial.begin(115200);

  // Задержка для стабилизации питания
  Serial.println("\n......................");

  digitalWrite(WIN_PIN, HIGH);
  digitalWrite(PLAY_PIN, HIGH);
  pinMode(WIN_PIN, OUTPUT);
  pinMode(PLAY_PIN, OUTPUT);
  


 delay(50);
 digitalWrite(PLAY_PIN, LOW);
 delay(50);
 digitalWrite(PLAY_PIN, HIGH);

 delay(40);
 digitalWrite(PLAY_PIN, LOW);
 delay(40);
 digitalWrite(PLAY_PIN, HIGH);

 delay(90);
 digitalWrite(PLAY_PIN, LOW);
 delay(90);
 digitalWrite(PLAY_PIN, HIGH);

 delay(20);
 digitalWrite(PLAY_PIN, LOW);
 delay(20);
 digitalWrite(PLAY_PIN, HIGH);

 delay(40);
 digitalWrite(WIN_PIN, LOW);
 delay(40);
 digitalWrite(WIN_PIN, HIGH);
}

// ═══════════════════════════════════════════════════════
// LOOP
// ═══════════════════════════════════════════════════════

void loop() {



  delay(1000);
}


