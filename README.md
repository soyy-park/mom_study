# mom_study

학습 영상 퀴즈를 **캡처 → OCR → PDF/클라우드 동기화 → 폰 PWA 로 다시보기**하는 파이프라인.

## 사용법 (매일 이렇게 쓰면 됩니다)

준비는 끝나 있다고 가정합니다 (`.env`에 키 설정 완료, `run.cmd sync` 한 번 실행됨).
매번 아래 3단계만 반복하면 됩니다.

### 1. 강의 보다가 퀴즈 나오면 캡처

```cmd
run.cmd run python pipeline/capture_app.py
```

과목명 입력 → **캡처** 버튼 → 문제 영역을 마우스로 드래그해서 선택 → 손 떼면 자동 저장.
같은 창에서 **캡처**를 계속 눌러서 여러 문제를 이어서 찍을 수 있습니다. 잘못 눌렀으면
드래그 중에 `ESC`로 취소. 다 찍었으면 창을 닫으면 됩니다.

### 2. 텍스트로 변환 (정답도 자동으로 표시됨)

```cmd
run.cmd run python pipeline/ocr_pipeline.py
```

방금 캡처한 이미지들을 읽어서 텍스트로 바꿉니다. 화면에서 정답 보기가 파란 원으로
표시돼 있으면 그 줄 앞에 `[정답]`을 자동으로 붙여줍니다. 이미 처리한 캡처는 건너뛰므로
매번 전체를 새로 돌려도 됩니다.

### 3. 결과 확인 — 편한 방법 하나 골라서

| 보고 싶은 방식 | 명령 |
|---|---|
| **폰으로 보기** (추천) | `run.cmd run python pipeline/sync_pipeline.py` 실행 후 폰에서 https://jini-study.web.app 접속 |
| **PDF로 뽑아서 인쇄/공유** | `run.cmd run python pipeline/export_pdf.py` → `data/pdf/quiz_review.pdf` 생성 |

폰 웹 주소는 한 번 접속한 뒤 브라우저 메뉴에서 **"홈 화면에 추가"**를 누르면 앱처럼
아이콘이 생겨서 다음부턴 바로 열립니다. 캡처를 새로 할 때마다 2·3단계만 다시
돌리면 폰/PDF 내용이 갱신됩니다.

### 자주 막히는 것

- `run.cmd`가 "인식할 수 없는 명령"이라고 뜬다 → PowerShell에서는 앞에 `.\`를 붙여야
  합니다: `.\run.cmd run python pipeline/capture_app.py`. `cmd`(검정 창)에서는 그냥 됩니다.
- 명령이 프로젝트 폴더가 아닌 곳에서 안 먹힌다 → 먼저 이동:
  `cd "G:\다른 컴퓨터\내 노트북\googledrive\엄마"`
- 폰 화면에 목록이 안 뜬다 → 2번(OCR) 다음에 `pipeline/sync_pipeline.py`를 안 돌렸을 가능성이
  높습니다. 캡처만 하고 동기화를 깜빡하면 폰에는 안 보입니다.

---

## 진행 상황

| 단계 | 파일 | 상태 |
|---|---|---|
| 1. 화면 캡처 | `pipeline/capture_app.py` | ✅ |
| 2. OCR 추출 + 정답 자동 감지 | `pipeline/ocr_pipeline.py` | ✅ (Google Vision 키 필요) |
| 3. 구조화 파싱 (문제/보기/정답 분리) | `pipeline/quiz_parser.py` | ✅ |
| 4. PDF 내보내기 | `pipeline/export_pdf.py` | ✅ |
| 5. 클라우드 동기화 (Firestore) | `pipeline/sync_pipeline.py` | ✅ (Firebase 서비스 계정 키 필요) |
| 6. 폰 PWA 로 다시보기 | `webapp/` | ✅ 배포됨 — https://jini-study.web.app |

## 개발 환경

패키지 매니저는 [uv](https://docs.astral.sh/uv/). 이 폴더가 Google Drive 동기화 폴더 안에
있으면 가상환경을 Drive 밖에 둬야 하므로, `run.cmd`(cmd/PowerShell) 또는 `run.ps1` 래퍼로
uv 명령을 실행한다. Drive 밖에서 작업한다면 래퍼 없이 `uv` 를 직접 써도 된다.

```cmd
run.cmd sync                                             :: 의존성 설치 / 갱신
run.cmd run python pipeline/capture_app.py               :: 1단계 캡처 GUI
run.cmd run python pipeline/ocr_pipeline.py               :: 2단계 OCR 실행 (3단계 구조화 파싱 포함)
run.cmd run python pipeline/ocr_pipeline.py --selftest   :: GUI/키 없이 동작 검증
run.cmd run python pipeline/export_pdf.py                :: 4단계 PDF 내보내기
run.cmd run python pipeline/sync_pipeline.py             :: 5단계 Firestore 동기화
```

## 프로젝트 구조

```
mom_study/
├── pipeline/          # 1~5단계 파이썬 스크립트
│   ├── capture_app.py     (1단계 캡처)
│   ├── ocr_pipeline.py    (2단계 OCR + 정답 감지)
│   ├── quiz_parser.py     (3단계 구조화 파싱, ocr_pipeline 이 자동 호출)
│   ├── export_pdf.py      (4단계 PDF 내보내기)
│   └── sync_pipeline.py   (5단계 Firestore 동기화)
├── webapp/            # 6단계 폰 PWA (Firebase Hosting 에 배포)
├── data/              # 실행 시 자동 생성되는 산출물 (git 미포함)
│   ├── capture/            캡처 원본 PNG
│   ├── ocr_text/           OCR 원문 txt
│   ├── ocr_json/           OCR 결과 + 구조화된 문제 json
│   ├── pdf/                내보낸 PDF
│   └── sync_state.json     Firestore 동기화 완료 기록
├── docs/              # git-conventions.md 등 프로젝트 문서
├── firebase.json, firestore.rules, .firebaserc   # Firebase 배포 설정 (루트 고정 - CLI 관례)
└── pyproject.toml, uv.lock, run.cmd, run.ps1, .env(.example), README.md
```

## 1단계 — 캡처 (`pipeline/capture_app.py`)

메인 창에서 과목명을 입력하고 **캡처** 버튼 → 전체화면 반투명 오버레이에서 드래그로
영역 선택 → 그 영역만 `data/capture/{과목명}_{YYYYMMDD_HHMMSS}.png` 로 저장. ESC 로 취소.

## 2단계 — OCR + 정답 감지 (`pipeline/ocr_pipeline.py`)

`data/capture/` 의 PNG 를 읽어 OCR → `data/ocr_text/{이름}.txt` (원문) + `data/ocr_json/{이름}.json`
(과목·캡처시각·원문·문단 위치·**구조화된 문제 목록**). OCR 백엔드는 교체 가능:

**정답 자동 감지**: 이 강의 플랫폼은 정답 보기를 파란색 원으로 표시한다. 각 보기
줄 앞부분(번호 동그라미)의 색상을 원본 이미지에서 직접 샘플링해 파란색이면 그 줄을
정답으로 표시한다 — 별도 AI 모델 없이 Vision API 가 이미 주는 좌표로 평균 RGB만
비교하는 방식이라 추가 비용/호출이 없다. 화면에 정답이 파란색으로 표시되지 않는
퀴즈(다른 강의 플랫폼 등)에서는 감지되지 않는다(정답 없이 문제/보기만 저장됨).

- `google` — Google Cloud Vision REST API. `.env.example` 을 `.env` 로 복사하고
  `GOOGLE_VISION_API_KEY` 를 채운다.
- `stub` — API 키 없이 파이프라인 배관을 검증하는 가짜 백엔드.

```cmd
run.cmd run python pipeline/ocr_pipeline.py --backend google
run.cmd run python pipeline/ocr_pipeline.py --force        :: 이미 처리한 것도 다시
```

## 3단계 — 구조화 파싱 (`pipeline/quiz_parser.py`)

`pipeline/ocr_pipeline.py` 가 안에서 자동으로 호출한다(따로 실행할 일 없음). 캡처 한 장에
문제가 여러 개 들어있어도 문단(`paragraphs`)을 정규식 규칙으로 문제 단위로 쪼갠다:

- `1.`, `2.` 처럼 "숫자+ 마침표"로 시작하는 줄을 새 문제의 시작으로 본다.
- 그 다음 줄부터 다음 문제 전까지는 보기로 모으고, 앞에 붙은 번호 기호
  (`①` `1)` 등)는 잘라낸다.
- 정답 표시(위 2단계)가 된 보기의 순번을 `answer_index`(1부터)로 기록한다.
- 브라우저 주소/파일 경로가 같이 캡처된 경우나 "정답풀이" 같은 화면 버튼 글자는
  잡음으로 걸러낸다.

규칙 기반이라 완벽하지 않다 — 문제 번호가 `①②③` 형태이거나 OX 퀴즈처럼 다른
레이아웃이면 정확도가 떨어질 수 있다. 원본 `full_text`/`paragraphs`는 그대로
`data/ocr_json/`에 남아있으니 파싱이 틀려도 정보가 사라지지는 않는다.

```cmd
run.cmd run python pipeline/quiz_parser.py --selftest   # 실제 캡처 예시로 파싱 규칙 검증
```

## 4단계 — PDF 내보내기 (`pipeline/export_pdf.py`)

`data/ocr_json/` 을 과목별로 묶고 캡처시각순으로 정렬해 `data/pdf/quiz_review.pdf` 한 장으로 합친다.

```cmd
run.cmd run python pipeline/export_pdf.py                  :: 전체 -> data/pdf/quiz_review.pdf
run.cmd run python pipeline/export_pdf.py --subject 수학     :: 특정 과목만
run.cmd run python pipeline/export_pdf.py --selftest        :: 합성 데이터로 검증
```

## 5단계 — 클라우드 동기화 (`pipeline/sync_pipeline.py`)

`data/ocr_json/`의 `questions`(문제 단위)를 Firestore `questions` 컬렉션에 문제 1개당
문서 1개로 올려서, PC 가 꺼져 있어도 폰 PWA 에서 조회할 수 있게 한다. 문서 필드는
`subject`(과목), `question`(문제), `choices`(보기 배열), `answer_index`(정답
번호, 1부터·못 찾으면 null), `captured_at`, `source_image`, `ocr_backend`,
`synced_at` 뿐 — 화면 좌표나 원본 텍스트 통짜는 폰에 불필요해 올리지 않는다.
문서 ID는 `{캡처파일명}_q{순번}`.

1. [Firebase 콘솔](https://console.firebase.google.com/) 에서 프로젝트 생성(기존 Vision
   API 를 쓰는 GCP 프로젝트를 그대로 써도 됨), Firestore 사용 설정.
2. 프로젝트 설정 → 서비스 계정 → "새 비공개 키 생성" 으로 JSON 다운로드. **이 폴더는
   Google Drive 동기화 폴더이므로 키 파일은 Drive 밖에 저장한다** (예:
   `%LOCALAPPDATA%\mom_study\firebase-service-account.json`).
3. `.env` 에 `FIREBASE_PROJECT_ID`, `FIREBASE_SERVICE_ACCOUNT_PATH` 채우기.

```cmd
run.cmd run python pipeline/sync_pipeline.py --dry-run    :: 실제 전송 없이 페이로드만 확인
run.cmd run python pipeline/sync_pipeline.py              :: 실제 동기화 (이미 된 건 skip)
run.cmd run python pipeline/sync_pipeline.py --force      :: 이미 된 것도 다시
run.cmd run python pipeline/sync_pipeline.py --selftest   :: 키/네트워크 없이 동작 검증
```

> **여러 컴퓨터에서 쓴다면**: `.env`의 `FIREBASE_SERVICE_ACCOUNT_PATH`는 절대경로라
> 컴퓨터마다 다르다(이 폴더는 Google Drive로 동기화되지만 키 파일 자체는 의도적으로
> Drive 밖에 둔다). 새 컴퓨터에서는 그 컴퓨터의 `%LOCALAPPDATA%`에 키 파일을 따로
> 복사해두고 `.env` 경로를 그 컴퓨터 기준으로 맞춰야 한다. `--dry-run`은 키 없이도
> 되니 파싱 결과만 먼저 확인할 때 쓴다.

## 6단계 — 폰에서 다시보기 (`webapp/`, PWA)

과목/날짜별로 묶어서 목록으로 보여주고, 검색과 상세보기를 제공하는 정적 웹앱.
Firebase Hosting 에 배포하면 그 주소를 폰 브라우저에서 열고 "홈 화면에 추가"로
설치해서 앱처럼 쓸 수 있다.

1. `webapp/firebase-config.js` 를 Firebase 콘솔의 웹 앱 SDK 설정값으로 채운다
   (이 값은 비밀키가 아니라 커밋해도 안전 — 접근 제어는 `firestore.rules` 가 담당).
2. 배포 설정은 `firebase.json` 에 이미 들어 있다 (호스팅 = `webapp/`, 규칙 =
   `firestore.rules`). `firestore.rules` 는 `questions` 컬렉션을 읽기 전용 공개로
   설정한다. ⚠️ 즉 이 웹 주소와 설정을 아는 사람은 누구나 캡처된 문제/보기를 읽을 수
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

   > `firebase login`이 대화형 터미널이 아닌 곳(예: 스크립트/에이전트로 실행)에서
   > 크래시하면(`UV_HANDLE_CLOSING` 등), PowerShell/터미널을 직접 열어 그 안에서
   > 실행할 것 — 실제 배포 주소: **https://jini-study.web.app**
4. 이후 수정할 때마다 `firebase deploy` 로 재배포. 폰은 다음에 열 때 자동 반영된다.
5. 로컬에서 미리 보려면: `webapp/` 안에서 `python -m http.server` 실행 후
   `http://localhost:8000` 접속. (Firestore 는 실제 프로젝트에 연결된다.)

## 커밋하지 않는 것

`.env`(비밀 키), `venv/` · `.venv/`, `data/`(캡처·OCR·PDF·동기화 상태 등 생성물 전부).
Firebase 서비스 계정 키는 이 저장소 안에 두지 않는다(Drive 동기화 폴더이므로
`.gitignore` 로도 Drive 업로드를 막을 수 없기 때문).
