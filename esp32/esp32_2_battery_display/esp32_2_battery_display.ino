#include <Arduino.h>
#include <cstring>
#include "ESP32_NOW.h"
#include "WiFi.h"

#include "config.h"
#include "protocol.h"

volatile bool packetPending = false;
portMUX_TYPE packetMux = portMUX_INITIALIZER_UNLOCKED;
StatusPacket pendingPacket = {};
DeviceState receivedState = DeviceState::PcLinkError;
bool hasRadioPacket = false;
bool alarmOutputOn = false;
unsigned long lastPacketMs = 0;

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

void setAlarmOutputs(bool on) {
  alarmOutputOn = on;
  digitalWrite(ALARM_LED_PIN, on ? HIGH : LOW);
  const uint8_t buzzerOn = BUZZER_ACTIVE_HIGH ? HIGH : LOW;
  digitalWrite(BUZZER_PIN, on ? buzzerOn : !buzzerOn);
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
  pinMode(ALARM_LED_PIN, OUTPUT);
  pinMode(BUZZER_PIN, OUTPUT);
  setAlarmOutputs(false);

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
  Serial.println("Unit 2 ready. Alarm outputs are OFF until a problem arrives.");
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
  const bool alarmActive =
      radioTimedOut || receivedState != DeviceState::Normal;

  // Keep the alarm indicator steady. Repeated blinking is intentionally
  // avoided so that NORMAL and PROBLEM are shown as stable states.
  if (alarmOutputOn != alarmActive) {
    setAlarmOutputs(alarmActive);
  }

  delay(1);
}
