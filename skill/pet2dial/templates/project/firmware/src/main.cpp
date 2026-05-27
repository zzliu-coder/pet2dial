#include <Arduino.h>
#include <ArduinoJson.h>
#include <BLE2902.h>
#include <BLEDevice.h>
#include <BLEServer.h>
#include <BLEUtils.h>
#include <M5GFX.h>
#include <M5Dial.h>

#include "pet_frames.h"

static const char *DEVICE_NAME = "CodexDial";
static const char *SERVICE_UUID = "c0de0001-d1a1-4f6f-9b7c-5e55c0de0001";
static const char *STATE_CHAR_UUID = "c0de0002-d1a1-4f6f-9b7c-5e55c0de0002";
static const char *EVENT_CHAR_UUID = "c0de0003-d1a1-4f6f-9b7c-5e55c0de0003";

static constexpr int SCREEN_W = 240;
static constexpr int SCREEN_H = 240;
static constexpr int MAX_BUBBLES = 8;
static constexpr int MAX_TITLE = 96;
static constexpr int MAX_CWD = 96;
static constexpr int MAX_THREAD_ID = 37;

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
  uint32_t lastUpdateMs = 0;
  bool connected = false;
};

static AppState appState;
static M5Canvas canvas(&M5Dial.Display);
static BLECharacteristic *eventChar = nullptr;
static String frameSeq;
static int expectedChunks = 0;
static int receivedChunks = 0;
static String frameBuffer;
static uint32_t lastTouchMs = 0;
static uint32_t lastClickMs = 0;
static uint32_t lastAnimMs = 0;
static String lastStateJson;
static bool uiDirty = true;
static int petFrame = 0;
static int visiblePetState = -1;
static int pendingPetState = -1;
static int transientPetState = -1;
static int selectedIndex = 0;
static long lastEncoderPosition = 0;
static int encoderRemainder = 0;
static uint32_t transientUntilMs = 0;
static uint32_t focusUntilMs = 0;
static uint32_t lastUiAnimMs = 0;
static float focusProgress = 0.0f;
static char selectedThreadId[MAX_THREAD_ID] = "";
static bool focusReported = false;

static const uint16_t *currentPetFrames() {
  for (int i = 0; i < PET_SET_COUNT; i++) {
    if (strcmp(PET_SETS[i].id, appState.pet) == 0) {
      return PET_SETS[i].frames;
    }
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
  petFrame = 0;
  uiDirty = true;
}

static uint16_t rgb(uint8_t r, uint8_t g, uint8_t b) {
  return ((r & 0xF8) << 8) | ((g & 0xFC) << 3) | (b >> 3);
}

static uint16_t stateColor(const char *state) {
  if (strcmp(state, "review") == 0) return rgb(66, 198, 142);
  if (strcmp(state, "running") == 0) return rgb(240, 189, 75);
  return rgb(136, 160, 181);
}

static const char *stateShortLabel(const char *state) {
  if (strcmp(state, "review") == 0) return "REVIEW";
  if (strcmp(state, "running") == 0) return "RUN";
  return "-";
}

static bool isFocusMode() {
  return millis() < focusUntilMs;
}

static int stateCount(const char *state) {
  int count = 0;
  for (int i = 0; i < appState.count; i++) {
    if (strcmp(appState.bubbles[i].state, state) == 0) count++;
  }
  return count;
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
  return value.substring(0, maxChars - 1) + "...";
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
  if (canvas.textWidth(value) <= maxWidth) return value;
  const String dots = "...";
  int dotsWidth = canvas.textWidth(dots);
  while (value.length() > 0 && canvas.textWidth(value) + dotsWidth > maxWidth) {
    removeLastUtf8Char(value);
  }
  return value.length() ? value + dots : dots;
}

static String takeFittingPrefix(String &value, int maxWidth) {
  value.trim();
  String line = value;
  while (line.length() > 0 && canvas.textWidth(line) > maxWidth) {
    removeLastUtf8Char(line);
  }
  value.remove(0, line.length());
  value.trim();
  return line;
}

static void sendEvent(const char *kind, const char *threadId);

static void openSelectedThread() {
  if (appState.count <= 0 || millis() - lastClickMs < 350) return;
  lastClickMs = millis();
  sendEvent("CLICK", appState.bubbles[selectedIndex].threadId);
  triggerPetState(PET_ROW_WAVING, 1200);
  focusUntilMs = millis() + 5000;
  uiDirty = true;
}

static void sendEvent(const char *kind, const char *threadId) {
  if (!eventChar || strlen(threadId) == 0) return;
  String payload = kind;
  payload += "|";
  payload += threadId;
  eventChar->setValue(payload.c_str());
  eventChar->notify();
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
  int oldRunning = stateCount("running");
  int oldReview = stateCount("review");
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
  int newRunning = stateCount("running");
  int newReview = stateCount("review");
  if (newRunning > oldRunning || newReview > oldReview) {
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
    if (!splitFrame(value, parts)) {
      Serial.println("Ignoring invalid state frame");
      return;
    }

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
    receivedChunks += 1;

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
  if (size == PET_FRAME_SIZE) {
    canvas.pushImage(x0, y0, PET_FRAME_SIZE, PET_FRAME_SIZE, frame);
    return;
  }

  for (int y = 0; y < size; y++) {
    int srcY = (y * PET_FRAME_SIZE) / size;
    for (int x = 0; x < size; x++) {
      int srcX = (x * PET_FRAME_SIZE) / size;
      uint16_t color = pgm_read_word(frame + srcY * PET_FRAME_SIZE + srcX);
      canvas.drawPixel(x0 + x, y0 + y, color);
    }
  }
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
  int size = round(96 - focusProgress * 38);
  int centerY = round(122 + focusProgress * 58);
  drawPetScaled(frame, 120, centerY, size);
}

static void drawText() {
  uint16_t ring = appState.connected ? rgb(66, 198, 142) : rgb(240, 189, 75);
  canvas.drawCircle(120, 120, 116, ring);
}

static void drawCounts() {
  if (focusProgress > 0.08f) return;
  int y = 58;
  int runCount = stateCount("running");
  int reviewCount = stateCount("review");
  canvas.setTextDatum(middle_center);
  canvas.setTextSize(1);
  canvas.setFont(&fonts::efontCN_12);

  canvas.fillRoundRect(72, y - 10, 42, 20, 9, rgb(28, 36, 42));
  canvas.fillCircle(84, y, 4, stateColor("running"));
  canvas.setTextColor(rgb(229, 236, 240), rgb(28, 36, 42));
  canvas.drawString("R" + String(runCount), 99, y);

  canvas.fillRoundRect(126, y - 10, 42, 20, 9, rgb(28, 36, 42));
  canvas.fillCircle(138, y, 4, stateColor("review"));
  canvas.setTextColor(rgb(229, 236, 240), rgb(28, 36, 42));
  canvas.drawString("V" + String(reviewCount), 153, y);
}

static void drawTaskCard() {
  if (appState.count <= 0 || focusProgress < 0.05f) return;
  Bubble &bubble = appState.bubbles[selectedIndex];
  uint16_t accent = stateColor(bubble.state);
  int cardX = round(42 + (1.0f - focusProgress) * 68);
  int cardY = round(34 - (1.0f - focusProgress) * 80);
  int cardW = round(156 - (1.0f - focusProgress) * 116);
  int cardH = round(96 - (1.0f - focusProgress) * 64);
  if (cardH < 24) return;

  canvas.fillRoundRect(cardX, cardY, cardW, cardH, 12, rgb(23, 31, 37));
  canvas.drawRoundRect(cardX, cardY, cardW, cardH, 12, rgb(51, 65, 75));

  canvas.setFont(&fonts::efontCN_12);
  canvas.setTextSize(1);
  canvas.setTextDatum(middle_center);
  int labelW = strcmp(bubble.state, "review") == 0 ? 52 : 36;
  canvas.fillRoundRect(cardX + 12, cardY + 12, labelW, 18, 7, accent);
  canvas.setTextColor(rgb(14, 20, 24), accent);
  canvas.drawString(stateShortLabel(bubble.state), cardX + 12 + labelW / 2, cardY + 21);

  canvas.setTextDatum(middle_right);
  String counts = String(selectedIndex + 1) + "/" + String(appState.count);
  canvas.setTextColor(rgb(185, 198, 207), rgb(23, 31, 37));
  canvas.drawString(counts, cardX + cardW - 12, cardY + 22);

  canvas.setTextDatum(top_left);
  canvas.setTextColor(accent, rgb(23, 31, 37));

  int textX = cardX + 13;
  int textW = cardW - 26;
  String title = displayTitle(bubble);
  if (title.length() == 0) title = basenameOf(bubble.cwd);
  String remaining = title;
  String line1 = takeFittingPrefix(remaining, textW);
  String line2 = fitText(remaining, textW);
  canvas.setTextColor(rgb(235, 239, 242), rgb(23, 31, 37));
  canvas.drawString(line1, textX, cardY + 43);
  canvas.drawString(line2, textX, cardY + 66);
}

static void drawUi() {
  canvas.fillScreen(rgb(17, 23, 28));
  canvas.fillCircle(120, 120, 119, rgb(17, 23, 28));
  canvas.drawCircle(120, 120, 118, rgb(44, 57, 66));
  drawTaskCard();
  drawPet();
  drawText();
  drawCounts();
  canvas.pushSprite(0, 0);
}

static void handleTouch() {
  auto touch = M5Dial.Touch.getDetail();
  if (!touch.wasClicked() || millis() - lastTouchMs < 250) return;
  lastTouchMs = millis();

  if (appState.count > 0) {
    openSelectedThread();
  }
}

static void handleButton() {
  if (M5Dial.BtnA.wasClicked() && appState.count > 0) {
    openSelectedThread();
  }
}

static void handleEncoder() {
  long position = M5Dial.Encoder.read();
  if (position == lastEncoderPosition || appState.count <= 0) return;
  int rawDelta = position - lastEncoderPosition;
  lastEncoderPosition = position;
  encoderRemainder += rawDelta;
  int steps = encoderRemainder / 4;
  if (steps == 0) return;
  encoderRemainder -= steps * 4;
  int delta = steps > 0 ? 1 : -1;
  triggerPetState(delta > 0 ? PET_ROW_RUNNING_RIGHT : PET_ROW_RUNNING_LEFT, 700);
  char previousThreadId[MAX_THREAD_ID] = "";
  strlcpy(previousThreadId, appState.bubbles[selectedIndex].threadId, sizeof(previousThreadId));
  selectedIndex = (selectedIndex + delta + appState.count) % appState.count;
  strlcpy(selectedThreadId, appState.bubbles[selectedIndex].threadId, sizeof(selectedThreadId));
  if (strcmp(previousThreadId, selectedThreadId) != 0) {
    sendEvent("LEAVE", previousThreadId);
  }
  focusUntilMs = millis() + 5000;
  uiDirty = true;
}

static void updateFocusEvents() {
  bool focused = isFocusMode() && appState.count > 0;
  if (focused && !focusReported) {
    focusReported = true;
  } else if (!focused && focusReported) {
    focusReported = false;
    if (strlen(selectedThreadId) > 0) {
      sendEvent("LEAVE", selectedThreadId);
    }
  }
}

static void setupBle() {
  BLEDevice::init(DEVICE_NAME);
  BLEServer *server = BLEDevice::createServer();
  server->setCallbacks(new ServerCallbacks());

  BLEService *service = server->createService(SERVICE_UUID);
  BLECharacteristic *stateChar = service->createCharacteristic(
      STATE_CHAR_UUID,
      BLECharacteristic::PROPERTY_WRITE | BLECharacteristic::PROPERTY_WRITE_NR);
  stateChar->setCallbacks(new StateCallbacks());

  eventChar = service->createCharacteristic(EVENT_CHAR_UUID, BLECharacteristic::PROPERTY_NOTIFY | BLECharacteristic::PROPERTY_READ);
  eventChar->addDescriptor(new BLE2902());
  service->start();

  BLEAdvertising *advertising = BLEDevice::getAdvertising();
  advertising->addServiceUUID(SERVICE_UUID);
  advertising->setScanResponse(true);
  BLEDevice::startAdvertising();
}

void setup() {
  Serial.begin(115200);
  auto cfg = M5.config();
  M5Dial.begin(cfg, true, false);
  M5Dial.Display.setBrightness(160);
  M5Dial.Display.setSwapBytes(true);
  M5Dial.Display.setFont(&fonts::efontCN_12);
  canvas.setColorDepth(16);
  canvas.createSprite(SCREEN_W, SCREEN_H);
  canvas.setSwapBytes(true);
  canvas.setFont(&fonts::efontCN_12);

  lastEncoderPosition = M5Dial.Encoder.read();
  setupBle();
  drawUi();
  Serial.println("Codex Dial firmware ready");
}

void loop() {
  M5Dial.update();
  handleEncoder();
  handleButton();
  handleTouch();
  updateFocusEvents();

  if (millis() - lastUiAnimMs > 33) {
    lastUiAnimMs = millis();
    float target = isFocusMode() ? 1.0f : 0.0f;
    if (fabs(focusProgress - target) > 0.01f) {
      focusProgress += (target - focusProgress) * 0.22f;
      if (fabs(focusProgress - target) < 0.015f) focusProgress = target;
      uiDirty = true;
    }
  }

  if (PET_FRAME_COUNT > 1 && millis() - lastAnimMs > 180) {
    lastAnimMs = millis();
    int desiredPetState = currentPetState();
    if (desiredPetState != pendingPetState) pendingPetState = desiredPetState;
    petFrame = (petFrame + 1) % PET_FRAME_COUNT;
    if (pendingPetState >= 0 && pendingPetState != visiblePetState && petFrame == 0) {
      visiblePetState = pendingPetState;
    }
    uiDirty = true;
  }

  if (uiDirty) {
    uiDirty = false;
    drawUi();
  }
}
