from html import escape
from math import ceil
from pathlib import Path
import re
from weasyprint import HTML
from .parser import Question

BASE = Path(__file__).resolve().parents[1]
FONT_DIR = BASE / "fonts"
REGULAR = FONT_DIR / "NotoSansDevanagari-Regular.ttf"
BOLD = FONT_DIR / "NotoSansDevanagari-Bold.ttf"


def _e(value):
    return escape(str(value or ""), quote=True)


def _split_inline_options(q):
    """Support TXT questions where A)/B)/C)/D) are typed on the question line."""
    text = q.text.strip()
    opts = list(q.options or [])
    if len([x for x in opts if x.strip()]) >= 2:
        return text, opts[:4]
    matches = list(re.finditer(r'(?<!\S)\(?([A-D])\)\s*', text, re.I))
    # Also recognize option labels directly after punctuation/space, e.g. (A) and A)
    if len(matches) < 2:
        matches = list(re.finditer(r'\(?([A-D])\)\s*', text, re.I))
    valid = []
    for m in matches:
        letter = m.group(1).upper()
        if letter == chr(ord('A') + len(valid)):
            valid.append(m)
        elif letter == 'A' and not valid:
            valid.append(m)
    if len(valid) >= 2 and valid[0].start() > 0:
        stem = text[:valid[0].start()].strip()
        parsed = []
        for i, m in enumerate(valid[:4]):
            end = valid[i + 1].start() if i + 1 < len(valid) else len(text)
            parsed.append(text[m.end():end].strip())
        if stem and any(parsed):
            return stem, parsed
    return text, opts[:4]


def _question_html(q):
    stem, options = _split_inline_options(q)
    option_html = ''.join(
        f'<div class="option"><b>({chr(65+i)})</b> {_e(opt)}</div>'
        for i, opt in enumerate((options + ["", "", "", ""])[:4])
        if opt.strip()
    )
    return f'''<div class="question">
      <div class="question-text"><b>{q.number}.</b> {_e(stem)}</div>
      <div class="options">{option_html}</div>
    </div>'''


def _optional_meta(subject, topic, set_no):
    vals = [x for x in (subject, topic, f"SET {set_no}" if set_no else None) if x]
    return f'<div class="subtitle">{_e("  |  ".join(vals))}</div>' if vals else '<div class="subtitle">QUESTION SET</div>'


def _page_html(group, page_index, total_pages, headline, subject, topic, set_no):
    left = group[:25]
    right = group[25:50]
    left_html = ''.join(_question_html(q) for q in left)
    right_html = ''.join(_question_html(q) for q in right)
    return f'''<section class="paper-page">
      <header class="header"><div class="headline">{_e(headline)}</div>
      {_optional_meta(subject, topic, set_no)}</header>
      <div class="rule"></div>
      <main class="columns"><div class="column">{left_html}</div><div class="column">{right_html}</div></main>
      <footer>Page {page_index} of {total_pages}</footer>
    </section>'''


def generate_pdf(questions: list[Question], output_path: Path, headline: str,
                 subject: str | None = None, topic: str | None = None,
                 set_no: str | None = None, watermark: str = "ENGLISH STUDY CENTRE"):
    if not questions:
        raise ValueError("No questions to render")
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    groups = [questions[i:i + 50] for i in range(0, len(questions), 50)]
    pages = ''.join(_page_html(g, i + 1, len(groups), headline, subject, topic, set_no)
                    for i, g in enumerate(groups))
    html = f'''<!doctype html><html><head><meta charset="utf-8"><style>
@font-face {{ font-family: NotoDev; src: url("{REGULAR.as_uri()}") format("truetype"); font-weight:400; }}
@font-face {{ font-family: NotoDev; src: url("{BOLD.as_uri()}") format("truetype"); font-weight:700; }}
@page {{ size:A4; margin:8mm 9mm 8mm; }}
* {{ box-sizing:border-box; }} html,body {{ margin:0; padding:0; font-family:NotoDev,sans-serif; color:#111; }}
.paper-page {{ height:281mm; position:relative; display:flex; flex-direction:column; page-break-after:always; break-after:page; overflow:hidden; }}
.paper-page:last-child {{ page-break-after:auto; break-after:auto; }}
.header {{ text-align:center; flex:none; padding:3mm 0 1mm; }}
.headline {{ font-size:16pt; font-weight:700; line-height:1.12; letter-spacing:.15px; }}
.subtitle {{ font-size:8.5pt; line-height:1.2; margin-top:1mm; letter-spacing:.4px; }}
.rule {{ border-top:1px solid #333; margin:2.5mm 0 2mm; flex:none; }}
.columns {{ display:grid; grid-template-columns:minmax(0,1fr) minmax(0,1fr); column-gap:7mm; flex:1; min-height:0; }}
.column {{ min-width:0; overflow:hidden; }}
.question {{ break-inside:avoid; margin:0 0 1.1mm; font-size:7.2pt; line-height:1.13; }}
.question-text {{ margin:0 0 .35mm; font-weight:600; overflow-wrap:anywhere; }}
.options {{ display:grid; grid-template-columns:minmax(0,1fr) minmax(0,1fr); column-gap:2.2mm; margin-left:1.2mm; }}
.option {{ font-size:6.8pt; line-height:1.12; overflow-wrap:anywhere; margin:0 0 .15mm; }}
footer {{ position:absolute; bottom:0; left:0; right:0; text-align:center; font-size:6.5pt; color:#666; }}
</style></head><body>{pages}</body></html>'''
    HTML(string=html, base_url=str(BASE)).write_pdf(str(output_path))
