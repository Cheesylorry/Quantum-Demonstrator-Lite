// ============================================================================
//  Quantum Demonstrator embedded code
//
//    Copyright (C) 2026  Henry Hill, Max Planck Institute of Quantum Optics
//
//    This program is free software: you can redistribute it and/or modify
//    it under the terms of the GNU General Public License as published by
//    the Free Software Foundation, either version 3 of the License, or
//    (at your option) any later version.
//
//    This program is distributed in the hope that it will be useful,
//    but WITHOUT ANY WARRANTY; without even the implied warranty of
//    MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
//    GNU General Public License for more details.
//
//    You should have received a copy of the GNU General Public License
//    along with this program.  If not, see <https://www.gnu.org/licenses/>.
//
//
//    21 MFRC522 NFC readers connected to a Raspberry Pi Pico 2 (RP2350)
//
//    - Readers share SPI0 (SCK=18, MOSI=19, MISO=20) with one software CS each.
//    - Shared hardware RST on GPIO28; per-reader init uses SOFT reset.
//    - WS2815 on GPIO27, driven on core 1.
//
//     SPEED: the RC522's internal timeout timer is shortened from the library
//     default (~25 ms) to WUPA_TIMEOUT_US. A present tag answers in <0.2 ms regardless. HLTA is only sent when
//     a tag was actually found.
//
//      USB protocol (newline-terminated ASCII), device -> host:
//      PLACE,<pos>,<uid_hex>       REMOVE,<pos>
//
//      host -> device (single letter, optional digit, e.g. "G5", "P7"): Commands to set specific variables
//
//      R      resync: dump all occupied slots, then SYNC_DONE
//      V      re-run the SPI self-check
//      G<0-7> set receiver gain on all readers   (7 = max, default 6)
//      P<0-7> set TX driver power on all readers (7 = max, default 6)
//      (Gain set to 6 is the most stable)
// ============================================================================

#include <Arduino.h>
#include <SPI.h>
#include <MFRC522.h>
#include <FastLED.h>

#define DEBUG 1   // 0 silences all '#'-prefixed debug output

// ---------------------------------------------------------------------------
// Board size
// ---------------------------------------------------------------------------
static constexpr uint8_t  NUM_LINES        = 3;
static constexpr uint8_t  READERS_PER_LINE = 7;
static constexpr uint16_t LEDS_PER_LINE    = 32;
static constexpr uint8_t  NUM_READERS = NUM_LINES * READERS_PER_LINE;
static constexpr uint16_t NUM_LEDS    = NUM_LINES * LEDS_PER_LINE;

// ---------------------------------------------------------------------------
// Reader CS to GPIO mapping
// ---------------------------------------------------------------------------
static constexpr uint8_t CS_PINS[21] = {
  26, 22, 21, 17, 16, 15, 14,
   7,  8,  9, 10, 11, 12, 13,
   0,  1,  2,  3,  4,  5,  6
};
static constexpr uint8_t PIN_SCK    = 18;
static constexpr uint8_t PIN_MOSI   = 19;
static constexpr uint8_t PIN_MISO   = 20;
static constexpr uint8_t PIN_RST    = 28;
static constexpr uint8_t PIN_WS2815 = 27;

// ---------------------------------------------------------------------------
// Tuning
// ---------------------------------------------------------------------------
// How long to wait for USB serial at boot before continuing.
static constexpr uint32_t USB_STARTUP_DELAY_MS = 3500;

// RC522 command timeout. 
// A tag's ATQA arrives in <200 us; 2000 us leaves ample margin. If present tags ever flicker tout/OK
// in the debug line, raise this first. Then play with gain and Transmission Power
// Timer tick = 25 us (prescaler 0xA9), so resolution is 25 us.
static constexpr uint32_t WUPA_TIMEOUT_US = 2000;

// Consecutive failed wakeups before a slot is declared empty (debounce).
static constexpr uint8_t MISS_THRESHOLD = 2;

// Default RF settings, applied to all readers at boot (changeable at runtime
// with the G/P serial commands).
static constexpr uint8_t DEFAULT_RX_GAIN_LEVEL  = 6;  // 0..7 receiver gain
static constexpr uint8_t DEFAULT_TX_POWER_LEVEL = 6;  // 0..7 antenna drive

// TX power mapping: the RC522 has no single "power" register; antenna drive
// strength comes from the CWGsN (N-driver, 0..15) and CWGsP (P-driver, 0..63)
// conductance fields. Chip reset default is mid-strength (~8 / 32).
static constexpr uint8_t TX_GSN[8] = {  1,  3,  5,  7,  9, 11, 13, 15 };
static constexpr uint8_t TX_GSP[8] = {  4,  8, 14, 20, 28, 38, 50, 63 };
static constexpr uint8_t MOD_GSN   = 0x8;  // modulation-phase N conductance

// ---------------------------------------------------------------------------
// State
// ---------------------------------------------------------------------------
static MFRC522       readers[NUM_READERS];
static MFRC522::Uid  lastUid[NUM_READERS];
static bool          present[NUM_READERS]   = { false };
static uint8_t       missCount[NUM_READERS] = { 0 };
static volatile bool occupied[NUM_READERS]  = { false };
static uint8_t       rxGainLevel  = DEFAULT_RX_GAIN_LEVEL;
static uint8_t       txPowerLevel = DEFAULT_TX_POWER_LEVEL;
static CRGB          leds[NUM_LEDS];

#if DEBUG
static MFRC522::StatusCode lastStatus[NUM_READERS];
#endif

// ---------------------------------------------------------------------------
// RF configuration helpers
// ---------------------------------------------------------------------------
static void applyTimeout(MFRC522 &r) {
  // TAuto=1, prescaler 0xA9 -> 25 us ticks; reload = timeout / 25 us.
  uint16_t reload = WUPA_TIMEOUT_US / 15;
  r.PCD_WriteRegister(MFRC522::TModeReg,      0x80);
  r.PCD_WriteRegister(MFRC522::TPrescalerReg, 0xA9);
  r.PCD_WriteRegister(MFRC522::TReloadRegH,   reload >> 8);
  r.PCD_WriteRegister(MFRC522::TReloadRegL,   reload & 0xFF);
}

static void applyRxGain(MFRC522 &r, uint8_t level) {
  r.PCD_SetAntennaGain((level & 0x07) << 4);
}

static void applyTxPower(MFRC522 &r, uint8_t level) {
  level &= 0x07;
  r.PCD_WriteRegister(MFRC522::GsNReg,   (TX_GSN[level] << 4) | MOD_GSN);
  r.PCD_WriteRegister(MFRC522::CWGsPReg, TX_GSP[level]);
}

static void applyRfToAll() {
  for (uint8_t i = 0; i < NUM_READERS; i++) {
    applyRxGain(readers[i], rxGainLevel);
    applyTxPower(readers[i], txPowerLevel);
  }
}

// ---------------------------------------------------------------------------
// Output helpers
// ---------------------------------------------------------------------------
static bool uidEqual(const MFRC522::Uid &a, const MFRC522::Uid &b) {
  return a.size == b.size && memcmp(a.uidByte, b.uidByte, a.size) == 0;
}

static void printUid(const MFRC522::Uid &uid) {
  for (uint8_t k = 0; k < uid.size; k++) {
    if (uid.uidByte[k] < 0x10) Serial.print('0');
    Serial.print(uid.uidByte[k], HEX);
  }
}

static void emitPlace(uint8_t pos, const MFRC522::Uid &uid) {
  Serial.print(F("PLACE,")); Serial.print(pos); Serial.print(',');
  printUid(uid); Serial.println();
}

static void emitRemove(uint8_t pos) {
  Serial.print(F("REMOVE,")); Serial.println(pos);
}

#if DEBUG
static const char* shortStatus(MFRC522::StatusCode s) {
  switch (s) {
    case MFRC522::STATUS_OK:        return "OK";
    case MFRC522::STATUS_COLLISION: return "COLL";
    case MFRC522::STATUS_TIMEOUT:   return "tout";
    case MFRC522::STATUS_ERROR:     return "ERR";
    case MFRC522::STATUS_CRC_WRONG: return "CRC";
    default:                        return "?";
  }
}

static void printSelfCheck() {
  Serial.println(F("# --- reader self-check (VersionReg) ---"));
  for (uint8_t i = 0; i < NUM_READERS; i++) {
    byte v = readers[i].PCD_ReadRegister(MFRC522::VersionReg);
    Serial.print(F("# r"));  Serial.print(i);
    Serial.print(F(" cs=")); Serial.print(CS_PINS[i]);
    Serial.print(F(" ver=0x"));
    if (v < 0x10) Serial.print('0');
    Serial.print(v, HEX);
    Serial.println((v != 0x00 && v != 0xFF)
        ? F("  OK - SPI comms good")
        : F("  *** NO RESPONSE: check power / CS pin / SPI wiring ***"));
  }
  Serial.print(F("# gain=")); Serial.print(rxGainLevel);
  Serial.print(F(" power=")); Serial.print(txPowerLevel);
  Serial.print(F(" timeout_us=")); Serial.println(WUPA_TIMEOUT_US);
  Serial.println(F("# --- end self-check ('V' repeats, 'G<0-7>' gain, 'P<0-7>' power) ---"));
}
#endif

// ---------------------------------------------------------------------------
// Polling
// ---------------------------------------------------------------------------
static bool pollReader(uint8_t i, MFRC522::Uid &out) {
  MFRC522 &r = readers[i];

  byte atqa[2];
  byte atqaLen = sizeof(atqa);
  MFRC522::StatusCode s = r.PICC_WakeupA(atqa, &atqaLen);
#if DEBUG
  lastStatus[i] = s;
#endif

  if (s != MFRC522::STATUS_OK && s != MFRC522::STATUS_COLLISION)
    return false;                    // empty pad: no HLTA needed, exit fast

  bool found = false;
  if (r.PICC_ReadCardSerial()) {     // anticollision + SELECT
    out   = r.uid;
    found = true;
  }
  r.PICC_HaltA();                    // only halt when something answered
  return found;
}

// ---------------------------------------------------------------------------
// Serial commands: single letter + optional decimal digit (e.g. "G5")
// ---------------------------------------------------------------------------
static void handleSerial() {
  while (Serial.available()) {
    int c = Serial.read();
    switch (c) {
      case 'R': case 'r':
        for (uint8_t i = 0; i < NUM_READERS; i++)
          if (present[i]) emitPlace(i, lastUid[i]);
        Serial.println(F("SYNC_DONE"));
        break;

      case 'G': case 'g':
      case 'P': case 'p': {
        // Wait briefly for the digit to arrive after the letter.
        uint32_t t0 = millis();
        while (!Serial.available() && millis() - t0 < 100) {}
        int d = Serial.peek();
        if (d >= '0' && d <= '7') {
          Serial.read();
          uint8_t lvl = d - '0';
          if (c == 'G' || c == 'g') rxGainLevel  = lvl;
          else                      txPowerLevel = lvl;
          applyRfToAll();
          Serial.print(F("# set ")); Serial.print((char)toupper(c));
          Serial.print('='); Serial.println(lvl);
        }
        break;
      }

#if DEBUG
      case 'V': case 'v':
        printSelfCheck();
        break;
#endif
      default: break;   // ignore CR/LF and unknown bytes
    }
  }
}

// ---------------------------------------------------------------------------
// Core 0 Readers
// ---------------------------------------------------------------------------
void setup() {
  Serial.begin(115200);
  delay(3500);
  Serial.println("Start");
  // USB startup delay: wait for the host to open the port, up to 3.5 s,
  // so boot output (self-check) is visible in a freshly opened monitor.
  uint32_t t0 = millis();
  while (!Serial && millis() - t0 < USB_STARTUP_DELAY_MS) delay(10);

  SPI.setSCK(PIN_SCK);
  SPI.setTX(PIN_MOSI);
  SPI.setRX(PIN_MISO);
  SPI.begin();

  // One hardware reset for the whole bank (RST is shared).
  pinMode(PIN_RST, OUTPUT);
  digitalWrite(PIN_RST, LOW);
  delay(5);
  digitalWrite(PIN_RST, HIGH);
  delay(50);

  for (uint8_t i = 0; i < NUM_READERS; i++) {
    readers[i].PCD_Init(CS_PINS[i], MFRC522::UNUSED_PIN);  // soft reset only
    applyTimeout(readers[i]);       // fast (2 ms) command timeout
  }
  applyRfToAll();                   // gain + TX power defaults

#if DEBUG
  printSelfCheck();
#endif
}

void loop() {
  handleSerial();

  for (uint8_t i = 0; i < NUM_READERS; i++) {
    MFRC522::Uid uid;
    if (pollReader(i, uid)) {
      missCount[i] = 0;
      if (!present[i] || !uidEqual(uid, lastUid[i])) {
        present[i]  = true;
        occupied[i] = true;
        lastUid[i]  = uid;
        emitPlace(i, uid);
      }
    } else if (present[i]) {
      if (++missCount[i] >= MISS_THRESHOLD) {
        present[i]  = false;
        occupied[i] = false;
        emitRemove(i);
      }
    }
  }

#if DEBUG
  static uint32_t lastDbg = 0;
  if (millis() - lastDbg >= 1000) {
    lastDbg = millis();
    Serial.print(F("# wupa:"));
    for (uint8_t i = 0; i < NUM_READERS; i++) {
      Serial.print(F(" r")); Serial.print(i);
      Serial.print('=');     Serial.print(shortStatus(lastStatus[i]));
    }
    Serial.println();
  }
#endif
}

// ---------------------------------------------------------------------------
// Core 1 : LEDs
// ---------------------------------------------------------------------------

// ---------------------------------------------------------------------------
// Manual LED mapping: exactly which LED indices light up for each reader position. 
// ---------------------------------------------------------------------------
static const uint16_t READER_LEDS_14[] = {  1,  2,  3};
static const uint16_t READER_LEDS_15[] = {  4,  5,  6,  7,  8, 9};
static const uint16_t READER_LEDS_16[] = {  9, 10, 11, 12, 13};
static const uint16_t READER_LEDS_17[] = { 14, 15, 16, 17,  };
static const uint16_t READER_LEDS_18[] = { 18, 19, 20, 21, 22 };
static const uint16_t READER_LEDS_19[] = { 23, 24, 25, 26, 27 };
static const uint16_t READER_LEDS_20[] = { 28, 29, 30};
static const uint16_t READER_LEDS_7[] = { 31, 32, 33, 34};
static const uint16_t READER_LEDS_8[] = {  35,  36,  37,  38,  39};
static const uint16_t READER_LEDS_9[] = {  40, 41, 42, 43};
static const uint16_t READER_LEDS_10[] = { 45, 46, 47, 48 };
static const uint16_t READER_LEDS_11[] = { 50, 51, 52, 53 };
static const uint16_t READER_LEDS_12[] = { 55, 56, 57, 58 };
static const uint16_t READER_LEDS_13[] = { 59, 60};
static const uint16_t READER_LEDS_0[] = { 89, 90, 91};
static const uint16_t READER_LEDS_1[] = { 86, 87, 89 };
static const uint16_t READER_LEDS_2[] = { 81, 82, 83, 84 };
static const uint16_t READER_LEDS_3[] = { 76, 77, 78, 79 };
static const uint16_t READER_LEDS_4[] = { 71, 72, 73, 74};
static const uint16_t READER_LEDS_5[] = { 66,  67,  68,  69,  70};
static const uint16_t READER_LEDS_6[] = { 62, 63, 64, 65};

struct LedMap { const uint16_t *leds; uint8_t count; };

// Row i here = reader position i. Keep this in sync with NUM_READERS.
static const LedMap READER_LED_MAP[NUM_READERS] = {
  { READER_LEDS_0, sizeof(READER_LEDS_0) / sizeof(uint16_t) },
  { READER_LEDS_1, sizeof(READER_LEDS_1) / sizeof(uint16_t) },
  { READER_LEDS_2, sizeof(READER_LEDS_2) / sizeof(uint16_t) },
  { READER_LEDS_3, sizeof(READER_LEDS_3) / sizeof(uint16_t) },
  { READER_LEDS_4, sizeof(READER_LEDS_4) / sizeof(uint16_t) },
  { READER_LEDS_5, sizeof(READER_LEDS_5) / sizeof(uint16_t) },
  { READER_LEDS_6, sizeof(READER_LEDS_6) / sizeof(uint16_t) },
  { READER_LEDS_7, sizeof(READER_LEDS_7) / sizeof(uint16_t) },
  { READER_LEDS_8, sizeof(READER_LEDS_8) / sizeof(uint16_t) },
  { READER_LEDS_9, sizeof(READER_LEDS_9) / sizeof(uint16_t) },
  { READER_LEDS_10, sizeof(READER_LEDS_10) / sizeof(uint16_t) },
  { READER_LEDS_11, sizeof(READER_LEDS_11) / sizeof(uint16_t) },
  { READER_LEDS_12, sizeof(READER_LEDS_12) / sizeof(uint16_t) },
  { READER_LEDS_13, sizeof(READER_LEDS_13) / sizeof(uint16_t) },
  { READER_LEDS_14, sizeof(READER_LEDS_14) / sizeof(uint16_t) },
  { READER_LEDS_15, sizeof(READER_LEDS_15) / sizeof(uint16_t) },
  { READER_LEDS_16, sizeof(READER_LEDS_16) / sizeof(uint16_t) },
  { READER_LEDS_17, sizeof(READER_LEDS_17) / sizeof(uint16_t) },
  { READER_LEDS_18, sizeof(READER_LEDS_18) / sizeof(uint16_t) },
  { READER_LEDS_19, sizeof(READER_LEDS_19) / sizeof(uint16_t) },
  { READER_LEDS_20, sizeof(READER_LEDS_20) / sizeof(uint16_t) },
};

static void paintReader(uint8_t i, const CRGB &c) {
  if (i >= NUM_READERS) return;
  const LedMap &m = READER_LED_MAP[i];
  for (uint8_t k = 0; k < m.count; k++) {
    uint16_t l = m.leds[k];
    if (l < NUM_LEDS) leds[l] = c;
  }
}

void setup1() {
  FastLED.addLeds<WS2815, PIN_WS2815, GRB>(leds, NUM_LEDS);
  FastLED.setBrightness(250);
}

void loop1() {
  for (uint8_t i = 0; i < NUM_READERS; i++)
    paintReader(i, occupied[i] ? CRGB(0, 180, 60) : CRGB(20, 20, 20));
  FastLED.show();
  delay(25);
}