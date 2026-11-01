# -*- coding: utf-8 -*-
"""얼굴 인식 벤치마크 — 이전 엔진(Haar+LBPH)과 현재 엔진(YuNet+SFace)을 같은 데이터로 비교한다.

앱의 판정 코드(vpass.facerec)를 그대로 불러 쓰므로 검출·정렬·임계값·마진·LBPH 신뢰도
기준이 운용 중인 앱과 같다. 결과는 JSON 으로 저장하고 요약을 마크다운으로 출력한다.

  uv run python tools/face_benchmark.py --lfw <lfw_funneled 폴더> \\
      --device-gallery <등록 사진 폴더> --device-frames <카메라 프레임 폴더> \\
      --out reports/face-benchmark/results.json

측정 항목
  1) LFW 표준 검증 — pairs.txt 6,000쌍(10겹). 10-fold 정확도(9겹에서 임계값 선택),
     ROC AUC, 오수락률(FAR) 1%·0.1% 에서의 본인 수락률(TAR), 운용 임계값에서의 정확도.
  2) 승선 게이트 모의(개방형 식별) — LFW 에서 사진 10장 이상인 사람 중 선원 G명을 뽑아
     사람당 E장으로 등록, 나머지 사진은 본인 시도, 등록 안 된 사람 U명의 사진은 미등록자 시도.
     앱과 같은 판정으로 TAR / 타인 오인식(misID) / FRR / 미등록자 오수락(FAR) 을 R회 반복 측정.
  3) 실제 설치 카메라 — 앱 등록 사진(선원 1명) + LFW 선원 G-1명 갤러리에 대해 라즈베리파이
     카메라 프레임의 검출률과 본인 인식률. 얼굴 방향(YuNet 랜드마크)별로 나눈다.
  4) 시간 투표 — 미등록자 한 사람의 사진 5장을 연속 검출로 보고 "5회 중 3회 같은 사람"
     규칙(RecognitionVoter)으로 확정될 확률을, 사진 한 장 기준 오수락률과 비교.
  5) 처리 시간 — 640x480 프레임 한 장의 검출+특징 추출 시간(--timing-only 로 기기에서 따로 측정).

LBPH 의 두 사진 비교 점수는 한 장으로 학습한 LBPH 인식기의 predict 신뢰도(작을수록 유사)다.
검출에 실패한 사진은 그 엔진의 실패로 센다(검증: 오답 처리, 식별: 거부 처리).
"""

from __future__ import annotations

import argparse
import json
import random
import statistics
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import cv2  # noqa: E402
import numpy as np  # noqa: E402

from vpass import config  # noqa: E402
from vpass.facerec import (  # noqa: E402
    Gallery, LbphEngine, RecognitionVoter, SFaceEngine, cosine_match, fit_image, imread_unicode,
)
from vpass.jacketturn import pose_of  # noqa: E402

IMG_EXT = (".jpg", ".jpeg", ".png")


# ── 특징 추출 (엔진별 캐시) ──────────────────────────────────────────────
class Extractor:
    """경로 → (특징, 검출 정보). 앱과 같은 순서: fit_image → detect_largest → 실패 시 패딩 재검출."""

    def __init__(self, name: str):
        self.name = name
        self.engine = (SFaceEngine(config.FACE_DET_MODEL_PATH, config.FACE_REC_MODEL_PATH)
                       if name == "sface" else LbphEngine())
        self.cache: dict[str, tuple] = {}

    def feature(self, path: Path, padded_retry: bool = True):
        key = str(path)
        if key not in self.cache:
            img = imread_unicode(path)
            feat = det = None
            if img is not None:
                img = fit_image(img)
                det = self.engine.detect_largest(img)
                if det is None and padded_retry:
                    det = self.engine._detect_padded(img)
                if det is not None:
                    feat = self.engine.embed(img, det)
            self.cache[key] = (feat, det)
        return self.cache[key]


def lbph_distance(a: np.ndarray, b: np.ndarray) -> float:
    rec = cv2.face.LBPHFaceRecognizer_create()
    rec.train([a], np.array([0]))
    return float(rec.predict(b)[1])


# ── 1) LFW 표준 검증 ────────────────────────────────────────────────────
def read_pairs(lfw: Path):
    lines = (lfw / "pairs.txt").read_text().split("\n")
    n_folds, n = (int(v) for v in lines[0].split())
    pairs = []
    for i, line in enumerate(l for l in lines[1:] if l.strip()):
        t = line.split()
        if len(t) == 3:
            a, b, same = (t[0], int(t[1])), (t[0], int(t[2])), True
        else:
            a, b, same = (t[0], int(t[1])), (t[2], int(t[3])), False
        pairs.append((lfw / a[0] / f"{a[0]}_{a[1]:04d}.jpg", lfw / b[0] / f"{b[0]}_{b[1]:04d}.jpg",
                      same, i // (2 * n)))
    return pairs, n_folds


def roc_points(scores: np.ndarray, labels: np.ndarray, higher_is_same: bool):
    s = scores if higher_is_same else -scores
    order = np.argsort(-s)
    lab = labels[order]
    tp = np.cumsum(lab)
    fp = np.cumsum(~lab)
    tpr = tp / max(1, lab.sum())
    fpr = fp / max(1, (~lab).sum())
    auc = float(np.trapezoid(np.concatenate([[0], tpr]), np.concatenate([[0], fpr])))
    return fpr, tpr, auc


def tar_at_far(fpr, tpr, far: float) -> float:
    ok = fpr <= far
    return float(tpr[ok].max()) if ok.any() else 0.0


def lfw_verification(ex: Extractor, pairs, n_folds: int, op_thr: float) -> dict:
    higher = ex.name == "sface"
    worst = -1.0 if higher else 1e9
    scores, labels, folds, failed = [], [], [], 0
    for a, b, same, fold in pairs:
        fa, _ = ex.feature(a)
        fb, _ = ex.feature(b)
        if fa is None or fb is None:
            failed += 1
            s = worst
        else:
            s = float(np.dot(fa, fb)) if higher else lbph_distance(fa, fb)
        scores.append(s)
        labels.append(same)
        folds.append(fold)
    scores, labels, folds = np.array(scores), np.array(labels), np.array(folds)

    def acc_at(thr, idx):
        pred = scores[idx] >= thr if higher else scores[idx] <= thr
        return float((pred == labels[idx]).mean())

    accs = []
    for k in range(n_folds):
        tr, te = folds != k, folds == k
        cand = np.unique(scores[tr])
        if len(cand) > 400:
            cand = np.quantile(scores[tr], np.linspace(0, 1, 400))
        best = max(cand, key=lambda t: acc_at(t, tr))
        accs.append(acc_at(best, te))
    fpr, tpr, auc = roc_points(scores, labels, higher)
    return {
        "pairs": int(len(pairs)), "detect_failed_pairs": failed,
        "acc_10fold_mean": round(statistics.fmean(accs), 4), "acc_10fold_std": round(statistics.pstdev(accs), 4),
        "auc": round(auc, 4),
        "tar_at_far_1pct": round(tar_at_far(fpr, tpr, 0.01), 4),
        "tar_at_far_0_1pct": round(tar_at_far(fpr, tpr, 0.001), 4),
        "acc_at_operating_threshold": round(acc_at(op_thr, np.ones(len(scores), bool)), 4),
        "operating_threshold": op_thr,
        "roc": {"fpr": [round(float(v), 5) for v in fpr[:: max(1, len(fpr) // 300)]],
                "tpr": [round(float(v), 5) for v in tpr[:: max(1, len(tpr) // 300)]]},
    }


# ── 2) 승선 게이트 모의(개방형 식별) ────────────────────────────────────
def lfw_people(lfw: Path, min_imgs: int):
    out = {}
    for d in sorted(p for p in lfw.iterdir() if p.is_dir()):
        imgs = sorted(p for p in d.iterdir() if p.suffix.lower() in IMG_EXT)
        if len(imgs) >= min_imgs:
            out[d.name] = imgs
    return out


class GateMatcher:
    """앱의 match 와 같은 판정으로 갤러리를 만들고 판정한다."""

    def __init__(self, ex: Extractor, members: dict[str, list[Path]], flip: bool = False):
        self.ex, self.g = ex, Gallery()
        for name, imgs in members.items():
            for p in imgs:
                f, det = ex.feature(p)
                if f is None:
                    continue
                self.g.add({"id": name, "name": name}, f)
                if flip and ex.name == "sface":
                    ff = self._flip_feature(p)
                    if ff is not None:
                        self.g.add({"id": name, "name": name}, ff)
        self.rec, self.label_to_uid = None, {}
        if ex.name == "lbph" and not self.g.empty:
            uid_to_label = {u: i for i, u in enumerate(self.g.users)}
            self.rec = cv2.face.LBPHFaceRecognizer_create()
            self.rec.train([f for _, f in self.g.entries], np.array([uid_to_label[u] for u, _ in self.g.entries]))
            self.label_to_uid = {i: u for u, i in uid_to_label.items()}

    def _flip_feature(self, p: Path):
        img = imread_unicode(p)
        if img is None:
            return None
        img = cv2.flip(fit_image(img), 1)
        eng = self.ex.engine
        det = eng.detect_largest(img) or eng._detect_padded(img)
        return None if det is None else eng.embed(img, det)

    def raw(self, feat):
        """(후보 id, 점수, 마진 통과 여부). SFace 점수는 클수록, LBPH 는 작을수록 유사."""
        if feat is None:
            return None
        if self.ex.name == "sface":
            m = cosine_match(feat, self.g, -2.0, config.FACE_SFACE_MARGIN)
            margin_ok = m.second is None or m.score - m.second >= config.FACE_SFACE_MARGIN
            return (m.candidate or {}).get("id"), m.score, margin_ok
        label, conf = self.rec.predict(feat)
        return self.label_to_uid.get(int(label)), float(conf), True

    def decide_raw(self, raw, thr: float | None = None):
        if raw is None:
            return None
        uid, score, margin_ok = raw
        if self.ex.name == "sface":
            thr = config.FACE_SFACE_THRESHOLD if thr is None else thr
            return uid if score >= thr and margin_ok else None
        thr = config.MATCH_THRESHOLD if thr is None else thr
        return uid if score <= thr else None

    def decide(self, feat, thr: float | None = None):
        return self.decide_raw(self.raw(feat), thr)


SWEEP = {"sface": [round(float(t), 3) for t in np.arange(0.20, 0.701, 0.025)],
         "lbph": [float(t) for t in range(20, 141, 5)]}


def gate_trials(ex: Extractor, people: dict, crew: int, enroll: int, unknown: int, rounds: int,
                seed: int, flip: bool = False) -> dict:
    rng = random.Random(seed)
    names = sorted(people)
    per_round = []
    sweep_counts = {t: {"tar": 0, "far": 0} for t in SWEEP[ex.name]}
    for r in range(rounds):
        pick = rng.sample(names, crew + unknown)
        members = {n: rng.sample(people[n], len(people[n]))[:enroll] for n in pick[:crew]}
        probes = [(n, p) for n in pick[:crew] for p in people[n] if p not in members[n]]
        probes += [(None, p) for n in pick[crew:] for p in people[n][:10]]
        gm = GateMatcher(ex, members, flip=flip)
        c = {"tar": 0, "misid": 0, "frr": 0, "far": 0, "gen": 0, "imp": 0}
        for truth, p in probes:
            raw = gm.raw(ex.feature(p)[0])
            for t, sc in sweep_counts.items():
                pt = gm.decide_raw(raw, t)
                if truth is None:
                    sc["far"] += pt is not None
                else:
                    sc["tar"] += pt == truth
            pred = gm.decide_raw(raw)
            if truth is None:
                c["imp"] += 1
                c["far"] += pred is not None
            else:
                c["gen"] += 1
                c["tar"] += pred == truth
                c["misid"] += pred is not None and pred != truth
                c["frr"] += pred is None
        per_round.append({k: c[k] / c["gen" if k in ("tar", "misid", "frr") else "imp"]
                          for k in ("tar", "misid", "frr", "far")} | {"gen": c["gen"], "imp": c["imp"]})

    def ms(k):
        v = [x[k] for x in per_round]
        return {"mean": round(statistics.fmean(v), 4), "std": round(statistics.pstdev(v), 4)}
    n_gen = sum(x["gen"] for x in per_round)
    n_imp = sum(x["imp"] for x in per_round)
    sweep = [{"thr": t, "TAR": round(c["tar"] / n_gen, 4), "FAR": round(c["far"] / n_imp, 4)}
             for t, c in sweep_counts.items()]
    ok = [x for x in sweep if x["FAR"] <= 0.01]
    best = max(ok, key=lambda x: x["TAR"]) if ok else None
    return {"crew": crew, "enroll_per_person": enroll, "unknown_people": unknown, "rounds": rounds,
            "genuine_trials": n_gen, "impostor_trials": n_imp,
            "TAR": ms("tar"), "misID": ms("misid"), "FRR": ms("frr"), "FAR": ms("far"),
            "sweep": sweep, "best_TAR_at_FAR_le_1pct": best}


# ── 3) 실제 설치 카메라 ─────────────────────────────────────────────────
def device_eval(exs: dict, gallery_dir: Path, frames_dir: Path, people: dict, crew: int, enroll: int,
                seed: int, flip: bool = False) -> dict:
    rng = random.Random(seed)
    enrolled = sorted(p for p in gallery_dir.iterdir() if p.suffix.lower() in IMG_EXT)
    others = rng.sample(sorted(people), crew - 1)
    members = {"crew0": enrolled} | {n: people[n][:enroll] for n in others}
    frames = sorted(p for p in frames_dir.iterdir() if p.suffix.lower() in IMG_EXT)
    # 얼굴이 있는 프레임 = 어느 엔진이든 검출한 프레임(사람이 화면 밖인 프레임 제외)
    det = {n: [ex.feature(p, padded_retry=False) for p in frames] for n, ex in exs.items()}
    present = [i for i in range(len(frames)) if any(det[n][i][1] is not None for n in exs)]
    poses = {}
    if "sface" in exs:
        for i in present:
            d = det["sface"][i][1]
            poses[i] = (pose_of(d) or "between") if d is not None else "unknown"
    out = {"frames_total": len(frames), "frames_with_face": len(present), "engines": {}}
    for n, ex in exs.items():
        gm = GateMatcher(ex, members, flip=flip)
        rows = []
        for i in present:
            f, d = det[n][i]
            pred = gm.decide(f) if f is not None else None
            rows.append((i, d is not None, pred == "crew0", pred is not None and pred != "crew0"))
        res = {"detected": sum(r[1] for r in rows) / len(rows),
               "accepted_correct": sum(r[2] for r in rows) / len(rows),
               "misidentified": sum(r[3] for r in rows) / len(rows), "by_pose": {}}
        for pose in ("front", "between", "side"):
            sub = [r for r in rows if poses.get(r[0]) == pose]
            if sub:
                res["by_pose"][pose] = {"frames": len(sub), "detected": round(sum(r[1] for r in sub) / len(sub), 4),
                                        "accepted_correct": round(sum(r[2] for r in sub) / len(sub), 4)}
        res = {k: (round(v, 4) if isinstance(v, float) else v) for k, v in res.items()}
        out["engines"][n] = res
    return out


# ── 4) 시간 투표 ────────────────────────────────────────────────────────
def voting_eval(ex: Extractor, people: dict, crew: int, enroll: int, rounds: int, seed: int,
                thr: float | None = None) -> dict:
    """미등록자 사진 5장을 0.2초 간격 연속 검출로 보고, 단일 사진 오수락과 투표 확정 확률을 비교."""
    rng = random.Random(seed)
    names = sorted(n for n in people if len(people[n]) >= enroll + 5)
    single_acc = single_n = seq_conf = seq_n = 0
    for r in range(rounds):
        pick = rng.sample(names, crew + 40)
        gm = GateMatcher(ex, {n: people[n][:enroll] for n in pick[:crew]})
        for n in pick[crew:]:
            imgs = people[n]
            for _ in range(5):
                seq = rng.sample(imgs, 5)
                v = RecognitionVoter(config.FACE_VOTE_WINDOW, config.FACE_VOTE_NEED, config.FACE_VOTE_SECONDS)
                confirmed = None
                for k, p in enumerate(seq):
                    pred = gm.decide(ex.feature(p)[0], thr)
                    single_n += 1
                    single_acc += pred is not None
                    c, _ = v.vote(pred, now=1000.0 + 0.2 * k)
                    confirmed = confirmed or c
                seq_n += 1
                seq_conf += confirmed is not None
    return {"threshold": thr, "single_image_FAR": round(single_acc / single_n, 5), "single_trials": single_n,
            "voted_FAR": round(seq_conf / seq_n, 5), "voted_sequences": seq_n,
            "rule": f"{config.FACE_VOTE_NEED} of {config.FACE_VOTE_WINDOW} within {config.FACE_VOTE_SECONDS}s"}


# ── 5) 처리 시간 ────────────────────────────────────────────────────────
def timing(exs: dict, frames: list[Path], n: int = 60) -> dict:
    out = {}
    imgs = [cv2.resize(imread_unicode(p), (640, 480)) for p in frames[:n]]
    for name, ex in exs.items():
        eng = ex.engine
        for im in imgs[:3]:
            eng.detect_largest(im)
        ts = []
        for im in imgs:
            t = time.perf_counter()
            d = eng.detect_largest(im)
            if d is not None:
                eng.embed(im, d)
            ts.append(1000 * (time.perf_counter() - t))
        out[name] = {"ms_median": round(statistics.median(ts), 1), "ms_p90": round(float(np.percentile(ts, 90)), 1),
                     "frames": len(ts)}
    return out


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--lfw", type=Path, help="LFW 이미지 폴더(사람별 하위 폴더 + pairs.txt)")
    ap.add_argument("--device-gallery", type=Path, help="앱 등록 사진 폴더(한 사람)")
    ap.add_argument("--device-frames", type=Path, help="설치 카메라 프레임 폴더(같은 사람)")
    ap.add_argument("--engines", nargs="+", default=["lbph", "sface"], choices=["lbph", "sface"])
    ap.add_argument("--crew", type=int, default=10)
    ap.add_argument("--enroll", type=int, default=config.FACE_ENROLL_SAMPLES)
    ap.add_argument("--unknown", type=int, default=50)
    ap.add_argument("--rounds", type=int, default=10)
    ap.add_argument("--seed", type=int, default=20261101)
    ap.add_argument("--flip-enroll", action="store_true", help="(실험) 등록 사진 좌우 반전 특징도 갤러리에 추가")
    ap.add_argument("--timing-only", action="store_true", help="처리 시간만 측정(기기에서 실행)")
    ap.add_argument("--out", type=Path)
    args = ap.parse_args()

    exs = {n: Extractor(n) for n in args.engines}
    result: dict = {"config": {"sface_threshold": config.FACE_SFACE_THRESHOLD, "sface_margin": config.FACE_SFACE_MARGIN,
                               "lbph_threshold": config.MATCH_THRESHOLD, "vote": [config.FACE_VOTE_NEED, config.FACE_VOTE_WINDOW],
                               "opencv": cv2.__version__, "flip_enroll": args.flip_enroll}}
    if args.timing_only:
        frames = sorted(p for p in args.device_frames.iterdir() if p.suffix.lower() in IMG_EXT)
        result["timing"] = timing(exs, frames)
        print(json.dumps(result, ensure_ascii=False, indent=1))
        if args.out:
            args.out.parent.mkdir(parents=True, exist_ok=True)
            args.out.write_text(json.dumps(result, ensure_ascii=False, indent=1), encoding="utf-8")
        return

    people = lfw_people(args.lfw, 10)
    pairs, n_folds = read_pairs(args.lfw)
    for name, ex in exs.items():
        t = time.time()
        op = config.FACE_SFACE_THRESHOLD if name == "sface" else config.MATCH_THRESHOLD
        result.setdefault("lfw_verification", {})[name] = lfw_verification(ex, pairs, n_folds, op)
        result.setdefault("gate_simulation", {})[name] = gate_trials(
            ex, people, args.crew, args.enroll, args.unknown, args.rounds, args.seed, args.flip_enroll)
        result.setdefault("voting", {})[name] = voting_eval(ex, people, args.crew, args.enroll, 3, args.seed)
        print(f"[{name}] {time.time() - t:.0f}s", file=sys.stderr)
    if args.device_gallery and args.device_frames:
        result["device"] = device_eval(exs, args.device_gallery, args.device_frames, people,
                                       args.crew, args.enroll, args.seed, args.flip_enroll)
        frames = sorted(p for p in args.device_frames.iterdir() if p.suffix.lower() in IMG_EXT)
        result["timing_pc"] = timing(exs, frames)

    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(json.dumps(result, ensure_ascii=False, indent=1), encoding="utf-8")
    v, g = result["lfw_verification"], result["gate_simulation"]
    print("| 항목 | " + " | ".join(exs) + " |")
    print("|---|" + "---|" * len(exs))
    rows = [("LFW 10-fold 정확도", lambda n: f"{v[n]['acc_10fold_mean']:.2%}"),
            ("LFW AUC", lambda n: f"{v[n]['auc']:.4f}"),
            ("LFW TAR@FAR=1%", lambda n: f"{v[n]['tar_at_far_1pct']:.2%}"),
            ("LFW 검출 실패 쌍", lambda n: str(v[n]["detect_failed_pairs"])),
            ("게이트 TAR", lambda n: f"{g[n]['TAR']['mean']:.2%}"),
            ("게이트 타인 오인식", lambda n: f"{g[n]['misID']['mean']:.2%}"),
            ("게이트 미등록자 오수락", lambda n: f"{g[n]['FAR']['mean']:.2%}"),
            ("게이트 최적 임계값 TAR(FAR≤1%)", lambda n: "-" if not g[n]["best_TAR_at_FAR_le_1pct"]
             else f"{g[n]['best_TAR_at_FAR_le_1pct']['TAR']:.2%} (thr {g[n]['best_TAR_at_FAR_le_1pct']['thr']})"),
            ("투표 전 오수락", lambda n: f"{result['voting'][n]['single_image_FAR']:.2%}"),
            ("투표 후 오수락", lambda n: f"{result['voting'][n]['voted_FAR']:.2%}")]
    if "device" in result:
        d = result["device"]["engines"]
        rows += [("설치 카메라 검출률", lambda n: f"{d[n]['detected']:.2%}"),
                 ("설치 카메라 본인 인식", lambda n: f"{d[n]['accepted_correct']:.2%}")]
    for label, f in rows:
        print(f"| {label} | " + " | ".join(f(n) for n in exs) + " |")


if __name__ == "__main__":
    main()
