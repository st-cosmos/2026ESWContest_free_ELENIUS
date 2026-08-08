"""해양 기상 정보 제공자.

운영 시 기상청(KMA) 해양 예보 API 를 연동할 자리이며,
현재는 시연용 정적 데이터에 시간에 따른 미세 변화를 더해 제공한다.

풍향·풍속·해류는 데모 관제 서버(국립해양조사원 연동)에서 관할 기상을 내려받아
덮어쓸 수 있도록 개별 필드로도 제공한다. 이 값들은 관제 서버의 요구조자 표류
예측과 같은 입력이라, 두 화면에 같은 수치가 보여야 한다.
  wind_dir      바람이 불어오는 8방위
  wind_speed_ms 풍속(m/s)
  current_dir   해류가 흘러가는 방위(°)
  current_kn    유속(kn)
"""

from __future__ import annotations

import math
import time
from datetime import datetime


def get_weather() -> dict:
    t = time.time() / 3600.0
    temp = 27 + round(math.sin(t) * 1.0)
    return {
        "temp_c": temp,
        "condition": "맑음",
        "feels_like_c": temp + 2,
        "precip_prob": 10,
        "wind": "NW 4.2 m/s",
        "wind_dir": "NW",
        "wind_speed_ms": 4.2,
        "gust_ms": 6.5,
        "current_dir": 55,
        "current_kn": 0.32,
        "wave_height_m": 0.8,
        "water_temp_c": 24.5,
        "humidity": 68,
        "visibility_km": 10,
        "pressure_hpa": 1012,
        "advisory": None,  # 발효 중 해상 특보 없음
        "sunrise": "05:24",
        "sunset": "19:42",
        "high_tide": "11:32",
        "low_tide": "17:48",
        "updated_at": datetime.now().strftime("%H:%M"),
        "source": "기상청 해양 예보",
    }
