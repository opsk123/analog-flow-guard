#pragma once

#include <Arduino.h>

// 1602A LCD with a 4-pin PCF8574 I2C backpack.
constexpr uint8_t LCD_SDA_PIN = 21;
constexpr uint8_t LCD_SCL_PIN = 22;
constexpr uint8_t LCD_I2C_ADDRESS = 0x3F;
constexpr uint8_t LCD_COLUMNS = 16;
constexpr uint8_t LCD_ROWS = 2;

// Must match the ESP-NOW channel configured on Unit 1.
constexpr uint8_t ESPNOW_CHANNEL = 6;

// Unit 1 broadcasts once per second. Missing packets is treated as an alarm.
constexpr unsigned long RADIO_TIMEOUT_MS = 3500;
