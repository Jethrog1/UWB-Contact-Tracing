/*
TAG CODE BLE
Tag Name + Distances from A0, A1, A2, A3
*/

#define UWB_INDEX 2
#define TAG
#define UWB_TAG_COUNT 3
#define ANCHOR_COUNT 4

#include <Wire.h>
#include <Adafruit_GFX.h>
#include <Adafruit_SSD1306.h>
#include <Arduino.h>
#include <NimBLEDevice.h>

#define SERIAL_LOG Serial
HardwareSerial SERIAL_AT(2);

// ESP32S3 pins
#define RESET 16
#define IO_RXD2 18
#define IO_TXD2 17
#define I2C_SDA 39
#define I2C_SCL 38

Adafruit_SSD1306 display(128, 64, &Wire, -1);

NimBLECharacteristic *pCharacteristic;

static const float CM_TO_FT = 1.0f / 30.48f;

//Linear Calibration
static const float CAL_SLOPE     = 0.7514969f;
static const float CAL_OFFSET_FT = 0.0295246f;

// Smoothing
static const float EMA_ALPHA_MOVE   = 0.95f;
static const float EMA_ALPHA_STILL  = 0.12f;
static const float STILL_BAND_FT    = 0.15f;
static const float SNAP_BIG_MOVE_FT = 2.0f;
static const float MAX_JUMP_FT      = 80.0f;

// Validity
static const float MIN_VALID_FT = 0.50f;
static const unsigned long STALE_MS = 2000;

// Rates
static const unsigned long POLL_MS = 200;
static const unsigned long OLED_MS = 80;

// State
static String lineBuf;
static unsigned long lastUiMs = 0;
static float smooth_ft[ANCHOR_COUNT];
static bool have_val[ANCHOR_COUNT];
static unsigned long lastSeenMs[ANCHOR_COUNT];

// Calibration
static float apply_cal_ft(float measured_ft) {
  return (CAL_SLOPE * measured_ft) + CAL_OFFSET_FT;
}

// Polynomial correction AFTER smoothing
static float apply_poly_correction(float x) {

  float result;

  if (x < 21.3f) {
    // Original polynomial
    result =
        (((0.0000727f * x
        - 0.00325f) * x
        + 0.0496f) * x
        + 0.992f) * x
        - 0.853f;
  } else {
    // Past 21.3 ft after smoothing. Calibrated upto 200 ft +/- 1 ft error
    result =
        (((0.000000146f * x
        - 0.0000273f) * x
        + 0.00176f) * x
        + 1.26f) * x
        - 1.25f;
  }

  if (result < 0.0f) result = 0.0f;

  return result;
}

static float smooth_update_ft(float x, float prev) {
  if (prev < 0.0f) return x;
  float diff = fabsf(x - prev);
  if (diff > SNAP_BIG_MOVE_FT) return x;
  float a = (diff <= STILL_BAND_FT) ? EMA_ALPHA_STILL : EMA_ALPHA_MOVE;
  return a * x + (1.0f - a) * prev;
}

static bool parse_range_vector_cm(const String &s, long outCm[], int count) {
  int p = s.indexOf("range:(");
  if (p < 0) return false;
  p += 7;
  int end = s.indexOf(')', p);
  if (end < 0) return false;

  int idx = 0;
  int i = p;
  while (i < end && idx < count) {
    while (i < end && (s[i] == ' ' || s[i] == ',')) i++;
    if (i >= end) break;

    int j = i;
    if (s[j] == '+' || s[j] == '-') j++;
    bool hasDigit = false;
    while (j < end && isDigit(s[j])) { hasDigit = true; j++; }

    if (!hasDigit) {
      while (j < end && s[j] != ',') j++;
      i = j;
      continue;
    }

    long v = s.substring(i, j).toInt();
    outCm[idx++] = v;
    i = j;
    while (i < end && s[i] != ',') i++;
    if (i < end && s[i] == ',') i++;
  }

  while (idx < count) outCm[idx++] = -1;
  return true;
}

// UI & BLE
static void drawUI_and_Broadcast() {
  display.clearDisplay();
  display.setTextColor(SSD1306_WHITE);
  display.setTextSize(1);
  display.setCursor(0, 0);

  String tagID = "T" + String(UWB_INDEX);
  display.println(tagID);

  String bleMsg = tagID + " | ";

  for (int i = 0; i < ANCHOR_COUNT; i++) {
    display.setCursor(0, 12 + i * 13);
    display.print("A");
    display.print(i);
    display.print(": ");

    bleMsg += "A" + String(i) + ":";

    if (!have_val[i] || smooth_ft[i] < 0.0f) {
      display.print("---");
      bleMsg += "---";
    } else {
      float final_ft = apply_poly_correction(smooth_ft[i]);

      display.print(final_ft, 2);
      display.print(" ft");

      char buf[8];
      snprintf(buf, sizeof(buf), "%.2f", final_ft);
      bleMsg += String(buf);
    }

    if (i < ANCHOR_COUNT - 1) bleMsg += " | ";
  }

  display.display();

  if (pCharacteristic) {
    pCharacteristic->setValue(bleMsg.c_str());
    pCharacteristic->notify();
  }
}

static void clearStale() {
  unsigned long now = millis();
  for (int i = 0; i < ANCHOR_COUNT; i++) {
    if (have_val[i] && (now - lastSeenMs[i] > STALE_MS)) {
      have_val[i] = false;
      smooth_ft[i] = -1.0f;
    }
  }
}

static void handleLine(String line) {
  line.trim();
  if (line.length() == 0) return;

  long cm[ANCHOR_COUNT];
  if (!parse_range_vector_cm(line, cm, ANCHOR_COUNT)) return;

  unsigned long now = millis();

  for (int i = 0; i < ANCHOR_COUNT; i++) {
    if (cm[i] <= 0) continue;

    float measured_ft = (float)cm[i] * CM_TO_FT;
    float cal_ft = apply_cal_ft(measured_ft);

    if (cal_ft < MIN_VALID_FT) continue;
    if (have_val[i] && fabsf(cal_ft - smooth_ft[i]) > MAX_JUMP_FT) continue;

    smooth_ft[i] = smooth_update_ft(cal_ft, smooth_ft[i]);
    have_val[i] = true;
    lastSeenMs[i] = now;
  }

  clearStale();

  if (millis() - lastUiMs >= OLED_MS) {
    lastUiMs = millis();
    drawUI_and_Broadcast();
  }
}

static String sendData(const String &command, int timeoutMs, bool debug) {
  String response = "";
  SERIAL_LOG.println(command);
  SERIAL_AT.println(command);

  unsigned long t0 = millis();
  while (millis() - t0 < (unsigned long)timeoutMs) {
    while (SERIAL_AT.available())
      response += (char)SERIAL_AT.read();
    yield();
  }

  if (debug) SERIAL_LOG.println(response);
  return response;
}

static String config_cmd() {
  String s = "AT+SETCFG=";
  s += UWB_INDEX;
  s += ",0,1,1";
  return s;
}

static String cap_cmd() {
  String s = "AT+SETCAP=";
  s += UWB_TAG_COUNT;
  s += ",10,1";
  return s;
}

void setup() {
  pinMode(RESET, OUTPUT);
  digitalWrite(RESET, HIGH);

  SERIAL_LOG.begin(115200);
  SERIAL_AT.begin(115200, SERIAL_8N1, IO_RXD2, IO_TXD2);
  Wire.begin(I2C_SDA, I2C_SCL);
  delay(300);

  if (!display.begin(SSD1306_SWITCHCAPVCC, 0x3C)) {
    while (1) delay(10);
  }

  String deviceName = "UWB_TAG_" + String(UWB_INDEX);
  NimBLEDevice::init(deviceName.c_str());
  NimBLEServer *pServer = NimBLEDevice::createServer();
  NimBLEService *pService = pServer->createService("DEADBEEF-0000-0000-0000-000000000000");
  pCharacteristic = pService->createCharacteristic(
                      "DEADBEEF-0000-0000-0000-000000000001",
                      NIMBLE_PROPERTY::READ | NIMBLE_PROPERTY::NOTIFY
                    );
  pService->start();

  NimBLEAdvertising *pAdvertising = NimBLEDevice::getAdvertising();
  pAdvertising->addServiceUUID(pService->getUUID());
  pAdvertising->start();

  lineBuf.reserve(420);

  for (int i = 0; i < ANCHOR_COUNT; i++) {
    smooth_ft[i] = -1.0f;
    have_val[i] = false;
    lastSeenMs[i] = 0;
  }

  drawUI_and_Broadcast();

  sendData("AT?", 1500, 1);
  sendData("AT+RESTORE", 5000, 1);
  sendData(config_cmd(), 2000, 1);
  sendData(cap_cmd(), 2000, 1);
  sendData("AT+SETRPT=1", 2000, 1);
  sendData("AT+SAVE", 2000, 1);
  sendData("AT+RESTART", 2000, 1);
  delay(2000);
  sendData("AT+SETRPT=1", 2000, 1);
}

void loop() {
  static unsigned long lastPoll = 0;

  if (millis() - lastPoll >= POLL_MS) {
    lastPoll = millis();
    SERIAL_AT.println("AT+RANGE");
  }

  while (SERIAL_AT.available()) {
    char c = (char)SERIAL_AT.read();
    if (c == '\r') continue;

    if (c == '\n') {
      String line = lineBuf;
      lineBuf = "";
      handleLine(line);
    } else {
      lineBuf += c;
      if (lineBuf.length() > 600) lineBuf.remove(0, 300);
    }
  }

  while (SERIAL_LOG.available()) {
    SERIAL_AT.write(SERIAL_LOG.read());
    yield();
  }
}