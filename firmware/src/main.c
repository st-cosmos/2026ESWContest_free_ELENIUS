/* ── 스마트 구명조끼 펌웨어 (E73-2G4M08S1C / nRF52840, BLE) ────────────────
 *
 * ESP8266 + WiFi/HTTP 버전을 BLE 브로드캐스트로 교체한 것. V-PASS(라즈베리
 * 파이)는 연결 없이 광고 패킷만 수신한다 (수중 전파 차단 = 신호 두절 원리).
 *
 *   1) 버클 스위치 닫힘 = 착용 → worn=1 광고를 주기 송출 (광고 자체가 핑)
 *   2) IMU 자유낙하/충격 감지 → 낙하 카운터 증가 + 고속 광고 버스트.
 *      이후 V-PASS 가 신호 두절을 확인하면 익수 판정 → 킬스위치 + 자동 신고
 *   3) 낙하 후 물 감지(전극) → 로컬 익수 확정 → LED 스트로브 (야간 구조)
 *
 * 원칙 (회로 설계 대화에서 확정): 1차 익수 판정은 항상 "신호 소실 타임아웃"
 * (V-PASS 측)이고, 낙하 버스트·물 플래그는 판정을 앞당기는 가속기일 뿐이다.
 * 어떤 패킷이 유실되어도 최종 결과는 틀리지 않는다.
 * ──────────────────────────────────────────────────────────────────────── */

#include "jacket.h"
#include "jacket_adv.h"
#include "imu.h"
#include "water.h"
#include "strobe.h"
#include "battery.h"

#include <zephyr/kernel.h>
#include <zephyr/drivers/gpio.h>
#include <zephyr/usb/usb_device.h>
#include <zephyr/sys/poweroff.h>
#include <zephyr/logging/log.h>
#include <hal/nrf_power.h>

LOG_MODULE_REGISTER(jacket, CONFIG_JACKET_LOG_LEVEL);

#define TICK_MS 100

static const struct gpio_dt_spec buckle =
	GPIO_DT_SPEC_GET(DT_ALIAS(buckle_sw), gpios);

/* ── 상태 ── */
static struct {
	bool worn;
	bool mob;		/* 낙하+물 로컬 래치 */
	bool low_batt;
	uint8_t seq;
	uint8_t fall_count;
	uint8_t fall_mag_dg;
	int batt_mv;
	int64_t fall_ms;	/* 마지막 낙하 이벤트 시각 (0 = 없음) */
	int64_t doff_ms;	/* 탈의 시각 (0 = 착용 중/해당 없음) */
	int64_t burst_until_ms;
	int64_t fall_flag_until_ms;
} st;
static K_MUTEX_DEFINE(st_lock);

static K_SEM_DEFINE(fall_sem, 0, 1);
static uint32_t fall_peak_mg;
static bool fall_was_freefall;

/* IMU 스레드 컨텍스트 — 기록만 하고 처리는 메인 루프에서 */
static void on_fall_event(uint32_t peak_mg, bool freefall)
{
	fall_peak_mg = peak_mg;
	fall_was_freefall = freefall;
	k_sem_give(&fall_sem);
}

void jacket_simulate_fall(void)
{
	on_fall_event(3200, true);
}

static bool usb_powered(void)
{
	return nrf_power_usbregstatus_vbusdet_get(NRF_POWER);
}

static void adv_push(void)
{
	struct jacket_adv_status a;
	int64_t now = k_uptime_get();

	k_mutex_lock(&st_lock, K_FOREVER);
	a.flags = (st.worn ? JACKET_FLAG_WORN : 0) |
		  (water_wet() ? JACKET_FLAG_WATER : 0) |
		  (now < st.fall_flag_until_ms ? JACKET_FLAG_FALL : 0) |
		  (st.low_batt ? JACKET_FLAG_LOW_BATT : 0) |
		  (strobe_active() ? JACKET_FLAG_STROBE : 0);
	a.seq = st.seq;
	a.fall_count = st.fall_count;
	a.fall_mag_dg = st.fall_mag_dg;
	a.batt_mv = (uint16_t)MAX(st.batt_mv, 0);
	k_mutex_unlock(&st_lock);

	jacket_adv_update(&a);
}

static void handle_fall(void)
{
	int64_t now = k_uptime_get();

	k_mutex_lock(&st_lock, K_FOREVER);
	if (!st.worn) {
		/* 미착용 상태의 충격(운반 등)은 무시 — ESP 버전과 동일 */
		k_mutex_unlock(&st_lock);
		return;
	}
	st.fall_count++;
	st.fall_mag_dg = (uint8_t)MIN(fall_peak_mg / 100, 255);
	st.fall_ms = now;
	st.fall_flag_until_ms = now + 30 * 1000;
	st.burst_until_ms = now + CONFIG_JACKET_ADV_BURST_DURATION_S * 1000;
	k_mutex_unlock(&st_lock);

	LOG_WRN("낙하 이벤트 #%u (%s, %u.%u g) — 광고 버스트 시작",
		st.fall_count, fall_was_freefall ? "자유낙하" : "충격",
		fall_peak_mg / 1000, (fall_peak_mg % 1000) / 100);

	/* 입수 전 공중 구간이 마지막 송신 기회 — 즉시 갱신 + 고속 광고 */
	adv_push();
	jacket_adv_set_mode(JACKET_ADV_BURST);
	water_boost();
}

static void enter_storage_sleep(void)
{
	LOG_INF("System OFF — 버클이 닫히면 깨어남");
	/* 로그가 나가도록 잠시 대기 */
	k_msleep(100);
	jacket_adv_set_mode(JACKET_ADV_OFF);
	/* 스위치 핀 SENSE 웨이크업 (착용 = active) */
	gpio_pin_interrupt_configure_dt(&buckle, GPIO_INT_LEVEL_ACTIVE);
	sys_poweroff();
}

void jacket_get_snapshot(struct jacket_snapshot *out)
{
	k_mutex_lock(&st_lock, K_FOREVER);
	out->worn = st.worn;
	out->water = water_wet();
	out->mob = st.mob;
	out->low_batt = st.low_batt;
	out->fall_count = st.fall_count;
	out->fall_mag_dg = st.fall_mag_dg;
	out->batt_mv = (uint16_t)MAX(st.batt_mv, 0);
	out->seq = st.seq;
	k_mutex_unlock(&st_lock);
}

int main(void)
{
	int err = usb_enable(NULL);

	if (err && err != -EALREADY) {
		/* USB 없이도(현장 배터리 구동) 계속 동작해야 한다 */
		LOG_WRN("usb_enable 실패 (%d)", err);
	}

	LOG_INF("스마트 구명조끼 펌웨어 시작 (장치 번호 %d)",
		CONFIG_JACKET_DEVICE_NUM);

	if (!gpio_is_ready_dt(&buckle)) {
		LOG_ERR("버클 스위치 GPIO 준비 안 됨");
	} else {
		gpio_pin_configure_dt(&buckle, GPIO_INPUT);
	}

	strobe_init();
	battery_init();
	if (water_init() == 0) {
		water_start();
	} else {
		LOG_ERR("물 감지 초기화 실패");
	}
	if (imu_init() == 0) {
		imu_start(on_fall_event);
	} else {
		LOG_ERR("IMU 초기화 실패 — 낙하 감지 비활성 (셸 jacket fall 로 시험 가능)");
	}
	if (jacket_adv_init() != 0) {
		LOG_ERR("BLE 초기화 실패");
	}

	st.batt_mv = battery_read_mv();

	/* System OFF 에서 버클 닫힘으로 깨어난 직후라면 곧바로 착용 처리된다 */
	int sw_stable = -1;		/* 디바운스된 스위치 값 */
	int sw_last_raw = -1;
	int sw_same_ticks = 0;
	int64_t last_1s = 0;
	int64_t last_batt = 0;

	while (true) {
		k_msleep(TICK_MS);
		int64_t now = k_uptime_get();

		/* ── 버클 스위치 디바운스 (3틱 = 300 ms) ── */
		int raw = gpio_pin_get_dt(&buckle);	/* 1 = 착용(닫힘) */

		if (raw == sw_last_raw) {
			sw_same_ticks++;
		} else {
			sw_same_ticks = 0;
			sw_last_raw = raw;
		}

		if (sw_same_ticks >= 3 && raw >= 0 && raw != sw_stable) {
			sw_stable = raw;
			k_mutex_lock(&st_lock, K_FOREVER);
			st.worn = (raw == 1);
			if (st.worn) {
				st.doff_ms = 0;
				st.fall_ms = 0;
				st.mob = false;
			} else {
				st.doff_ms = now;
				st.mob = false;
			}
			k_mutex_unlock(&st_lock);

			if (raw == 1) {
				/* 착용 확인은 V-PASS UI 로 충분 — 별도 점등 없음 */
				LOG_INF("착용됨 — 광고 시작");
				jacket_adv_set_mode(JACKET_ADV_NORMAL);
				adv_push();
			} else {
				LOG_INF("탈의됨 — %d초 후 광고 종료",
					CONFIG_JACKET_DOFF_ADV_TIMEOUT_S);
				strobe_set(false);
				jacket_adv_set_mode(JACKET_ADV_NORMAL);
				adv_push();
			}
		}

		/* ── 낙하 이벤트 처리 ── */
		if (k_sem_take(&fall_sem, K_NO_WAIT) == 0) {
			handle_fall();
		}

		/* ── 버스트 종료 ── */
		k_mutex_lock(&st_lock, K_FOREVER);
		bool worn = st.worn;
		bool burst_over = st.burst_until_ms &&
				  now >= st.burst_until_ms;
		if (burst_over) {
			st.burst_until_ms = 0;
		}
		int64_t fall_ms = st.fall_ms;
		int64_t doff_ms = st.doff_ms;
		bool mob = st.mob;
		k_mutex_unlock(&st_lock);

		if (burst_over && jacket_adv_mode() == JACKET_ADV_BURST) {
			jacket_adv_set_mode(JACKET_ADV_NORMAL);
		}

		/* ── 로컬 익수 확정: 낙하 후 윈도 안에 물 감지 → 스트로브 ── */
		if (worn && !mob && fall_ms && water_wet() &&
		    now - fall_ms <= CONFIG_JACKET_MOB_WINDOW_S * 1000) {
			k_mutex_lock(&st_lock, K_FOREVER);
			st.mob = true;
			k_mutex_unlock(&st_lock);
			LOG_WRN("익수 확정 (낙하+물) — 스트로브 시작");
			strobe_set(true);
			adv_push();
		}

		/* 스트로브 해제: 물이 오래 마르면 (구조 완료 추정) */
		if (mob && strobe_active()) {
			int64_t wet_ms = water_last_wet_ms();

			if (wet_ms &&
			    now - wet_ms >
				    CONFIG_JACKET_STROBE_DRY_RELEASE_S * 1000) {
				LOG_INF("건조 지속 — 스트로브 해제");
				strobe_set(false);
				k_mutex_lock(&st_lock, K_FOREVER);
				st.mob = false;
				k_mutex_unlock(&st_lock);
			}
		}

		/* ── 탈의 후 유예 광고 종료 → 보관 슬립 ── */
		if (!worn && doff_ms &&
		    now - doff_ms > CONFIG_JACKET_DOFF_ADV_TIMEOUT_S * 1000) {
			jacket_adv_set_mode(JACKET_ADV_OFF);
			k_mutex_lock(&st_lock, K_FOREVER);
			st.doff_ms = 0;
			k_mutex_unlock(&st_lock);
			if (!IS_ENABLED(CONFIG_JACKET_STORAGE_SLEEP)) {
				LOG_INF("보관 슬립 비활성 — 깨어 있음 (버클 닫으면 광고 재개)");
			} else if (!usb_powered()) {
				enter_storage_sleep();	/* 복귀하지 않음 */
			} else {
				LOG_INF("USB 전원 감지 — 슬립 생략 (개발 모드)");
			}
		}

		/* ── 1초 주기: 시퀀스/배터리 갱신 + 광고 데이터 푸시 ── */
		if (now - last_1s >= 1000) {
			last_1s = now;
			k_mutex_lock(&st_lock, K_FOREVER);
			st.seq++;
			if (now - last_batt >= 30 * 1000 || last_batt == 0) {
				last_batt = now;
				int mv = battery_read_mv();

				if (mv > 0) {
					st.batt_mv = mv;
					st.low_batt =
						mv < CONFIG_JACKET_LOW_BATT_MV;
					strobe_set_low_batt(st.low_batt);
				}
			}
			k_mutex_unlock(&st_lock);
			if (jacket_adv_mode() != JACKET_ADV_OFF) {
				adv_push();
			}
		}
	}
	return 0;
}
