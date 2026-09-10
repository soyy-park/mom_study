# mom_study

학습 영상 퀴즈를 **캡처 → OCR → DB 저장 → PDF/모바일 앱 배포**하는 파이프라인.

## 진행 상황

| 단계 | 파일 | 상태 |
|---|---|---|
| 1. 화면 캡처 | `capture_app.py` | ✅ |
| 2. OCR 추출 | `ocr_pipeline.py` | ✅ (Google Vision 키 필요) |
| 3. 구조화 파싱 (문제/보기/정답) | — | 예정 |
| 4. DB 저장 | — | 예정 |
| 5. PDF / 모바일 앱 배포 | — | 예정 |

## 개발 환경

패키지 매니저는 [uv](https://docs.astral.sh/uv/). 이 폴더가 Google Drive 동기화 폴더 안에
있으면 가상환경을 Drive 밖에 둬야 하므로, `run.cmd`(cmd/PowerShell) 또는 `run.ps1` 래퍼로
uv 명령을 실행한다. Drive 밖에서 작업한다면 래퍼 없이 `uv` 를 직접 써도 된다.

```cmd
run.cmd sync                                    :: 의존성 설치 / 갱신
run.cmd run python capture_app.py               :: 1단계 캡처 GUI
run.cmd run python ocr_pipeline.py              :: 2단계 OCR 실행
run.cmd run python ocr_pipeline.py --selftest   :: GUI/키 없이 동작 검증
```

## 1단계 — 캡처 (`capture_app.py`)

메인 창에서 과목명을 입력하고 **캡처** 버튼 → 전체화면 반투명 오버레이에서 드래그로
영역 선택 → 그 영역만 `capture/{과목명}_{YYYYMMDD_HHMMSS}.png` 로 저장. ESC 로 취소.

## 2단계 — OCR (`ocr_pipeline.py`)

`capture/` 의 PNG 를 읽어 OCR → `ocr_text/{이름}.txt` (원문) + `ocr_json/{이름}.json`
(과목·캡처시각·원문·문단 위치). OCR 백엔드는 교체 가능:

- `google` — Google Cloud Vision REST API. `.env.example` 을 `.env` 로 복사하고
  `GOOGLE_VISION_API_KEY` 를 채운다.
- `stub` — API 키 없이 파이프라인 배관을 검증하는 가짜 백엔드.

```cmd
run.cmd run python ocr_pipeline.py --backend google
run.cmd run python ocr_pipeline.py --force        :: 이미 처리한 것도 다시
```

## 커밋하지 않는 것

`.env`(비밀 키), `venv/` · `.venv/`, `capture/` · `ocr_text/` · `ocr_json/`(생성물).
