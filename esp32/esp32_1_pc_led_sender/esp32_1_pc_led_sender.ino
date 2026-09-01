#include <Arduino.h>
#include "ESP32_NOW.h"
#include "WiFi.h"

#include "config.h"
#include "protocol.h"

class BroadcastPeer : public ESP_NOW_Peer {
 public:
  BroadcastPeer()
      : ESP_NOW_Peer(ESP_NOW.BROADCAST_ADDR, ESPNOW_CHANNEL, WIFI_IF_STA,
                     nullptr) {}

  bool begin() {
    return ESP_NOW.begin() && add();
  }

  bool sendPacket(const StatusPacket &packet) {
    return send(reinterpret_cast<const uint8_t *>(&packet), sizeof(packet)) ==
           sizeof(packet);
  }

  void onSent(bool success) override {
    lastSendSucceeded = success;
  }

  volatile bool lastSendSucceeded = false;
};

BroadcastPeer unit2;
DeviceState currentState = DeviceState::PcLinkError;
String inputLine;
uint32_t sequenceNumber = 0;
unsigned long lastHeartbeatMs = 0;
unsigned long lastPcCommandMs = 0;
bool hasPcCommand = false;
bool sendImmediately = true;

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

void applyState(DeviceState state) {
  const bool changed = state != currentState;
  currentState = state;
  if (state == DeviceState::Normal) {
    digitalWrite(GREEN_LED_PIN, HIGH);
    digitalWrite(RED_LED_PIN, LOW);
  } else {
    digitalWrite(GREEN_LED_PIN, LOW);
    digitalWrite(RED_LED_PIN, HIGH);
  }
  sendImmediately = sendImmediately || changed;

  if (changed) {
    Serial.print("STATE=");
    Serial.println(stateName(state));
  }
}

void markPcCommandReceived() {
  hasPcCommand = true;
  lastPcCommandMs = millis();
}

void sendCurrentState() {
  const StatusPacket packet = {
      STATUS_PACKET_MAGIC,
      STATUS_PROTOCOL_VERSION,
      currentState,
      sequenceNumber++,
  };

  const bool queued = unit2.sendPacket(packet);
  Serial.printf("TX %s seq=%lu state=%s\n", queued ? "OK" : "FAIL",
                static_cast<unsigned long>(packet.sequence),
                stateName(packet.state));
}

void printHelp() {
  Serial.println();
  Serial.println("Commands:");
  Serial.println("  ALARM  or 1 : red LED ON, send PROBLEM");
  Serial.println("  NORMAL or 0 : green LED ON, send NORMAL");
  Serial.println("  STATUS or ? : print current state");
  Serial.println("  HELP        : print this help");
}

void handleCommand(String command) {
  command.trim();
  command.toUpperCase();

  if (command == "ALARM" || command == "1") {
    markPcCommandReceived();
    applyState(DeviceState::Problem);
  } else if (command == "NORMAL" || command == "0") {
    markPcCommandReceived();
    applyState(DeviceState::Normal);
  } else if (command == "STATUS" || command == "?") {
    Serial.printf("STATE=%s, LAST_RADIO_RESULT=%s\n", stateName(currentState),
                  unit2.lastSendSucceeded ? "SUCCESS" : "UNKNOWN/FAIL");
  } else if (command == "HELP") {
    printHelp();
  } else if (command.length() > 0) {
    Serial.print("Unknown command: ");
    Serial.println(command);
    printHelp();
  }
}

void setup() {
  Serial.begin(115200);

  pinMode(GREEN_LED_PIN, OUTPUT);
  pinMode(RED_LED_PIN, OUTPUT);
  inputLine.reserve(32);
  // Stay in a visible problem state until the Python monitor sends its first
  // valid NORMAL or ALARM command.
  digitalWrite(GREEN_LED_PIN, LOW);
  digitalWrite(RED_LED_PIN, HIGH);
  Serial.println("STATE=PC_LINK_ERROR");

  WiFi.mode(WIFI_STA);
  WiFi.setChannel(ESPNOW_CHANNEL);
  while (!WiFi.STA.started()) {
    delay(10);
  }

  Serial.print("Unit 1 MAC: ");
  Serial.println(WiFi.macAddress());

  if (!unit2.begin()) {
    Serial.println("ESP-NOW initialization failed. Restarting...");
    delay(3000);
    ESP.restart();
  }

  printHelp();
}

void loop() {
  while (Serial.available() > 0) {
    const char received = static_cast<char>(Serial.read());

    if (received == '\n' || received == '\r') {
      if (inputLine.length() > 0) {
        handleCommand(inputLine);
        inputLine = "";
      }
    } else if (inputLine.length() < 31) {
      inputLine += received;
    }
  }

  const unsigned long now = millis();
  if ((!hasPcCommand || now - lastPcCommandMs >= PC_COMMAND_TIMEOUT_MS) &&
      currentState != DeviceState::PcLinkError) {
    applyState(DeviceState::PcLinkError);
  }

  if (sendImmediately || now - lastHeartbeatMs >= HEARTBEAT_INTERVAL_MS) {
    sendImmediately = false;
    lastHeartbeatMs = now;
    sendCurrentState();
  }

  delay(1);
}
