/* 구조용 스트로브 LED (SX1308 부스트 정전류, LED_EN 단일 GPIO). */
#ifndef STROBE_H_
#define STROBE_H_

#include <stdbool.h>

int strobe_init(void);

/* 익수 스트로브 래치 on/off (1 Hz, CONFIG_JACKET_STROBE_ON_MS 펄스) */
void strobe_set(bool on);
bool strobe_active(void);

/* 저전압이면 펄스 폭을 절반으로 (브라운아웃 예방) */
void strobe_set_low_batt(bool low);

/* 램프 테스트: n 회 짧은 플래시 (블로킹, 셸 `jacket ledtest` 용) */
void strobe_selftest(int n);

/* LED 상시 점등 강제 (셸 테스트용). strobe_set 과 배타적으로 쓸 것 */
void strobe_force(bool on);

#endif /* STROBE_H_ */
