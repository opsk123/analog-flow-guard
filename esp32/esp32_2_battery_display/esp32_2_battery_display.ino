#include <Arduino.h>
#include <cstring>
#include "ESP32_NOW.h"
#include <LiquidCrystal_I2C.h>
#include "WiFi.h"
#include "Wire.h"

#include "config.h"
#include "protocol.h"

volatile bool packetPending = false;
portMUX_TYPE packetMux = portMUX_INITIALIZER_UNLOCKED;
StatusPacket pendingPacket = {};
DeviceState receivedState = DeviceState::PcLinkError;
bool hasRadioPacket = false;
unsigned long lastPacketMs = 0;

LiquidCrystal_I2C display(LCD_I2C_ADDRESS, LCD_COLUMNS, LCD_ROWS);

enum class DisplayState : uint8_t {
  GasNormal,
  GasLow,
  PcLinkError,
  RadioLinkError,
};

DisplayState displayedState = DisplayState::RadioLinkError;
bool displayInitialized = false;

const char *stateName(DeviceState state) {
  switch (state) {
    case DeviceState::Normal:
      return "NORMAL";
    case DeviceState::Problem:
      return "PROBLEM";
    case DeviceState::PcLinkError:
      return "PC_LINK_ERROR";
  }
  return "UNKNOWN";
}

void writeLine(uint8_t row, const char *text) {
  display.setCursor(0, row);
  uint8_t column = 0;
  while (text[column] != '\0' && column < LCD_COLUMNS) {
    display.print(text[column]);
    ++column;
  }
  while (column < LCD_COLUMNS) {
    display.print(' ');
    ++column;
  }
}

void showState(DisplayState state) {
  switch (state) {
    case DisplayState::GasNormal:
      writeLine(0, "GAS STATUS");
      writeLine(1, "NORMAL");
      break;
    case DisplayState::GasLow:
      writeLine(0, "GAS STATUS");
      writeLine(1, "LOW");
      break;
    case DisplayState::PcLinkError:
      writeLine(0, "PC LINK");
      writeLine(1, "ERROR");
      break;
    case DisplayState::RadioLinkError:
      writeLine(0, "RADIO LINK");
      writeLine(1, "ERROR");
      break;
  }

  displayedState = state;
}

bool isValidPacket(const uint8_t *data, int len, StatusPacket &packet) {
  if (len != static_cast<int>(sizeof(StatusPacket))) {
    return false;
  }

  memcpy(&packet, data, sizeof(packet));
  if (packet.magic != STATUS_PACKET_MAGIC ||
      packet.version != STATUS_PROTOCOL_VERSION) {
    return false;
  }

  return packet.state == DeviceState::Normal ||
         packet.state == DeviceState::Problem ||
         packet.state == DeviceState::PcLinkError;
}

void onMessage(const esp_now_recv_info_t *info, const uint8_t *data, int len,
               void *arg) {
  (void)info;
  (void)arg;

  StatusPacket packet;
  if (!isValidPacket(data, len, packet)) {
    return;
  }

  portENTER_CRITICAL(&packetMux);
  pendingPacket = packet;
  packetPending = true;
  portEXIT_CRITICAL(&packetMux);
}

void setup() {
  Serial.begin(115200);

  Wire.begin(LCD_SDA_PIN, LCD_SCL_PIN);
  display.init();
  display.backlight();
  displayInitialized = true;
  showState(DisplayState::RadioLinkError);

  WiFi.mode(WIFI_STA);
  WiFi.setChannel(ESPNOW_CHANNEL);
  while (!WiFi.STA.started()) {
    delay(10);
  }

  Serial.print("Unit 2 MAC: ");
  Serial.println(WiFi.macAddress());

  if (!ESP_NOW.begin()) {
    Serial.println("ESP-NOW initialization failed. Restarting...");
    delay(3000);
    ESP.restart();
  }

  ESP_NOW.onNewPeer(onMessage, nullptr);
  Serial.println("Unit 2 ready. Waiting for gas status from Unit 1.");
}

void loop() {
  StatusPacket packet;
  bool hasPacket = false;

  portENTER_CRITICAL(&packetMux);
  if (packetPending) {
    packet = pendingPacket;
    packetPending = false;
    hasPacket = true;
  }
  portEXIT_CRITICAL(&packetMux);

  const unsigned long now = millis();
  if (hasPacket) {
    receivedState = packet.state;
    lastPacketMs = now;
    hasRadioPacket = true;
    Serial.printf("RX seq=%lu state=%s\n",
                  static_cast<unsigned long>(packet.sequence),
                  stateName(packet.state));
  }

  const bool radioTimedOut =
      !hasRadioPacket || now - lastPacketMs >= RADIO_TIMEOUT_MS;
  DisplayState nextDisplayState;
  if (radioTimedOut) {
    nextDisplayState = DisplayState::RadioLinkError;
  } else if (receivedState == DeviceState::Normal) {
    nextDisplayState = DisplayState::GasNormal;
  } else if (receivedState == DeviceState::Problem) {
    nextDisplayState = DisplayState::GasLow;
  } else {
    nextDisplayState = DisplayState::PcLinkError;
  }

  if (!displayInitialized || displayedState != nextDisplayState) {
    showState(nextDisplayState);
  }

  delay(1);
}
