/* IMU 낙하 감지 — 60 Hz 폴링 + 소프트웨어 판정.
 *
 * 자유낙하: |a| < CONFIG_JACKET_FREEFALL_THRESHOLD_MG 가
 *           CONFIG_JACKET_FREEFALL_MIN_MS 이상 지속 (입수 낙하)
 * 충격:     |a| > CONFIG_JACKET_IMPACT_THRESHOLD_MG (갑판 낙상)
 */
#ifndef IMU_H_
#define IMU_H_

#include <stdbool.h>
#include <stdint.h>

/* peak_mg: 이벤트 전후 최대 |a| (충격 크기), freefall: 자유낙하 여부.
 * 콜백은 IMU 스레드 컨텍스트에서 호출된다 — 가볍게 유지할 것. */
typedef void (*imu_fall_cb_t)(uint32_t peak_mg, bool freefall);

int imu_init(void);
void imu_start(imu_fall_cb_t on_fall);

bool imu_ok(void);

/* 최근 샘플 (셸/테스트용) */
void imu_last(int32_t mg[3], uint32_t *mag_mg);

#endif /* IMU_H_ */
