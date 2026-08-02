#include <ESP8266WiFi.h>
#include <ESP8266HTTPClient.h>
#include <WiFiClient.h>
#include <Wire.h>
#include "MPU9250.h"
#include "config.h"

// Default configuration if not defined in config.h
#ifndef DEVICE_ID
#define DEVICE_ID "DEFAULT_DEVICE"
#endif
#ifndef SERVER_URL
#define SERVER_URL "http://localhost:3000"
#endif
#ifndef WIFI_SSID
#define WIFI_SSID ""
#endif
#ifndef WIFI_PASSWORD
#define WIFI_PASSWORD ""
#endif

// ── 스마트 구명조끼 펌웨어 ───────────────────────────────────────────────
// 기능
//   1) 외장 스위치를 누르면 "착용 여부"를 토글 → 서버에 알림
//   2) 착용 상태이면 3초에 한 번씩 서버로 ping(생존 신호)을 보냄
//   3) MPU9250 으로 큰 낙상(운동량 급변)을 감지하면 서버에 넘어짐을 알림
//
// ESP8266 은 esp32-tutorial 과 마찬가지로 "서버를 보는 하나의 클라이언트"이며,
// 상태 변화는 모두 HTTP 요청으로 서버에 전달합니다.
// ────────────────────────────────────────────────────────────────────────

// ── 핀 배치 (esp12e / NodeMCU 기준) ──
const int SWITCH_PIN = 14;  // D5, 외장 스위치 (INPUT_PULLUP: 누르면 LOW)
const int LED_PIN    = 2;   // D4, 보드 내장 LED (착용 상태 표시, active-LOW)
const int SDA_PIN    = 4;   // D2, MPU9250 SDA
const int SCL_PIN    = 5;   // D1, MPU9250 SCL

// ── 동작 파라미터 ──
const unsigned long PING_INTERVAL   = 3000;  // 착용 중 ping 주기 (3초)
const unsigned long DEBOUNCE_MS     = 50;    // 스위치 채터링 제거 시간
const unsigned long FALL_COOLDOWN   = 3000;  // 낙상 재감지 최소 간격
const float         FALL_THRESHOLD  = 2.5;   // 낙상으로 볼 가속도 크기 (g)
const unsigned long WEARING_RETRY_MS = 2000; // wearing 전송 실패 시 재시도 간격

// ── 상태 변수 ──
MPU9250 mpu;
bool worn = false;                 // 착용 여부
bool wearingSynced = true;         // 서버가 현재 worn 값을 알고 있는지
unsigned long lastWearingTry = 0;  // 마지막 wearing 전송 시각
unsigned long lastPing = 0;        // 마지막 ping 시각
unsigned long lastFall = 0;        // 마지막 낙상 감지 시각

int  lastSwitchReading = HIGH;     // 직전 원시 스위치 값
int  switchState       = HIGH;     // 디바운스된 스위치 값
unsigned long lastSwitchChange = 0;

int  mpuFailCount = 0;             // MPU 연속 응답 실패 횟수 (버스 복구 판단용)

// I2C 를 (재)초기화하며 안정적인 속도로 설정.
void i2cInit() {
  Wire.begin(SDA_PIN, SCL_PIN);
  Wire.setClock(100000);           // 400k→100k: 브레드보드/긴 배선에서 훨씬 안정적
  Wire.setClockStretchLimit(2000); // MPU 클럭 스트레칭 여유
}

// 버스가 멈췄을 때(슬레이브가 SDA 를 LOW 로 붙잡음) SCL 을 수동으로 9번 흔들어
// 슬레이브를 강제로 놓아주고 I2C 를 다시 시작합니다.
void i2cRecover() {
  pinMode(SDA_PIN, INPUT_PULLUP);
  pinMode(SCL_PIN, OUTPUT);
  for (int i = 0; i < 9; i++) {
    digitalWrite(SCL_PIN, HIGH); delayMicroseconds(5);
    digitalWrite(SCL_PIN, LOW);  delayMicroseconds(5);
  }
  pinMode(SCL_PIN, INPUT_PULLUP);
  i2cInit();
}

// 서버로 JSON POST 를 보내고 성공 여부를 돌려줍니다.
bool postJson(const String &path, const String &json) {
  if (WiFi.status() != WL_CONNECTED) return false;
  HTTPClient http;
  WiFiClient client;
  http.begin(client, String(SERVER_URL) + path);
  http.addHeader("Content-Type", "application/json");
  int code = http.POST(json);
  http.end();
  if (code > 0) {
    Serial.printf("POST %s -> %d\n", path.c_str(), code);
    return code == 200;
  }
  Serial.printf("POST %s 실패 — 서버 주소/실행/방화벽 확인\n", path.c_str());
  return false;
}

// 현재 착용 상태를 서버에 전송. 실패하면 handleWearingSync 가 재시도한다.
void sendWearing() {
  lastWearingTry = millis();
  wearingSynced = postJson(
      "/api/wearing",
      String("{\"device\":\"") + DEVICE_ID + "\",\"worn\":" + (worn ? "true" : "false") + "}");
  if (!wearingSynced) Serial.println("wearing 전송 실패 — 재시도 예약");
}

// 착용 상태를 토글하고 서버 + LED 에 반영
void toggleWorn() {
  worn = !worn;
  digitalWrite(LED_PIN, worn ? LOW : HIGH);  // active-LOW: 착용 시 점등
  Serial.println(worn ? "착용됨" : "미착용");
  sendWearing();
  if (worn) lastPing = millis() - PING_INTERVAL;  // 착용 즉시 첫 ping 전송
}

// wearing 전송이 실패한 채면 성공할 때까지 주기적으로 재시도한다.
// 탈의 알림이 유실되면 서버가 착용으로 오인한 채 ping 만 끊겨
// 익수 오경보(signal_loss)가 나므로, 반드시 최신 상태를 동기화한다.
void handleWearingSync() {
  if (wearingSynced) return;
  if (millis() - lastWearingTry >= WEARING_RETRY_MS) sendWearing();
}

// 외장 스위치를 읽어 눌림(HIGH->LOW)에서 착용 상태 토글 (디바운스 포함)
void handleSwitch() {
  int reading = digitalRead(SWITCH_PIN);
  if (reading != lastSwitchReading) {
    lastSwitchChange = millis();
    lastSwitchReading = reading;
  }
  if (millis() - lastSwitchChange > DEBOUNCE_MS && reading != switchState) {
    switchState = reading;
    if (switchState == LOW) toggleWorn();  // 눌린 순간에만 토글
  }
}

// 착용 중이면 3초마다 ping 전송
void handlePing() {
  if (!worn) return;
  if (millis() - lastPing >= PING_INTERVAL) {
    lastPing = millis();
    postJson("/api/ping", String("{\"device\":\"") + DEVICE_ID + "\"}");
  }
}

// MPU9250 로 큰 낙상(가속도 크기 급변)을 감지하면 서버에 알림 (착용 중에만 동작)
void handleFall() {
  if (!worn) return;
  if (!mpu.update()) {
    // 응답이 계속 없으면 버스가 멈춘 것으로 보고 복구 + 재초기화 시도
    if (++mpuFailCount >= 100) {
      mpuFailCount = 0;
      Serial.println("MPU 응답 없음 — I2C 버스 복구 시도");
      i2cRecover();
      mpu.setup(0x68);
    }
    return;
  }
  mpuFailCount = 0;

  float ax = mpu.getAccX();
  float ay = mpu.getAccY();
  float az = mpu.getAccZ();
  float mag = sqrt(ax * ax + ay * ay + az * az);  // 정지 시 약 1g

  if (mag > FALL_THRESHOLD && millis() - lastFall > FALL_COOLDOWN) {
    lastFall = millis();
    Serial.printf("낙상 감지! 가속도 크기 = %.2f g\n", mag);
    postJson("/api/fall",
             String("{\"device\":\"") + DEVICE_ID + "\",\"magnitude\":" + String(mag, 2) + "}");
  }
}

void setup() {
  Serial.begin(115200);
  pinMode(SWITCH_PIN, INPUT_PULLUP);
  pinMode(LED_PIN, OUTPUT);
  digitalWrite(LED_PIN, HIGH);  // 시작은 미착용 → 소등

  // WiFi 연결 (esp32-tutorial 과 동일)
  WiFi.begin(WIFI_SSID, WIFI_PASSWORD);
  Serial.print("WiFi 연결 중");
  while (WiFi.status() != WL_CONNECTED) {
    delay(500);
    Serial.print(".");
  }
  Serial.println("\n연결됨, IP: " + WiFi.localIP().toString());

  // MPU9250 초기화
  i2cInit();
  if (!mpu.setup(0x68)) {
    Serial.println("MPU9250 을 찾지 못했습니다 — 배선(SDA/SCL/전원)을 확인하세요.");
  } else {
    Serial.println("MPU9250 준비 완료");
  }
}

void loop() {
  handleSwitch();
  handleWearingSync();
  handlePing();
  handleFall();
}
