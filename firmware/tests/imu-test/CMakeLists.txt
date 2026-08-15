#
# LSM6DSV16X IMU 단독 테스트 (I2C 배선·주소·낙하 판정 파라미터 검증)
#
# MCUboot 없이 0번지에 링크되는 독립 앱 — 초기 브링업 단계에서 SWD 로 굽는다.
# 메인 펌웨어의 드라이버(src/lsm6dsv16x.c)를 그대로 가져와 같이 검증한다.
#
cmake_minimum_required(VERSION 3.20.0)

find_package(Zephyr REQUIRED HINTS $ENV{ZEPHYR_BASE})
project(jacket_imu_test)

target_sources(app PRIVATE
  src/main.c
  ../../src/lsm6dsv16x.c
)

target_include_directories(app PRIVATE ../../src)
