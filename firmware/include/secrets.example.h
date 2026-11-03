#pragma once
// Copy to include/secrets.h (gitignored) and fill in per node from ChirpStack.
// Every node MUST have its own unique AppKey. Never commit real keys.

#define NODE_JOIN_EUI 0x0000000000000000ULL
#define NODE_DEV_EUI  0x0000000000000000ULL

// LoRaWAN 1.0.x: AppKey only (NwkKey = AppKey). MSB first, as shown in ChirpStack.
#define NODE_APP_KEY { 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, \
                       0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00 }
