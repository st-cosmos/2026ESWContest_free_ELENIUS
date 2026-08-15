/* ── LED / 스트로브 회로 테스트 ─────────────────────────────────────────────
 *
 * 검증 대상: LED_EN(P0.13) 단일 핀 → 부스트 + LED 경로 (High = 점등)
 * ※ LED 계통 전원은 배터리(VBAT) — 배터리 미장착이면 안 켜진다.
 *
 * 부팅하면 자동으로 1 Hz / 20 ms 스트로브를 시작한다. USB 콘솔(셸)에서:
 *
 *   led on / off                  상시 점등·소등 (전류 실측용 — 수 초 이상 금지)
 *   led strobe <주기ms> <온ms>    점멸 파라미터 변경 (예: led strobe 500 50)
 *   led stop                      점멸 정지
 *   led test [n]                  100 ms 플래시 n회 (자가진단 패턴)
 *
 * 체크리스트:
 *   1) 소등 상태에서 LED 가 완전히 꺼져 있는가 (잔광 = 풀다운/부스트 누설 문제)
 *   2) `led on` 에서 LED 전류가 목표와 맞는가
 *   3) 20 ms 펄스가 육안으로 또렷한가
 * ──────────────────────────────────────────────────────────────────────── */

#include <stdlib.h>
#include <string.h>

#include <zephyr/kernel.h>
#include <zephyr/drivers/gpio.h>
#include <zephyr/shell/shell.h>
#include <zephyr/usb/usb_device.h>
#include <zephyr/logging/log.h>

LOG_MODULE_REGISTER(led_test);

static const struct gpio_dt_spec led =
	GPIO_DT_SPEC_GET(DT_ALIAS(strobe_led), gpios);

static int period_ms = 1000;
static int on_ms = 20;
static bool strobing = true;
static bool forced;

int main(void)
{
	(void)usb_enable(NULL);

	gpio_pin_configure_dt(&led, GPIO_OUTPUT_INACTIVE);
	LOG_INF("LED 테스트 시작 — 1 Hz / %d ms 스트로브 (셸: led help)", on_ms);

	while (true) {
		if (strobing && !forced) {
			gpio_pin_set_dt(&led, 1);
			k_msleep(on_ms);
			gpio_pin_set_dt(&led, 0);
			k_msleep(MAX(period_ms - on_ms, 10));
		} else {
			k_msleep(100);
		}
	}
	return 0;
}

static int cmd_on(const struct shell *sh, size_t argc, char **argv)
{
	ARG_UNUSED(argc); ARG_UNUSED(argv);
	forced = true;
	gpio_pin_set_dt(&led, 1);
	shell_print(sh, "상시 점등 — 수 초 이상 켜두지 말 것!");
	return 0;
}

static int cmd_off(const struct shell *sh, size_t argc, char **argv)
{
	ARG_UNUSED(argc); ARG_UNUSED(argv);
	forced = false;
	strobing = false;
	gpio_pin_set_dt(&led, 0);
	shell_print(sh, "소등");
	return 0;
}

static int cmd_strobe(const struct shell *sh, size_t argc, char **argv)
{
	if (argc >= 3) {
		period_ms = CLAMP(atoi(argv[1]), 100, 10000);
		on_ms = CLAMP(atoi(argv[2]), 5, period_ms - 50);
	}
	forced = false;
	strobing = true;
	shell_print(sh, "스트로브: 주기 %d ms / 점등 %d ms", period_ms, on_ms);
	return 0;
}

static int cmd_stop(const struct shell *sh, size_t argc, char **argv)
{
	ARG_UNUSED(argc); ARG_UNUSED(argv);
	strobing = false;
	forced = false;
	gpio_pin_set_dt(&led, 0);
	shell_print(sh, "정지");
	return 0;
}

static int cmd_test(const struct shell *sh, size_t argc, char **argv)
{
	int n = (argc > 1) ? CLAMP(atoi(argv[1]), 1, 20) : 3;
	bool prev = strobing;

	strobing = false;
	shell_print(sh, "자가진단 플래시 %d회", n);
	for (int i = 0; i < n; i++) {
		gpio_pin_set_dt(&led, 1);
		k_msleep(100);
		gpio_pin_set_dt(&led, 0);
		k_msleep(200);
	}
	strobing = prev;
	return 0;
}

SHELL_STATIC_SUBCMD_SET_CREATE(sub_led,
	SHELL_CMD(on, NULL, "상시 점등 (전류 실측용)", cmd_on),
	SHELL_CMD(off, NULL, "소등", cmd_off),
	SHELL_CMD(strobe, NULL, "점멸 [주기ms 온ms]", cmd_strobe),
	SHELL_CMD(stop, NULL, "점멸 정지", cmd_stop),
	SHELL_CMD(test, NULL, "짧은 플래시 [횟수]", cmd_test),
	SHELL_SUBCMD_SET_END);

SHELL_CMD_REGISTER(led, &sub_led, "LED/스트로브 테스트", NULL);
