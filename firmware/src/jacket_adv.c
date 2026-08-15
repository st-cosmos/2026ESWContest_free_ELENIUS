#include "jacket_adv.h"

#include <zephyr/kernel.h>
#include <zephyr/bluetooth/bluetooth.h>
#include <zephyr/logging/log.h>

LOG_MODULE_REGISTER(jacket_adv, CONFIG_JACKET_LOG_LEVEL);

#define COMPANY_ID 0xFFFF	/* 개발/시험용 회사 ID */

/* 회사 ID(2) + 페이로드(9) */
static uint8_t mfg_data[2 + 9] = {
	COMPANY_ID & 0xFF, COMPANY_ID >> 8,
	'V', 'J', 1, CONFIG_JACKET_DEVICE_NUM, 0, 0, 0, 0, 0,
};

static const struct bt_data ad[] = {
	BT_DATA_BYTES(BT_DATA_FLAGS, BT_LE_AD_NO_BREDR),
	BT_DATA(BT_DATA_MANUFACTURER_DATA, mfg_data, sizeof(mfg_data)),
	BT_DATA(BT_DATA_NAME_COMPLETE, CONFIG_BT_DEVICE_NAME,
		sizeof(CONFIG_BT_DEVICE_NAME) - 1),
};

static enum jacket_adv_mode cur_mode = JACKET_ADV_OFF;
static K_MUTEX_DEFINE(adv_lock);

#define MS_TO_ADV_UNITS(ms) ((uint32_t)(ms) * 1000 / 625)

static int adv_start(uint32_t interval_ms)
{
	/* non-connectable, identity 주소(FICR 유래 static random — 장치 고정) */
	struct bt_le_adv_param param = {
		.id = BT_ID_DEFAULT,
		.options = BT_LE_ADV_OPT_USE_IDENTITY,
		.interval_min = MS_TO_ADV_UNITS(interval_ms),
		.interval_max = MS_TO_ADV_UNITS(interval_ms) + 16,
	};

	return bt_le_adv_start(&param, ad, ARRAY_SIZE(ad), NULL, 0);
}

int jacket_adv_init(void)
{
	int err = bt_enable(NULL);

	if (err) {
		LOG_ERR("bt_enable 실패 (%d)", err);
	}
	return err;
}

int jacket_adv_set_mode(enum jacket_adv_mode mode)
{
	int err = 0;

	k_mutex_lock(&adv_lock, K_FOREVER);
	if (mode == cur_mode) {
		k_mutex_unlock(&adv_lock);
		return 0;
	}

	if (cur_mode != JACKET_ADV_OFF) {
		bt_le_adv_stop();
	}
	if (mode == JACKET_ADV_NORMAL) {
		err = adv_start(CONFIG_JACKET_ADV_INTERVAL_MS);
	} else if (mode == JACKET_ADV_BURST) {
		err = adv_start(CONFIG_JACKET_ADV_BURST_INTERVAL_MS);
		if (err) {
			/* 컨트롤러가 짧은 간격을 거부하면 일반 간격으로 폴백 */
			LOG_WRN("버스트 간격 거부 (%d) — 일반 간격으로 폴백", err);
			err = adv_start(CONFIG_JACKET_ADV_INTERVAL_MS);
		}
	}

	if (err) {
		LOG_ERR("광고 시작 실패 (%d)", err);
		cur_mode = JACKET_ADV_OFF;
	} else {
		cur_mode = mode;
		LOG_INF("광고 모드: %s",
			mode == JACKET_ADV_OFF ? "off" :
			mode == JACKET_ADV_NORMAL ? "normal" : "burst");
	}
	k_mutex_unlock(&adv_lock);
	return err;
}

enum jacket_adv_mode jacket_adv_mode(void)
{
	return cur_mode;
}

void jacket_adv_update(const struct jacket_adv_status *st)
{
	uint16_t batt = MIN(st->batt_mv, 20 * 255);

	k_mutex_lock(&adv_lock, K_FOREVER);
	mfg_data[6] = st->flags;
	mfg_data[7] = st->seq;
	mfg_data[8] = st->fall_count;
	mfg_data[9] = st->fall_mag_dg;
	mfg_data[10] = (uint8_t)(batt / 20);

	if (cur_mode != JACKET_ADV_OFF) {
		int err = bt_le_adv_update_data(ad, ARRAY_SIZE(ad), NULL, 0);

		if (err) {
			LOG_WRN("광고 데이터 갱신 실패 (%d)", err);
		}
	}
	k_mutex_unlock(&adv_lock);
}
