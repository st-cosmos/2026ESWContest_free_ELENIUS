/* BLE 브로드캐스트 — non-connectable 광고에 상태를 실어 V-PASS 로 보낸다.
 *
 * Manufacturer Specific Data (회사 ID 0xFFFF, 개발용) 페이로드 9바이트:
 *
 *   [0] 'V'  [1] 'J'      매직
 *   [2] 버전 (1)
 *   [3] 장치 번호          CONFIG_JACKET_DEVICE_NUM → V-PASS "jacket-<n>"
 *   [4] 플래그             b0 착용, b1 물 감지, b2 낙하 래치, b3 저전압, b4 스트로브
 *   [5] 시퀀스             1초마다 증가 — 수신측(BlueZ)의 중복 필터를 뚫고
 *                          매 패킷이 콜백되도록 페이로드를 항상 변화시킨다
 *   [6] 낙하 카운터        낙하 이벤트마다 증가 (수신측이 새 낙하를 식별)
 *   [7] 낙하 크기          0.1 g 단위
 *   [8] 배터리             VDD [mV] / 20
 *
 * "핑" 의 의미: 착용(worn=1) 광고가 수신되는 것 자체가 생존 신호다.
 * V-PASS 는 마지막 수신 시각으로 신호 두절(수중 전파 차단)을 판정한다.
 */
#ifndef JACKET_ADV_H_
#define JACKET_ADV_H_

#include <stdbool.h>
#include <stdint.h>

#define JACKET_FLAG_WORN     BIT(0)
#define JACKET_FLAG_WATER    BIT(1)
#define JACKET_FLAG_FALL     BIT(2)
#define JACKET_FLAG_LOW_BATT BIT(3)
#define JACKET_FLAG_STROBE   BIT(4)

struct jacket_adv_status {
	uint8_t flags;
	uint8_t seq;
	uint8_t fall_count;
	uint8_t fall_mag_dg;	/* 0.1 g 단위 */
	uint16_t batt_mv;
};

enum jacket_adv_mode {
	JACKET_ADV_OFF,
	JACKET_ADV_NORMAL,	/* CONFIG_JACKET_ADV_INTERVAL_MS */
	JACKET_ADV_BURST,	/* CONFIG_JACKET_ADV_BURST_INTERVAL_MS */
};

int jacket_adv_init(void);
int jacket_adv_set_mode(enum jacket_adv_mode mode);
enum jacket_adv_mode jacket_adv_mode(void);

/* 현재 상태로 광고 데이터를 갱신 (광고 중이 아니면 무시) */
void jacket_adv_update(const struct jacket_adv_status *st);

#endif /* JACKET_ADV_H_ */
