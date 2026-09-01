#pragma once

#include <Arduino.h>

// 1번 ESP32의 외부 LED 핀
constexpr uint8_t GREEN_LED_PIN = 26;
constexpr uint8_t RED_LED_PIN = 27;

// 2번 ESP32와 반드시 같은 채널을 사용해야 합니다.
constexpr uint8_t ESPNOW_CHANNEL = 6;

// 현재 상태를 다시 전송하는 간격입니다.
constexpr unsigned long HEARTBEAT_INTERVAL_MS = 1000;

// Python sends a serial heartbeat every 2 seconds. Missing three heartbeats is
// treated as a problem instead of silently leaving the last NORMAL state on.
constexpr unsigned long PC_COMMAND_TIMEOUT_MS = 6500;
