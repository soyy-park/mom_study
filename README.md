# mom_study

학습 영상 퀴즈를 **캡처 → OCR → PDF/클라우드 동기화 → 폰 PWA 로 다시보기**하는 파이프라인.

## 진행 상황

| 단계 | 파일 | 상태 |
|---|---|---|
| 1. 화면 캡처 | `capture_app.py` | ✅ |
| 2. OCR 추출 + 정답 자동 감지 | `ocr_pipeline.py` | ✅ (Google Vision 키 필요) |
| 3. 구조화 파싱 (문제 단위 분리) | — | 보류 (지금은 보기 단위 정답 표시로 충분) |
| 4. PDF 내보내기 | `export_pdf.py` | ✅ |
| 5. 클라우드 동기화 (Firestore) | `sync_pipeline.py` | ✅ (Firebase 서비스 계정 키 필요) |
| 6. 폰 PWA 로 다시보기 | `webapp/` | ✅ (Firebase Hosting 배포 필요) |

## 개발 환경

패키지 매니저는 [uv](https://docs.astral.sh/uv/). 이 폴더가 Google Drive 동기화 폴더 안에
있으면 가상환경을 Drive 밖에 둬야 하므로, `run.cmd`(cmd/PowerShell) 또는 `run.ps1` 래퍼로
uv 명령을 실행한다. Drive 밖에서 작업한다면 래퍼 없이 `uv` 를 직접 써도 된다.

```cmd
run.cmd sync                                    :: 의존성 설치 / 갱신
run.cmd run python capture_app.py               :: 1단계 캡처 GUI
run.cmd run python ocr_pipeline.py              :: 2단계 OCR 실행
run.cmd run python ocr_pipeline.py --selftest   :: GUI/키 없이 동작 검증
run.cmd run python export_pdf.py                :: 4단계 PDF 내보내기
run.cmd run python sync_pipeline.py             :: 5단계 Firestore 동기화
```

## 1단계 — 캡처 (`capture_app.py`)

메인 창에서 과목명을 입력하고 **캡처** 버튼 → 전체화면 반투명 오버레이에서 드래그로
영역 선택 → 그 영역만 `capture/{과목명}_{YYYYMMDD_HHMMSS}.png` 로 저장. ESC 로 취소.

## 2단계 — OCR + 정답 감지 (`ocr_pipeline.py`)

`capture/` 의 PNG 를 읽어 OCR → `ocr_text/{이름}.txt` (원문) + `ocr_json/{이름}.json`
(과목·캡처시각·원문·문단 위치). OCR 백엔드는 교체 가능:

**정답 자동 감지**: 이 강의 플랫폼은 정답 보기를 파란색 원으로 표시한다. 각 보기
줄 앞부분(번호 동그라미)의 색상을 원본 이미지에서 직접 샘플링해 파란색이면 그 줄
앞에 `[정답] ` 을 붙인다 — 별도 AI 모델 없이 Vision API 가 이미 주는 좌표로 평균
RGB만 비교하는 방식이라 추가 비용/호출이 없다. `export_pdf.py`(굵은 파란 글씨)와
`webapp/`(파란 강조) 모두 이 마커를 그대로 강조해서 보여준다. 화면에 정답이
파란색으로 표시되지 않는 퀴즈(다른 강의 플랫폼 등)에서는 감지되지 않는다.

- `google` — Google Cloud Vision REST API. `.env.example` 을 `.env` 로 복사하고
  `GOOGLE_VISION_API_KEY` 를 채운다.
- `stub` — API 키 없이 파이프라인 배관을 검증하는 가짜 백엔드.

```cmd
run.cmd run python ocr_pipeline.py --backend google
run.cmd run python ocr_pipeline.py --force        :: 이미 처리한 것도 다시
```

## 4단계 — PDF 내보내기 (`export_pdf.py`)

`ocr_json/` 을 과목별로 묶고 캡처시각순으로 정렬해 `pdf/quiz_review.pdf` 한 장으로 합친다.

```cmd
run.cmd run python export_pdf.py                  :: 전체 -> pdf/quiz_review.pdf
run.cmd run python export_pdf.py --subject 수학     :: 특정 과목만
run.cmd run python export_pdf.py --selftest        :: 합성 데이터로 검증
```

## 5단계 — 클라우드 동기화 (`sync_pipeline.py`)

`ocr_json/` 을 Firestore `captures` 컬렉션에 올려서, PC 가 꺼져 있어도 폰 PWA 에서
조회할 수 있게 한다.

1. [Firebase 콘솔](https://console.firebase.google.com/) 에서 프로젝트 생성(기존 Vision
   API 를 쓰는 GCP 프로젝트를 그대로 써도 됨), Firestore 사용 설정.
2. 프로젝트 설정 → 서비스 계정 → "새 비공개 키 생성" 으로 JSON 다운로드. **이 폴더는
   Google Drive 동기화 폴더이므로 키 파일은 Drive 밖에 저장한다** (예:
   `%LOCALAPPDATA%\mom_study\firebase-service-account.json`).
3. `.env` 에 `FIREBASE_PROJECT_ID`, `FIREBASE_SERVICE_ACCOUNT_PATH` 채우기.

```cmd
run.cmd run python sync_pipeline.py --dry-run    :: 실제 전송 없이 페이로드만 확인
run.cmd run python sync_pipeline.py              :: 실제 동기화 (이미 된 건 skip)
run.cmd run python sync_pipeline.py --force      :: 이미 된 것도 다시
run.cmd run python sync_pipeline.py --selftest   :: 키/네트워크 없이 동작 검증
```

## 6단계 — 폰에서 다시보기 (`webapp/`, PWA)

과목/날짜별로 묶어서 목록으로 보여주고, 검색과 상세보기를 제공하는 정적 웹앱.
Firebase Hosting 에 배포하면 그 주소를 폰 브라우저에서 열고 "홈 화면에 추가"로
설치해서 앱처럼 쓸 수 있다.

1. `webapp/firebase-config.js` 를 Firebase 콘솔의 웹 앱 SDK 설정값으로 채운다
   (이 값은 비밀키가 아니라 커밋해도 안전 — 접근 제어는 `firestore.rules` 가 담당).
2. 배포 설정은 `firebase.json` 에 이미 들어 있다 (호스팅 = `webapp/`, 규칙 =
   `firestore.rules`). `firestore.rules` 는 `captures` 컬렉션을 읽기 전용 공개로
   설정한다. ⚠️ 즉 이 웹 주소와 설정을 아는 사람은 누구나 캡처된 텍스트를 읽을 수
   있다 — 개인정보가 아닌 학습용 텍스트를 가정한 트레이드오프다.
3. 최초 1회 (Node.js 필요):
   ```cmd
   npm install -g firebase-tools
   firebase login
   firebase use --add       :: 위에서 만든 Firebase 프로젝트 선택 (.firebaserc 생성)
   firebase deploy          :: 호스팅 + Firestore 규칙 함께 배포
   ```
   배포가 끝나면 `https://<프로젝트ID>.web.app` 주소가 출력된다. 폰 브라우저에서 열고
   "홈 화면에 추가"하면 앱 아이콘이 생긴다.
4. 이후 수정할 때마다 `firebase deploy` 로 재배포. 폰은 다음에 열 때 자동 반영된다.
5. 로컬에서 미리 보려면: `webapp/` 안에서 `python -m http.server` 실행 후
   `http://localhost:8000` 접속. (Firestore 는 실제 프로젝트에 연결된다.)

## 커밋하지 않는 것

`.env`(비밀 키), `venv/` · `.venv/`, `capture/` · `ocr_text/` · `ocr_json/` · `pdf/` ·
`sync_state.json`(생성물). Firebase 서비스 계정 키는 이 저장소 안에 두지 않는다
(Drive 동기화 폴더이므로 `.gitignore` 로도 Drive 업로드를 막을 수 없기 때문).
