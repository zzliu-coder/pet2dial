#include <Arduino.h>
#include <ArduinoJson.h>
#include <BLE2902.h>
#include <BLEDevice.h>
#include <BLEServer.h>
#include <BLEUtils.h>
#include <math.h>
#include <U8g2lib.h>
#include <Arduino_GFX_Library.h>
#include <esp_heap_caps.h>
#include <memory>
#include <Wire.h>
#include "Arduino_DriveBus_Library.h"

#include "pet_frames.h"

static const char *DEVICE_NAME = "CodexDial";
static const char *SERVICE_UUID = "c0de0001-d1a1-4f6f-9b7c-5e55c0de0001";
static const char *STATE_CHAR_UUID = "c0de0002-d1a1-4f6f-9b7c-5e55c0de0002";
static const char *EVENT_CHAR_UUID = "c0de0003-d1a1-4f6f-9b7c-5e55c0de0003";

static constexpr int SCREEN_W = 390;
static constexpr int SCREEN_H = 390;
static constexpr int CENTER_X = SCREEN_W / 2;
static constexpr int CENTER_Y = SCREEN_H / 2;
static constexpr int MAX_BUBBLES = 8;
static constexpr int MAX_TITLE = 96;
static constexpr int MAX_CWD = 96;
static constexpr int MAX_THREAD_ID = 37;
static constexpr int PET_SIZE_NORMAL = 176;
static constexpr int PET_SIZE_FOCUS = 116;
static constexpr int PET_SIZE_MAX = PET_SIZE_NORMAL;

static constexpr int SCREEN_SDIO0 = 11;
static constexpr int SCREEN_SDIO1 = 13;
static constexpr int SCREEN_SDIO2 = 7;
static constexpr int SCREEN_SDIO3 = 14;
static constexpr int SCREEN_SCLK = 12;
static constexpr int SCREEN_CS = 10;
static constexpr int SCREEN_RST = 4;
static constexpr int SCREEN_EN = 3;
static constexpr int IIC_SDA = 5;
static constexpr int IIC_SCL = 6;
static constexpr int TOUCH_RST = 8;
static constexpr int TOUCH_INT = 9;
static constexpr int KNOB_DATA_A = 1;
static constexpr int KNOB_DATA_B = 2;
static constexpr int KNOB_KEY = 0;

Arduino_DataBus *bus = new Arduino_ESP32QSPI(
    SCREEN_CS, SCREEN_SCLK, SCREEN_SDIO0, SCREEN_SDIO1, SCREEN_SDIO2, SCREEN_SDIO3);
Arduino_GFX *panel = new Arduino_CO5300(bus, SCREEN_RST, 0, false, SCREEN_W, SCREEN_H,
                                        0, 0, 0, 0);
Arduino_Canvas *canvas = new Arduino_Canvas(SCREEN_W, SCREEN_H, panel);
Arduino_GFX *gfx = canvas;

std::shared_ptr<Arduino_IIC_DriveBus> touchBus =
    std::make_shared<Arduino_HWIIC>(IIC_SDA, IIC_SCL, &Wire);
void touchInterrupt();
std::unique_ptr<Arduino_IIC> touchDevice(new Arduino_CST816x(
    touchBus, CST816D_DEVICE_ADDRESS, TOUCH_RST, TOUCH_INT, touchInterrupt));

void touchInterrupt() {
  touchDevice->IIC_Interrupt_Flag = true;
}

struct Bubble {
  char threadId[MAX_THREAD_ID] = "";
  char title[MAX_TITLE] = "";
  char cwd[MAX_CWD] = "";
  char state[10] = "idle";
  float updatedAt = 0;
};

struct AppState {
  char mode[12] = "idle";
  char pet[32] = "";
  Bubble bubbles[MAX_BUBBLES];
  int count = 0;
  int waitingCount = 0;
  int failedCount = 0;
  int reviewCount = 0;
  int runningCount = 0;
  uint32_t lastUpdateMs = 0;
  bool connected = false;
};

static AppState appState;
static BLECharacteristic *eventChar = nullptr;
static String frameSeq;
static int expectedChunks = 0;
static int receivedChunks = 0;
static String frameBuffer;
static String lastStateJson;
static bool uiDirty = true;
static int petFrame = 0;
static int visiblePetState = -1;
static int pendingPetState = -1;
static int transientPetState = -1;
static int selectedIndex = 0;
static uint8_t knobPreviousLogical = 0;
static int pendingKnobDelta = 0;
static bool buttonWasDown = false;
static uint32_t transientUntilMs = 0;
static uint32_t focusUntilMs = 0;
static uint32_t lastAnimMs = 0;
static uint32_t lastUiAnimMs = 0;
static uint32_t lastKnobScanMs = 0;
static uint32_t lastTouchMs = 0;
static uint32_t lastClickMs = 0;
static float focusProgress = 0.0f;
static char selectedThreadId[MAX_THREAD_ID] = "";
static bool focusReported = false;
static uint16_t *petScaleBuffer = nullptr;
static bool canvasReady = false;
static bool touchReady = false;
static bool touchWasDown = false;

static uint16_t rgb(uint8_t r, uint8_t g, uint8_t b) {
  return ((r & 0xF8) << 8) | ((g & 0xFC) << 3) | (b >> 3);
}

static uint16_t stateColor(const char *state) {
  if (strcmp(state, "waiting") == 0) return rgb(245, 181, 72);
  if (strcmp(state, "failed") == 0) return rgb(226, 92, 84);
  if (strcmp(state, "review") == 0) return rgb(66, 198, 142);
  if (strcmp(state, "running") == 0) return rgb(91, 166, 255);
  return rgb(136, 160, 181);
}

static const char *stateFullLabel(const char *state) {
  if (strcmp(state, "waiting") == 0) return "WAITING";
  if (strcmp(state, "failed") == 0) return "FAILED";
  if (strcmp(state, "review") == 0) return "REVIEW";
  if (strcmp(state, "running") == 0) return "RUNNING";
  return "IDLE";
}

static const uint16_t *currentPetFrames() {
  for (int i = 0; i < PET_SET_COUNT; i++) {
    if (strcmp(PET_SETS[i].id, appState.pet) == 0) return PET_SETS[i].frames;
  }
  return PET_SETS[0].frames;
}

static int currentPetState() {
  if (!appState.connected) return PET_ROW_WAITING;
  if (transientPetState >= 0 && millis() < transientUntilMs) return transientPetState;
  if (strcmp(appState.mode, "waiting") == 0) return PET_ROW_WAITING;
  if (strcmp(appState.mode, "failed") == 0) return PET_ROW_FAILED;
  if (strcmp(appState.mode, "running") == 0) return PET_ROW_RUNNING;
  if (strcmp(appState.mode, "review") == 0) return PET_ROW_REVIEW;
  return PET_ROW_IDLE;
}

static void triggerPetState(int state, uint32_t durationMs) {
  if (!appState.connected) return;
  transientPetState = state;
  transientUntilMs = millis() + durationMs;
  pendingPetState = state;
  visiblePetState = state;
  petFrame = 0;
  uiDirty = true;
}

static bool isFocusMode() {
  return millis() < focusUntilMs;
}

static bool ensurePetScaleBuffer() {
  if (petScaleBuffer) return true;
  size_t bytes = PET_SIZE_MAX * PET_SIZE_MAX * sizeof(uint16_t);
  petScaleBuffer = static_cast<uint16_t *>(
      heap_caps_malloc(bytes, MALLOC_CAP_SPIRAM | MALLOC_CAP_8BIT));
  if (!petScaleBuffer) {
    petScaleBuffer = static_cast<uint16_t *>(malloc(bytes));
  }
  if (!petScaleBuffer) {
    Serial.printf("pet scale buffer allocation failed: %u bytes\n", static_cast<unsigned>(bytes));
    return false;
  }
  Serial.printf("pet scale buffer ready: %u bytes\n", static_cast<unsigned>(bytes));
  return true;
}

static int stateCount(const char *state) {
  int count = 0;
  for (int i = 0; i < appState.count; i++) {
    if (strcmp(appState.bubbles[i].state, state) == 0) count++;
  }
  return count;
}

static int totalStateCount(const char *state) {
  if (strcmp(state, "waiting") == 0) return appState.waitingCount;
  if (strcmp(state, "failed") == 0) return appState.failedCount;
  if (strcmp(state, "review") == 0) return appState.reviewCount;
  if (strcmp(state, "running") == 0) return appState.runningCount;
  return 0;
}

static String basenameOf(const char *path) {
  String value(path);
  int slash = value.lastIndexOf('/');
  if (slash >= 0 && slash < value.length() - 1) return value.substring(slash + 1);
  return value;
}

static String displayTitle(const Bubble &bubble) {
  String title(bubble.title);
  if (title.length() == 0) title = basenameOf(bubble.cwd);
  title.replace("[$", "");
  title.replace("](", " ");
  return title;
}

static String ellipsize(String value, int maxChars) {
  value.trim();
  if (value.length() <= maxChars) return value;
  return value.substring(0, maxChars - 3) + "...";
}

static void selectUiFont(uint8_t size) {
  gfx->setTextSize(size);
#if defined(U8G2_FONT_SUPPORT)
  gfx->setUTF8Print(true);
  gfx->setFont(u8g2_font_quan7_h_cjk);
#endif
}

static int textWidth(const String &value) {
  if (value.length() == 0) return 0;
  int16_t x1 = 0;
  int16_t y1 = 0;
  uint16_t w = 0;
  uint16_t h = 0;
  gfx->getTextBounds(value, 0, 24, &x1, &y1, &w, &h);
  return (int)w;
}

static void removeLastUtf8Char(String &value) {
  int len = value.length();
  if (len <= 0) return;
  int idx = len - 1;
  while (idx > 0 && ((uint8_t)value[idx] & 0xC0) == 0x80) idx--;
  value.remove(idx);
}

static String fitText(String value, int maxWidth) {
  value.trim();
  if (textWidth(value) <= maxWidth) return value;
  const String dots = "...";
  int dotsWidth = textWidth(dots);
  while (value.length() > 0 && textWidth(value) + dotsWidth > maxWidth) {
    removeLastUtf8Char(value);
  }
  return value.length() ? value + dots : dots;
}

static String takeFittingPrefix(String &value, int maxWidth) {
  value.trim();
  String line = value;
  while (line.length() > 0 && textWidth(line) > maxWidth) {
    removeLastUtf8Char(line);
  }
  value.remove(0, line.length());
  value.trim();
  return line;
}

static void sendEvent(const char *kind, const char *threadId) {
  if (!eventChar || strlen(threadId) == 0) return;
  String payload = kind;
  payload += "|";
  payload += threadId;
  eventChar->setValue(payload.c_str());
  eventChar->notify();
}

static void openSelectedThread() {
  if (appState.count <= 0 || millis() - lastClickMs < 350) return;
  lastClickMs = millis();
  sendEvent("CLICK", appState.bubbles[selectedIndex].threadId);
  triggerPetState(PET_ROW_WAVING, 1200);
  focusUntilMs = millis() + 5000;
  uiDirty = true;
}

static void parseStateJson(const String &json) {
  if (json == lastStateJson) {
    appState.lastUpdateMs = millis();
    return;
  }
  lastStateJson = json;

  JsonDocument doc;
  DeserializationError err = deserializeJson(doc, json);
  if (err) {
    Serial.printf("JSON parse failed: %s\n", err.c_str());
    return;
  }

  strlcpy(appState.mode, doc["mode"] | "idle", sizeof(appState.mode));
  strlcpy(appState.pet, doc["pet"] | PET_SETS[0].id, sizeof(appState.pet));
  int oldRunning = appState.runningCount;
  int oldReview = appState.reviewCount;
  JsonArray bubbles = doc["bubbles"].as<JsonArray>();
  appState.count = min((int)bubbles.size(), MAX_BUBBLES);
  for (int i = 0; i < appState.count; i++) {
    JsonObject item = bubbles[i];
    strlcpy(appState.bubbles[i].threadId, item["thread_id"] | "", sizeof(appState.bubbles[i].threadId));
    strlcpy(appState.bubbles[i].title, item["title"] | "", sizeof(appState.bubbles[i].title));
    strlcpy(appState.bubbles[i].cwd, item["cwd"] | "", sizeof(appState.bubbles[i].cwd));
    strlcpy(appState.bubbles[i].state, item["state"] | "idle", sizeof(appState.bubbles[i].state));
    appState.bubbles[i].updatedAt = item["updated_at"] | 0.0;
  }
  appState.waitingCount = doc["counts"]["waiting"] | stateCount("waiting");
  appState.failedCount = doc["counts"]["failed"] | stateCount("failed");
  appState.reviewCount = doc["counts"]["review"] | stateCount("review");
  appState.runningCount = doc["counts"]["running"] | stateCount("running");

  int preservedIndex = -1;
  if (strlen(selectedThreadId) > 0) {
    for (int i = 0; i < appState.count; i++) {
      if (strcmp(appState.bubbles[i].threadId, selectedThreadId) == 0) {
        preservedIndex = i;
        break;
      }
    }
  }
  if (preservedIndex >= 0) {
    selectedIndex = preservedIndex;
  } else if (selectedIndex >= appState.count) {
    selectedIndex = max(appState.count - 1, 0);
  }
  if (appState.count > 0) strlcpy(selectedThreadId, appState.bubbles[selectedIndex].threadId, sizeof(selectedThreadId));
  appState.lastUpdateMs = millis();
  if (appState.runningCount > oldRunning || appState.reviewCount > oldReview) {
    triggerPetState(PET_ROW_JUMPING, 1200);
  }
  pendingPetState = currentPetState();
  uiDirty = true;
}

static bool splitFrame(const String &input, String parts[5]) {
  int start = 0;
  for (int i = 0; i < 4; i++) {
    int pos = input.indexOf('|', start);
    if (pos < 0) return false;
    parts[i] = input.substring(start, pos);
    start = pos + 1;
  }
  parts[4] = input.substring(start);
  return parts[0] == "CD1";
}

class StateCallbacks : public BLECharacteristicCallbacks {
  void onWrite(BLECharacteristic *characteristic) override {
    String value = characteristic->getValue().c_str();
    String parts[5];
    if (!splitFrame(value, parts)) return;

    String seq = parts[1];
    int idx = parts[2].toInt();
    int total = parts[3].toInt();
    String payload = parts[4];

    if (seq != frameSeq || idx == 0) {
      frameSeq = seq;
      expectedChunks = total;
      receivedChunks = 0;
      frameBuffer = "";
    }
    if (idx < 0 || idx >= total || total <= 0) return;
    frameBuffer += payload;
    receivedChunks++;
    if (receivedChunks >= expectedChunks) {
      parseStateJson(frameBuffer);
      frameBuffer = "";
    }
  }
};

class ServerCallbacks : public BLEServerCallbacks {
  void onConnect(BLEServer *server) override {
    appState.connected = true;
    triggerPetState(PET_ROW_WAVING, 1400);
    uiDirty = true;
    Serial.println("BLE client connected");
  }

  void onDisconnect(BLEServer *server) override {
    appState.connected = false;
    pendingPetState = currentPetState();
    uiDirty = true;
    Serial.println("BLE client disconnected");
    BLEDevice::startAdvertising();
  }
};

static void drawPetScaled(const uint16_t *frame, int centerX, int centerY, int size) {
  int x0 = centerX - size / 2;
  int y0 = centerY - size / 2;
  if (size <= 0 || size > PET_SIZE_MAX) {
    size = PET_FRAME_SIZE;
    x0 = centerX - size / 2;
    y0 = centerY - size / 2;
  }
  if (!ensurePetScaleBuffer()) {
    gfx->draw16bitRGBBitmap(x0, y0, frame, PET_FRAME_SIZE, PET_FRAME_SIZE);
    return;
  }
  for (int y = 0; y < size; y++) {
    int srcY = (y * PET_FRAME_SIZE) / size;
    for (int x = 0; x < size; x++) {
      int srcX = (x * PET_FRAME_SIZE) / size;
      petScaleBuffer[y * size + x] = pgm_read_word(frame + srcY * PET_FRAME_SIZE + srcX);
    }
  }
  gfx->draw16bitRGBBitmapWithTranColor(x0, y0, petScaleBuffer, PET_BACKGROUND_COLOR, size, size);
}

static void flushUi() {
  if (canvasReady) {
    canvas->flush();
  }
}

static void drawTextAt(int x, int y, const char *text, uint16_t color, uint8_t size) {
  selectUiFont(size);
  gfx->setTextColor(color);
  gfx->setCursor(x, y);
  gfx->print(text);
}

static void drawTextAt(int x, int y, const String &text, uint16_t color, uint8_t size) {
  selectUiFont(size);
  gfx->setTextColor(color);
  gfx->setCursor(x, y);
  gfx->print(text);
}

static void drawTextAt(int x, int y, int value, uint16_t color, uint8_t size) {
  selectUiFont(size);
  gfx->setTextColor(color);
  gfx->setCursor(x, y);
  gfx->print(value);
}

static void drawPet() {
  if (visiblePetState < 0) {
    visiblePetState = currentPetState();
    pendingPetState = visiblePetState;
  }
  int stateIndex = visiblePetState;
  int frameIndex = petFrame % PET_FRAME_COUNT;
  const uint16_t *frame =
      currentPetFrames() + ((stateIndex * PET_FRAME_COUNT + frameIndex) * PET_FRAME_SIZE * PET_FRAME_SIZE);
  int petSize = round(PET_SIZE_NORMAL - focusProgress * (PET_SIZE_NORMAL - PET_SIZE_FOCUS));
  int petY = round(238 + focusProgress * 42);
  drawPetScaled(frame, CENTER_X, petY, petSize);
}

static void drawCountPill(int x, int y, const char *state, const char *prefix) {
  selectUiFont(2);
  uint16_t bg = rgb(28, 36, 42);
  gfx->fillRoundRect(x, y, 76, 30, 12, bg);
  gfx->fillCircle(x + 16, y + 15, 5, stateColor(state));
  String label = fitText(String(prefix) + String(totalStateCount(state)), 38);
  drawTextAt(x + 31, y + 22, label, rgb(229, 236, 240), 2);
}

static void drawCounts() {
  if (focusProgress > 0.08f) return;
  drawCountPill(108, 48, "waiting", "W");
  drawCountPill(206, 48, "failed", "F");
  drawCountPill(108, 86, "review", "V");
  drawCountPill(206, 86, "running", "R");
}

static void drawTaskCard() {
  if (appState.count <= 0 || focusProgress < 0.05f) return;
  Bubble &bubble = appState.bubbles[selectedIndex];
  uint16_t accent = stateColor(bubble.state);
  int cardW = round(260 - (1.0f - focusProgress) * 126);
  int cardH = round(126 - (1.0f - focusProgress) * 84);
  int cardX = (SCREEN_W - cardW) / 2;
  int cardY = round(58 - (1.0f - focusProgress) * 82);
  if (cardH < 48) return;

  gfx->fillRoundRect(cardX, cardY, cardW, cardH, 16, rgb(23, 31, 37));
  gfx->drawRoundRect(cardX, cardY, cardW, cardH, 16, rgb(51, 65, 75));

  selectUiFont(2);
  const char *label = stateFullLabel(bubble.state);
  int labelW = min(max(textWidth(label) + 22, 82), max(72, cardW - 84));
  gfx->fillRoundRect(cardX + 17, cardY + 16, labelW, 28, 9, accent);
  drawTextAt(cardX + 17 + (labelW - textWidth(label)) / 2, cardY + 37,
             label, rgb(14, 20, 24), 2);

  String indexLabel = String(selectedIndex + 1) + "/" + String(appState.count);
  int indexW = textWidth(indexLabel);
  drawTextAt(cardX + cardW - 17 - indexW, cardY + 37, indexLabel, rgb(185, 198, 207), 2);

  int textX = cardX + 18;
  int textW = cardW - 36;
  String title = displayTitle(bubble);
  if (title.length() == 0) title = basenameOf(bubble.cwd);
  String remaining = title;
  String line1 = takeFittingPrefix(remaining, textW);
  String line2 = fitText(remaining, textW);
  drawTextAt(textX, cardY + 72, line1, rgb(235, 239, 242), 2);
  if (line2.length() > 0) {
    drawTextAt(textX, cardY + 94, line2, rgb(235, 239, 242), 2);
  }

  String cwd = basenameOf(bubble.cwd);
  if (cwd.length() > 0) {
    selectUiFont(1);
    drawTextAt(textX, cardY + 116, fitText(cwd, textW), accent, 1);
  }
}

static void drawUi() {
  gfx->fillScreen(rgb(17, 23, 28));
  drawTaskCard();
  drawPet();
  if (!isFocusMode()) drawCounts();
  flushUi();
}

static void rotateSelection(int delta) {
  if (appState.count <= 0) return;
  triggerPetState(delta > 0 ? PET_ROW_RUNNING_RIGHT : PET_ROW_RUNNING_LEFT, 700);
  char previousThreadId[MAX_THREAD_ID] = "";
  strlcpy(previousThreadId, appState.bubbles[selectedIndex].threadId, sizeof(previousThreadId));
  selectedIndex = (selectedIndex + delta + appState.count) % appState.count;
  strlcpy(selectedThreadId, appState.bubbles[selectedIndex].threadId, sizeof(selectedThreadId));
  if (strcmp(previousThreadId, selectedThreadId) != 0) sendEvent("LEAVE", previousThreadId);
  focusUntilMs = millis() + 5000;
  uiDirty = true;
}

static void scanKnob() {
  if (millis() - lastKnobScanMs < 8) return;
  lastKnobScanMs = millis();
  uint8_t logical = 0;
  if (digitalRead(KNOB_DATA_A) == HIGH) logical |= 0b10;
  if (digitalRead(KNOB_DATA_B) == HIGH) logical |= 0b01;
  if (logical != knobPreviousLogical) {
    if (logical == 0b10) {
      if (knobPreviousLogical == 0b00) pendingKnobDelta = 1;
      else if (knobPreviousLogical == 0b11) pendingKnobDelta = -1;
    } else if (logical == 0b01) {
      if (knobPreviousLogical == 0b00) pendingKnobDelta = -1;
      else if (knobPreviousLogical == 0b11) pendingKnobDelta = 1;
    } else if (logical == 0b00 || logical == 0b11) {
      knobPreviousLogical = logical;
      if (pendingKnobDelta != 0) {
        rotateSelection(pendingKnobDelta);
        pendingKnobDelta = 0;
      }
    }
  }

  bool buttonDown = digitalRead(KNOB_KEY) == LOW;
  if (!buttonDown && buttonWasDown) {
    if (isFocusMode() && appState.count > 0) openSelectedThread();
    else triggerPetState(PET_ROW_JUMPING, 900);
  }
  buttonWasDown = buttonDown;
}

static void handleTap() {
  if (millis() - lastTouchMs < 250) return;
  lastTouchMs = millis();
  if (isFocusMode() && appState.count > 0) {
    openSelectedThread();
  } else {
    triggerPetState(PET_ROW_JUMPING, 900);
  }
}

static void scanTouch() {
  if (!touchReady) return;
  int fingers = (int)touchDevice->IIC_Read_Device_Value(
      touchDevice->Arduino_IIC_Touch::Value_Information::TOUCH_FINGER_NUMBER);
  bool touchDown = fingers > 0;
  if (!touchDown && touchWasDown) {
    handleTap();
  }
  touchWasDown = touchDown;
}

static void updateFocusEvents() {
  bool focused = isFocusMode() && appState.count > 0;
  if (focused && !focusReported) {
    focusReported = true;
  } else if (!focused && focusReported) {
    focusReported = false;
    if (strlen(selectedThreadId) > 0) sendEvent("LEAVE", selectedThreadId);
  }
}

static void setupBle() {
  BLEDevice::init(DEVICE_NAME);
  BLEServer *server = BLEDevice::createServer();
  server->setCallbacks(new ServerCallbacks());
  BLEService *service = server->createService(SERVICE_UUID);
  BLECharacteristic *stateChar = service->createCharacteristic(
      STATE_CHAR_UUID, BLECharacteristic::PROPERTY_WRITE | BLECharacteristic::PROPERTY_WRITE_NR);
  stateChar->setCallbacks(new StateCallbacks());
  eventChar = service->createCharacteristic(
      EVENT_CHAR_UUID, BLECharacteristic::PROPERTY_NOTIFY | BLECharacteristic::PROPERTY_READ);
  eventChar->addDescriptor(new BLE2902());
  service->start();
  BLEAdvertising *advertising = BLEDevice::getAdvertising();
  advertising->addServiceUUID(SERVICE_UUID);
  advertising->setScanResponse(true);
  BLEDevice::startAdvertising();
}

static void setupTouch() {
  if (!touchDevice->begin()) {
    Serial.println("CST816 touch initialization failed");
    touchReady = false;
    return;
  }
  touchDevice->IIC_Write_Device_State(
      touchDevice->Arduino_IIC_Touch::Device::TOUCH_DEVICE_INTERRUPT_MODE,
      touchDevice->Arduino_IIC_Touch::Device_Mode::TOUCH_DEVICE_INTERRUPT_PERIODIC);
  touchReady = true;
  Serial.println("CST816 touch ready");
}

void setup() {
  Serial.begin(115200);
  pinMode(SCREEN_EN, OUTPUT);
  digitalWrite(SCREEN_EN, HIGH);
  pinMode(KNOB_DATA_A, INPUT_PULLUP);
  pinMode(KNOB_DATA_B, INPUT_PULLUP);
  pinMode(KNOB_KEY, INPUT_PULLUP);
  knobPreviousLogical = ((digitalRead(KNOB_DATA_A) == HIGH) ? 0b10 : 0) |
                        ((digitalRead(KNOB_DATA_B) == HIGH) ? 0b01 : 0);

  if (!panel->begin(40000000)) Serial.println("panel begin failed");
  for (int i = 0; i <= 255; i += 5) {
    panel->Display_Brightness(i);
    delay(2);
  }
  canvasReady = canvas->begin(GFX_SKIP_OUTPUT_BEGIN);
  if (!canvasReady) {
    Serial.println("canvas begin failed; drawing directly");
    gfx = panel;
  } else {
    Serial.println("canvas ready");
  }
  gfx->setTextWrap(false);
  setupTouch();
  setupBle();
  selectUiFont(2);
  drawUi();
  Serial.println("Codex T-Encoder Pro firmware ready");
}

void loop() {
  scanKnob();
  scanTouch();
  updateFocusEvents();

  if (millis() - lastUiAnimMs > 33) {
    lastUiAnimMs = millis();
    float target = isFocusMode() ? 1.0f : 0.0f;
    if (fabsf(focusProgress - target) > 0.01f) {
      focusProgress += (target - focusProgress) * 0.22f;
      if (fabsf(focusProgress - target) < 0.015f) focusProgress = target;
      uiDirty = true;
    }
  }

  if (PET_FRAME_COUNT > 1 && millis() - lastAnimMs > 180) {
    lastAnimMs = millis();
    int desiredPetState = currentPetState();
    if (desiredPetState != pendingPetState) {
      pendingPetState = desiredPetState;
    }
    petFrame = (petFrame + 1) % PET_FRAME_COUNT;
    if (pendingPetState >= 0 && pendingPetState != visiblePetState && petFrame == 0) {
      visiblePetState = desiredPetState;
    }
    uiDirty = true;
  }

  if (uiDirty) {
    uiDirty = false;
    drawUi();
  }
}
