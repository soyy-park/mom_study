"""웹앱 "퀴즈 등록"에서 Storage uploads/ 에 사진이 올라오면 자동으로
OCR + 문제 구조화 파싱을 돌려서 Firestore questions 컬렉션에 저장한다.

pipeline/ocr_pipeline.py, pipeline/quiz_parser.py 의 로직을 Cloud Functions
런타임(Python)으로 옮겨온 것 - 동작을 바꾸면 두 쪽 다 같이 고칠 것.
Vision API 키를 웹페이지에 노출하지 않으려고 이 서버 함수 뒤에 숨긴다
(키는 Secret Manager 에 저장, 함수 코드/로그에도 평문으로 안 남음).

배포:
    firebase functions:secrets:set GOOGLE_VISION_API_KEY   # 최초 1회
    firebase deploy --only functions
"""

import base64
import datetime
import io
import os
import re

import requests
from firebase_admin import firestore, initialize_app, storage as admin_storage
from firebase_functions import storage_fn
from firebase_functions.params import SecretParam
from PIL import Image

initialize_app()

GOOGLE_VISION_API_KEY = SecretParam("GOOGLE_VISION_API_KEY")
GOOGLE_VISION_ENDPOINT = "https://vision.googleapis.com/v1/images:annotate"
COLLECTION = "questions"
UPLOAD_PREFIX = "uploads/"

# --------------------------------------------------------------------------- #
# pipeline/quiz_parser.py 와 동일 (문제/보기 구조화). 여기서 복제해 사용한다.
# --------------------------------------------------------------------------- #
# "5.이념적..." 처럼 마침표 뒤 공백이 없어도 인정하되, 공백이 없을 땐 바로
# 뒤가 숫자가 아니어야 한다("3.14" 같은 소수를 문제로 오인하지 않기 위함).
QUESTION_RE = re.compile(r"^(\d{1,2})\.(?:\s+|(?=\D))(.+)", re.DOTALL)
CHOICE_MARKER_RE = re.compile(r"^(?:[①②③④⑤⑥⑦⑧⑨⑩]|\d{1,2}[.)]?)\s+")
ANSWER_PREFIX_RE = re.compile(r"^\[정답\]\s*")
# "정답풀이" 버튼을 펼쳤을 때 나오는 해설 문단: 항상 "정답 N번 ..."으로 시작한다.
EXPLANATION_RE = re.compile(r"^정답\s*(\d{1,2})번\s*(.*)", re.DOTALL)
NOISE_EXACT = {"정답풀이", "해설", "해설보기", "정답 및 해설", "다음", "이전", "제출"}
HANGUL_RE = re.compile(r"[가-힣]")

# OX 문제의 동그라미(O) 아이콘을 Vision 이 "10"/"1 0"/"0" 등으로 잘못 읽는 경우가
# 있다(같은 아이콘인데 호출마다 다르게 읽힘). X 도 앞에 번호 기호가 잘못 붙어
# "②X"/"2X" 처럼 나올 때가 있다.
_OX_O_NOISE = {"10", "1 0", "0", "1o", "1O"}
_OX_X_RE = re.compile(r"^[①②③④⑤]?\s*\d{0,2}\s*[Xx]$")


def _normalize_ox_choices(choices):
    if len(choices) != 2:
        return choices
    x_index = next((i for i, c in enumerate(choices) if _OX_X_RE.match(c.strip())), None)
    if x_index is None:
        return choices
    other_index = 1 - x_index
    other = choices[other_index].strip()
    fixed = list(choices)
    fixed[x_index] = "X"
    if other in _OX_O_NOISE or other.upper() == "O":
        fixed[other_index] = "O"
    return fixed


def _looks_like_url_noise(text):
    return "/" in text and not HANGUL_RE.search(text)


def parse_questions(paragraphs):
    questions = []
    current = None

    def finalize(q):
        return {
            "question": q["question"],
            "choices": _normalize_ox_choices(q["choices"]),
            "answer_index": q["answer_index"],
            "explanation": q["explanation"],
        }

    for para in paragraphs:
        raw = (para.get("text") or "").strip()
        is_answer = bool(para.get("is_answer"))
        text = ANSWER_PREFIX_RE.sub("", raw).strip()

        if not text or text in NOISE_EXACT or _looks_like_url_noise(text):
            continue

        m = QUESTION_RE.match(text)
        if m:
            if current is not None:
                questions.append(finalize(current))
            current = {"question": m.group(2).strip(), "choices": [], "answer_index": None,
                       "explanation": None}
            continue

        if current is None:
            continue

        em = EXPLANATION_RE.match(text)
        if em:
            current["explanation"] = em.group(2).strip()
            if current["answer_index"] is None:
                current["answer_index"] = int(em.group(1))
            continue

        choice_text = CHOICE_MARKER_RE.sub("", text).strip()
        if not choice_text:
            continue
        current["choices"].append(choice_text)
        if is_answer and current["answer_index"] is None:
            current["answer_index"] = len(current["choices"])

    if current is not None:
        questions.append(finalize(current))
    return questions


# --------------------------------------------------------------------------- #
# pipeline/ocr_pipeline.py 와 동일한 Vision 호출 + 파란 원 정답 감지.
# --------------------------------------------------------------------------- #
def _build_paragraph_text(words):
    parts = []
    for word in words:
        symbols = word.get("symbols", [])
        parts.append("".join(s.get("text", "") for s in symbols))
        break_type = None
        if symbols:
            break_type = symbols[-1].get("property", {}).get("detectedBreak", {}).get("type")
        if break_type in ("SPACE", "SURE_SPACE"):
            parts.append(" ")
        elif break_type in ("LINE_BREAK", "EOL_SURE_SPACE"):
            parts.append("\n")
    return "".join(parts).strip()


BLUE_MARKER_MIN_DIFF = 15


def _poly_to_bbox(poly):
    if not poly:
        return None
    xs = [v.get("x", 0) for v in poly.get("vertices", [])]
    ys = [v.get("y", 0) for v in poly.get("vertices", [])]
    if not xs or not ys:
        return None
    return [min(xs), min(ys), max(xs), max(ys)]


def _is_blue_marker(image, bbox):
    x0, y0, x1, y1 = bbox
    if x1 <= x0 or y1 <= y0:
        return False
    crop = image.crop((x0, y0, x1, y1))
    pixels = crop.tobytes()
    if not pixels:
        return False
    pixels = [pixels[i:i + 3] for i in range(0, len(pixels), 3)]
    n = len(pixels)
    avg_r = sum(p[0] for p in pixels) / n
    avg_g = sum(p[1] for p in pixels) / n
    avg_b = sum(p[2] for p in pixels) / n
    return (avg_b - avg_r) > BLUE_MARKER_MIN_DIFF and (avg_b - avg_g) > BLUE_MARKER_MIN_DIFF / 2


def recognize(image_bytes, api_key):
    content = base64.b64encode(image_bytes).decode("ascii")
    payload = {
        "requests": [{
            "image": {"content": content},
            "features": [{"type": "DOCUMENT_TEXT_DETECTION"}],
            "imageContext": {"languageHints": ["ko", "en"]},
        }]
    }
    resp = requests.post(GOOGLE_VISION_ENDPOINT, params={"key": api_key}, json=payload, timeout=30)
    resp.raise_for_status()
    result = resp.json().get("responses", [{}])[0]
    if "error" in result:
        raise RuntimeError(f"Vision API error: {result['error']}")

    annotation = result.get("fullTextAnnotation")
    if not annotation:
        return []

    image = Image.open(io.BytesIO(image_bytes)).convert("RGB")
    paragraphs = []
    for page in annotation.get("pages", []):
        for block in page.get("blocks", []):
            for para in block.get("paragraphs", []):
                words = para.get("words", [])
                para_text = _build_paragraph_text(words)
                marker_bbox = _poly_to_bbox(words[0]["boundingBox"]) if words else None
                is_answer = bool(marker_bbox and _is_blue_marker(image, marker_bbox))
                if is_answer:
                    para_text = "[정답] " + para_text
                paragraphs.append({"text": para_text, "is_answer": is_answer})
    return paragraphs


# --------------------------------------------------------------------------- #
# 파일명 -> 과목/캡처시각  (pipeline/ocr_pipeline.py 의 parse_capture_name 과 동일)
# --------------------------------------------------------------------------- #
def parse_capture_name(filename):
    stem = os.path.splitext(os.path.basename(filename))[0]
    subject, captured_at = stem, None
    parts = stem.rsplit("_", 2)
    if len(parts) == 3:
        subject, date_part, time_part = parts
        try:
            dt = datetime.datetime.strptime(date_part + time_part, "%Y%m%d%H%M%S")
            captured_at = dt.astimezone()
        except ValueError:
            subject, captured_at = stem, None
    return subject, captured_at


# --------------------------------------------------------------------------- #
# Storage 트리거: uploads/ 에 새 이미지가 올라오면 실행.
# 버킷이 us-east1 에 있어서 함수도 같은 리전이어야 트리거가 붙는다.
# --------------------------------------------------------------------------- #
@storage_fn.on_object_finalized(
    bucket="jini-study.firebasestorage.app",
    region="us-east1",
    secrets=[GOOGLE_VISION_API_KEY],
    memory=512,
    timeout_sec=120,
)
def on_quiz_upload(event: storage_fn.CloudEvent) -> None:
    data = event.data
    name = data.name or ""
    content_type = data.content_type or ""

    if not name.startswith(UPLOAD_PREFIX) or not content_type.startswith("image/"):
        return

    bucket = admin_storage.bucket(data.bucket)
    blob = bucket.blob(name)
    image_bytes = blob.download_as_bytes()

    subject, captured_at = parse_capture_name(name)

    try:
        paragraphs = recognize(image_bytes, GOOGLE_VISION_API_KEY.value)
    except Exception as exc:  # noqa: BLE001 - 실패해도 함수는 조용히 끝낸다(재시도 안 함)
        print(f"[on_quiz_upload] OCR 실패 {name}: {exc!r}")
        return

    questions = parse_questions(paragraphs)
    if not questions:
        print(f"[on_quiz_upload] 파싱된 문제 없음: {name}")
        return

    db = firestore.client()
    stem = os.path.splitext(os.path.basename(name))[0]
    synced_at = datetime.datetime.now(datetime.timezone.utc)
    for i, q in enumerate(questions, start=1):
        doc = {
            "subject": subject or "무제",
            "question": q["question"],
            "choices": q["choices"],
            "answer_index": q["answer_index"],
            "explanation": q["explanation"],
            "captured_at": captured_at,
            "source_image": name,
            "ocr_backend": "google",
            "synced_at": synced_at,
        }
        db.collection(COLLECTION).document(f"{stem}_q{i}").set(doc)

    print(f"[on_quiz_upload] {name}: 문제 {len(questions)}개 등록 완료")
