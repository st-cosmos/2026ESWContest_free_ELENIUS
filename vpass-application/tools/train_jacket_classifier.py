# -*- coding: utf-8 -*-
"""구명조끼 착용 분류기 학습 스크립트 (개발 PC 전용).

가슴 ROI 크롭 이미지를 입력으로 착용/미착용을 판정하는 MobileNetV3-Small
이진 분류기를 전이학습하고, 라즈베리파이용 int8 양자화 TFLite 로 내보낸다.
결과 모델은 vpass 앱의 jacketvision.py 가 그대로 로드한다.

전체 워크플로:
  1. 데이터 수집 — 실제 운용 환경(같은 카메라/조명/각도)에서 앱을 켜고
     ROI 크롭을 자동 저장한다:
       VPASS_JACKET_CAPTURE=1 uv run vpass
     크롭은 data/jacket_dataset/unsorted/ 에 저장되며, 파일명 뒤의 점수
     (hsv0.42 등)는 분류 참고용이다. 착용/미착용 상황을 골고루 찍는다.
  2. 라벨링 — 크롭을 두 폴더로 사람이 직접 분류한다:
       data/jacket_dataset/jacket/      (구명조끼 착용)
       data/jacket_dataset/no_jacket/   (미착용 — 일반 옷, 주황색 옷 포함 권장)
     클래스당 최소 200장, 조명/사람/각도가 다양할수록 좋다.
     Roboflow Universe 등의 공개 구명조끼 데이터셋에서 상체 크롭을 추가해
     보강해도 된다.
  3. 학습 (이 스크립트, PC 에서):
       pip install "tensorflow>=2.16"
       python tools/train_jacket_classifier.py --data data/jacket_dataset
     완료되면 models/jacket_classifier.tflite 가 생성된다.
  4. 배포 — models/jacket_classifier.tflite 를 라즈베리파이의 같은 경로에
     복사(또는 git 커밋)하고, 파이에서 런타임을 설치한다:
       uv sync --extra ml
     앱 재시작 시 로그에 "[jacketvision] TFLite 모델 로드"가 뜨면 적용된 것.
     이후에도 HSV 구현은 폴백으로 남는다 (VPASS_JACKET_METHOD=hsv 로 강제 가능).

모델 입출력 규약 (jacketvision._TFLiteJacketClassifier 와 맞춰야 함):
  입력  — (1, H, W, 3) RGB, 값 범위 0-255 (전처리는 모델 내부 포함)
  출력  — (1, 1) sigmoid, 구명조끼 착용 확률
"""

from __future__ import annotations

import argparse
import sys
import tempfile
from pathlib import Path

try:
    import tensorflow as tf
except ImportError:
    sys.exit("tensorflow 가 필요합니다 (PC 학습 전용): pip install 'tensorflow>=2.16'")

# 알파벳순 자동 매핑에 맡기지 않고 명시한다: 출력 sigmoid = P(jacket)
CLASS_NAMES = ["no_jacket", "jacket"]


def load_datasets(data_dir: Path, img_size: int, batch: int, seed: int):
    common = dict(
        labels="inferred",
        label_mode="binary",
        class_names=CLASS_NAMES,
        image_size=(img_size, img_size),
        batch_size=batch,
        seed=seed,
        validation_split=0.2,
    )
    train = tf.keras.utils.image_dataset_from_directory(data_dir, subset="training", **common)
    val = tf.keras.utils.image_dataset_from_directory(data_dir, subset="validation", **common)
    auto = tf.data.AUTOTUNE
    return train.prefetch(auto), val.prefetch(auto)


def build_model(img_size: int) -> tf.keras.Model:
    base = tf.keras.applications.MobileNetV3Small(
        input_shape=(img_size, img_size, 3),
        include_top=False,
        weights="imagenet",
        include_preprocessing=True,  # 모델이 0-255 입력을 직접 받는다
    )
    base.trainable = False

    augment = tf.keras.Sequential([
        tf.keras.layers.RandomFlip("horizontal"),
        tf.keras.layers.RandomRotation(0.05),
        tf.keras.layers.RandomZoom(0.1),
        tf.keras.layers.RandomBrightness(0.2, value_range=(0.0, 255.0)),
        tf.keras.layers.RandomContrast(0.2),
    ], name="augment")

    inputs = tf.keras.Input(shape=(img_size, img_size, 3))
    x = augment(inputs)
    x = base(x, training=False)
    x = tf.keras.layers.GlobalAveragePooling2D()(x)
    x = tf.keras.layers.Dropout(0.2)(x)
    outputs = tf.keras.layers.Dense(1, activation="sigmoid", name="jacket_prob")(x)
    return tf.keras.Model(inputs, outputs)


def convert_tflite(model: tf.keras.Model, train_ds, out_path: Path) -> None:
    """int8 전체 양자화 변환. 실패 시 dynamic-range 양자화로 폴백한다."""
    with tempfile.TemporaryDirectory() as tmp:
        saved = str(Path(tmp) / "saved_model")
        model.export(saved)  # Keras 3 호환 경로: SavedModel 을 거쳐 변환

        def representative_data():
            for images, _ in train_ds.take(64):
                for img in images[:4]:
                    yield [tf.expand_dims(tf.cast(img, tf.float32), 0)]

        converter = tf.lite.TFLiteConverter.from_saved_model(saved)
        converter.optimizations = [tf.lite.Optimize.DEFAULT]
        converter.representative_dataset = representative_data
        converter.target_spec.supported_ops = [tf.lite.OpsSet.TFLITE_BUILTINS_INT8]
        converter.inference_input_type = tf.uint8
        converter.inference_output_type = tf.uint8
        try:
            blob = converter.convert()
            kind = "int8 전체 양자화"
        except Exception as e:
            print(f"[변환] int8 양자화 실패({e}) — dynamic-range 로 폴백")
            converter = tf.lite.TFLiteConverter.from_saved_model(saved)
            converter.optimizations = [tf.lite.Optimize.DEFAULT]
            blob = converter.convert()
            kind = "dynamic-range 양자화 (float32 입출력)"

    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_bytes(blob)
    print(f"[변환] {kind} → {out_path} ({len(blob) / 1024:.0f} KB)")


def main():
    app_dir = Path(__file__).resolve().parents[1]
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--data", type=Path, default=app_dir / "data" / "jacket_dataset",
                    help="jacket/ 과 no_jacket/ 하위 폴더를 가진 데이터셋 디렉터리")
    ap.add_argument("--out", type=Path, default=app_dir / "models" / "jacket_classifier.tflite")
    ap.add_argument("--img-size", type=int, default=128)
    ap.add_argument("--batch", type=int, default=32)
    ap.add_argument("--epochs", type=int, default=12, help="헤드 학습 epoch")
    ap.add_argument("--fine-tune-epochs", type=int, default=5,
                    help="백본 상위 레이어 미세조정 epoch (0 이면 생략)")
    ap.add_argument("--seed", type=int, default=1234)
    args = ap.parse_args()

    for cls in CLASS_NAMES:
        d = args.data / cls
        n = len(list(d.glob("*"))) if d.is_dir() else 0
        if n == 0:
            sys.exit(f"데이터 없음: {d} — 스크립트 상단 docstring 의 수집/라벨링 절차 참고")
        print(f"[데이터] {cls}: {n}장")

    train_ds, val_ds = load_datasets(args.data, args.img_size, args.batch, args.seed)
    model = build_model(args.img_size)

    model.compile(optimizer=tf.keras.optimizers.Adam(1e-3),
                  loss="binary_crossentropy", metrics=["accuracy"])
    print("\n[1/3] 분류 헤드 학습 (백본 고정)")
    model.fit(train_ds, validation_data=val_ds, epochs=args.epochs)

    if args.fine_tune_epochs > 0:
        print("\n[2/3] 백본 상위 레이어 미세조정")
        base = next(l for l in model.layers if l.name.startswith("MobilenetV3")
                    or "mobilenet" in l.name.lower())
        base.trainable = True
        for layer in base.layers[:-30]:  # 상위 30개 레이어만 학습
            layer.trainable = False
        model.compile(optimizer=tf.keras.optimizers.Adam(1e-5),
                      loss="binary_crossentropy", metrics=["accuracy"])
        model.fit(train_ds, validation_data=val_ds, epochs=args.fine_tune_epochs)

    loss, acc = model.evaluate(val_ds, verbose=0)
    print(f"\n[평가] 검증 정확도 {acc:.1%} (loss {loss:.4f})")
    if acc < 0.9:
        print("[경고] 검증 정확도가 90% 미만입니다 — 데이터를 더 모으거나 오분류 샘플을 확인하세요")

    print("\n[3/3] TFLite 변환")
    convert_tflite(model, train_ds, args.out)
    print("\n완료. 라즈베리파이 배포:")
    print(f"  1) {args.out.relative_to(app_dir)} 를 파이의 같은 경로로 복사")
    print("  2) 파이에서: uv sync --extra ml")
    print("  3) 앱 재시작 → 로그에 '[jacketvision] TFLite 모델 로드' 확인")


if __name__ == "__main__":
    main()
