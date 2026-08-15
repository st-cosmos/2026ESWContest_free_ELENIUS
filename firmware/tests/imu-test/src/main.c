/* ── LSM6DSV16X IMU 테스트 ─────────────────────────────────────────────────
 *
 * 검증 대상: I2C 배선(SDA/SCL), 주소(SA0=GND → 0x6A), 축 방향,
 *            자유낙하/충격 판정 파라미터.
 *
 * 부팅하면 WHO_AM_I 확인 후 2 Hz 로 가속도를 로그에 찍고, 자유낙하
 * (|a| < 400 mg, 100 ms 지속)와 충격(|a| > 2.5 g)을 이벤트로 출력한다.
 * 보드를 손에 들고 20 cm 만 자유낙하시켜도 FREEFALL 이 찍혀야 정상.
 *
 * USB 콘솔(셸):
 *   imu raw              현재 XYZ + 크기 1회 출력
 *   imu stream on|off    2 Hz 스트림 토글
 * ──────────────────────────────────────────────────────────────────────── */

#include "lsm6dsv16x.h"

#include <math.h>
#include <string.h>

#include <zephyr/kernel.h>
#include <zephyr/shell/shell.h>
#include <zephyr/usb/usb_device.h>
#include <zephyr/logging/log.h>

LOG_MODULE_REGISTER(imu_test);

#define FF_THRESHOLD_MG   400
#define FF_MIN_MS         100
#define IMPACT_THRESHOLD_MG 2500
#define SAMPLE_PERIOD_MS  16

static bool stream = true;
static int32_t cur_mg[3];
static uint32_t cur_mag;

static uint32_t magnitude_mg(const int32_t mg[3])
{
	int64_t s = (int64_t)mg[0] * mg[0] + (int64_t)mg[1] * mg[1] +
		    (int64_t)mg[2] * mg[2];

	return (uint32_t)sqrt((double)s);
}

int main(void)
{
	(void)usb_enable(NULL);

	LOG_INF("IMU 테스트 시작");
	if (lsm6dsv16x_init() != 0) {
		LOG_ERR("IMU 초기화 실패 — SDA/SCL 배선, 풀업, SA0(0x6A) 확인");
		LOG_ERR("10초 후 재시도를 반복합니다");
		while (lsm6dsv16x_init() != 0) {
			k_msleep(10000);
		}
	}

	int ff_ms = 0;
	bool ff_reported = false;
	int64_t last_print = 0;

	while (true) {
		k_msleep(SAMPLE_PERIOD_MS);

		int32_t mg[3];

		if (lsm6dsv16x_read_mg(mg) != 0) {
			continue;
		}
		memcpy(cur_mg, mg, sizeof(cur_mg));
		cur_mag = magnitude_mg(mg);

		/* 자유낙하 */
		if (cur_mag < FF_THRESHOLD_MG) {
			ff_ms += SAMPLE_PERIOD_MS;
			if (ff_ms >= FF_MIN_MS && !ff_reported) {
				ff_reported = true;
				LOG_WRN(">>> FREEFALL (%d ms, |a|=%u mg)",
					ff_ms, cur_mag);
			}
		} else if (cur_mag > 800) {
			if (ff_reported) {
				LOG_INF("자유낙하 종료 (총 %d ms)", ff_ms);
			}
			ff_ms = 0;
			ff_reported = false;
		}

		/* 충격 */
		if (cur_mag > IMPACT_THRESHOLD_MG) {
			LOG_WRN(">>> IMPACT |a|=%u mg", cur_mag);
		}

		/* 2 Hz 스트림 */
		int64_t now = k_uptime_get();

		if (stream && now - last_print >= 500) {
			last_print = now;
			LOG_INF("X %+6d  Y %+6d  Z %+6d  |a| %5u mg",
				mg[0], mg[1], mg[2], cur_mag);
		}
	}
	return 0;
}

static int cmd_raw(const struct shell *sh, size_t argc, char **argv)
{
	ARG_UNUSED(argc); ARG_UNUSED(argv);
	shell_print(sh, "X %+d  Y %+d  Z %+d  |a| %u mg",
		    cur_mg[0], cur_mg[1], cur_mg[2], cur_mag);
	return 0;
}

static int cmd_stream(const struct shell *sh, size_t argc, char **argv)
{
	if (argc > 1) {
		stream = strcmp(argv[1], "on") == 0;
	}
	shell_print(sh, "스트림 %s", stream ? "on" : "off");
	return 0;
}

SHELL_STATIC_SUBCMD_SET_CREATE(sub_imu,
	SHELL_CMD(raw, NULL, "현재 XYZ 1회 출력", cmd_raw),
	SHELL_CMD(stream, NULL, "2 Hz 스트림 on|off", cmd_stream),
	SHELL_SUBCMD_SET_END);

SHELL_CMD_REGISTER(imu, &sub_imu, "IMU 테스트", NULL);
