/* 물 감지 전극 측정.
 *
 * 회로: 전극 2개 + 47k 직렬 + TVS (P0.02/P0.03 = AIN0/1). 평상시 두 핀 모두
 * 하이임피던스(전극 간 전위차 0 — 갈바닉 부식 방지).
 *
 * 한 방향 측정은 "방전 후 물을 통한 충전" 방식:
 *   1) 측정(비구동) 전극을 잠깐 0V 로 구동해 방전
 *   2) Hi-Z 로 놓고 반대 전극을 High 구동, 10 ms 대기
 *   3) ADC — 젖으면 물 경로로 충전되어 올라가고, 건조면 0 근처 유지
 * 이어서 A/B 역할을 바꿔 극성을 교대한다 (전기분해 상쇄).
 *
 * 실측(2026-08-16, 수돗물): 이 전극 기하에서는 물 저항이 수 MΩ 급이라
 * 젖음 신호가 VDD 의 2~4% 로 작다. 대신 건조 값이 극도로 안정적이어서
 * (0.0~0.2%), 부팅 시 건조 기준선을 캡처하고 **기준선 대비 증가분(Δ)** 이
 * CONFIG_JACKET_WATER_DELTA_PERMILLE 이상이면 젖음으로 판정한다 — 방향별
 * 상수 오프셋(보드 개체차)에 영향받지 않는다.
 *
 * 판정은 두 방향 중 큰 Δ 를 쓴다: 실보드에서 한 방향의 감도가 훨씬 크게
 * 측정됐다 (전극 비대칭). ADC 기준이 VDD/4 라 값은 배터리 전압과 무관.
 *
 * 주의: 기준선은 "부팅 시 건조" 를 가정한다. 물속에서 부팅하는 극단 상황은
 * 감지가 늦을 수 있다 (운용상 착용→항해→입수 순서라 실사용 문제 없음).
 */
#include "water.h"

#include <zephyr/kernel.h>
#include <zephyr/drivers/adc.h>
#include <zephyr/drivers/gpio.h>
#include <zephyr/logging/log.h>

LOG_MODULE_REGISTER(water, CONFIG_JACKET_LOG_LEVEL);

static const struct gpio_dt_spec elec_a =
	GPIO_DT_SPEC_GET(DT_PATH(zephyr_user), elec_a_gpios);
static const struct gpio_dt_spec elec_b =
	GPIO_DT_SPEC_GET(DT_PATH(zephyr_user), elec_b_gpios);
/* zephyr,user io-channels: 1 = 전극 A(AIN0), 2 = 전극 B(AIN1) */
static const struct adc_dt_spec adc_a =
	ADC_DT_SPEC_GET_BY_IDX(DT_PATH(zephyr_user), 1);
static const struct adc_dt_spec adc_b =
	ADC_DT_SPEC_GET_BY_IDX(DT_PATH(zephyr_user), 2);

/* 10비트, 기준 = VDD → 1023 == VDD. 퍼밀(0~1000)로 환산해 쓴다. */
#define FULL_SCALE 1023

/* 부팅 후 이만큼의 측정으로 건조 기준선을 잡는다 (최소값 채택) */
#define BASELINE_SAMPLES 5

static K_MUTEX_DEFINE(lock);
static bool wet;
static bool baseline_ready;
static uint16_t base_fwd_pm, base_rev_pm;
static uint16_t last_delta_pm;
static int64_t last_wet_ms;
static int wet_streak;
static atomic_t fast_until_ms;	/* uptime ms; 이 시각까지 고속 측정 */

static K_THREAD_STACK_DEFINE(water_stack, 1024);
static struct k_thread water_thread;

/* 측정 스레드와 셸 명령이 같은 핀·SAADC 를 쓰므로 직렬화 */
static K_MUTEX_DEFINE(measure_lock);

static int adc_read_pm(const struct adc_dt_spec *ch, uint16_t *pm)
{
	int16_t buf;
	struct adc_sequence seq = {
		.buffer = &buf,
		.buffer_size = sizeof(buf),
	};
	int err = adc_sequence_init_dt(ch, &seq);

	/* 첫 변환은 샘플 캐패시터 조건 맞추기용으로 버린다 — 고임피던스
	 * 노드라 직전 변환(다른 채널)의 잔류 전하가 섞여 읽힌다.
	 * 두 변환 사이 1 ms 는 물 경로 재충전 시간. */
	err = err ? err : adc_read_dt(ch, &seq);
	if (!err) {
		k_busy_wait(1000);
	}
	err = err ? err : adc_read_dt(ch, &seq);
	if (err) {
		return err;
	}
	if (buf < 0) {
		buf = 0;
	}
	*pm = (uint16_t)MIN(((int32_t)buf * 1000) / FULL_SCALE, 1000);
	return 0;
}

static int measure_dir(const struct gpio_dt_spec *drive,
		       const struct gpio_dt_spec *sense_gpio,
		       const struct adc_dt_spec *sense_adc, uint16_t *pm)
{
	int err;

	gpio_pin_configure_dt(sense_gpio, GPIO_OUTPUT_INACTIVE);	/* 방전 */
	k_busy_wait(100);
	gpio_pin_configure_dt(sense_gpio, GPIO_DISCONNECTED);

	gpio_pin_configure_dt(drive, GPIO_OUTPUT_ACTIVE);
	k_msleep(10);		/* 물 경로(수 MΩ)를 통한 충전 대기 */
	err = adc_read_pm(sense_adc, pm);
	gpio_pin_configure_dt(drive, GPIO_DISCONNECTED);
	return err;
}

int water_measure_once(uint16_t *fwd_pm, uint16_t *rev_pm)
{
	int err;

	k_mutex_lock(&measure_lock, K_FOREVER);
	/* 정방향: A 구동 → B 측정 */
	err = measure_dir(&elec_a, &elec_b, &adc_b, fwd_pm);
	/* 역방향: B 구동 → A 측정 (극성 교대) */
	err = err ? err : measure_dir(&elec_b, &elec_a, &adc_a, rev_pm);
	k_mutex_unlock(&measure_lock);
	return err;
}

static void water_loop(void *a, void *b, void *c)
{
	ARG_UNUSED(a); ARG_UNUSED(b); ARG_UNUSED(c);

	int base_n = 0;

	while (true) {
		uint16_t fwd = 0, rev = 0;

		if (water_measure_once(&fwd, &rev) == 0) {
			k_mutex_lock(&lock, K_FOREVER);
			if (base_n < BASELINE_SAMPLES) {
				/* 건조 기준선: 초기 측정의 최소값 */
				if (base_n == 0) {
					base_fwd_pm = fwd;
					base_rev_pm = rev;
				} else {
					base_fwd_pm = MIN(base_fwd_pm, fwd);
					base_rev_pm = MIN(base_rev_pm, rev);
				}
				if (++base_n == BASELINE_SAMPLES) {
					baseline_ready = true;
					LOG_INF("건조 기준선: 정 %u.%u%% / 역 %u.%u%%",
						base_fwd_pm / 10, base_fwd_pm % 10,
						base_rev_pm / 10, base_rev_pm % 10);
				}
				k_mutex_unlock(&lock);
				k_msleep(CONFIG_JACKET_WATER_PERIOD_MS);
				continue;
			}

			int d_fwd = (int)fwd - (int)base_fwd_pm;
			int d_rev = (int)rev - (int)base_rev_pm;
			uint16_t delta = (uint16_t)MAX(MAX(d_fwd, d_rev), 0);
			bool sample_wet =
				delta >= CONFIG_JACKET_WATER_DELTA_PERMILLE;

			last_delta_pm = delta;
			if (sample_wet) {
				last_wet_ms = k_uptime_get();
				if (++wet_streak >= CONFIG_JACKET_WATER_CONFIRM_COUNT
				    && !wet) {
					wet = true;
					LOG_INF("물 감지 (Δ%u.%u%%)",
						delta / 10, delta % 10);
				}
			} else {
				wet_streak = 0;
				if (wet) {
					wet = false;
					LOG_INF("건조 상태로 복귀");
				}
			}
			k_mutex_unlock(&lock);
		}

		bool fast = k_uptime_get() < atomic_get(&fast_until_ms);

		k_msleep(fast ? CONFIG_JACKET_WATER_FAST_PERIOD_MS
			      : CONFIG_JACKET_WATER_PERIOD_MS);
	}
}

int water_init(void)
{
	if (!adc_is_ready_dt(&adc_a) || !adc_is_ready_dt(&adc_b) ||
	    !gpio_is_ready_dt(&elec_a) || !gpio_is_ready_dt(&elec_b)) {
		return -ENODEV;
	}
	int err = adc_channel_setup_dt(&adc_a);

	err = err ? err : adc_channel_setup_dt(&adc_b);
	/* 시작은 양쪽 모두 하이임피던스 */
	gpio_pin_configure_dt(&elec_a, GPIO_DISCONNECTED);
	gpio_pin_configure_dt(&elec_b, GPIO_DISCONNECTED);
	return err;
}

void water_start(void)
{
	k_thread_create(&water_thread, water_stack,
			K_THREAD_STACK_SIZEOF(water_stack),
			water_loop, NULL, NULL, NULL,
			K_PRIO_PREEMPT(7), 0, K_NO_WAIT);
	k_thread_name_set(&water_thread, "water");
}

bool water_wet(void)
{
	k_mutex_lock(&lock, K_FOREVER);
	bool w = wet;

	k_mutex_unlock(&lock);
	return w;
}

void water_boost(void)
{
	atomic_set(&fast_until_ms,
		   k_uptime_get() + CONFIG_JACKET_WATER_FAST_WINDOW_S * 1000);
}

int64_t water_last_wet_ms(void)
{
	k_mutex_lock(&lock, K_FOREVER);
	int64_t t = last_wet_ms;

	k_mutex_unlock(&lock);
	return t;
}

bool water_baseline(uint16_t *fwd_pm, uint16_t *rev_pm)
{
	k_mutex_lock(&lock, K_FOREVER);
	bool ready = baseline_ready;

	if (ready) {
		*fwd_pm = base_fwd_pm;
		*rev_pm = base_rev_pm;
	}
	k_mutex_unlock(&lock);
	return ready;
}

uint16_t water_last_delta_pm(void)
{
	k_mutex_lock(&lock, K_FOREVER);
	uint16_t d = last_delta_pm;

	k_mutex_unlock(&lock);
	return d;
}
