# -*- coding: utf-8 -*-
"""얼굴 인식 오프라인 평가 — SFace 와 LBPH 를 같은 사진으로 비교한다.

  uv run python tools/face_eval.py                         # data/face_eval 사용
  uv run python tools/face_eval.py --data data/face_eval --enroll 5 --engines sface lbph

데이터 구조 (tools/face_capture.py 로 수집):
  data/face_eval/<사람>/*.jpg     등록자 — 앞 --enroll 장은 등록, 나머지는 시험
  data/face_eval/_unknown/*.jpg   미등록자 — 전부 시험(오수락 측정)

출력(마크다운):
  - 엔진별 요약: 본인 수락률(TAR), 본인 거부율(FRR), 타인 오인식률, 미등록자 오수락률(FAR),
    얼굴 검출 실패 수, 평균 처리 시간
  - 임계값 스윕표: 임계값을 바꿀 때 TAR/FAR 가 어떻게 움직이는지 (운용 임계값 선정 근거)

판정 규칙은 앱과 같다(임계값 + 마진). 시간 투표는 단일 사진 평가라 적용하지 않는다.
"""

from __future__ import annotations

import argparse
import statistics
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import numpy as np  # noqa: E402

from vpass import config  # noqa: E402
from vpass.facerec import (  # noqa: E402
    LbphEngine, SFaceEngine, cosine_match, fit_image, imread_unicode, sface_models_available,
)

IMG_EXT = (".jpg", ".jpeg", ".png")


def list_images(d: Path) -> list[Path]:
    return sorted(p for p in d.iterdir() if p.suffix.lower() in IMG_EXT)


def load_dataset(root: Path):
    people, unknown = {}, []
    for d in sorted(root.iterdir()):
        if not d.is_dir():
            continue
        imgs = list_images(d)
        if d.name.startswith("_"):
            unknown += imgs
        elif imgs:
            people[d.name] = imgs
    return people, unknown


def make_engine(name: str):
    if name == "sface":
        if not sface_models_available():
            print("(sface 건너뜀: models/ 에 ONNX 모델이 없음 — tools/fetch_face_models.py)")
            return None
        return SFaceEngine(config.FACE_DET_MODEL_PATH, config.FACE_REC_MODEL_PATH)
    return LbphEngine()


def feature_of(engine, path: Path):
    img = imread_unicode(path)
    if img is None:
        return None, 0.0
    img = fit_image(img)
    t = time.perf_counter()
    det = engine.detect_largest(img) or engine._detect_padded(img)
    if det is None:
        return None, time.perf_counter() - t
    feat = engine.embed(img, det)
    return feat, time.perf_counter() - t


def evaluate(engine_name: str, people: dict, unknown: list, n_enroll: int):
    engine = make_engine(engine_name)
    if engine is None:
        return None
    # 등록
    users = [{"id": name, "name": name, "photos": [str(p) for p in imgs[:n_enroll]]}
             for name, imgs in people.items()]
    gallery = engine.build_gallery(users, Path("."))
    # 시험 집합: (정답 id 또는 None, 특징)
    trials, times, undetected = [], [], 0
    for name, imgs in people.items():
        for p in imgs[n_enroll:]:
            feat, dt = feature_of(engine, p)
            times.append(dt)
            if feat is None:
                undetected += 1
                continue
            trials.append((name, feat))
    for p in unknown:
        feat, dt = feature_of(engine, p)
        times.append(dt)
        if feat is None:
            undetected += 1
            continue
        trials.append((None, feat))

    def judge(feat, thr):
        if engine_name == "sface":
            m = cosine_match(feat, gallery, thr, config.FACE_SFACE_MARGIN)
            return (m.user or {}).get("id"), m.score
        m = engine.match(feat, gallery)
        uid = (m.candidate or {}).get("id") if m.score <= thr else None
        return uid, m.score

    def tally(thr):
        tar = frr = misid = far = tn = 0
        for truth, feat in trials:
            pred, _ = judge(feat, thr)
            if truth is None:
                far += pred is not None
                tn += pred is None
            elif pred == truth:
                tar += 1
            elif pred is None:
                frr += 1
            else:
                misid += 1
        n_gen = sum(1 for t, _ in trials if t is not None)
        n_imp = sum(1 for t, _ in trials if t is None)
        return {
            "thr": thr, "genuine": n_gen, "impostor": n_imp,
            "TAR%": round(100 * tar / n_gen, 1) if n_gen else None,
            "FRR%": round(100 * frr / n_gen, 1) if n_gen else None,
            "misID%": round(100 * misid / n_gen, 1) if n_gen else None,
            "FAR%": round(100 * far / n_imp, 1) if n_imp else None,
        }

    base_thr = config.FACE_SFACE_THRESHOLD if engine_name == "sface" else config.MATCH_THRESHOLD
    sweep = (np.round(np.arange(0.20, 0.61, 0.05), 2) if engine_name == "sface"
             else list(range(30, 101, 10)))
    return {
        "engine": engine_name,
        "users": len(gallery),
        "enroll_per_user": n_enroll,
        "undetected": undetected,
        "ms_per_image": round(1000 * statistics.fmean(times), 1) if times else None,
        "at_threshold": tally(base_thr),
        "sweep": [tally(float(t)) for t in sweep],
    }


def md_table(rows: list[dict]) -> str:
    cols = list(rows[0].keys())
    out = ["| " + " | ".join(cols) + " |", "|" + "---|" * len(cols)]
    for r in rows:
        out.append("| " + " | ".join("-" if r[c] is None else str(r[c]) for c in cols) + " |")
    return "\n".join(out)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--data", type=Path, default=config.DATA_DIR / "face_eval")
    ap.add_argument("--enroll", type=int, default=config.FACE_ENROLL_SAMPLES,
                    help="사람당 등록에 쓸 사진 수(앞에서부터)")
    ap.add_argument("--engines", nargs="+", default=["sface", "lbph"], choices=["sface", "lbph"])
    args = ap.parse_args()

    if not args.data.is_dir():
        sys.exit(f"데이터 폴더가 없습니다: {args.data} (tools/face_capture.py 로 수집)")
    people, unknown = load_dataset(args.data)
    if not people:
        sys.exit("등록자 폴더가 없습니다")
    print(f"# 얼굴 인식 평가 ({args.data})\n")
    print(f"- 등록자 {len(people)}명: " + ", ".join(f"{k}({len(v)}장)" for k, v in people.items()))
    print(f"- 미등록자 사진 {len(unknown)}장 / 사람당 등록 {args.enroll}장, 나머지는 시험\n")

    summary = []
    for name in args.engines:
        r = evaluate(name, people, unknown, args.enroll)
        if r is None:
            continue
        a = r["at_threshold"]
        summary.append({
            "engine": name, "threshold": a["thr"], "TAR%": a["TAR%"], "FRR%": a["FRR%"],
            "misID%": a["misID%"], "FAR%": a["FAR%"], "undetected": r["undetected"],
            "ms/img": r["ms_per_image"],
        })
        print(f"## {name} — 임계값 스윕 (마진 {config.FACE_SFACE_MARGIN if name == 'sface' else '-'})\n")
        print(md_table(r["sweep"]) + "\n")
    print("## 요약 (운용 임계값 기준)\n")
    print(md_table(summary))
    print("\nTAR 본인 수락 / FRR 본인 거부 / misID 타인으로 오인식 / FAR 미등록자 오수락")


if __name__ == "__main__":
    main()
