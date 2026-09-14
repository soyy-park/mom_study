"""OCR 결과 -> PDF 문서 (3단계)

ocr_json/ 의 레코드를 읽어 과목별로 묶고 캡처시각순으로 정렬해
사람이 읽기 좋은 PDF 한 장(pdf/quiz_review.pdf)으로 합친다.

사용법:
    python export_pdf.py                       # ocr_json 전체 -> pdf/quiz_review.pdf
    python export_pdf.py --subject 수학          # 특정 과목만
    python export_pdf.py --output pdf/math.pdf  # 출력 경로 지정
    python export_pdf.py --selftest             # 합성 데이터로 전체 흐름 검증
"""

import argparse
import datetime
import glob
import json
import os
import sys

JSON_DIR = "ocr_json"
OUTPUT_PATH = os.path.join("pdf", "quiz_review.pdf")

FONT_REGULAR = "C:/Windows/Fonts/malgun.ttf"
FONT_BOLD = "C:/Windows/Fonts/malgunbd.ttf"


# --------------------------------------------------------------------------- #
def load_records(json_dir, subject_filter=None):
    records = []
    for path in sorted(glob.glob(os.path.join(json_dir, "*.json"))):
        with open(path, encoding="utf-8") as fh:
            record = json.load(fh)
        if subject_filter and record.get("subject") != subject_filter:
            continue
        records.append(record)
    return records


def group_by_subject(records):
    groups = {}
    for record in records:
        groups.setdefault(record.get("subject") or "무제", []).append(record)
    for items in groups.values():
        items.sort(key=lambda r: r.get("captured_at") or "")
    return dict(sorted(groups.items()))


# --------------------------------------------------------------------------- #
def build_pdf(records_by_subject, output_path, font_regular=FONT_REGULAR, font_bold=FONT_BOLD):
    import logging

    from fpdf import FPDF

    # Malgun 폰트 서브셋 시 fontTools 가 "MERG NOT subset" 경고를 매번 찍는다. 무해하므로 숨김.
    logging.getLogger("fontTools").setLevel(logging.ERROR)

    pdf = FPDF()
    pdf.set_auto_page_break(auto=True, margin=18)
    pdf.add_font("Malgun", "", font_regular)
    pdf.add_font("Malgun", "B", font_bold if os.path.isfile(font_bold) else font_regular)

    def footer():
        pdf.set_y(-15)
        pdf.set_font("Malgun", "", 8)
        pdf.set_text_color(150, 150, 150)
        pdf.cell(0, 10, f"{pdf.page_no()}", align="C")

    pdf.footer = footer

    pdf.add_page()
    pdf.set_font("Malgun", "B", 20)
    pdf.set_text_color(20, 20, 20)
    pdf.cell(0, 14, "학습 퀴즈 복습", new_x="LMARGIN", new_y="NEXT")
    pdf.set_font("Malgun", "", 10)
    pdf.set_text_color(120, 120, 120)
    generated_at = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    pdf.cell(0, 8, f"생성: {generated_at}", new_x="LMARGIN", new_y="NEXT")

    for subject, records in records_by_subject.items():
        pdf.add_page()
        pdf.set_font("Malgun", "B", 16)
        pdf.set_text_color(20, 20, 20)
        pdf.cell(0, 12, subject, new_x="LMARGIN", new_y="NEXT")
        pdf.ln(2)

        for record in records:
            captured_at = record.get("captured_at") or ""
            source_image = record.get("source_image") or ""
            pdf.set_font("Malgun", "", 9)
            pdf.set_text_color(130, 130, 130)
            pdf.cell(0, 6, f"{captured_at}  ·  {source_image}", new_x="LMARGIN", new_y="NEXT")

            questions = record.get("questions")
            if questions:
                for q in questions:
                    _write_question(pdf, q)
            else:
                # 구조화 파싱이 안 된(또는 예전 스키마) 레코드는 원문 그대로 표시.
                body = record.get("full_text") or "(내용 없음)"
                for line in body.splitlines() or [body]:
                    if line.startswith("[정답]"):
                        pdf.set_font("Malgun", "B", 11)
                        pdf.set_text_color(21, 101, 192)
                    else:
                        pdf.set_font("Malgun", "", 11)
                        pdf.set_text_color(20, 20, 20)
                    pdf.multi_cell(0, 6.5, line, new_x="LMARGIN", new_y="NEXT")
            pdf.ln(4)

    os.makedirs(os.path.dirname(output_path) or ".", exist_ok=True)
    pdf.output(output_path)
    return output_path


def _write_question(pdf, question):
    pdf.set_font("Malgun", "B", 11)
    pdf.set_text_color(20, 20, 20)
    pdf.multi_cell(0, 6.5, question.get("question") or "(문제 없음)", new_x="LMARGIN", new_y="NEXT")

    answer_index = question.get("answer_index")
    for i, choice in enumerate(question.get("choices") or [], start=1):
        is_answer = i == answer_index
        pdf.set_font("Malgun", "B" if is_answer else "", 10)
        pdf.set_text_color(21, 101, 192) if is_answer else pdf.set_text_color(20, 20, 20)
        pdf.multi_cell(0, 6, f"{i}) {choice}", new_x="LMARGIN", new_y="NEXT")

    if answer_index is None:
        pdf.set_font("Malgun", "", 9)
        pdf.set_text_color(180, 120, 0)
        pdf.cell(0, 6, "(정답 표시가 감지되지 않았습니다)", new_x="LMARGIN", new_y="NEXT")
    pdf.ln(2)


# --------------------------------------------------------------------------- #
def run_export(json_dir=JSON_DIR, output_path=OUTPUT_PATH, subject_filter=None, log=print):
    records = load_records(json_dir, subject_filter=subject_filter)
    if not records:
        log(f"[pdf] {json_dir}/ 에 처리할 OCR 결과가 없습니다.")
        return {"records": 0, "subjects": 0, "output": None}

    groups = group_by_subject(records)
    build_pdf(groups, output_path)
    log(f"[pdf] 생성됨: {os.path.abspath(output_path)}  (과목 {len(groups)}개, 항목 {len(records)}개)")
    return {"records": len(records), "subjects": len(groups), "output": output_path}


# --------------------------------------------------------------------------- #
def selftest():
    import shutil
    import tempfile

    print("=== export_pdf selftest ===")
    print(f"python : {sys.version.split()[0]}  ({sys.platform})")

    font_ok = os.path.isfile(FONT_REGULAR)
    print(f"[0] 한글 폰트     : {FONT_REGULAR}  exists={font_ok}")
    if not font_ok:
        print("=== result: FAIL (Malgun 폰트를 찾을 수 없음) ===")
        return 1

    tmp = tempfile.mkdtemp(prefix="pdf_selftest_")
    jdir = os.path.join(tmp, "ocr_json")
    os.makedirs(jdir)

    fixtures = [
        ("수학_20260910_090000.json", "수학", "2026-09-10T09:00:00",
         "다음 중 옳은 것은?", []),
        ("수학_20260910_080000.json", "수학", "2026-09-10T08:00:00",
         "미분과 적분의 관계", []),
        ("영어_20260911_070000.json", "영어", "2026-09-11T07:00:00", "(생략)", [
            {"question": "빈칸에 알맞은 단어는?", "choices": ["apple", "banana", "cherry"],
             "answer_index": 2},
        ]),
    ]
    for name, subject, captured_at, text, questions in fixtures:
        record = {
            "source_image": name.replace(".json", ".png"),
            "subject": subject,
            "captured_at": captured_at,
            "ocr_backend": "stub",
            "full_text": text,
            "paragraphs": [],
            "questions": questions,
        }
        with open(os.path.join(jdir, name), "w", encoding="utf-8") as fh:
            json.dump(record, fh, ensure_ascii=False)

    print(f"[1] 임시 입력     : {jdir}  (레코드 {len(fixtures)}개, 과목 2개)")

    output_path = os.path.join(tmp, "pdf", "quiz_review.pdf")
    summary = run_export(json_dir=jdir, output_path=output_path, log=lambda m: print("    " + m))
    print(f"[2] 내보내기 요약 : {summary}")

    file_ok = os.path.isfile(output_path) and os.path.getsize(output_path) > 0
    print(f"[3] 산출물        : exists={file_ok}")

    from pypdf import PdfReader

    reader = PdfReader(output_path)
    page_count_ok = len(reader.pages) >= 2  # 표지 1 + 과목 2
    extracted = "\n".join(page.extract_text() or "" for page in reader.pages)
    text_ok = all(
        needle in extracted
        for needle in ["수학", "영어", "다음 중 옳은 것은?", "빈칸에 알맞은 단어는?", "banana"]
    )
    print(f"[4] PDF 검증      : pages={len(reader.pages)}  page_count_ok={page_count_ok}  text_ok={text_ok}")

    shutil.rmtree(tmp, ignore_errors=True)

    all_ok = (
        summary["records"] == len(fixtures)
        and summary["subjects"] == 2
        and file_ok
        and page_count_ok
        and text_ok
    )
    print(f"=== result: {'PASS' if all_ok else 'FAIL'} ===")
    return 0 if all_ok else 1


# --------------------------------------------------------------------------- #
def main():
    parser = argparse.ArgumentParser(description="OCR 결과를 PDF 로 내보내기")
    parser.add_argument("--input", default=JSON_DIR, help="입력 폴더 (기본: ocr_json)")
    parser.add_argument("--output", default=OUTPUT_PATH, help="출력 PDF 경로 (기본: pdf/quiz_review.pdf)")
    parser.add_argument("--subject", default=None, help="특정 과목만 내보내기")
    parser.add_argument("--selftest", action="store_true", help="합성 데이터로 전체 흐름 검증")
    args = parser.parse_args()

    if args.selftest:
        raise SystemExit(selftest())

    summary = run_export(json_dir=args.input, output_path=args.output, subject_filter=args.subject)
    raise SystemExit(0 if summary["output"] else 1)


if __name__ == "__main__":
    main()
