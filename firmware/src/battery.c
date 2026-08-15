#include "battery.h"

#include <zephyr/kernel.h>
#include <zephyr/drivers/adc.h>
#include <zephyr/logging/log.h>

LOG_MODULE_REGISTER(battery, CONFIG_JACKET_LOG_LEVEL);

/* zephyr,user io-channels: 0 = VDD (게인 1/6, 내부 0.6V 기준 → FS 3.6V) */
static const struct adc_dt_spec vdd_ch =
	ADC_DT_SPEC_GET_BY_IDX(DT_PATH(zephyr_user), 0);

int battery_init(void)
{
	if (!adc_is_ready_dt(&vdd_ch)) {
		LOG_ERR("SAADC 준비 안 됨");
		return -ENODEV;
	}
	return adc_channel_setup_dt(&vdd_ch);
}

int battery_read_mv(void)
{
	int16_t buf;
	struct adc_sequence seq = {
		.buffer = &buf,
		.buffer_size = sizeof(buf),
	};
	int err = adc_sequence_init_dt(&vdd_ch, &seq);

	err = err ? err : adc_read_dt(&vdd_ch, &seq);
	if (err) {
		return err;
	}
	if (buf < 0) {
		buf = 0;
	}
	/* 12비트, 풀스케일 3.6 V */
	return ((int32_t)buf * 3600) / 4096;
}
