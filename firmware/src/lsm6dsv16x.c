#include "lsm6dsv16x.h"

#include <zephyr/kernel.h>
#include <zephyr/drivers/i2c.h>
#include <zephyr/logging/log.h>

LOG_MODULE_REGISTER(lsm6dsv16x, CONFIG_JACKET_LOG_LEVEL);

#define REG_WHO_AM_I   0x0F
#define WHO_AM_I_VAL   0x70

#define REG_CTRL1      0x10	/* [6:4] OP_MODE_XL, [3:0] ODR_XL */
#define REG_CTRL3      0x12	/* BOOT | BDU | ... | IF_INC | SW_RESET */
#define REG_CTRL8      0x17	/* [1:0] FS_XL */
#define REG_STATUS     0x1E	/* bit0 XLDA */
#define REG_OUTX_L_A   0x28	/* 6바이트 연속 (X/Y/Z, LE) */

#define CTRL3_BDU      BIT(6)
#define CTRL3_IF_INC   BIT(2)
#define CTRL3_SW_RESET BIT(0)

#define CTRL1_ODR_60HZ 0x05	/* 고성능 모드(OP_MODE 000) + 60 Hz */
#define CTRL8_FS_8G    0x02
/* ±8g 감도: 0.244 mg/LSB */
#define SENS_UG_PER_LSB 244

static const struct i2c_dt_spec imu_bus = I2C_DT_SPEC_GET(DT_NODELABEL(imu));
static bool present;

static int reg_write(uint8_t reg, uint8_t val)
{
	return i2c_reg_write_byte_dt(&imu_bus, reg, val);
}

static int reg_read(uint8_t reg, uint8_t *val)
{
	return i2c_reg_read_byte_dt(&imu_bus, reg, val);
}

int lsm6dsv16x_init(void)
{
	uint8_t id = 0;

	if (!device_is_ready(imu_bus.bus)) {
		LOG_ERR("I2C 버스가 준비되지 않음");
		return -ENODEV;
	}

	/* 전원 인가 직후 부팅 시간(수 ms)을 감안해 몇 번 재시도 */
	for (int i = 0; i < 5; i++) {
		if (reg_read(REG_WHO_AM_I, &id) == 0 && id == WHO_AM_I_VAL) {
			break;
		}
		k_msleep(10);
	}
	if (id != WHO_AM_I_VAL) {
		LOG_ERR("WHO_AM_I 불일치: 0x%02x (기대 0x70) — 배선/주소(SA0) 확인",
			id);
		return -ENODEV;
	}

	int err = reg_write(REG_CTRL3, CTRL3_SW_RESET);

	if (err) {
		return err;
	}
	k_msleep(20);

	err = reg_write(REG_CTRL3, CTRL3_BDU | CTRL3_IF_INC);
	err = err ? err : reg_write(REG_CTRL8, CTRL8_FS_8G);
	err = err ? err : reg_write(REG_CTRL1, CTRL1_ODR_60HZ);
	if (err) {
		LOG_ERR("설정 실패 (%d)", err);
		return err;
	}

	present = true;
	LOG_INF("LSM6DSV16X 준비 완료 (±8g, 60 Hz)");
	return 0;
}

bool lsm6dsv16x_present(void)
{
	return present;
}

int lsm6dsv16x_read_mg(int32_t mg[3])
{
	uint8_t status;
	uint8_t raw[6];

	if (!present) {
		return -ENODEV;
	}
	if (reg_read(REG_STATUS, &status) != 0) {
		return -EIO;
	}
	if (!(status & BIT(0))) {	/* XLDA */
		return -EAGAIN;
	}
	if (i2c_burst_read_dt(&imu_bus, REG_OUTX_L_A, raw, sizeof(raw)) != 0) {
		return -EIO;
	}

	for (int i = 0; i < 3; i++) {
		int16_t v = (int16_t)((raw[2 * i + 1] << 8) | raw[2 * i]);

		mg[i] = ((int32_t)v * SENS_UG_PER_LSB) / 1000;
	}
	return 0;
}
