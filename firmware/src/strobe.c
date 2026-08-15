/* LED_EN(P0.13) 단일 핀이 부스트 EN 과 LED 경로를 함께 제어한다.
 * High = 점등 (2026-08-15 실기기 확인). LED 계통 전원은 배터리(VBAT).
 *
 * 펌웨어가 멈췄을 때 LED 가 상시 점등으로 굳는 게 최악의 고장 모드라
 * (~100 mA 상시 → 전지 소진) 점멸은 워크큐 타이머로만 제어하고, off 경로가
 * 항상 스케줄되도록 한다. 보드 풀다운이 리셋 중 소등을 보장한다.
 */
#include "strobe.h"

#include <zephyr/kernel.h>
#include <zephyr/drivers/gpio.h>
#include <zephyr/logging/log.h>

LOG_MODULE_REGISTER(strobe, CONFIG_JACKET_LOG_LEVEL);

static const struct gpio_dt_spec led =
	GPIO_DT_SPEC_GET(DT_ALIAS(strobe_led), gpios);

static atomic_t active;
static atomic_t low_batt;
static atomic_t forced;
static bool lit;		/* 점멸 상태기계용 — 워크큐에서만 접근 */

static void flash_work_fn(struct k_work *work);
static K_WORK_DELAYABLE_DEFINE(flash_work, flash_work_fn);

static int on_time_ms(void)
{
	int on = CONFIG_JACKET_STROBE_ON_MS;

	return atomic_get(&low_batt) ? MAX(on / 2, 5) : on;
}

static void flash_work_fn(struct k_work *work)
{
	ARG_UNUSED(work);

	if (!atomic_get(&active)) {
		lit = false;
		if (!atomic_get(&forced)) {
			gpio_pin_set_dt(&led, 0);
		}
		return;
	}

	if (lit) {
		lit = false;
		gpio_pin_set_dt(&led, 0);
		k_work_reschedule(&flash_work,
			K_MSEC(CONFIG_JACKET_STROBE_PERIOD_MS - on_time_ms()));
	} else {
		lit = true;
		gpio_pin_set_dt(&led, 1);
		k_work_reschedule(&flash_work, K_MSEC(on_time_ms()));
	}
}

int strobe_init(void)
{
	if (!gpio_is_ready_dt(&led)) {
		return -ENODEV;
	}
	return gpio_pin_configure_dt(&led, GPIO_OUTPUT_INACTIVE);
}

void strobe_set(bool on)
{
	bool was = atomic_set(&active, on ? 1 : 0);

	if (on && !was) {
		LOG_WRN("익수 스트로브 시작 (1 Hz)");
		k_work_reschedule(&flash_work, K_NO_WAIT);
	} else if (!on && was) {
		LOG_INF("스트로브 정지");
		k_work_reschedule(&flash_work, K_NO_WAIT);
	}
}

bool strobe_active(void)
{
	return atomic_get(&active);
}

void strobe_set_low_batt(bool low)
{
	atomic_set(&low_batt, low ? 1 : 0);
}

void strobe_selftest(int n)
{
	if (atomic_get(&active)) {
		return;		/* 익수 스트로브 우선 */
	}
	for (int i = 0; i < n; i++) {
		gpio_pin_set_dt(&led, 1);
		k_msleep(30);
		gpio_pin_set_dt(&led, 0);
		k_msleep(120);
	}
}

void strobe_force(bool on)
{
	atomic_set(&forced, on ? 1 : 0);
	if (!atomic_get(&active)) {
		gpio_pin_set_dt(&led, on ? 1 : 0);
	}
}
