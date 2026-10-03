from pathlib import Path
from pdfgen.parser import parse_questions
from pdfgen.generator import generate_pdf


def test_100_questions(tmp_path):
    raw = '\n\n'.join(
        f'{i}. यह प्रश्न क्रम संख्या {i} है।\nA) पहला विकल्प\nB) दूसरा विकल्प\nC) तीसरा विकल्प\nD) चौथा विकल्प'
        for i in range(1, 101)
    )
    qs = parse_questions(raw)
    assert len(qs) == 100
    out = tmp_path / 'test.pdf'
    generate_pdf(qs, out, 'ENGLISH STUDY CENTRE', subject='हिंदी', topic=None, set_no='01')
    assert out.exists() and out.stat().st_size > 1000
