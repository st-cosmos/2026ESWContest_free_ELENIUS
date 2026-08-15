#include "imu.h"
#include "lsm6dsv16x.h"

#include <math.h>
#include <string.h>

#include <zephyr/kernel.h>
#include <zephyr/logging/log.h>

LOG_MODULE_REGISTER(imu, CONFIG_JACKET_LOG_LEVEL);

#define SAMPLE_PERIOD_MS 16	/* 60 Hz ODR 에 맞춘 폴링 주기 */

static imu_fall_cb_t fall_cb;
static bool ok;

static struct k_spinlock last_lock;
static int32_t last_mg[3];
static uint32_t last_mag;

static K_THREAD_STACK_DEFINE(imu_stack, 1536);
static struct k_thread imu_thread;

static uint32_t magnitude_mg(const int32_t mg[3])
{
	int64_t s = (int64_t)mg[0] * mg[0] + (int64_t)mg[1] * mg[1] +
		    (int64_t)mg[2] * mg[2];

	return (uint32_t)sqrt((double)s);
}

static void imu_loop(void *a, void *b, void *c)
{
	ARG_UNUSED(a); ARG_UNUSED(b); ARG_UNUSED(c);

	int32_t mg[3];
	int ff_ms = 0;		/* 자유낙하 지속 시간 누적 */
	bool ff_reported = false;
	int64_t last_event_ms = -CONFIG_JACKET_FALL_COOLDOWN_S * 1000;
	uint32_t peak = 0;
	int fail = 0;

	while (true) {
		k_msleep(SAMPLE_PERIOD_MS);

		int err = lsm6dsv16x_read_mg(mg);

		if (err == -EAGAIN) {
			continue;
		}
		if (err) {
			/* 버스가 계속 죽어 있으면 재초기화 시도 */
			if (++fail >= 100) {
				fail = 0;
				LOG_WRN("IMU 응답 없음 — 재초기화");
				ok = (lsm6dsv16x_init() == 0);
			}
			continue;
		}
		fail = 0;

		uint32_t mag = magnitude_mg(mg);

		K_SPINLOCK(&last_lock) {
			memcpy(last_mg, mg, sizeof(last_mg));
			last_mag = mag;
		}

		int64_t now = k_uptime_get();
		bool cooldown = now - last_event_ms <
				CONFIG_JACKET_FALL_COOLDOWN_S * 1000;

		peak = MAX(peak, mag);

		/* 자유낙하: 저가속 상태 지속 시간 측정 */
		if (mag < CONFIG_JACKET_FREEFALL_THRESHOLD_MG) {
			ff_ms += SAMPLE_PERIOD_MS;
			if (ff_ms >= CONFIG_JACKET_FREEFALL_MIN_MS &&
			    !ff_reported && !cooldown) {
				ff_reported = true;
				last_event_ms = now;
				LOG_WRN("자유낙하 감지 (%d ms)", ff_ms);
				if (fall_cb) {
					fall_cb(MAX(peak, 1000), true);
				}
				peak = 0;
			}
		} else if (mag > 800) {
			/* 정상 중력 부근으로 복귀 → 다음 낙하 감지 준비 */
			ff_ms = 0;
			ff_reported = false;
		}

		/* 충격 (갑판 낙상 등) */
		if (mag > CONFIG_JACKET_IMPACT_THRESHOLD_MG && !cooldown) {
			last_event_ms = now;
			LOG_WRN("충격 감지 (%u mg)", mag);
			if (fall_cb) {
				fall_cb(mag, false);
			}
			peak = 0;
		}
	}
}

int imu_init(void)
{
	int err = lsm6dsv16x_init();

	ok = (err == 0);
	return err;
}

void imu_start(imu_fall_cb_t on_fall)
{
	fall_cb = on_fall;
	k_thread_create(&imu_thread, imu_stack,
			K_THREAD_STACK_SIZEOF(imu_stack),
			imu_loop, NULL, NULL, NULL,
			K_PRIO_PREEMPT(6), 0, K_NO_WAIT);
	k_thread_name_set(&imu_thread, "imu");
}

bool imu_ok(void)
{
	return ok;
}

void imu_last(int32_t mg[3], uint32_t *mag_mg)
{
	K_SPINLOCK(&last_lock) {
		if (mg) {
			memcpy(mg, last_mg, sizeof(last_mg));
		}
		if (mag_mg) {
			*mag_mg = last_mag;
		}
	}
}
