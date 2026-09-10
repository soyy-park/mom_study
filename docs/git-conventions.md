# Git / 브랜치 컨벤션

소규모 개인 프로젝트에 맞춘 가벼운 규칙. GitHub Flow 기반 —
`main` 하나를 항상 정상 동작 상태로 두고, 모든 작업은 짧게 사는 브랜치에서 한다.

## 빠른 참조

```bash
git switch main && git pull                 # 최신화
git switch -c feat/ocr-parsing              # 작업 브랜치 생성
# ... 작업 & 커밋 ...
git push -u origin feat/ocr-parsing         # 올리고 PR 생성
# GitHub에서 Squash merge → 브랜치 삭제
git switch main && git pull                 # 병합분 회수
git branch -d feat/ocr-parsing              # 로컬 브랜치 정리
```

---

## 1. 브랜치 전략

| 브랜치 | 용도 | 규칙 |
|---|---|---|
| `main` | 배포/기준선 | 항상 `--selftest` 통과 상태 유지. 직접 커밋하지 않고 PR로만 병합. |
| 작업 브랜치 | 기능/수정 1건 | `main`에서 분기, 1~3일 안에 병합하고 삭제. 하나의 목적만. |

- 작업 브랜치는 **작게** 유지한다. 커지면 쪼갠다.
- `main`이 앞서가면 리베이스로 따라잡는다: `git switch feat/x && git rebase main`.
- 오래된 브랜치(1주+ 방치)는 버리고 다시 딴다.

## 2. 브랜치 이름 규칙

```
<type>/<간단한-설명>
```

- 소문자 영문 + 하이픈(kebab-case). 한글·공백·대문자 금지.
- `<type>`은 커밋 타입과 동일 목록 사용 (아래 3번).
- 설명은 2~4단어. 이슈 번호가 있으면 뒤에 붙여도 됨: `feat/db-schema-12`.

| 예시 | 의미 |
|---|---|
| `feat/ocr-parsing` | OCR 결과 구조화 파싱 기능 |
| `feat/db-save` | DB 저장 단계 |
| `fix/capture-dpi-offset` | 캡처 좌표 어긋남 수정 |
| `refactor/ocr-backend-iface` | OCR 백엔드 인터페이스 정리 |
| `docs/deploy-guide` | 배포 문서 |
| `chore/bump-pillow` | 의존성 버전 상향 |

## 3. 커밋 메시지 규칙

[Conventional Commits](https://www.conventionalcommits.org/) 형식.

```
<type>(<scope>): <제목>

<본문 — 무엇을 왜 바꿨는지. 한국어. 한 줄 72자 내외.>

<꼬리말 — Co-Authored-By, 이슈 참조 등>
```

### 규칙
- **제목**: 명령형·현재형, 50자 이내, 마침표 없음. 한국어/영어 무엇이든 일관되게.
  - 좋음: `feat(ocr): 문제/보기/정답 분리 파서 추가`
  - 나쁨: `파서 추가함.` (타입 없음, 과거형, 모호)
- **scope**(선택): 바뀐 영역. `capture`, `ocr`, `db`, `deploy`, `docs`, `deps` 등.
- **본문**(선택): 사소하지 않은 변경이면 "왜"를 남긴다. "어떻게"는 코드가 말해준다.
- 한 커밋 = 한 논리 단위. 포맷팅과 기능 변경을 섞지 않는다.

### type 목록

| type | 쓰는 경우 |
|---|---|
| `feat` | 사용자에게 보이는 기능 추가/변경 |
| `fix` | 버그 수정 |
| `docs` | 문서만 변경 |
| `refactor` | 동작 변화 없는 내부 구조 개선 |
| `test` | 테스트 추가/수정 |
| `chore` | 빌드·설정·의존성·잡일 (제품 코드 아님) |
| `perf` | 성능 개선 |

## 4. 작업 흐름 (PR)

1. `main` 최신화 후 작업 브랜치 생성.
2. 작게 자주 커밋. WIP 커밋은 병합 전에 정리(squash)해도 된다.
3. 푸시 후 GitHub에서 Pull Request 생성. 제목은 커밋 제목 규칙과 동일.
4. PR 설명에 **무엇을/왜/어떻게 테스트했는지** 적는다.
5. 셀프 리뷰 → **Squash and merge** → 소스 브랜치 삭제(GitHub 버튼).
6. 로컬에서 `git switch main && git pull`, 작업 브랜치 삭제.

### 병합 방식
- 기본 **Squash and merge** — `main` 히스토리를 한 브랜치 = 한 커밋으로 깔끔하게.
- 병합 커밋 제목은 Conventional Commits 형식으로 다듬고 병합한다.

## 5. PR 체크리스트

- [ ] `run.cmd run python capture_app.py --selftest` / `ocr_pipeline.py --selftest` 통과
- [ ] `.env`, `venv/`, `capture/`, `ocr_text/`, `ocr_json/` 등 미포함 (`git status` 확인)
- [ ] 새 의존성은 `pyproject.toml`에 추가하고 `run.cmd sync` 후 `uv.lock` 같이 커밋
- [ ] 동작이 바뀌었으면 `README.md` 갱신

## 6. 태그 / 마일스톤 (선택)

각 단계가 끝나면 태그를 남긴다.

```bash
git tag -a stage-2 -m "OCR 파이프라인 완료"
git push origin stage-2
```

| 태그 | 단계 |
|---|---|
| `stage-1` | 화면 캡처 |
| `stage-2` | OCR 추출 |
| `stage-3` | 구조화 파싱 |
| `stage-4` | DB 저장 |
| `stage-5` | PDF / 모바일 앱 배포 |

## 7. 커밋하지 않는 것

`.gitignore`에 정리돼 있음. 원칙:

- **비밀**: `.env`, API 키, 토큰 — 절대 커밋 금지. 노출되면 즉시 키 폐기·재발급.
- **가상환경**: `venv/`, `.venv/`.
- **생성물**: `capture/`, `ocr_text/`, `ocr_json/`, `__pycache__/`.
- 예시/양식은 올린다: `.env.example`.
