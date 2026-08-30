#include <Arduino.h>
#include <BLE2902.h>
#include <BLEDevice.h>
#include <BLEServer.h>
#include <BLEUtils.h>

// ESP32-C3 SuperMini demo wiring, matching ../c3test.
constexpr uint8_t RED_LED_PIN = 2;
constexpr uint8_t GREEN_LED_PIN = 3;
constexpr uint8_t RELAY_PIN = 4;

// Temporary demo mode for battery-powered demos: the relay coil pulls enough
// current to brown out the ESP32-C3, so leave the relay de-energised (NC
// closed, boat powered) and only alternate the LEDs. Set to 0 to restore the
// normal kill-switch behaviour.
#define DEMO_LED_BLINK 1
constexpr uint32_t DEMO_BLINK_INTERVAL_MS = 5000;

constexpr char DEVICE_NAME[] = "VPass Kill Switch";
constexpr char SERVICE_UUID[] = "8d4f2a10-5f5f-4c0b-9a8c-0f6f7f7b2a10";
constexpr char COMMAND_UUID[] = "8d4f2a11-5f5f-4c0b-9a8c-0f6f7f7b2a10";

BLECharacteristic *commandCharacteristic = nullptr;
bool relayOn = true;
bool connected = false;

String normalize(String value) {
  value.trim();
  value.toLowerCase();
  return value;
}

String stateText() {
  return relayOn ? "ON" : "OFF";
}

void publishState() {
  if (!commandCharacteristic) return;
  commandCharacteristic->setValue(stateText().c_str());
  if (connected) commandCharacteristic->notify();
}

void setRelay(bool on) {
  relayOn = on;

#if DEMO_LED_BLINK
  // Demo mode: only track and report the state. The relay stays de-energised
  // and the LEDs are driven by the blink loop.
  Serial.println(String("Demo mode, relay untouched. State: ") + stateText());
  publishState();
  return;
#endif

  // Relay ON energizes the module and opens the normally-closed line.
  // That cuts the model boat power, so red is the stopped state.
  digitalWrite(RELAY_PIN, relayOn ? HIGH : LOW);
  digitalWrite(RED_LED_PIN, relayOn ? HIGH : LOW);
  digitalWrite(GREEN_LED_PIN, relayOn ? LOW : HIGH);

  Serial.println(relayOn ? "Relay ON: boat power CUT, red LED ON"
                         : "Relay OFF: boat power CONNECTED, green LED ON");
  publishState();
}

bool applyCommand(const String &raw) {
  String command = normalize(raw);
  if (command == "on" || command == "1" || command == "cut" ||
      command == "lock" || command == "engage" || command == "relay:on") {
    setRelay(true);
    return true;
  }

  if (command == "off" || command == "0" || command == "run" ||
      command == "unlock" || command == "restore" || command == "relay:off") {
    setRelay(false);
    return true;
  }

  if (command == "status" || command == "?") {
    publishState();
    Serial.println(String("Status: ") + stateText());
    return true;
  }

  Serial.println(String("Unknown command: ") + raw);
  return false;
}

class ServerCallbacks : public BLEServerCallbacks {
  void onConnect(BLEServer *server) override {
    connected = true;
    publishState();
    Serial.println("BLE client connected");
  }

  void onDisconnect(BLEServer *server) override {
    connected = false;
    Serial.println("BLE client disconnected");
    BLEDevice::startAdvertising();
  }
};

class CommandCallbacks : public BLECharacteristicCallbacks {
  void onWrite(BLECharacteristic *characteristic) override {
    String value = String(characteristic->getValue().c_str());
    if (value.length() == 0) return;
    applyCommand(value);
  }

  void onRead(BLECharacteristic *characteristic) override {
    characteristic->setValue(stateText().c_str());
  }
};

void setupBle() {
  BLEDevice::init(DEVICE_NAME);

  BLEServer *server = BLEDevice::createServer();
  server->setCallbacks(new ServerCallbacks());

  BLEService *service = server->createService(SERVICE_UUID);
  commandCharacteristic = service->createCharacteristic(
      COMMAND_UUID,
      BLECharacteristic::PROPERTY_READ |
          BLECharacteristic::PROPERTY_WRITE |
          BLECharacteristic::PROPERTY_WRITE_NR |
          BLECharacteristic::PROPERTY_NOTIFY);
  commandCharacteristic->setCallbacks(new CommandCallbacks());
  commandCharacteristic->addDescriptor(new BLE2902());
  commandCharacteristic->setValue(stateText().c_str());

  service->start();

  BLEAdvertising *advertising = BLEDevice::getAdvertising();
  advertising->addServiceUUID(SERVICE_UUID);
  advertising->setScanResponse(true);
  advertising->setMinPreferred(0x06);
  advertising->setMinPreferred(0x12);
  BLEDevice::startAdvertising();

  Serial.println(String("BLE advertising: ") + DEVICE_NAME);
  Serial.println(String("Service: ") + SERVICE_UUID);
  Serial.println(String("Command: ") + COMMAND_UUID);
}

void setup() {
  Serial.begin(115200);
  delay(500);

  pinMode(RED_LED_PIN, OUTPUT);
  pinMode(GREEN_LED_PIN, OUTPUT);
  pinMode(RELAY_PIN, OUTPUT);

#if DEMO_LED_BLINK
  digitalWrite(RELAY_PIN, LOW);  // de-energised: NC closed, boat powered
  digitalWrite(RED_LED_PIN, HIGH);
  digitalWrite(GREEN_LED_PIN, LOW);
  Serial.println("DEMO_LED_BLINK: relay left OFF, LEDs alternate every 5 s");
#else
  setRelay(true);
#endif
  setupBle();

  Serial.println("Serial commands: 1/on/cut = relay ON, 0/off/run = relay OFF");
}

#if DEMO_LED_BLINK
void demoBlink() {
  static uint32_t lastToggle = 0;
  static bool redOn = true;

  uint32_t now = millis();
  if (now - lastToggle < DEMO_BLINK_INTERVAL_MS) return;
  lastToggle = now;

  redOn = !redOn;
  digitalWrite(RED_LED_PIN, redOn ? HIGH : LOW);
  digitalWrite(GREEN_LED_PIN, redOn ? LOW : HIGH);
}
#endif

void loop() {
#if DEMO_LED_BLINK
  demoBlink();
#endif

  if (!Serial.available()) {
    delay(20);
    return;
  }

  String command = Serial.readStringUntil('\n');
  applyCommand(command);
}
