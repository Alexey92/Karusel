// Простейшая программа для ESP32
// Генерация импульсов отрицательной полярности
// Пины: D13, D12, D14

void setup() {
  pinMode(13, OUTPUT);
  pinMode(12, OUTPUT);
  pinMode(14, OUTPUT);
  
  // Начальное состояние - HIGH (3.3V)
  digitalWrite(13, HIGH);
  digitalWrite(12, HIGH);
  digitalWrite(14, HIGH);
}

void loop() {
  // ===== D13: 4 импульса по 40 мс, пауза 5 мс =====
  for (int i = 0; i < 4; i++) {
    digitalWrite(13, LOW);   // импульс
    delay(40);
    digitalWrite(13, HIGH);  // пауза
    delay(5);
  }
  
  // ===== D12: 5 импульсов по 70 мс, пауза 10 мс =====
  for (int i = 0; i < 5; i++) {
    digitalWrite(12, LOW);   // импульс
    delay(70);
    digitalWrite(12, HIGH);  // пауза
    delay(10);
  }
  
  // ===== D14: 3 импульса по 35 мс, пауза 2 мс =====
  for (int i = 0; i < 3; i++) {
    digitalWrite(14, LOW);   // импульс
    delay(35);
    digitalWrite(14, HIGH);  // пауза
    delay(2);
  }
  
  // Пауза 10 секунд перед повторением
  delay(10000);
}