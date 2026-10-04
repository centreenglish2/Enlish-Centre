"""Generate the single, locked English Study Centre exam-paper layout.

The PDF format is intentionally fixed: A4 portrait, centered title, one rule,
two columns, questions 1-25 on the left and 26-50 on the right, with a subtle
ENGLISH STUDY CENTRE watermark on every page.
"""
from html import escape
from pathlib import Path
import re
from weasyprint import HTML
from .parser import Question, split_inline_options

BASE = Path(__file__).resolve().parents[1]
FONT_DIR = BASE / "fonts"
REGULAR = FONT_DIR / "NotoSansDevanagari-Regular.ttf"
BOLD = FONT_DIR / "NotoSansDevanagari-Bold.ttf"
PAGE_QUESTION_LIMIT = 50


def _e(value):
    return escape(str(value or ""), quote=True)


def _split_inline_options(q):
    """Use the parser's shared option-label rules for inline questions."""
    text = str(q.text or "").strip()
    opts = list(q.options or [])
    if len([x for x in opts if str(x).strip()]) >= 2:
        return text, opts[:4]
    stem, parsed = split_inline_options(text)
    if parsed:
        return stem, parsed[:4]
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


def _page_html(group, set_no, watermark, subject=None, lesson=None, topic=None, class_name=None):
    # One fixed header design; optional metadata is omitted when not supplied.
    left_html = ''.join(_question_html(q) for q in group[:25])
    right_html = ''.join(_question_html(q) for q in group[25:50])
    set_label = str(set_no or "").strip()
    left_meta = ''.join(
        f'<div>{label}: {_e(value)}</div>'
        for label, value in (("Sub", subject), ("Lesson", lesson))
        if value and str(value).strip()
    )
    right_meta = ''.join(
        f'<div>{label}: {_e(value)}</div>'
        for label, value in (("Topic", topic), ("Class", class_name))
        if value and str(value).strip()
    )
    set_meta = f'<div class="set-meta">SET {_e(set_label)}</div>' if set_label else ''
    return f'''<section class="paper-page">
      <div class="watermark" aria-hidden="true">{_e(watermark or 'ENGLISH STUDY CENTRE')}</div>
      <div class="metadata">
        <div class="meta-left">{left_meta}</div>
        <div class="meta-right">{right_meta}{set_meta}</div>
      </div>
      <header class="header">
        <div class="headline">ENGLISH STUDY CENTRE</div>
        <div class="school-name">AKASHI SASARAM</div>
        <div class="phone">Mob. No. 7050492611</div>
      </header>
      <div class="rule"></div>
      <main class="columns">
        <div class="column">{left_html}</div>
        <div class="column">{right_html}</div>
      </main>
    </section>'''

def generate_pdf(questions: list[Question], output_path: Path, headline: str = "ENGLISH STUDY CENTRE",
                 subject: str | None = None, topic: str | None = None,
                 set_no: str | None = None, watermark: str = "ENGLISH STUDY CENTRE",
                 lesson: str | None = None, class_name: str | None = None):
    """Write a PDF using only the locked 50-questions-per-page layout.

    Legacy arguments remain accepted so existing bot code keeps working. The
    layout remains fixed; a light watermark is printed on every page.
    """
    if not questions:
        raise ValueError("No questions to render")
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    groups = [questions[i:i + PAGE_QUESTION_LIMIT]
              for i in range(0, len(questions), PAGE_QUESTION_LIMIT)]
    pages = ''.join(_page_html(group, set_no, watermark, subject, lesson, topic, class_name) for group in groups)
    html = f'''<!doctype html><html><head><meta charset="utf-8"><style>
@font-face {{ font-family: NotoDev; src: url("{REGULAR.as_uri()}") format("truetype"); font-weight:400; }}
@font-face {{ font-family: NotoDev; src: url("{BOLD.as_uri()}") format("truetype"); font-weight:700; }}
@page {{ size:A4; margin:0; }}
* {{ box-sizing:border-box; }}
html, body {{ margin:0; padding:0; font-family:NotoDev,"DejaVu Sans",sans-serif; color:#111; }}
.paper-page {{ width:210mm; height:297mm; padding:7mm 9mm 5mm; position:relative; display:block; page-break-after:always; break-after:page; overflow:hidden; }}
.paper-page:last-child {{ page-break-after:auto; break-after:auto; }}
.watermark {{ position:absolute; z-index:0; top:52%; left:50%; transform:translate(-50%,-50%) rotate(-35deg); white-space:nowrap; font-size:30pt; font-weight:700; letter-spacing:1px; color:rgba(0,0,0,.065); pointer-events:none; }}
.header {{ position:relative; z-index:1; text-align:center; padding:2mm 0 0; min-height:28mm; }}
.headline {{ font-family:"DejaVu Serif",serif; font-size:25pt; font-weight:900; line-height:1.05; letter-spacing:.15px; white-space:nowrap; }}
.school-name {{ font-family:"DejaVu Serif",serif; font-size:17pt; font-weight:800; line-height:1.12; margin-top:1.3mm; }}
.phone {{ font-family:"DejaVu Sans",sans-serif; font-size:12pt; font-weight:700; line-height:1.1; margin-top:.8mm; }}
.metadata {{ position:absolute; z-index:2; top:2mm; left:2mm; right:2mm; display:flex; justify-content:space-between; align-items:flex-start; gap:4mm; font-size:9pt; line-height:1.15; font-weight:700; }}
.meta-left,.meta-right {{ width:auto; min-width:0; max-width:30%; border:0; padding:0; background:transparent; }}
.meta-right {{ text-align:right; margin-left:auto; }}
.set-meta {{ font-size:8pt; font-weight:400; }}
.rule {{ position:relative; z-index:1; border-top:1px solid #333; margin:3mm 0 1.5mm; }}
/* Keep all content in normal page flow. Absolute-positioned columns could
   fragment at the page boundary and paint Q25/Q50 above the next page header.
   The rule is followed immediately by two fixed-width columns; compact spacing
   leaves enough room for 25 questions per column without clipping. */
.columns {{ position:relative; z-index:1; display:grid; grid-template-columns:minmax(0,1fr) minmax(0,1fr); column-gap:7mm; height:242mm; min-height:0; overflow:hidden; }}
.column {{ min-width:0; min-height:0; height:100%; overflow:hidden; }}
.question {{ break-inside:avoid; page-break-inside:avoid; margin:0 0 .75mm; font-size:6.9pt; line-height:1.08; }}
.question-text {{ margin:0 0 .2mm; font-weight:600; overflow-wrap:anywhere; }}
.options {{ display:grid; grid-template-columns:minmax(0,1fr) minmax(0,1fr); column-gap:2mm; margin-left:1mm; }}
.option {{ font-size:6.5pt; line-height:1.06; overflow-wrap:anywhere; margin:0; }}
</style></head><body>{pages}</body></html>'''
    HTML(string=html, base_url=str(BASE)).write_pdf(str(output_path))
