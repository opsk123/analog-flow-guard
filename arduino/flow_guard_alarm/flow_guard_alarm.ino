#include <Arduino.h>
#include <WiFi.h>

void setup() {
  Serial.begin(115200);
  delay(1200);

  WiFi.mode(WIFI_STA);

  const uint64_t chipId = ESP.getEfuseMac();

  Serial.println();
  Serial.println("=== ESP32 board check ===");
  Serial.printf("Chip model     : %s\n", ESP.getChipModel());
  Serial.printf("Chip revision  : %u\n", ESP.getChipRevision());
  Serial.printf("CPU cores      : %u\n", ESP.getChipCores());
  Serial.printf("CPU frequency  : %u MHz\n", ESP.getCpuFreqMHz());
  Serial.printf("Flash size     : %u bytes\n", ESP.getFlashChipSize());
  Serial.printf("WiFi STA MAC   : %s\n", WiFi.macAddress().c_str());
  Serial.printf("Sketch size    : %u bytes\n", ESP.getSketchSize());
  Serial.printf("Free heap      : %u bytes\n", ESP.getFreeHeap());
  Serial.printf("Chip ID        : %04X%08X\n",
                static_cast<uint16_t>(chipId >> 32),
                static_cast<uint32_t>(chipId));
  Serial.println("Board check complete.");
}

void loop() {
  static uint32_t lastHeartbeat = 0;
  if (millis() - lastHeartbeat >= 2000) {
    lastHeartbeat = millis();
    Serial.printf("alive: %lu ms\n", static_cast<unsigned long>(millis()));
  }
}
