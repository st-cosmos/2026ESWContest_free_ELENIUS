#
# LED / 스트로브 회로 단독 테스트 (SX1308 + Q2, LED_EN 핀)
#
# MCUboot 없이 0번지에 링크되는 독립 앱 — 초기 브링업 단계에서 SWD 로 굽는다.
# 부트로더가 이미 설치된 보드에 이걸 SWD 로 구우면 부트로더가 지워지므로,
# 브링업이 끝나면 메인 펌웨어를 sysbuild 로 다시 구울 것.
#
cmake_minimum_required(VERSION 3.20.0)

find_package(Zephyr REQUIRED HINTS $ENV{ZEPHYR_BASE})
project(jacket_led_test)

target_sources(app PRIVATE src/main.c)
