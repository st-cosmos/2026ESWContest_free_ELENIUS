# -*- coding: utf-8 -*-
"""평가용 얼굴 사진 수집기 — 웹캠에서 사람별 얼굴 크롭을 저장한다.

  uv run python tools/face_capture.py --person 홍길동 --count 20
  uv run python tools/face_capture.py --person _unknown --count 30   # 미등록자(오수락 측정용)

data/face_eval/<person>/NNN.jpg 로 저장된다. 사진은 0.5초 간격으로 찍히므로
그 사이에 고개 각도·표정·거리를 조금씩 바꿔 주면 좋다. 저장된 폴더는
tools/face_eval.py 가 읽는다. q 로 중단.
"""

from __future__ import annotations

import argparse
import os
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import cv2  # noqa: E402

from vpass import config  # noqa: E402
from vpass.facerec import create_engine, imwrite_unicode  # noqa: E402


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--person", required=True, help="폴더 이름(사람 이름, 미등록자는 _unknown)")
    ap.add_argument("--count", type=int, default=20)
    ap.add_argument("--interval", type=float, default=0.5)
    ap.add_argument("--out", type=Path, default=config.DATA_DIR / "face_eval")
    ap.add_argument("--camera", type=int, default=config.CAMERA_INDEX)
    args = ap.parse_args()

    out = args.out / args.person
    out.mkdir(parents=True, exist_ok=True)
    existing = len([p for p in out.iterdir() if p.suffix.lower() in (".jpg", ".png")])

    engine = create_engine()
    cap = cv2.VideoCapture(args.camera)
    if not cap.isOpened():
        sys.exit("카메라를 열 수 없습니다")
    headless = not os.environ.get("DISPLAY") and sys.platform != "win32"
    saved, last = 0, 0.0
    print(f"{out} 에 {args.count}장 저장 (이미 {existing}장). q 로 중단")
    while saved < args.count:
        ok, frame = cap.read()
        if not ok:
            time.sleep(0.1)
            continue
        frame = cv2.flip(frame, 1)
        det = engine.detect_largest(frame)
        display = frame.copy()
        if det is not None:
            x, y, w, h = det.box
            good, why = engine.quality_check(frame, det)
            color = (0, 255, 0) if good else (0, 0, 255)
            cv2.rectangle(display, (x, y), (x + w, y + h), color, 2)
            if good and time.time() - last >= args.interval:
                last = time.time()
                px, py = int(w * 0.3), int(h * 0.3)
                crop = frame[max(0, y - py):y + h + py, max(0, x - px):x + w + px]
                path = out / f"{existing + saved + 1:03d}.jpg"
                if imwrite_unicode(path, crop):
                    saved += 1
                    print(f"  {path.name} (score {det.score:.2f})")
            elif not good:
                print(f"  건너뜀: {why}", end="\r")
        cv2.putText(display, f"{args.person} {saved}/{args.count}", (10, 30),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 255, 255), 2)
        if not headless:
            cv2.imshow("face_capture", display)
            if cv2.waitKey(1) & 0xFF == ord("q"):
                break
    cap.release()
    if not headless:
        cv2.destroyAllWindows()
    print(f"완료: {saved}장 저장")


if __name__ == "__main__":
    main()
