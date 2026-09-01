#pragma once

#include <Arduino.h>

constexpr uint32_t STATUS_PACKET_MAGIC = 0x47534153;
constexpr uint8_t STATUS_PROTOCOL_VERSION = 1;

enum class DeviceState : uint8_t {
  Normal = 0,
  Problem = 1,
  PcLinkError = 2,
};

struct __attribute__((packed)) StatusPacket {
  uint32_t magic;
  uint8_t version;
  DeviceState state;
  uint32_t sequence;
};

static_assert(sizeof(StatusPacket) == 10, "Unexpected StatusPacket size");
