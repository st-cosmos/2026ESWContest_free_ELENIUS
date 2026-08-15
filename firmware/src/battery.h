/* 배터리(VDD) 전압 측정 — SAADC 내부 VDD 채널, 분압 저항 없음. */
#ifndef BATTERY_H_
#define BATTERY_H_

#include <stdint.h>

int battery_init(void);

/* VDD 를 mV 로 반환. 실패 시 음수(-errno). */
int battery_read_mv(void);

#endif /* BATTERY_H_ */
