/* USB 콘솔 벤치 테스트용 `jacket` 셸 명령. */
#include "jacket.h"
#include "jacket_adv.h"
#include "imu.h"
#include "water.h"
#include "strobe.h"
#include "battery.h"

#include <stdlib.h>
#include <string.h>

#include <zephyr/kernel.h>
#include <zephyr/shell/shell.h>

static int cmd_status(const struct shell *sh, size_t argc, char **argv)
{
	ARG_UNUSED(argc); ARG_UNUSED(argv);
	struct jacket_snapshot s;

	jacket_get_snapshot(&s);
	shell_print(sh, "착용: %s   물: %s   익수 래치: %s   스트로브: %s",
		    s.worn ? "예" : "아니오", s.water ? "감지" : "-",
		    s.mob ? "ON" : "-", strobe_active() ? "ON" : "-");
	shell_print(sh, "배터리: %u mV%s   낙하: %u회 (%u.%u g)   seq: %u",
		    s.batt_mv, s.low_batt ? " (저전압)" : "",
		    s.fall_count, s.fall_mag_dg / 10, s.fall_mag_dg % 10,
		    s.seq);
	shell_print(sh, "광고: %s   IMU: %s   전극 Δ: %u.%u%%",
		    jacket_adv_mode() == JACKET_ADV_OFF ? "off" :
		    jacket_adv_mode() == JACKET_ADV_NORMAL ? "normal" : "burst",
		    imu_ok() ? "정상" : "오류",
		    water_last_delta_pm() / 10, water_last_delta_pm() % 10);
	return 0;
}

static int cmd_ledtest(const struct shell *sh, size_t argc, char **argv)
{
	int n = (argc > 1) ? atoi(argv[1]) : 3;

	n = CLAMP(n, 1, 20);
	shell_print(sh, "스트로브 자가진단 %d회", n);
	strobe_selftest(n);
	return 0;
}

static int cmd_strobe(const struct shell *sh, size_t argc, char **argv)
{
	if (argc < 2) {
		shell_print(sh, "usage: jacket strobe on|off");
		return -EINVAL;
	}
	bool on = strcmp(argv[1], "on") == 0;

	strobe_set(on);
	shell_print(sh, "스트로브 %s", on ? "시작 (1 Hz)" : "정지");
	return 0;
}

static int cmd_led(const struct shell *sh, size_t argc, char **argv)
{
	if (argc < 2) {
		shell_print(sh, "usage: jacket led on|off  (상시 점등 — 전류 실측용, 수 초 이상 금지)");
		return -EINVAL;
	}
	bool on = strcmp(argv[1], "on") == 0;

	strobe_force(on);
	shell_print(sh, "LED %s", on ? "상시 점등 — 오래 켜두지 말 것!" : "소등");
	return 0;
}

static int cmd_water(const struct shell *sh, size_t argc, char **argv)
{
	ARG_UNUSED(argc); ARG_UNUSED(argv);
	uint16_t fwd = 0, rev = 0;
	uint16_t bf = 0, br = 0;
	int err = water_measure_once(&fwd, &rev);

	if (err) {
		shell_error(sh, "측정 실패 (%d)", err);
		return err;
	}
	shell_print(sh, "정방향 %u.%u%%  역방향 %u.%u%% (VDD 대비)",
		    fwd / 10, fwd % 10, rev / 10, rev % 10);
	if (water_baseline(&bf, &br)) {
		int delta = MAX(MAX((int)fwd - bf, (int)rev - br), 0);

		shell_print(sh,
			    "기준선 정 %u.%u%% / 역 %u.%u%% — Δ%d.%d%% → %s "
			    "(임계 %d.%d%%, 연속 %d회)",
			    bf / 10, bf % 10, br / 10, br % 10,
			    delta / 10, delta % 10,
			    delta >= CONFIG_JACKET_WATER_DELTA_PERMILLE
				    ? "젖음" : "건조",
			    CONFIG_JACKET_WATER_DELTA_PERMILLE / 10,
			    CONFIG_JACKET_WATER_DELTA_PERMILLE % 10,
			    CONFIG_JACKET_WATER_CONFIRM_COUNT);
	} else {
		shell_print(sh, "기준선 캡처 중 (부팅 직후)");
	}
	return 0;
}

static int cmd_imu(const struct shell *sh, size_t argc, char **argv)
{
	ARG_UNUSED(argc); ARG_UNUSED(argv);
	int32_t mg[3];
	uint32_t mag;

	if (!imu_ok()) {
		shell_error(sh, "IMU 미검출 — 배선/주소(0x6A) 확인");
		return -ENODEV;
	}
	imu_last(mg, &mag);
	shell_print(sh, "X %+d  Y %+d  Z %+d  |a| %u mg (정지 시 약 1000)",
		    mg[0], mg[1], mg[2], mag);
	return 0;
}

static int cmd_batt(const struct shell *sh, size_t argc, char **argv)
{
	ARG_UNUSED(argc); ARG_UNUSED(argv);
	int mv = battery_read_mv();

	if (mv < 0) {
		shell_error(sh, "측정 실패 (%d)", mv);
		return mv;
	}
	shell_print(sh, "VDD %d mV (AA 리튬 2셀: 신품 ~3300, 교체 <%d)",
		    mv, CONFIG_JACKET_LOW_BATT_MV);
	return 0;
}

static int cmd_fall(const struct shell *sh, size_t argc, char **argv)
{
	ARG_UNUSED(argc); ARG_UNUSED(argv);
	shell_print(sh, "낙하 이벤트 시뮬레이션 (착용 상태에서만 처리됨)");
	jacket_simulate_fall();
	return 0;
}

SHELL_STATIC_SUBCMD_SET_CREATE(sub_jacket,
	SHELL_CMD(status, NULL, "현재 상태", cmd_status),
	SHELL_CMD(ledtest, NULL, "스트로브 자가진단 [횟수]", cmd_ledtest),
	SHELL_CMD(strobe, NULL, "익수 스트로브 on|off", cmd_strobe),
	SHELL_CMD(led, NULL, "LED 상시 점등 on|off (전류 실측용)", cmd_led),
	SHELL_CMD(water, NULL, "전극 1회 측정", cmd_water),
	SHELL_CMD(imu, NULL, "가속도 현재값", cmd_imu),
	SHELL_CMD(batt, NULL, "배터리 전압", cmd_batt),
	SHELL_CMD(fall, NULL, "낙하 이벤트 시뮬레이션", cmd_fall),
	SHELL_SUBCMD_SET_END);

SHELL_CMD_REGISTER(jacket, &sub_jacket, "스마트 구명조끼", NULL);
