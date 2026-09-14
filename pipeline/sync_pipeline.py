"""OCR 결과 -> Firestore 동기화 (5단계)

data/ocr_json/ 의 레코드(캡처 한 장, 문제 여러 개 포함 가능)를 문제 단위로 풀어서
Firestore `questions` 컬렉션에 올린다. 캡처 화면 좌표(paragraphs/bbox)나 원본
텍스트 통짜(full_text)는 뷰어에 불필요해 동기화하지 않고, 과목/문제/보기/
정답번호 같은 필요한 필드만 보낸다.

문서 ID는 "{캡처파일명}_q{순번}" (예: 수학_20260910_090000_q1). 캡처 하나를
--force 로 다시 동기화했을 때 문제 개수가 줄면, 이전에 올라간 초과분 문서가
Firestore 에 남을 수 있다(자동 정리는 하지 않음 - 드물게 재동기화하는
개인용 규모라 지금은 콘솔에서 수동 삭제로 충분하다고 판단).

인증: Firebase 서비스 계정 키. 이 폴더는 Google Drive 동기화 폴더라 .gitignore
에 넣어도 파일 자체가 Drive 에는 올라가므로, 키 파일은 Drive 밖(.env 의
FIREBASE_SERVICE_ACCOUNT_PATH)에 두고 경로만 참조한다.

사용법 (프로젝트 루트에서 실행):
    python pipeline/sync_pipeline.py                # data/ocr_json 전체 동기화 (이미 된 건 skip)
    python pipeline/sync_pipeline.py --force        # 이미 동기화된 것도 다시
    python pipeline/sync_pipeline.py --dry-run      # 실제 전송 없이 페이로드만 로그
    python pipeline/sync_pipeline.py --selftest     # 키/네트워크 없이 전체 흐름 검증
"""

import argparse
import datetime
import glob
import json
import os
import sys

JSON_DIR = "data/ocr_json"
STATE_PATH = "data/sync_state.json"
COLLECTION = "questions"


# --------------------------------------------------------------------------- #
# .env 로더 (ocr_pipeline.py 와 동일)
# --------------------------------------------------------------------------- #
def load_dotenv(path=".env"):
    if not os.path.isfile(path):
        return
    with open(path, encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, value = line.partition("=")
            key, value = key.strip(), value.strip().strip('"').strip("'")
            os.environ.setdefault(key, value)


# --------------------------------------------------------------------------- #
# Firestore 연결
# --------------------------------------------------------------------------- #
class SyncError(RuntimeError):
    pass


def get_firestore_client(env=None):
    env = env if env is not None else os.environ
    cred_path = env.get("FIREBASE_SERVICE_ACCOUNT_PATH", "")
    project_id = env.get("FIREBASE_PROJECT_ID", "")
    if not cred_path or not os.path.isfile(cred_path):
        raise SyncError(
            "FIREBASE_SERVICE_ACCOUNT_PATH 가 없거나 파일을 찾을 수 없습니다. "
            ".env 에 설정하거나 --dry-run / --selftest 로 실행하세요."
        )

    import firebase_admin
    from firebase_admin import credentials, firestore

    if not firebase_admin._apps:
        cred = credentials.Certificate(cred_path)
        firebase_admin.initialize_app(cred, {"projectId": project_id} if project_id else None)
    return firestore.client()


# --------------------------------------------------------------------------- #
# 레코드 -> Firestore 문서 매핑 (캡처 1개 -> 문제 N개 문서)
# --------------------------------------------------------------------------- #
def _parse_captured_at(captured_at):
    if not captured_at:
        return None
    try:
        # 파일명의 시각은 PC 로컬 시간. 시간대 없이 올리면 Firestore 가 UTC 로 해석해
        # 폰에서 9시간 어긋나므로 로컬 시간대를 붙인다.
        return datetime.datetime.fromisoformat(captured_at).astimezone()
    except ValueError:
        return None


def record_to_docs(stem, record):
    """레코드(캡처 1장) -> [(문서ID, 문서데이터), ...]. 문제가 하나도 파싱 안 됐으면 빈 리스트."""
    subject = record.get("subject") or "무제"
    captured_dt = _parse_captured_at(record.get("captured_at"))
    synced_at = datetime.datetime.now(datetime.timezone.utc)
    source_image = record.get("source_image", "")
    ocr_backend = record.get("ocr_backend", "")

    docs = []
    for i, q in enumerate(record.get("questions") or [], start=1):
        doc = {
            "subject": subject,
            "question": q.get("question", ""),
            "choices": q.get("choices", []),
            "answer_index": q.get("answer_index"),
            "captured_at": captured_dt,
            "source_image": source_image,
            "ocr_backend": ocr_backend,
            "synced_at": synced_at,
        }
        docs.append((f"{stem}_q{i}", doc))
    return docs


# --------------------------------------------------------------------------- #
# 로컬 동기화 상태 (재실행 시 skip 판단용)
# --------------------------------------------------------------------------- #
def load_sync_state(path):
    if not os.path.isfile(path):
        return {}
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)


def save_sync_state(path, state):
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(state, fh, ensure_ascii=False, indent=2)


# --------------------------------------------------------------------------- #
# 파이프라인
# --------------------------------------------------------------------------- #
def run_sync(json_dir=JSON_DIR, client=None, state_path=STATE_PATH,
             force=False, dry_run=False, log=print):
    if client is None and not dry_run:
        raise SyncError("client 가 없습니다 (dry_run=False 인 경우 필수).")

    if not os.path.isdir(json_dir):
        log(f"[sync] 입력 폴더 없음: {json_dir}  (ocr_pipeline.py 를 먼저 실행하세요)")
        return {"synced": 0, "skipped": 0, "failed": 0}

    state = load_sync_state(state_path)
    paths = sorted(glob.glob(os.path.join(json_dir, "*.json")))
    if not paths:
        log(f"[sync] {json_dir}/ 에 동기화할 OCR 결과가 없습니다.")
        return {"synced": 0, "skipped": 0, "failed": 0}

    synced = skipped = failed = 0
    for path in paths:
        stem = os.path.splitext(os.path.basename(path))[0]
        if stem in state and not force:
            skipped += 1
            continue

        with open(path, encoding="utf-8") as fh:
            record = json.load(fh)
        docs = record_to_docs(stem, record)

        if not docs:
            # 업로드할 문제가 없을 뿐 처리 자체는 끝났으므로 synced 로 세고, 다음
            # 실행에서 이 캡처를 또 시도하지 않도록 state 에 기록한다.
            log(f"[sync] skip    {stem}  (파싱된 문제 없음)")
            state[stem] = datetime.datetime.now(datetime.timezone.utc).isoformat()
            synced += 1
            continue

        if dry_run:
            for doc_id, doc in docs:
                log(f"[sync] dry-run {doc_id}  subject={doc['subject']}  "
                    f"question={doc['question']!r}  보기{len(doc['choices'])}개  "
                    f"정답={doc['answer_index']}")
        else:
            ok = True
            for doc_id, doc in docs:
                try:
                    client.collection(COLLECTION).document(doc_id).set(doc)
                except Exception as exc:  # noqa: BLE001 - 네트워크/권한 오류는 건너뛰고 계속
                    failed += 1
                    ok = False
                    log(f"[sync] FAIL    {doc_id}  -> {exc!r}")
                    continue
                log(f"[sync] ok      {doc_id}  subject={doc['subject']}")
            if not ok:
                continue

        state[stem] = datetime.datetime.now(datetime.timezone.utc).isoformat()
        synced += 1

    if not dry_run:
        save_sync_state(state_path, state)

    log(f"[sync] 완료: 동기화 {synced} / 건너뜀 {skipped} / 실패 {failed}")
    return {"synced": synced, "skipped": skipped, "failed": failed}


# --------------------------------------------------------------------------- #
# 셀프테스트 (Firestore 없이 검증)
# --------------------------------------------------------------------------- #
class FakeFirestoreClient:
    """실제 Firestore 없이 client.collection(x).document(y).set(z) 호출을 기록."""

    def __init__(self):
        self.docs = {}

    def collection(self, name):
        return _FakeCollection(self, name)


class _FakeCollection:
    def __init__(self, client, name):
        self.client = client
        self.name = name

    def document(self, doc_id):
        return _FakeDocument(self.client, self.name, doc_id)


class _FakeDocument:
    def __init__(self, client, collection, doc_id):
        self.client = client
        self.collection = collection
        self.doc_id = doc_id

    def set(self, data):
        self.client.docs[(self.collection, self.doc_id)] = data


def selftest():
    import shutil
    import tempfile

    print("=== sync_pipeline selftest ===")
    print(f"python : {sys.version.split()[0]}  ({sys.platform})")

    tmp = tempfile.mkdtemp(prefix="sync_selftest_")
    jdir = os.path.join(tmp, "ocr_json")
    os.makedirs(jdir)
    state_path = os.path.join(tmp, "sync_state.json")

    # (파일명, 과목, 캡처시각, 문제 리스트) - 실제 구조는 ocr_pipeline.py 의
    # questions 필드와 동일. 캡처 한 장에 문제가 여러 개 있는 경우(영어)와
    # 파싱이 하나도 안 된 경우(국어)를 함께 검증한다.
    fixtures = [
        ("수학_20260910_090000.json", "수학", "2026-09-10T09:00:00", [
            {"question": "다음 중 옳은 것은?", "choices": ["1번", "2번", "3번"], "answer_index": 2},
        ]),
        ("영어_20260911_070000.json", "영어", "2026-09-11T07:00:00", [
            {"question": "빈칸에 알맞은 단어는?", "choices": ["apple", "banana"], "answer_index": 1},
            {"question": "다음 문장을 해석하면?", "choices": ["A", "B", "C"], "answer_index": None},
        ]),
        ("국어_20260912_080000.json", "국어", "2026-09-12T08:00:00", []),
    ]
    expected_docs = sum(len(qs) for *_, qs in fixtures)  # 3

    for name, subject, captured_at, questions in fixtures:
        record = {
            "source_image": name.replace(".json", ".png"),
            "subject": subject,
            "captured_at": captured_at,
            "ocr_backend": "stub",
            "ocr_at": captured_at,
            "full_text": "(생략)",
            "paragraphs": [],
            "questions": questions,
        }
        with open(os.path.join(jdir, name), "w", encoding="utf-8") as fh:
            json.dump(record, fh, ensure_ascii=False)

    print(f"[1] 임시 입력      : {jdir}  (캡처 {len(fixtures)}개, 문제 {expected_docs}개)")

    client = FakeFirestoreClient()
    summary = run_sync(json_dir=jdir, client=client, state_path=state_path,
                        log=lambda m: print("    " + m))
    print(f"[2] 1차 동기화 요약: {summary}")

    doc_count_ok = len(client.docs) == expected_docs
    subjects_ok = {doc["subject"] for doc in client.docs.values()} == {"수학", "영어"}
    fields_ok = all(
        set(doc) == {"subject", "question", "choices", "answer_index",
                      "captured_at", "source_image", "ocr_backend", "synced_at"}
        for doc in client.docs.values()
    )
    types_ok = all(
        isinstance(doc["captured_at"], datetime.datetime) and doc["captured_at"].tzinfo is not None
        for doc in client.docs.values()
    )
    q1 = client.docs.get((COLLECTION, "영어_20260911_070000_q1"))
    q2 = client.docs.get((COLLECTION, "영어_20260911_070000_q2"))
    multi_question_ok = (
        q1 is not None and q1["choices"] == ["apple", "banana"] and q1["answer_index"] == 1
        and q2 is not None and q2["answer_index"] is None
    )
    no_questions_case_ok = (COLLECTION, "국어_20260912_080000_q1") not in client.docs
    print(f"[3] 문서 검증      : count_ok={doc_count_ok}  subjects_ok={subjects_ok}  "
          f"fields_ok={fields_ok}  captured_at_is_aware_datetime={types_ok}  "
          f"multi_question_ok={multi_question_ok}  no_questions_case_ok={no_questions_case_ok}")

    # 재실행 시 skip (국어 캡처도 "문제 없음"으로 처리 완료된 상태라 다시 안 건드림)
    summary2 = run_sync(json_dir=jdir, client=client, state_path=state_path, log=lambda m: None)
    skip_ok = summary2["skipped"] == len(fixtures) and summary2["synced"] == 0
    print(f"[4] 재실행 skip    : {skip_ok}  ({summary2})")

    # --force 재동기화
    summary3 = run_sync(json_dir=jdir, client=client, state_path=state_path, force=True,
                         log=lambda m: None)
    force_ok = summary3["synced"] == len(fixtures)
    print(f"[5] --force 재동기화: {force_ok}  ({summary3})")

    # 전송 실패 시 중단하지 않고 건너뛰는지 (문제가 있는 캡처만 실패 대상이 됨)
    class FailingClient(FakeFirestoreClient):
        def collection(self, name):
            raise RuntimeError("network down")

    summary4 = run_sync(json_dir=jdir, client=FailingClient(), state_path=state_path, force=True,
                         log=lambda m: None)
    fail_ok = summary4["failed"] == expected_docs and summary4["synced"] == 1  # 국어(문제 0개)만 성공
    print(f"[6] 실패 건너뛰기  : {fail_ok}  ({summary4})")

    shutil.rmtree(tmp, ignore_errors=True)

    all_ok = all([
        summary["synced"] == len(fixtures), summary["skipped"] == 0,
        doc_count_ok, subjects_ok, fields_ok, types_ok, multi_question_ok,
        no_questions_case_ok, skip_ok, force_ok, fail_ok,
    ])
    print(f"=== result: {'PASS' if all_ok else 'FAIL'} ===")
    return 0 if all_ok else 1


# --------------------------------------------------------------------------- #
def main():
    parser = argparse.ArgumentParser(description="OCR 결과를 Firestore 로 동기화")
    parser.add_argument("--input", default=JSON_DIR, help="입력 폴더 (기본: data/ocr_json)")
    parser.add_argument("--force", action="store_true", help="이미 동기화된 것도 다시")
    parser.add_argument("--dry-run", action="store_true", help="실제 전송 없이 페이로드만 로그")
    parser.add_argument("--selftest", action="store_true", help="키/네트워크 없이 전체 흐름 검증")
    args = parser.parse_args()

    load_dotenv()

    if args.selftest:
        raise SystemExit(selftest())

    try:
        client = None if args.dry_run else get_firestore_client()
        summary = run_sync(json_dir=args.input, client=client, force=args.force, dry_run=args.dry_run)
    except SyncError as exc:
        print(f"[sync] 설정 오류: {exc}")
        raise SystemExit(2)
    raise SystemExit(0 if summary["failed"] == 0 else 1)


if __name__ == "__main__":
    main()
