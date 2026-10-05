from pathlib import Path

from pypdf import PdfReader

from pdfgen.parser import parse_questions
from pdfgen.generator import generate_pdf


def _question_bank(count, question_text=None, option_text=None):
    question_text = question_text or "यह प्रश्न क्रम संख्या {} है।"
    option_text = option_text or "{} विकल्प"
    return "\n\n".join(
        f'{i}. {question_text.format(i)}\n'
        f'A) {option_text.format("पहला")}\n'
        f'B) {option_text.format("दूसरा")}\n'
        f'C) {option_text.format("तीसरा")}\n'
        f'D) {option_text.format("चौथा")}'
        for i in range(1, count + 1)
    )


def test_100_questions_create_two_pages_and_keep_ranges(tmp_path):
    qs = parse_questions(_question_bank(100))
    assert len(qs) == 100
    out = tmp_path / "test.pdf"
    generate_pdf(qs, out, "ENGLISH STUDY CENTRE", subject="हिंदी", section=None, set_no="01")

    reader = PdfReader(str(out))
    assert len(reader.pages) == 2
    page_texts = [page.extract_text() or "" for page in reader.pages]
    assert "Questions 1–50" in page_texts[0]
    assert "Questions 51–100" in page_texts[1]
    assert "Page 1 of 2" in page_texts[0]
    assert "Page 2 of 2" in page_texts[1]


def test_long_questions_remain_on_one_page_per_50_question_group(tmp_path):
    long_question = "यह एक लंबा प्रश्न है जिसमें परीक्षा के लिए आवश्यक विवरण और संदर्भ शामिल हैं। " + "{}"
    long_option = "यह एक विस्तृत विकल्प है जिसमें अतिरिक्त व्याख्या दी गई है। " + "{}"
    qs = parse_questions(_question_bank(50, long_question, long_option))
    out = tmp_path / "long.pdf"
    generate_pdf(qs, out, "ENGLISH STUDY CENTRE")

    reader = PdfReader(str(out))
    assert len(reader.pages) == 1
    extracted = reader.pages[0].extract_text() or ""
    assert "Questions 1–50" in extracted
    assert "50." in extracted
    assert "चौथा" in extracted


def test_empty_question_list_is_rejected(tmp_path):
    import pytest

    with pytest.raises(ValueError, match="No questions"):
        generate_pdf([], tmp_path / "empty.pdf", "ENGLISH STUDY CENTRE")


def test_51_questions_create_a_second_page_for_question_51(tmp_path):
    qs = parse_questions(_question_bank(51))
    out = tmp_path / "test_51.pdf"
    generate_pdf(qs, out, "ENGLISH STUDY CENTRE")

    reader = PdfReader(str(out))
    assert len(reader.pages) == 2
    page_texts = [page.extract_text() or "" for page in reader.pages]
    assert "Questions 1–50" in page_texts[0]
    assert "Questions 51–51" in page_texts[1]
    assert "51." in page_texts[1]
