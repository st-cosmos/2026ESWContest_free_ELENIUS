# firmware — 스마트 구명조끼 (E73-2G4M08S1C / BLE)

E73-2G4M08S1C (nRF52840) 커스텀 보드용 구명조끼 펌웨어.
BLE 브로드캐스트(광고 패킷)로 착용/생존/낙하 상태를 V-PASS(라즈베리파이)에 보고한다.

> 이전의 ESP8266(PlatformIO + Wi-Fi/HTTP) 버전은 git 히스토리에 있습니다.
> 이 버전은 **nRF Connect SDK v3.4.0 (Zephyr) + BLE 브로드캐스터** 스택으로 교체된 것이며,
> 툴체인·플래싱 구성은 검증된 [`../../smart-chemical-shelf/firmware`](../../smart-chemical-shelf/firmware) 와 동일합니다.

## 동작

1. **버클 스위치 (착용)** — 마이크로스위치가 닫히면(착용) BLE 광고를 500 ms 주기로
   송출한다. **광고 수신 자체가 생존 신호(핑)** 이고, 사람이 물에 빠지면 2.4 GHz
   전파가 차단되어 광고가 끊긴다 → V-PASS 가 신호 두절 타임아웃으로 익수 판정.
2. **IMU 낙하 감지 (LSM6DSV16X)** — 자유낙하(|a| < 0.4 g, 100 ms)와 충격(> 2.5 g)을
   소프트웨어로 판정한다. 낙하 즉시 낙하 카운터를 올리고 **고속 광고 버스트**를
   시작한다 — 입수 전 공중 구간(0.3~0.7 s)이 마지막 송신 기회이기 때문.
   이후 V-PASS 는 "낙하 + 신호 두절"로 익수를 확정하고 킬스위치 + 자동 신고를 수행한다.
3. **익수 스트로브** — 낙하 후 10초 안에 전극에 물이 감지되면 로컬 익수 확정으로 보고
   1 Hz / 20 ms 고휘도 LED 점멸을 시작한다 (SOLAS 구명조끼등 점멸 대역, 야간 구조용).
4. **탈의/보관** — 버클을 풀면 worn=0 을 60초 광고한 뒤 System OFF 로 잠든다
   (대기 수 µA). 버클이 다시 닫히는 순간 SENSE 웨이크업으로 깨어난다.
   USB 전원이 연결돼 있으면 개발 편의를 위해 잠들지 않는다.

원칙: **1차 익수 판정은 항상 V-PASS 측 신호 소실 타임아웃**이고, 낙하 버스트·물
플래그는 판정을 앞당기는 가속기다. 어떤 패킷이 유실돼도 최종 결과는 틀리지 않는다.

## 광고 프로토콜

non-connectable 광고, Manufacturer Specific Data(회사 ID `0xFFFF`, 개발용) 9바이트.
수신 측 구현은 [`../vpass-application/src/vpass/jacketble.py`](../vpass-application/src/vpass/jacketble.py).

| 오프셋 | 필드 | 의미 |
|---|---|---|
| 0–1 | `'V' 'J'` | 매직 |
| 2 | 버전 | 1 |
| 3 | 장치 번호 | `CONFIG_JACKET_DEVICE_NUM` → V-PASS 의 `jacket-<n>` |
| 4 | 플래그 | b0 착용, b1 물, b2 낙하 래치, b3 저전압, b4 스트로브 |
| 5 | 시퀀스 | 1초마다 증가 (BlueZ 중복 필터 무력화 겸용) |
| 6 | 낙하 카운터 | 이벤트마다 증가 — 수신 측이 증가분으로 새 낙하 식별 |
| 7 | 낙하 크기 | 0.1 g 단위 |
| 8 | 배터리 | VDD [mV] / 20 |

광고 간격: 평상시 500 ms / 낙하 직후 5초간 100 ms 버스트. TX +8 dBm.

## 하드웨어

전원: AA 1.5 V ×2 직렬 → Q1(역삽입 보호) → D2(쇼트키) → **VDD 직결**.
선반 보드와 달리 **VDDH 를 쓰지 않는 normal-voltage 모드**라서:

* `UICR.REGOUT0` 설정이 **필요 없다** (REG0 자체를 안 씀).
* SWD 도 처음부터 VDD 3 V 에서 동작하므로 선반의 "1.8 V 저속 함정"이 없다.
* 배터리 전압은 SAADC 내부 **VDD** 채널로 잰다 (선반은 VDDH/5 였음).

### 핀맵 (`boards/jacket_board.dtsi` 한 곳에서 관리)

| 기능 | 핀 | 회로 | 상태 |
|---|---|---|---|
| LED_EN | P0.13 | 단일 핀 — 부스트 EN + LED 경로 공통, High = 점등, 풀다운 | 점등 확인 (2026-08-15) |
| 전극 A | P0.02 (AIN0) | 47k 직렬 + 470k 풀다운 + PESD3V3L2BT | 확인됨 |
| 전극 B | P0.03 (AIN1) | 상동, 극성 교대 구동 | 확인됨 |
| 버클 스위치 | P0.15 | COM–NO, 직렬 1k + 100nF, 내부 풀업, 착용=닫힘=LOW | 확인됨 |
| IMU SDA | P0.20 | 4.7k 풀업, SA0=GND(0x6A), CS=VDD | 확인됨 |
| IMU SCL | P0.22 | | 확인됨 |

주의: **LED 계통 전원은 배터리(VBAT)** — 배터리 미장착이면 nRF(USB/SWD 전원)는
살아 있어도 LED 는 켜지지 않는다 (실제로 한 번 헤맨 항목).

물 감지는 평상시 두 전극 모두 하이임피던스, 250 ms(낙하 후 50 ms)마다
"측정 전극 방전 → 반대 전극 구동 → 물 경로 충전을 ADC 측정" 을 극성
교대로 수행한다 (전기분해 부식 상쇄, 외부 풀다운 유무 무관).
실측상 이 전극 기하 + 담수의 신호는 VDD 의 3~5% 로 작지만 건조 값이
극도로 안정적이라, **부팅 시 건조 기준선을 캡처하고 증가분(Δ) ≥ 2.0 %VDD**
로 판정한다 (건조 블립 ≤1.5%, 젖음 2.8~5.5% — 2026-08-16 수돗물 실측).
ADC 기준이 VDD/4 라 판정이 배터리 전압과 무관하다.

## 구성

```
CMakeLists.txt / Kconfig / prj.conf   애플리케이션 빌드 + 파라미터 (임계값 전부 Kconfig)
sysbuild.conf, sysbuild/              MCUboot (USB CDC 시리얼 리커버리)
partitions.dtsi                       플래시 레이아웃 (앱/부트로더 공유)
boards/jacket_board.dtsi              핀맵 + 주변장치 (메인·테스트 공용)
boards/nrf52840dk_nrf52840.overlay    메인 펌웨어용 (공용 + 파티션)
src/main.c                            상태기계 (착용/낙하/익수/슬립)
src/jacket_adv.[ch]                   BLE 광고 (페이로드/모드)
src/lsm6dsv16x.[ch]                   IMU 경량 I2C 드라이버
src/imu.[ch]                          60 Hz 폴링 + 자유낙하/충격 판정
src/water.[ch]                        전극 AC 측정 (SAADC 레이시오메트릭)
src/strobe.[ch]                       스트로브 (1 Hz 점멸, 저전압 시 축소)
src/battery.[ch]                      SAADC 내부 VDD 채널
src/jacket_shell.c                    `jacket` 셸 명령 (벤치 테스트)
tests/led-test/                       LED·부스트 회로 단독 테스트 앱
tests/imu-test/                       IMU 배선·판정 단독 테스트 앱
```

## 빌드

NCS 환경 셸에서 (툴체인 함정·해결법은 [선반 build-and-flash.md §2](../../smart-chemical-shelf/firmware/docs/build-and-flash.md) 참고):

```powershell
cd C:\Users\seadmisk\workspace\smart-vpass-system\firmware
west build -b nrf52840dk/nrf52840 --sysbuild -p always .

# 조끼별 장치 번호 (V-PASS 의 jacket-<n>). 기본 빌드는 1 — 여러 개를 동시에
# 운용하려면 보드마다 다른 번호로 빌드한다. MCUboot 는 번호와 무관하게 동일.
west build -b nrf52840dk/nrf52840 --sysbuild -p always -d build-jacket2 . -- -Dfirmware_CONFIG_JACKET_DEVICE_NUM=2

# 테스트 앱 (MCUboot 없음 — SWD 전용, 브링업 단계)
west build -b nrf52840dk/nrf52840 -p always tests/led-test -d tests/led-test/build
west build -b nrf52840dk/nrf52840 -p always tests/imu-test -d tests/imu-test/build
```

산출물: `build/mcuboot/zephyr/zephyr.hex` (부트로더),
`build/firmware/zephyr/zephyr.signed.hex` (SWD용 앱), `zephyr.signed.bin` (USB DFU용).

## 플래싱

### 최초 1회 (SWD)

nRF52840 은 공장 USB 부트로더가 없어 최초 1회는 SWD 가 필요하다.
절차는 선반과 같되 **REGOUT0 단계가 통째로 빠진다** (normal-voltage 모드):

```powershell
$env:NRFUTIL_HOME = "C:\ncs\toolchains\dcbdc366a1\nrfutil\home"
Set-Alias nrfutil "C:\ncs\toolchains\dcbdc366a1\nrfutil\bin\nrfutil.exe"

nrfutil device recover              # 공장 펌웨어 제거 + AP-Protect 해제
nrfutil device pinreset-enable      # 리셋 핀 활성화 (recover 때마다 재실행!)

$opt = "chip_erase_mode=ERASE_RANGES_TOUCHED_BY_FIRMWARE,verify=VERIFY_READ"
nrfutil device program --firmware build\mcuboot\zephyr\zephyr.hex --options $opt
nrfutil device program --firmware build\firmware\zephyr\zephyr.signed.hex --options "$opt,reset=RESET_SYSTEM"
```

* 배터리(3 V) 또는 외부 3.0~3.3 V 를 VDD 에 넣은 상태로 J-Link 를 연결한다
  (VTref 필수). VDD 3 V 라 SWD 1~4 MHz 가 바로 붙는다.
* `west flash` 는 쓰지 않는다 — UICR(PSELRESET)이 지워지는 사례가 있었다.
* 공장 테스트 펌웨어가 슬립에 들어가 접속이 안 되면 [선반 §4.3](../../smart-chemical-shelf/firmware/docs/build-and-flash.md) 의 리셋 버튼 + recover 반복 조합을 쓴다.

### 이후 업데이트 (USB-C만)

리셋 후 5초 안에 (부트로더가 `Smart Lifejacket Bootloader`, VID `0x2FE3` 로 열거):

```powershell
$mc = "$env:USERPROFILE\go\bin\mcumgr.exe"
$cs = "dev=COM7,baud=115200,mtu=512"   # 포트 번호는 장치 관리자에서 확인
& $mc --conntype serial --connstring $cs image upload build\firmware\zephyr\zephyr.signed.bin
& $mc --conntype serial --connstring $cs reset
```

## 벤치 테스트

애플리케이션 USB 콘솔(`Smart Lifejacket`)의 셸:

```
jacket status        착용/물/배터리/낙하/광고 상태 요약
jacket ledtest [n]   스트로브 자가진단 플래시
jacket strobe on     익수 스트로브 강제 (1 Hz)
jacket led on|off    상시 점등 — LED 전류 실측용 (수 초 이상 금지)
jacket water         전극 1회 측정 (정/역방향 %VDD)
jacket imu           가속도 현재값
jacket batt          배터리 전압
jacket fall          낙하 이벤트 시뮬레이션 (V-PASS 연동 시험 — 보드 안 떨어뜨려도 됨)
```

권장 브링업 순서: `tests/led-test` (부스트·LED 전류 확인) → `tests/imu-test`
(I2C·축·자유낙하 확인, 20 cm 낙하로 FREEFALL 로그) → 메인 펌웨어 + MCUboot →
V-PASS 실행 후 착용 토글·`jacket fall`·전극에 젖은 티슈로 통합 시나리오 확인.

## V-PASS 연동

`vpass-application` 은 시작 시 BLE 스캐너(`jacketble.py`, bleak)를 자동으로 띄운다.
광고 수신 → 기존 `DeviceRegistry` (`set_wearing`/`ping`/`fall`) 로 변환되므로
익수 판정 타임아웃(`FALL_PING_TIMEOUT` 5 s / `SIGNAL_LOSS_TIMEOUT` 10 s)과
킬스위치·자동 SOS 흐름은 ESP HTTP 시절과 동일하게 동작한다.
HTTP 엔드포인트와 SimJacket 시뮬레이터도 그대로 병행 지원한다.

환경 변수: `VPASS_BLE=off` (스캔 비활성), `VPASS_BLE_COMPANY_ID` (기본 0xFFFF).

## 남은 항목

1. **핀맵 실보드 대조** — 위 표의 [확인 필요] 항목. `jacket_board.dtsi` 한 파일만 수정하면 된다.
2. 물 임계값 실측 튜닝 — 해수/담수/젖은 원단/물보라 각각의 %VDD 를 `jacket water` 로 수집.
3. 자유낙하 파라미터 현장 검증 (파도·요동 오탐 여부).
4. 온칩 자유낙하 인터럽트(INT1) 전환 — 폴링 대비 소비전류 추가 절감 여지 (현재도 AA 2셀 기준 충분).
5. 착용 중 저전력 최적화 — 광고 간격/IMU ODR 을 늘리면 수명이 더 늘어난다 (실측 후 판단).
