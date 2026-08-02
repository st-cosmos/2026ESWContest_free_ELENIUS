# 스마트 구명조끼 펌웨어 (ESP8266)

VSCode + PlatformIO 로 개발하는 ESP8266(esp12e / NodeMCU) 펌웨어입니다.
(esp32-tutorial 과 동일한 보드·빌드 설정)

## 기능

1. **외장 스위치**를 누르면 착용 여부를 토글 → 서버에 `POST /api/wearing`
   (전송 실패 시 성공할 때까지 2초 간격 재시도 — 탈의 알림 유실로 인한
   익수 오경보 방지)
2. **착용 상태**이면 3초마다 서버로 생존 신호 → `POST /api/ping`
3. **MPU9250** 으로 큰 낙상(가속도 급변)을 감지하면 → `POST /api/fall`

## 배선 (esp12e / NodeMCU)

| 부품 | 핀 | GPIO |
|------|----|------|
| 외장 스위치 | D5 | GPIO14 (INPUT_PULLUP, 반대편은 GND) |
| MPU9250 SDA | D2 | GPIO4 |
| MPU9250 SCL | D1 | GPIO5 |
| 상태 LED | D4 | GPIO2 (보드 내장, 착용 시 점등) |

MPU9250 는 VCC(3.3V) / GND 도 연결하세요. I2C 주소는 기본 `0x68` 입니다.

## 설정

`include/config.example.h` 를 `config.h` 로 복사한 뒤 값을 채웁니다.

```bash
copy include\config.example.h include\config.h   # Windows
```

```c
#define WIFI_SSID     "우리집-와이파이"
#define WIFI_PASSWORD "비밀번호"
#define SERVER_URL    "http://192.168.0.10:8000"   // 서버 PC 의 IP
#define DEVICE_ID     "jacket-1"                     // 구명조끼 이름
```

## 빌드 · 업로드

- PlatformIO: **Build** → **Upload** → **Monitor** (115200 baud)
- 첫 빌드 시 `hideakitai/MPU9250` 라이브러리가 자동 설치됩니다.

## 낙상 감지 튜닝

`src/main.cpp` 의 `FALL_THRESHOLD`(기본 2.5g) 값으로 민감도를 조절합니다.
값을 낮추면 더 민감하게, 높이면 더 큰 충격에만 반응합니다.
