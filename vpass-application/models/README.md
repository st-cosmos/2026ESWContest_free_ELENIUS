# models/

구명조끼 착용 분류 TFLite 모델 배치 위치입니다.

- `jacket_classifier.tflite` — `tools/train_jacket_classifier.py` 로 학습한
  가슴 ROI 이진 분류기. 이 파일이 있으면 `jacketvision.py` 가 자동으로
  ML 판정을 사용하고, 없으면 HSV 색 검사로 폴백합니다.
- 경로는 `VPASS_JACKET_MODEL` 환경변수로 바꿀 수 있습니다.

학습·배포 절차는 상위 `README.md` 의 "분류 모델 학습·배포" 절 참고.
