"""학습 영상 퀴즈 캡처 -> OCR 파이프라인 (2단계)

capture/ 폴더의 PNG들을 읽어 OCR 을 돌리고, 결과를 두 형태로 저장한다.
  - ocr_text/{이름}.txt   : OCR 원문 (사람이 눈으로 확인/수정)
  - ocr_json/{이름}.json  : 다음 단계(구조화/DB) 입력용. 과목/캡처시각/원문/문단 위치 포함

OCR 백엔드는 교체 가능:
  - google : Google Cloud Vision REST API (DOCUMENT_TEXT_DETECTION, 한국어 힌트)
  - stub   : 가짜 텍스트 반환. API 키 없이 파이프라인 배관 검증용

사용법:
    python ocr_pipeline.py                     # capture/ 전체 처리 (.env 의 OCR_BACKEND 사용)
    python ocr_pipeline.py --backend google    # 백엔드 강제 지정
    python ocr_pipeline.py --force             # 이미 처리된 것도 다시
    python ocr_pipeline.py --selftest          # GUI/키 없이 전체 흐름 검증
"""

import argparse
import base64
import datetime
import json
import os
import sys

CAPTURE_DIR = "capture"
TEXT_DIR = "ocr_text"
JSON_DIR = "ocr_json"

GOOGLE_VISION_ENDPOINT = "https://vision.googleapis.com/v1/images:annotate"


# --------------------------------------------------------------------------- #
# .env 로더 (외부 의존성 없이)
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
# 파일명 파싱  {과목}_{YYYYMMDD_HHMMSS}.png
# --------------------------------------------------------------------------- #
def parse_capture_name(filename):
    stem = os.path.splitext(os.path.basename(filename))[0]
    subject, captured_at = stem, None
    parts = stem.rsplit("_", 2)
    if len(parts) == 3:
        subject, date_part, time_part = parts
        try:
            dt = datetime.datetime.strptime(date_part + time_part, "%Y%m%d%H%M%S")
            captured_at = dt.isoformat()
        except ValueError:
            subject, captured_at = stem, None
    return subject, captured_at


# --------------------------------------------------------------------------- #
# OCR 백엔드
# --------------------------------------------------------------------------- #
class OcrError(RuntimeError):
    pass


class StubBackend:
    """API 키 없이 파이프라인을 검증하기 위한 가짜 백엔드.

    이미지 옆에 {이름}.expected.txt 가 있으면 그 내용을 반환하고,
    없으면 자리표시 텍스트를 반환한다.
    """

    name = "stub"

    def recognize(self, image_path):
        sidecar = os.path.splitext(image_path)[0] + ".expected.txt"
        if os.path.isfile(sidecar):
            with open(sidecar, encoding="utf-8") as fh:
                text = fh.read().strip()
        else:
            text = f"[STUB OCR] {os.path.basename(image_path)}"
        paragraphs = [
            {"text": line, "bbox": [0, i * 20, 100, i * 20 + 18]}
            for i, line in enumerate(text.splitlines() or [text])
        ]
        return {"full_text": text, "paragraphs": paragraphs}


class GoogleVisionBackend:
    """Google Cloud Vision REST API. API 키 인증."""

    name = "google"

    def __init__(self, api_key, language_hints=("ko", "en"), timeout=30):
        if not api_key:
            raise OcrError(
                "GOOGLE_VISION_API_KEY 가 없습니다. .env 에 넣거나 --backend stub 로 실행하세요."
            )
        self.api_key = api_key
        self.language_hints = list(language_hints)
        self.timeout = timeout

    def recognize(self, image_path):
        import requests  # google 백엔드에서만 필요

        with open(image_path, "rb") as fh:
            content = base64.b64encode(fh.read()).decode("ascii")

        payload = {
            "requests": [
                {
                    "image": {"content": content},
                    "features": [{"type": "DOCUMENT_TEXT_DETECTION"}],
                    "imageContext": {"languageHints": self.language_hints},
                }
            ]
        }
        try:
            resp = requests.post(
                GOOGLE_VISION_ENDPOINT,
                params={"key": self.api_key},
                json=payload,
                timeout=self.timeout,
            )
        except requests.RequestException as exc:
            raise OcrError(f"Vision API 요청 실패: {exc!r}") from exc

        if resp.status_code != 200:
            raise OcrError(f"Vision API HTTP {resp.status_code}: {resp.text[:300]}")

        body = resp.json()
        result = body.get("responses", [{}])[0]
        if "error" in result:
            raise OcrError(f"Vision API error: {result['error']}")

        annotation = result.get("fullTextAnnotation")
        if not annotation:
            return {"full_text": "", "paragraphs": []}

        full_text = annotation.get("text", "")
        paragraphs = []
        for page in annotation.get("pages", []):
            for block in page.get("blocks", []):
                for para in block.get("paragraphs", []):
                    words = []
                    for word in para.get("words", []):
                        words.append(
                            "".join(s.get("text", "") for s in word.get("symbols", []))
                        )
                    para_text = " ".join(w for w in words if w)
                    paragraphs.append(
                        {"text": para_text, "bbox": _poly_to_bbox(para.get("boundingBox"))}
                    )
        return {"full_text": full_text, "paragraphs": paragraphs}


def _poly_to_bbox(poly):
    if not poly:
        return None
    xs, ys = [], []
    for vertex in poly.get("vertices", []):
        xs.append(vertex.get("x", 0))
        ys.append(vertex.get("y", 0))
    if not xs or not ys:
        return None
    return [min(xs), min(ys), max(xs), max(ys)]


def make_backend(name, env=None):
    env = env if env is not None else os.environ
    name = (name or "google").lower()
    if name == "stub":
        return StubBackend()
    if name == "google":
        return GoogleVisionBackend(api_key=env.get("GOOGLE_VISION_API_KEY", ""))
    raise OcrError(f"알 수 없는 OCR_BACKEND: {name!r} (google | stub)")


# --------------------------------------------------------------------------- #
# 파이프라인
# --------------------------------------------------------------------------- #
def process_image(image_path, backend, text_dir, json_dir):
    subject, captured_at = parse_capture_name(image_path)
    ocr = backend.recognize(image_path)

    stem = os.path.splitext(os.path.basename(image_path))[0]
    os.makedirs(text_dir, exist_ok=True)
    os.makedirs(json_dir, exist_ok=True)

    text_path = os.path.join(text_dir, stem + ".txt")
    json_path = os.path.join(json_dir, stem + ".json")

    with open(text_path, "w", encoding="utf-8") as fh:
        fh.write(ocr["full_text"])

    record = {
        "source_image": os.path.basename(image_path),
        "subject": subject,
        "captured_at": captured_at,
        "ocr_backend": backend.name,
        "ocr_at": datetime.datetime.now().isoformat(timespec="seconds"),
        "full_text": ocr["full_text"],
        "paragraphs": ocr["paragraphs"],
    }
    with open(json_path, "w", encoding="utf-8") as fh:
        json.dump(record, fh, ensure_ascii=False, indent=2)

    return record, text_path, json_path


def run_pipeline(input_dir=CAPTURE_DIR, text_dir=TEXT_DIR, json_dir=JSON_DIR,
                 backend_name="google", force=False, log=print, env=None):
    backend = make_backend(backend_name, env=env)
    log(f"[ocr] 백엔드: {backend.name}")

    if not os.path.isdir(input_dir):
        log(f"[ocr] 입력 폴더 없음: {input_dir}  (캡처 프로그램을 먼저 실행하세요)")
        return {"processed": 0, "skipped": 0, "failed": 0}

    images = sorted(
        f for f in os.listdir(input_dir) if f.lower().endswith((".png", ".jpg", ".jpeg"))
    )
    if not images:
        log(f"[ocr] {input_dir}/ 에 이미지가 없습니다.")
        return {"processed": 0, "skipped": 0, "failed": 0}

    processed = skipped = failed = 0
    for name in images:
        stem = os.path.splitext(name)[0]
        json_path = os.path.join(json_dir, stem + ".json")
        if os.path.isfile(json_path) and not force:
            skipped += 1
            log(f"[ocr] skip   {name}  (이미 처리됨)")
            continue
        try:
            record, _, _ = process_image(
                os.path.join(input_dir, name), backend, text_dir, json_dir
            )
        except OcrError as exc:
            failed += 1
            log(f"[ocr] FAIL   {name}  -> {exc}")
            continue
        processed += 1
        chars = len(record["full_text"])
        paras = len(record["paragraphs"])
        log(f"[ocr] ok     {name}  과목={record['subject']}  {chars}자  문단{paras}개")

    log(f"[ocr] 완료: 처리 {processed} / 건너뜀 {skipped} / 실패 {failed}")
    return {"processed": processed, "skipped": skipped, "failed": failed}


# --------------------------------------------------------------------------- #
# 셀프테스트
# --------------------------------------------------------------------------- #
def selftest():
    import tempfile

    print("=== ocr_pipeline selftest ===")
    print(f"python   : {sys.version.split()[0]}  ({sys.platform})")
    try:
        import requests

        print(f"requests : {requests.__version__}  (google 백엔드용, 설치됨)")
    except ImportError:
        print("requests : 미설치 (stub/selftest 엔 불필요, google 백엔드 쓸 때 설치)")

    # google 백엔드 모듈이 구성 자체는 되는지 (API 호출은 안 함)
    try:
        GoogleVisionBackend(api_key="dummy-key-for-construction-check")
        print("[0] google backend  : 구성 OK (실제 호출은 키 발급 후)")
    except Exception as exc:  # noqa: BLE001
        print(f"[0] google backend  : 구성 실패 {exc!r}")
        return 1

    tmp = tempfile.mkdtemp(prefix="ocr_selftest_")
    cap = os.path.join(tmp, "capture")
    tdir = os.path.join(tmp, "ocr_text")
    jdir = os.path.join(tmp, "ocr_json")
    os.makedirs(cap)

    # 한글 텍스트가 든 합성 PNG 생성 (google 백엔드로 바꿔 돌려도 의미가 있도록)
    from PIL import Image, ImageDraw, ImageFont

    expected_lines = [
        "다음 중 옳은 것은?",
        "1) 보기 하나",
        "2) 보기 둘",
        "3) 보기 셋",
    ]
    img = Image.new("RGB", (480, 200), "white")
    draw = ImageDraw.Draw(img)
    try:
        font = ImageFont.truetype("C:/Windows/Fonts/malgun.ttf", 28)
    except OSError:
        font = ImageFont.load_default()
    for i, line in enumerate(expected_lines):
        draw.text((20, 20 + i * 40), line, fill="black", font=font)
    img_name = "수학_20260910_125226.png"
    img.save(os.path.join(cap, img_name))

    # stub 백엔드가 읽을 정답 사이드카
    with open(os.path.join(cap, "수학_20260910_125226.expected.txt"), "w", encoding="utf-8") as fh:
        fh.write("\n".join(expected_lines))

    print(f"[1] 임시 입력      : {cap}  (합성 이미지 1장)")

    summary = run_pipeline(
        input_dir=cap, text_dir=tdir, json_dir=jdir, backend_name="stub",
        log=lambda m: print("    " + m),
    )
    print(f"[2] 파이프라인 요약: {summary}")

    txt_path = os.path.join(tdir, "수학_20260910_125226.txt")
    json_path = os.path.join(jdir, "수학_20260910_125226.json")
    txt_ok = os.path.isfile(txt_path)
    json_ok = os.path.isfile(json_path)
    print(f"[3] 산출물         : txt={txt_ok}  json={json_ok}")

    record = {}
    if json_ok:
        with open(json_path, encoding="utf-8") as fh:
            record = json.load(fh)

    required = ["source_image", "subject", "captured_at", "ocr_backend", "full_text", "paragraphs"]
    keys_ok = all(k in record for k in required)
    subject_ok = record.get("subject") == "수학"
    date_ok = record.get("captured_at") == "2026-09-10T12:52:26"
    text_ok = "옳은 것은" in record.get("full_text", "")
    print(f"[4] JSON 스키마    : keys_ok={keys_ok}  subject_ok={subject_ok}  "
          f"captured_at_ok={date_ok}  text_ok={text_ok}")
    print(f"    subject={record.get('subject')!r}  captured_at={record.get('captured_at')!r}  "
          f"paragraphs={len(record.get('paragraphs', []))}개")

    # 재실행 시 skip 되는지
    summary2 = run_pipeline(
        input_dir=cap, text_dir=tdir, json_dir=jdir, backend_name="stub",
        log=lambda m: None,
    )
    skip_ok = summary2["skipped"] == 1 and summary2["processed"] == 0
    print(f"[5] 재실행 skip    : {skip_ok}  ({summary2})")

    all_ok = all([
        summary["processed"] == 1, summary["failed"] == 0,
        txt_ok, json_ok, keys_ok, subject_ok, date_ok, text_ok, skip_ok,
    ])
    # 정리
    import shutil

    shutil.rmtree(tmp, ignore_errors=True)
    print(f"=== result: {'PASS' if all_ok else 'FAIL'} ===")
    return 0 if all_ok else 1


# --------------------------------------------------------------------------- #
def main():
    parser = argparse.ArgumentParser(description="캡처 이미지 OCR 파이프라인")
    parser.add_argument("--backend", help="google | stub  (기본: .env 의 OCR_BACKEND, 없으면 google)")
    parser.add_argument("--force", action="store_true", help="이미 처리된 것도 다시 OCR")
    parser.add_argument("--input", default=CAPTURE_DIR, help="입력 폴더 (기본: capture)")
    parser.add_argument("--selftest", action="store_true", help="키 없이 전체 흐름 검증")
    args = parser.parse_args()

    load_dotenv()

    if args.selftest:
        raise SystemExit(selftest())

    backend_name = args.backend or os.environ.get("OCR_BACKEND") or "google"
    try:
        summary = run_pipeline(
            input_dir=args.input, backend_name=backend_name, force=args.force
        )
    except OcrError as exc:
        print(f"[ocr] 설정 오류: {exc}")
        raise SystemExit(2)
    raise SystemExit(0 if summary["failed"] == 0 else 1)


if __name__ == "__main__":
    main()
