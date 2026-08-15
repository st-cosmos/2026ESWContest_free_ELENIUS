# V-PASS Kill Switch Firmware

ESP32-C3 SuperMini + PlatformIO 데모용 킬 스위치 펌웨어입니다.

## 동작

릴레이는 normal close(NC) 배선 기준입니다.

| 명령 | 릴레이 | 모형 배 전원 | LED |
| --- | --- | --- | --- |
| `ON` | 여자됨 | 차단 | 빨강 |
| `OFF` | 비여자 | 연결 | 초록 |

펌웨어는 전원 투입 시 fail-safe 쪽인 `ON`으로 시작합니다. V-PASS 앱에서 승선 확인 후 시동 잠금이 풀리면 BLE로 `OFF`를 보내 모형 배가 운항할 수 있습니다.

## 배선

상위 `c3test`와 같은 핀 배치를 사용합니다.

| ESP32-C3 GPIO | 연결 |
| --- | --- |
| `GPIO4` | 릴레이 IN |
| `GPIO2` | 빨간 LED |
| `GPIO3` | 초록 LED |
| `3V3` / `GND` | LED/릴레이 모듈 전원 기준 |

릴레이 접점은 모형 배 전원선을 `COM`과 `NC`에 넣습니다. 릴레이가 `OFF`일 때 NC가 닫혀 배가 켜지고, 릴레이가 `ON`일 때 NC가 열려 배가 꺼집니다.

## BLE

- Device name: `VPass Kill Switch`
- Service UUID: `8d4f2a10-5f5f-4c0b-9a8c-0f6f7f7b2a10`
- Command characteristic UUID: `8d4f2a11-5f5f-4c0b-9a8c-0f6f7f7b2a10`

Characteristic에 UTF-8 문자열을 write합니다.

- 차단: `ON`, `1`, `cut`, `lock`, `engage`, `relay:on`
- 운항 허용: `OFF`, `0`, `run`, `unlock`, `restore`, `relay:off`
- 상태 확인: `status`, `?`

## PlatformIO

VS Code에서 `kill-switch` 폴더를 PlatformIO 프로젝트로 열고 Upload하면 됩니다.

```bash
pio run -t upload
pio device monitor
```

