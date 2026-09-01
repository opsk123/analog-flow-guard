#pragma once

#include <Arduino.h>

// Unit 2 alarm outputs. Use a current-limiting resistor with the LED.
constexpr uint8_t ALARM_LED_PIN = 27;
constexpr uint8_t BUZZER_PIN = 25;

// Set false when using a buzzer module that sounds on LOW.
constexpr bool BUZZER_ACTIVE_HIGH = true;

// Must match the ESP-NOW channel configured on Unit 1.
constexpr uint8_t ESPNOW_CHANNEL = 6;

// Unit 1 broadcasts once per second. Missing packets is treated as an alarm.
constexpr unsigned long RADIO_TIMEOUT_MS = 3500;
