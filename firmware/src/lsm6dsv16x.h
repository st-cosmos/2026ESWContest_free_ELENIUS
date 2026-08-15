/* LSM6DSV16X 경량 I2C 드라이버 — 가속도 전용.
 *
 * Zephyr 인트리 센서 드라이버 대신 필요한 레지스터만 직접 다룬다.
 * 낙하 판정은 소프트웨어(imu.c)에서 하므로 온칩 자유낙하 인터럽트는
 * 쓰지 않는다 (INT1 배선 확정 후 확장 여지).
 */
#ifndef LSM6DSV16X_H_
#define LSM6DSV16X_H_

#include <stdbool.h>
#include <stdint.h>

/* 초기화: SW 리셋 → BDU/IF_INC → ±8g → 60 Hz 고성능 모드. 0 또는 -errno */
int lsm6dsv16x_init(void);

bool lsm6dsv16x_present(void);

/* 새 샘플이 있으면 mg 단위 XYZ 를 채우고 0, 데이터 없음 -EAGAIN, 오류 -EIO */
int lsm6dsv16x_read_mg(int32_t mg[3]);

#endif /* LSM6DSV16X_H_ */
