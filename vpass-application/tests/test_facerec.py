# -*- coding: utf-8 -*-
"""얼굴 인식 판정 로직 검증 (카메라·실제 얼굴 사진 불필요).

실행: uv run python tests/test_facerec.py
"""

import os
import tempfile

os.environ["VPASS_DATA_DIR"] = tempfile.mkdtemp(prefix="vpass-face-test-")

import numpy as np  # noqa: E402

from vpass import config  # noqa: E402
from vpass.facerec import (  # noqa: E402
    Gallery, LbphEngine, RecognitionVoter, cosine_match, create_engine,
    sface_models_available, user_photos,
)

PASS = 0
FAIL = 0


def check(name, cond, detail=""):
    global PASS, FAIL
    if cond:
        PASS += 1
        print(f"  [PASS] {name}")
    else:
        FAIL += 1
        print(f"  [FAIL] {name} {detail}")


def unit(v):
    v = np.asarray(v, dtype=np.float32)
    return v / np.linalg.norm(v)


def main():
    print("\n== 1) 코사인 매칭: 임계값 + 마진 ==")
    g = Gallery()
    a, b = {"id": "a", "name": "A"}, {"id": "b", "name": "B"}
    g.add(a, unit([1, 0, 0, 0]))
    g.add(a, unit([0.9, 0.1, 0, 0]))     # 같은 사람의 두 번째 샘플
    g.add(b, unit([0, 1, 0, 0]))
    check("갤러리 사용자 수 = 2 (샘플 3)", len(g) == 2 and len(g.entries) == 3)

    m = cosine_match(unit([1, 0.05, 0, 0]), g, 0.363, 0.08)
    check("A 와 가까운 질의 → A 인정", m.user is a and m.score > 0.9, f"{m}")
    m = cosine_match(unit([0, 0, 1, 0]), g, 0.363, 0.08)
    check("아무와도 안 닮음 → 미인정, 후보는 남음", m.user is None and m.candidate is not None)
    m = cosine_match(unit([1, 1, 0, 0]), g, 0.363, 0.08)
    check("A·B 중간(마진 미달) → 미인정", m.user is None and m.second is not None
          and abs(m.score - m.second) < 0.08, f"{m.score} {m.second}")
    m = cosine_match(unit([1, 1, 0, 0]), g, 0.363, 0.0)
    check("마진 0 이면 최고점 사용자 인정", m.user is not None)
    m = cosine_match(unit([1, 0, 0, 0]), Gallery(), 0.363, 0.08)
    check("빈 갤러리 → 미인정", m.user is None)

    print("\n== 2) 시간 투표 ==")
    v = RecognitionVoter(window=5, need=3, seconds=2.0)
    t = 1000.0
    r = [v.vote("a", t + 0.1 * i) for i in range(3)]
    check("같은 사람 3표 → 3번째에 확정", r[0][0] is None and r[1][0] is None and r[2] == ("a", 3), str(r))
    v.reset()
    r = [v.vote(u, t + 0.1 * i) for i, u in enumerate(["a", "b", "a", "b", None])]
    check("표가 갈리면 확정 없음", all(x[0] is None for x in r), str(r))
    check("창이 찼음(full)", v.full)
    v.reset()
    v.vote("a", t); v.vote("a", t + 0.1)
    confirmed, n = v.vote("a", t + 5.0)
    check("오래된 표(2초 초과)는 세지 않음", confirmed is None and n == 1, f"{confirmed} {n}")
    v.reset()
    r = [v.vote(None, t + 0.1 * i) for i in range(5)]
    check("미인정만 5회 → 확정 없음, 득표 0", r[-1] == (None, 0) and v.full)

    print("\n== 3) 엔진 선택과 폴백 ==")
    e = create_engine("lbph")
    check("lbph 강제 → LbphEngine", isinstance(e, LbphEngine) and e.name == "lbph")
    e = create_engine("auto")
    expected = "sface" if sface_models_available() else "lbph"
    check(f"auto → {expected} (모델 {'있음' if expected == 'sface' else '없음'})", e.name == expected)
    noise = np.random.default_rng(0).integers(0, 255, (480, 640, 3), dtype=np.uint8)
    check("잡음 영상에서 얼굴 미검출", e.detect_largest(noise) is None)
    gal = e.build_gallery([{"id": "x", "name": "X", "photo": "data/faces/없는파일.jpg"},
                           {"id": "y", "name": "Y", "photo": None}], config.APP_DIR)
    check("사진 없는 사용자 → 빈 갤러리", gal.empty)
    m = e.match(np.zeros(128, np.float32) if expected == "sface" else np.zeros(config.FACE_SIZE, np.uint8), gal)
    check("빈 갤러리 match → 미인정", m.user is None)

    print("\n== 4) 사진 경로 목록 ==")
    check("photos 우선", user_photos({"photo": "a.jpg", "photos": ["a.jpg", "b.jpg"]}) == ["a.jpg", "b.jpg"])
    check("photos 없으면 photo", user_photos({"photo": "a.jpg"}) == ["a.jpg"])
    check("둘 다 없으면 빈 목록", user_photos({"photo": None}) == [])

    print(f"\n결과: PASS {PASS} / FAIL {FAIL}")
    raise SystemExit(1 if FAIL else 0)


if __name__ == "__main__":
    main()
