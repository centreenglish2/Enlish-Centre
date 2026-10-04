"""Generate the single, locked English Study Centre exam-paper layout.

The PDF format is intentionally fixed: A4 portrait, centered title, one rule,
two columns, questions 1-25 on the left and 26-50 on the right. No alternate
styles, themes, watermark, or page footer are rendered.
"""
from html import escape
from pathlib import Path
import re
from weasyprint import HTML
from .parser import Question

BASE = Path(__file__).resolve().parents[1]
FONT_DIR = BASE / "fonts"
REGULAR = FONT_DIR / "NotoSansDevanagari-Regular.ttf"
BOLD = FONT_DIR / "NotoSansDevanagari-Bold.ttf"
PAGE_QUESTION_LIMIT = 50


def _e(value):
    return escape(str(value or ""), quote=True)


def _split_inline_options(q):
    """Split options embedded on the question line, while preserving parsed options."""
    text = str(q.text or "").strip()
    opts = list(q.options or [])
    if len([x for x in opts if str(x).strip()]) >= 2:
        return text, opts[:4]

    matches = list(re.finditer(r'(?<!\S)\(?([A-Da-dकखगघ])\)\s*', text))
    if len(matches) < 2:
        matches = list(re.finditer(r'\(?([A-Da-dकखगघ])\)\s*', text))

    valid = []
    for labels in [('A', 'B', 'C', 'D'), ('a', 'b', 'c', 'd'), ('क', 'ख', 'ग', 'घ')]:
        candidate = []
        expected_index = 0
        for match in matches:
            letter = match.group(1)
            if expected_index < 4 and letter == labels[expected_index]:
                candidate.append(match)
                expected_index += 1
                if expected_index == 4:
                    break
        if len(candidate) >= 2:
            valid = candidate
            break
    if len(valid) >= 2 and valid[0].start() > 0:
        stem = text[:valid[0].start()].strip()
        parsed = []
        for i, match in enumerate(valid[:4]):
            end = valid[i + 1].start() if i + 1 < len(valid) else len(text)
            parsed.append(text[match.end():end].strip())
        if stem and any(parsed):
            return stem, parsed
    return text, opts[:4]


def _question_html(q):
    stem, options = _split_inline_options(q)
    option_html = ''.join(
        f'<div class="option"><b>({("क", "ख", "ग", "घ")[i]})</b> {_e(opt)}</div>'
        for i, opt in enumerate((options + ["", "", "", ""])[:4])
        if str(opt).strip()
    )
    return (
        '<div class="question">'
        f'<div class="question-text"><b>{int(q.number)}.</b> {_e(stem)}</div>'
        f'<div class="options">{option_html}</div>'
        '</div>'
    )


def _page_html(group, set_no):
    # Lock the exact heading and page structure; do not use per-quiz alternate styles.
    left_html = ''.join(_question_html(q) for q in group[:25])
    right_html = ''.join(_question_html(q) for q in group[25:50])
    set_label = str(set_no or "01").strip()
    return f'''<section class="paper-page">
      <header class="header">
        <div class="headline">ENGLISH STUDY CENTRE</div>
        <div class="subtitle">QUESTION SET — SET {_e(set_label)}</div>
      </header>
      <div class="rule"></div>
      <main class="columns">
        <div class="column">{left_html}</div>
        <div class="column">{right_html}</div>
      </main>
    </section>'''


def generate_pdf(questions: list[Question], output_path: Path, headline: str = "ENGLISH STUDY CENTRE",
                 subject: str | None = None, topic: str | None = None,
                 set_no: str | None = None, watermark: str = "ENGLISH STUDY CENTRE"):
    """Write a PDF using only the locked 50-questions-per-page layout.

    Legacy arguments remain accepted so existing bot code keeps working, but
    headline/subject/topic/watermark cannot change the visual template.
    """
    if not questions:
        raise ValueError("No questions to render")
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    groups = [questions[i:i + PAGE_QUESTION_LIMIT]
              for i in range(0, len(questions), PAGE_QUESTION_LIMIT)]
    pages = ''.join(_page_html(group, set_no) for group in groups)
    html = f'''<!doctype html><html><head><meta charset="utf-8"><style>
@font-face {{ font-family: NotoDev; src: url("{REGULAR.as_uri()}") format("truetype"); font-weight:400; }}
@font-face {{ font-family: NotoDev; src: url("{BOLD.as_uri()}") format("truetype"); font-weight:700; }}
@page {{ size:A4; margin:8mm 9mm 8mm; }}
* {{ box-sizing:border-box; }}
html, body {{ margin:0; padding:0; font-family:NotoDev,sans-serif; color:#111; }}
.paper-page {{ height:281mm; position:relative; display:flex; flex-direction:column; page-break-after:always; break-after:page; overflow:hidden; }}
.paper-page:last-child {{ page-break-after:auto; break-after:auto; }}
.header {{ text-align:center; flex:none; padding:3mm 0 1mm; }}
.headline {{ font-size:16pt; font-weight:700; line-height:1.12; letter-spacing:.15px; }}
.subtitle {{ font-size:8.5pt; line-height:1.2; margin-top:1mm; letter-spacing:.4px; }}
.rule {{ border-top:1px solid #333; margin:2.5mm 0 2mm; flex:none; }}
.columns {{ position:absolute; top:20mm; bottom:0; left:0; right:0; display:grid; grid-template-columns:minmax(0,1fr) minmax(0,1fr); column-gap:7mm; min-height:0; }}
.column {{ min-width:0; overflow:hidden; }}
.question {{ break-inside:avoid; margin:0 0 1.1mm; font-size:7.2pt; line-height:1.13; }}
.question-text {{ margin:0 0 .35mm; font-weight:600; overflow-wrap:anywhere; }}
.options {{ display:grid; grid-template-columns:minmax(0,1fr) minmax(0,1fr); column-gap:2.2mm; margin-left:1.2mm; }}
.option {{ font-size:6.8pt; line-height:1.12; overflow-wrap:anywhere; margin:0 0 .15mm; }}
</style></head><body>{pages}</body></html>'''
    HTML(string=html, base_url=str(BASE)).write_pdf(str(output_path))
