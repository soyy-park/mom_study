"""OCR 문단 -> 문제 단위 구조화 파싱

ocr_pipeline.py 가 만든 paragraphs(문단별 텍스트 + is_answer)를 입력받아,
캡처 한 장 안에 여러 문제가 들어있어도 각각을 아래 형태로 쪼갠다.

    {"question": "...", "choices": ["...", "...", ...], "answer_index": 1based,
     "explanation": "..." 또는 None}

규칙 기반(정규식)이라 완벽하지 않다 — 다른 플랫폼/레이아웃에서는 안 맞을 수 있다.
answer_index 는 화면에 파란 원(정답 표시)이 없으면 None(단, "정답풀이" 펼쳤을 때
나오는 "정답 N번 ..." 텍스트에서라도 번호를 읽을 수 있으면 그걸로 채운다).

사용법:
    python pipeline/quiz_parser.py --selftest   # 실제 캡처 예시로 파싱 규칙 검증
"""

import re
import sys

# 문제 줄: "1. 문제 내용" 형태. 보통 마침표 뒤에 공백이 있지만("1. 사회에..."),
# OCR이 공백을 빼먹고 "5.이념적..." 처럼 붙여버리는 경우도 있어 그것도 인정한다.
# 단, 공백이 없을 땐 바로 뒤가 숫자가 아니어야 한다("3.14" 같은 소수를 문제로
# 오인하지 않기 위함) - 공백이 있으면("2. 10명 중...") 뒤에 숫자가 와도 그대로 인정.
QUESTION_RE = re.compile(r"^(\d{1,2})\.(?:\s+|(?=\D))(.+)", re.DOTALL)

# 보기 앞에 붙는 표시를 벗겨낸다: 원문자(①②..), "1)", "1.", 또는 OCR이 원문자를
# 맨숫자로 잘못 읽은 "1 " 까지 포함.
CHOICE_MARKER_RE = re.compile(r"^(?:[①②③④⑤⑥⑦⑧⑨⑩]|\d{1,2}[.)]?)\s+")

# ocr_pipeline.py 가 정답 보기 앞에 붙여둔 표시.
ANSWER_PREFIX_RE = re.compile(r"^\[정답\]\s*")

# "정답풀이" 버튼을 펼쳤을 때 나오는 해설 문단: 항상 "정답 N번 ..."으로 시작한다.
# 보기로 섞여 들어가지 않게 따로 빼내고, 번호는 answer_index 의 보조 출처로도 쓴다.
EXPLANATION_RE = re.compile(r"^정답\s*(\d{1,2})번\s*(.*)", re.DOTALL)

# 문제 시작 전/보기 사이에 섞여 들어오는 화면 UI 잡음(버튼 글자 등).
NOISE_EXACT = {"정답풀이", "해설", "해설보기", "정답 및 해설", "다음", "이전", "제출"}

HANGUL_RE = re.compile(r"[가-힣]")

# OX 문제의 동그라미(O) 아이콘을 Vision 이 "10"/"1 0"/"0" 등으로 잘못 읽는 경우가
# 있다(같은 아이콘인데 호출마다 다르게 읽힘 - 폰트가 아니라 그래픽 아이콘이라서).
# X 도 앞에 번호 기호가 잘못 붙어 "②X"/"2X" 처럼 나올 때가 있다.
_OX_O_NOISE = {"10", "1 0", "0", "1o", "1O"}
_OX_X_RE = re.compile(r"^[①②③④⑤]?\s*\d{0,2}\s*[Xx]$")


def _normalize_ox_choices(choices):
    """보기가 정확히 2개고 그중 하나가 X 로 보이면 OX 문제로 간주해 보정한다."""
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
            # 첫 문제가 나오기 전의 잡음(제목 등) - 버린다.
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
        {"text": "정답 4번 ① 인간들의 집합체, ② 규칙 형성, ③ 소속 욕구는 사회의 일반적\n특성이다.", "is_answer": False},
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
        print(f"         해설: {q['explanation']!r}")

    q1_ok = (
        len(result) >= 1
        and result[0]["question"] == "사회에 대한 설명으로 틀린 것을 고르시오"
        and result[0]["choices"] == [
            "인간들의 집합체", "각자 고유의 규칙을 형성",
            "인간은 사회에 소속 되고자 하는 욕구를 가짐", "개인의 개성만을 인정함",
        ]
        and result[0]["answer_index"] == 4
        and result[0]["explanation"] == "① 인간들의 집합체, ② 규칙 형성, ③ 소속 욕구는 사회의 일반적\n특성이다."
    )
    q2_ok = (
        len(result) >= 2
        and result[1]["question"] == "사회문제의 정의로 맞는 것을 고르시오"
        and result[1]["choices"][0].startswith("개별적이고 개인적인 것")
        and len(result[1]["choices"]) == 4
        and result[1]["answer_index"] == 1
        and result[1]["explanation"] is None
    )
    no_noise = all(
        "정답풀이" not in c and "MyClassroom" not in c and not c.startswith("정답 ")
        for q in result for c in q["choices"]
    )
    print(f"[2] 검증      : q1_ok={q1_ok}  q2_ok={q2_ok}  no_noise={no_noise}")

    # 정답 표시가 전혀 없는 경우 answer_index 는 None 이어야 한다.
    no_answer = parse_questions([
        {"text": "1. 질문", "is_answer": False},
        {"text": "① 보기1", "is_answer": False},
        {"text": "② 보기2", "is_answer": False},
    ])
    none_ok = (
        len(no_answer) == 1
        and no_answer[0]["answer_index"] is None
        and no_answer[0]["explanation"] is None
    )
    print(f"[3] 정답 없음 처리 : {none_ok}")

    # 파란 원 감지는 실패했지만 "정답 N번" 해설 텍스트에서 번호를 읽어올 수 있는 경우.
    fallback = parse_questions([
        {"text": "1. 질문", "is_answer": False},
        {"text": "① 보기1", "is_answer": False},
        {"text": "② 보기2", "is_answer": False},
        {"text": "정답 2번 이게 맞는 이유", "is_answer": False},
    ])
    fallback_ok = (
        len(fallback) == 1
        and fallback[0]["answer_index"] == 2
        and fallback[0]["explanation"] == "이게 맞는 이유"
        and fallback[0]["choices"] == ["보기1", "보기2"]
    )
    print(f"[4] 해설로 정답 유추 : {fallback_ok}")

    # OX 문제의 O 아이콘이 "10"으로 잘못 읽힌 실제 사례 - "O"로 보정돼야 한다.
    ox_garbled = parse_questions([
        {"text": "1. OX 질문", "is_answer": False},
        {"text": "10", "is_answer": True},
        {"text": "X", "is_answer": False},
    ])
    ox_ok = len(ox_garbled) == 1 and ox_garbled[0]["choices"] == ["O", "X"]

    # X 쪽에 번호 기호가 잘못 붙은 경우("②X")도 "X"로 보정.
    ox_x_garbled = parse_questions([
        {"text": "1. OX 질문", "is_answer": False},
        {"text": "O", "is_answer": False},
        {"text": "②X", "is_answer": True},
    ])
    ox_x_ok = len(ox_x_garbled) == 1 and ox_x_garbled[0]["choices"] == ["O", "X"]

    # 4지선다에서 진짜 숫자 보기("10")는 건드리면 안 된다.
    real_number = parse_questions([
        {"text": "1. 다음 중 소수는?", "is_answer": False},
        {"text": "① 9", "is_answer": False},
        {"text": "② 10", "is_answer": False},
        {"text": "③ 11", "is_answer": True},
        {"text": "④ 12", "is_answer": False},
    ])
    real_number_ok = len(real_number) == 1 and real_number[0]["choices"] == ["9", "10", "11", "12"]

    print(f"[5] OX 보정        : ox_ok={ox_ok}  ox_x_ok={ox_x_ok}  real_number_ok={real_number_ok}")

    # 마침표 뒤 공백 없이 붙은 문제 번호("5.이념적...") - 실제 캡처(074701.jpg)에서
    # 재현된 사례. 새 문제로 끊기지 않고 앞 문제의 보기로 잘못 붙던 버그.
    glued_number = parse_questions([
        {"text": "4. 문화의 차이로 사회문제가 발생할 수 있다", "is_answer": False},
        {"text": "10", "is_answer": True},
        {"text": "②X", "is_answer": False},
        {"text": "5.이념적 대립이 강해지는 경우 사회문제가 발생할 가능성이 높다", "is_answer": False},
        {"text": "10", "is_answer": True},
        {"text": "②X", "is_answer": False},
    ])
    glued_ok = (
        len(glued_number) == 2
        and glued_number[0]["question"] == "문화의 차이로 사회문제가 발생할 수 있다"
        and glued_number[0]["choices"] == ["O", "X"]
        and glued_number[1]["question"] == "이념적 대립이 강해지는 경우 사회문제가 발생할 가능성이 높다"
        and glued_number[1]["choices"] == ["O", "X"]
    )
    # "3.14" 같은 소수는 새 문제로 오인하면 안 된다.
    decimal_ok = parse_questions([
        {"text": "1. 원주율에 가장 가까운 값은?", "is_answer": False},
        {"text": "① 3.14", "is_answer": True},
        {"text": "② 2.71", "is_answer": False},
    ])
    decimal_ok = (
        len(decimal_ok) == 1
        and decimal_ok[0]["choices"] == ["3.14", "2.71"]
    )
    print(f"[6] 붙은 문제번호   : glued_ok={glued_ok}  decimal_ok={decimal_ok}")

    all_ok = (q1_ok and q2_ok and no_noise and none_ok and fallback_ok
              and ox_ok and ox_x_ok and real_number_ok and glued_ok and decimal_ok)
    print(f"=== result: {'PASS' if all_ok else 'FAIL'} ===")
    return 0 if all_ok else 1


if __name__ == "__main__":
    if "--selftest" in sys.argv:
        raise SystemExit(selftest())
    print("사용법: python pipeline/quiz_parser.py --selftest")
