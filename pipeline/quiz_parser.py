"""OCR 문단 -> 문제 단위 구조화 파싱

ocr_pipeline.py 가 만든 paragraphs(문단별 텍스트 + is_answer)를 입력받아,
캡처 한 장 안에 여러 문제가 들어있어도 각각을 아래 형태로 쪼갠다.

    {"question": "...", "choices": ["...", "...", ...], "answer_index": 1based}

규칙 기반(정규식)이라 완벽하지 않다 — 다른 플랫폼/레이아웃에서는 안 맞을 수 있다.
answer_index 는 화면에 파란 원(정답 표시)이 없으면 None.

사용법:
    python pipeline/quiz_parser.py --selftest   # 실제 캡처 예시로 파싱 규칙 검증
"""

import re
import sys

# 문제 줄: "1. 문제 내용" 형태. 보기 줄과 헷갈리지 않게 "숫자 + 마침표 + 공백"을 요구한다.
QUESTION_RE = re.compile(r"^(\d{1,2})\.\s+(.+)", re.DOTALL)

# 보기 앞에 붙는 표시를 벗겨낸다: 원문자(①②..), "1)", "1.", 또는 OCR이 원문자를
# 맨숫자로 잘못 읽은 "1 " 까지 포함.
CHOICE_MARKER_RE = re.compile(r"^(?:[①②③④⑤⑥⑦⑧⑨⑩]|\d{1,2}[.)]?)\s+")

# ocr_pipeline.py 가 정답 보기 앞에 붙여둔 표시.
ANSWER_PREFIX_RE = re.compile(r"^\[정답\]\s*")

# 문제 시작 전/보기 사이에 섞여 들어오는 화면 UI 잡음(버튼 글자 등).
NOISE_EXACT = {"정답풀이", "해설", "해설보기", "정답 및 해설", "다음", "이전", "제출"}

HANGUL_RE = re.compile(r"[가-힣]")


def _looks_like_url_noise(text):
    # 브라우저 주소창/파일 경로가 캡처 영역에 같이 잡힌 경우: 슬래시가 있고 한글이 없다.
    return "/" in text and not HANGUL_RE.search(text)


def parse_questions(paragraphs):
    """문단 리스트 -> 문제 단위 리스트. paragraphs 는 ocr_pipeline 의 그 형식.

    각 문제 사전: {"question": str, "choices": [str, ...], "answer_index": int | None}
    answer_index 는 1부터 시작 (몇 번째 보기가 정답인지).
    """
    questions = []
    current = None

    def finalize(q):
        return {
            "question": q["question"],
            "choices": q["choices"],
            "answer_index": q["answer_index"],
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
            current = {"question": m.group(2).strip(), "choices": [], "answer_index": None}
            continue

        if current is None:
            # 첫 문제가 나오기 전의 잡음(제목 등) - 버린다.
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
def selftest():
    print("=== quiz_parser selftest ===")
    print(f"python : {sys.version.split()[0]}  ({sys.platform})")

    # 실제 캡처(사회문제론)에서 나온 OCR 결과를 그대로 옮긴 것 - 합성 데이터가 아니다.
    paragraphs = [
        {"text": "lent/MyClassroom/YJMyClassroomPlayer.jsp", "is_answer": False},
        {"text": "사회문제론 1주차", "is_answer": False},
        {"text": "1. 사회에 대한 설명으로 틀린 것을 고르시오", "is_answer": False},
        {"text": "① 인간들의 집합체", "is_answer": False},
        {"text": "② 각자 고유의 규칙을 형성", "is_answer": False},
        {"text": "③ 인간은 사회에 소속 되고자 하는 욕구를 가짐", "is_answer": False},
        {"text": "[정답] 1 개인의 개성만을 인정함", "is_answer": True},
        {"text": "정답풀이", "is_answer": False},
        {"text": "2. 사회문제의 정의로 맞는 것을 고르시오", "is_answer": False},
        {"text": "[정답] ⑦ 개별적이고 개인적인 것이 아니라 집합적이고 집단적이며 다수 사회구\n성원과 관련",
         "is_answer": True},
        {"text": "② 사회구조와는 무관함", "is_answer": False},
        {"text": "③ 극복해야 할 대상은 아님", "is_answer": False},
        {"text": "④ 문제로 지정되지는 않음", "is_answer": False},
        {"text": "정답풀이", "is_answer": False},
    ]

    result = parse_questions(paragraphs)
    print(f"[1] 문제 개수 : {len(result)}개 (기대: 2)")
    for i, q in enumerate(result, 1):
        print(f"    Q{i}: {q['question']!r}")
        for j, c in enumerate(q["choices"], 1):
            mark = " <- 정답" if j == q["answer_index"] else ""
            print(f"         {j}) {c!r}{mark}")

    q1_ok = (
        len(result) >= 1
        and result[0]["question"] == "사회에 대한 설명으로 틀린 것을 고르시오"
        and result[0]["choices"] == [
            "인간들의 집합체", "각자 고유의 규칙을 형성",
            "인간은 사회에 소속 되고자 하는 욕구를 가짐", "개인의 개성만을 인정함",
        ]
        and result[0]["answer_index"] == 4
    )
    q2_ok = (
        len(result) >= 2
        and result[1]["question"] == "사회문제의 정의로 맞는 것을 고르시오"
        and result[1]["choices"][0].startswith("개별적이고 개인적인 것")
        and len(result[1]["choices"]) == 4
        and result[1]["answer_index"] == 1
    )
    no_noise = all(
        "정답풀이" not in c and "MyClassroom" not in c
        for q in result for c in q["choices"]
    )
    print(f"[2] 검증      : q1_ok={q1_ok}  q2_ok={q2_ok}  no_noise={no_noise}")

    # 정답 표시가 전혀 없는 경우 answer_index 는 None 이어야 한다.
    no_answer = parse_questions([
        {"text": "1. 질문", "is_answer": False},
        {"text": "① 보기1", "is_answer": False},
        {"text": "② 보기2", "is_answer": False},
    ])
    none_ok = len(no_answer) == 1 and no_answer[0]["answer_index"] is None
    print(f"[3] 정답 없음 처리 : {none_ok}")

    all_ok = q1_ok and q2_ok and no_noise and none_ok
    print(f"=== result: {'PASS' if all_ok else 'FAIL'} ===")
    return 0 if all_ok else 1


if __name__ == "__main__":
    if "--selftest" in sys.argv:
        raise SystemExit(selftest())
    print("사용법: python pipeline/quiz_parser.py --selftest")
