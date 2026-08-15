#
# Smart lifejacket - E73-2G4M08S1C (nRF52840) + LSM6DSV16X
#
cmake_minimum_required(VERSION 3.20.0)

find_package(Zephyr REQUIRED HINTS $ENV{ZEPHYR_BASE})
project(smart_lifejacket)

target_sources(app PRIVATE
  src/main.c
  src/lsm6dsv16x.c
  src/imu.c
  src/water.c
  src/battery.c
  src/strobe.c
  src/jacket_adv.c
  src/jacket_shell.c
)

target_include_directories(app PRIVATE src)
