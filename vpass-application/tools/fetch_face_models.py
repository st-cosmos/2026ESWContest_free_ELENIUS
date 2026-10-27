# -*- coding: utf-8 -*-
"""얼굴 인식용 OpenCV Zoo ONNX 모델을 models/ 에 내려받는다.

  uv run python tools/fetch_face_models.py            # 없을 때만 내려받음
  uv run python tools/fetch_face_models.py --force    # 다시 내려받음

받는 파일 (Apache-2.0, https://github.com/opencv/opencv_zoo):
  face_detection_yunet_2023mar.onnx      YuNet 얼굴 검출기 (약 230 KB)
  face_recognition_sface_2021dec.onnx    SFace 얼굴 임베딩 (약 37 MB)

두 파일이 있으면 앱이 자동으로 SFace 엔진을 쓰고, 없으면 LBPH 로 폴백한다.
라즈베리파이는 인터넷이 없을 수 있으니 PC 에서 받아 scp 로 복사해도 된다.
"""

from __future__ import annotations

import argparse
import sys
import urllib.request
from pathlib import Path

MODELS_DIR = Path(__file__).resolve().parents[1] / "models"
BASE = "https://github.com/opencv/opencv_zoo/raw/main/models"
FILES = {
    "face_detection_yunet_2023mar.onnx": (
        f"{BASE}/face_detection_yunet/face_detection_yunet_2023mar.onnx", 200_000),
    "face_recognition_sface_2021dec.onnx": (
        f"{BASE}/face_recognition_sface/face_recognition_sface_2021dec.onnx", 30_000_000),
}


def fetch(name: str, url: str, min_size: int, force: bool) -> bool:
    dest = MODELS_DIR / name
    if dest.is_file() and dest.stat().st_size >= min_size and not force:
        print(f"  있음  {name} ({dest.stat().st_size:,} B)")
        return True
    print(f"  받는 중  {name} ...", end="", flush=True)
    tmp = dest.with_suffix(".part")
    try:
        with urllib.request.urlopen(url, timeout=120) as r, open(tmp, "wb") as f:
            while chunk := r.read(1 << 16):
                f.write(chunk)
    except Exception as e:
        print(f" 실패: {e}")
        tmp.unlink(missing_ok=True)
        return False
    size = tmp.stat().st_size
    if size < min_size:
        print(f" 실패: 파일이 너무 작음({size} B) — LFS 포인터일 수 있음")
        tmp.unlink(missing_ok=True)
        return False
    tmp.replace(dest)
    print(f" 완료 ({size:,} B)")
    return True


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--force", action="store_true", help="이미 있어도 다시 내려받는다")
    args = ap.parse_args()
    MODELS_DIR.mkdir(parents=True, exist_ok=True)
    print(f"models/: {MODELS_DIR}")
    ok = all(fetch(n, u, m, args.force) for n, (u, m) in FILES.items())
    if not ok:
        sys.exit("일부 모델을 받지 못했습니다. 앱은 LBPH 로 폴백해 동작합니다.")
    try:
        import cv2
        cv2.FaceDetectorYN.create(str(MODELS_DIR / "face_detection_yunet_2023mar.onnx"), "", (320, 320))
        cv2.FaceRecognizerSF.create(str(MODELS_DIR / "face_recognition_sface_2021dec.onnx"), "")
        print("OpenCV 로드 확인: SFace 엔진 사용 가능")
    except Exception as e:
        sys.exit(f"OpenCV 가 모델을 열지 못했습니다: {e}")


if __name__ == "__main__":
    main()
