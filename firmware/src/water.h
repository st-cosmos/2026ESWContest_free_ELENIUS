/* 물 감지 — 전극 2핀 극성 교대(AC) "방전 후 충전" 측정 + 기준선 대비 판정. */
#ifndef WATER_H_
#define WATER_H_

#include <stdbool.h>
#include <stdint.h>

int water_init(void);
void water_start(void);

/* 디바운스 완료된 현재 젖음 상태 */
bool water_wet(void);

/* 낙하 직후 고속 측정 모드 (CONFIG_JACKET_WATER_FAST_WINDOW_S 동안) */
void water_boost(void);

/* 마지막으로 물이 감지된 시각(uptime ms). 감지 이력이 없으면 0 */
int64_t water_last_wet_ms(void);

/* 1회 측정 (셸/테스트용): 각 방향의 비구동 전극 전압, VDD 대비 퍼밀(0~1000) */
int water_measure_once(uint16_t *fwd_pm, uint16_t *rev_pm);

/* 부팅 시 캡처된 건조 기준선 (퍼밀). 아직 캡처 전이면 false */
bool water_baseline(uint16_t *fwd_pm, uint16_t *rev_pm);

/* 마지막 측정의 기준선 대비 증가분 (퍼밀, 두 방향 중 최대) */
uint16_t water_last_delta_pm(void);

#endif /* WATER_H_ */
