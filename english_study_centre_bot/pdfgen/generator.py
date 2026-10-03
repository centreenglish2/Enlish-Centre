from pathlib import Path
from html import escape
from weasyprint import HTML, CSS
from .parser import Question

BASE = Path(__file__).resolve().parents[1]
FONT_DIR = BASE / "fonts"
REGULAR = FONT_DIR / "NotoSansDevanagari-Regular.ttf"
BOLD = FONT_DIR / "NotoSansDevanagari-Bold.ttf"


def _e(value):
    return escape(str(value), quote=True)


def _optional_meta(subject, topic, set_no):
    parts = []
    if subject:
        parts.append(f'<span><b>Subject:</b> {_e(subject)}</span>')
    if topic:
        parts.append(f'<span><b>Topic:</b> {_e(topic)}</span>')
    if set_no:
        parts.append(f'<span><b>Set No:</b> {_e(set_no)}</span>')
    return '<div class="meta">' + '<span class="sep">|</span>'.join(parts) + '</div>' if parts else ''


def _question_html(q: Question):
    opts = ''.join(
        f'<div class="option"><b>{chr(65+i)})</b> {_e(opt)}</div>'
        for i, opt in enumerate(q.options[:4])
    )
    return f'''<div class="question">
      <div class="question-text"><b>{q.number}.</b> {_e(q.text)}</div>
      <div class="options">{opts}</div>
    </div>'''


def _page_html(group, page_index, total_pages, headline, subject, topic, set_no, watermark):
    questions = ''.join(_question_html(q) for q in group)
    return f'''
    <section class="paper-page">
      <div class="watermark">{_e(watermark)}</div>
      <header class="header">
        <div class="headline">{_e(headline)}</div>
        {_optional_meta(subject, topic, set_no)}
      </header>
      <div class="page-range">Questions {group[0].number}–{group[-1].number}</div>
      <main>{questions}</main>
      <footer>Page {page_index} of {total_pages}</footer>
    </section>'''


def generate_pdf(questions: list[Question], output_path: Path, headline: str,
                 subject: str | None = None, topic: str | None = None,
                 set_no: str | None = None, watermark: str = "ENGLISH STUDY CENTRE"):
    if not questions:
        raise ValueError("No questions to render")
    output_path.parent.mkdir(parents=True, exist_ok=True)

    groups = [questions[i:i+50] for i in range(0, len(questions), 50)]
    total_pages = len(groups)
    pages = ''.join(_page_html(g, i+1, total_pages, headline, subject, topic, set_no, watermark)
                    for i, g in enumerate(groups))

    html = f'''<!doctype html>
<html><head><meta charset="utf-8"><style>
@font-face {{
  font-family: "NotoDev";
  src: url("{REGULAR.as_uri()}") format("truetype");
  font-weight: 400;
}}
@font-face {{
  font-family: "NotoDev";
  src: url("{BOLD.as_uri()}") format("truetype");
  font-weight: 700;
}}
@page {{ size: A4; margin: 7mm 8mm 7mm 8mm; }}
* {{ box-sizing: border-box; }}
html, body {{ margin:0; padding:0; font-family:"NotoDev", sans-serif; color:#111; }}
.paper-page {{
  position:relative; height:283mm; overflow:hidden;
  page-break-after:always; break-after:page;
}}
.paper-page:last-child {{ page-break-after:auto; break-after:auto; }}
.watermark {{
  position:absolute; z-index:0; top:119mm; left:12mm; width:260mm;
  text-align:center; transform:rotate(-32deg); transform-origin:center;
  font-size:34pt; font-weight:700; color:rgba(100,100,100,.075);
  white-space:nowrap; pointer-events:none;
}}
.header {{
  position:relative; z-index:2; text-align:center; border:1.2px solid #17365D;
  border-radius:7px; padding:3.2mm 4mm 2.8mm; margin-bottom:1.8mm;
  background:#fff;
}}
.headline {{ font-size:16pt; line-height:1.15; font-weight:700; color:#17365D; letter-spacing:.2px; }}
.meta {{ margin-top:1.4mm; display:flex; justify-content:center; gap:2.5mm; flex-wrap:wrap; font-size:8.2pt; line-height:1.15; }}
.meta .sep {{ color:#888; margin:0 1mm; }}
.page-range {{ position:relative; z-index:2; text-align:center; font-size:7.5pt; color:#666; margin-bottom:1.5mm; }}
main {{ position:relative; z-index:2; height:267mm; columns:2; column-gap:7mm; column-fill:auto; }}
.question {{
  position:relative; break-inside:avoid; page-break-inside:avoid;
  margin:0 0 .45mm 0; font-size:6.8pt; line-height:1.0;
}}
.question-text {{ margin:0 0 .15mm 0; }}
.options {{ margin-left:3.2mm; display:grid; grid-template-columns:1fr 1fr; column-gap:3mm; }}
.option {{ margin:0 0 .10mm 0; break-inside:avoid; }}
footer {{ position:absolute; z-index:2; bottom:0; left:0; right:0; text-align:center; font-size:6.8pt; color:#777; }}
</style></head><body>{pages}</body></html>'''

    HTML(string=html, base_url=str(BASE)).write_pdf(str(output_path))
