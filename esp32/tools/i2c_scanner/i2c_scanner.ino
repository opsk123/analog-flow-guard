#include <Arduino.h>
#include <Wire.h>

constexpr uint8_t I2C_SDA_PIN = 21;
constexpr uint8_t I2C_SCL_PIN = 22;

void setup() {
  Serial.begin(115200);
  delay(500);

  Wire.begin(I2C_SDA_PIN, I2C_SCL_PIN);
  Serial.println();
  Serial.println("I2C scanner started");
  Serial.printf("SDA=%u, SCL=%u\n", I2C_SDA_PIN, I2C_SCL_PIN);
}

void loop() {
  uint8_t foundCount = 0;
  Serial.println("Scanning...");

  for (uint8_t address = 1; address < 127; ++address) {
    Wire.beginTransmission(address);
    const uint8_t error = Wire.endTransmission();

    if (error == 0) {
      Serial.printf("I2C device found at 0x%02X\n", address);
      ++foundCount;
    }
  }

  if (foundCount == 0) {
    Serial.println("No I2C device found");
  } else {
    Serial.printf("Scan complete: %u device(s)\n", foundCount);
  }

  Serial.println();
  delay(3000);
}

