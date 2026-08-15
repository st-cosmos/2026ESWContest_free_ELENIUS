/* 메인 상태기계가 셸에 노출하는 인터페이스. */
#ifndef JACKET_H_
#define JACKET_H_

#include <stdbool.h>
#include <stdint.h>

struct jacket_snapshot {
	bool worn;
	bool water;
	bool mob;		/* 로컬 익수 래치 (낙하+물) */
	bool low_batt;
	uint8_t fall_count;
	uint16_t fall_mag_dg;
	uint16_t batt_mv;
	uint8_t seq;
};

void jacket_get_snapshot(struct jacket_snapshot *out);

/* 낙하 이벤트 시뮬레이션 — 보드를 떨어뜨리지 않고 V-PASS 연동을 시험 */
void jacket_simulate_fall(void);

#endif /* JACKET_H_ */
