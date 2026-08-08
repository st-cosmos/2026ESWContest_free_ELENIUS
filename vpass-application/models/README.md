# models/

구명조끼 착용 분류 TFLite 모델 배치 위치입니다.

- `jacket_classifier.tflite` — `tools/train_jacket_classifier.py` 로 학습한
  가슴 ROI 이진 분류기. 이 파일이 있으면 `jacketvision.py` 가 자동으로
  ML 판정을 사용하고, 없으면 HSV 색 검사로 폴백합니다.
- 경로는 `VPASS_JACKET_MODEL` 환경변수로 바꿀 수 있습니다.

`*.tflite` 는 `.gitignore` 에 걸려 있어 저장소에 커밋되지 않습니다. 모델은
바이너리라 재학습할 때마다 저장소가 불어나므로 밖에서 따로 관리하고, 배포
대상 기기에는 학습 PC 에서 직접 복사합니다.

```bash
scp models/jacket_classifier.tflite pi@<라즈베리파이>:~/workspace/smart-vpass-system/vpass-application/models/
```

파일이 없으면 앱은 HSV 폴백으로 정상 동작하므로, 새 기기를 셋업할 때 모델
복사를 잊어도 승선 판정 자체는 멈추지 않습니다. 적용 여부는 앱 시작 로그의
`[jacketvision] TFLite 모델 로드` 줄로 확인하세요.

학습·배포 절차는 상위 `README.md` 의 "분류 모델 학습·배포" 절 참고.
