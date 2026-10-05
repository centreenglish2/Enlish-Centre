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
DEFAULT_PDF_MODE = 100



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


def _page_html(group, set_no, watermark, subject=None, lesson=None, topic=None, class_name=None, mode=100):
    # mode=50 => 25 questions per page; mode=100 => 50 questions per page.
    # Both layouts keep two columns; the 25/page layout simply uses fewer,
    # larger questions per column.
    split_at = (len(group) + 1) // 2
    left_group = group[:split_at]
    right_group = group[split_at:]
    left_html = ''.join(_question_html(q) for q in left_group)
    right_html = ''.join(_question_html(q) for q in right_group)
    left_rows = len(left_group)
    right_rows = len(right_group)
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
    set_meta = f'<div>Set No: {_e(set_label)}</div>' if set_label else ''
    return f'''<section class="paper-page mode-{mode}">
      <div class="watermark" aria-hidden="true">{_e(watermark or 'ENGLISH STUDY CENTRE')}</div>
      <header class="header">
        <div class="header-row">
          <div class="meta-left">{left_meta}</div>
          <div class="center-head">
            <div class="title-line">
              <span class="orange-mark">|</span>
              <span class="headline">ENGLISH STUDY CENTRE</span>
              <span class="orange-mark">|</span>
            </div>
            <div class="school-name">AKASHI SASARAM</div>
            <div class="phone">Mob. No. 7050492611</div>
            <div><b>Session: 2026-27</b></div>
          </div>
          <div class="meta-right">{right_meta}{set_meta}</div>
        </div>
      </header>
      <div class="rule"></div>
      <main class="columns">
        <div class="column" style="grid-template-rows:repeat({left_rows}, minmax(max-content, 1fr));">{left_html}</div>
        <div class="column" style="grid-template-rows:repeat({right_rows}, minmax(max-content, 1fr));">{right_html}</div>
      </main>
    </section>'''

def generate_pdf(questions: list[Question], output_path: Path, headline: str = "ENGLISH STUDY CENTRE",
                 subject: str | None = None, topic: str | None = None,
                 set_no: str | None = None, watermark: str = "ENGLISH STUDY CENTRE",
                 lesson: str | None = None, class_name: str | None = None,
                 pdf_mode: int = DEFAULT_PDF_MODE):
    """Write a PDF using only the locked 50-questions-per-page layout.

    Legacy arguments remain accepted so existing bot code keeps working. The
    layout remains fixed; a light watermark is printed on every page.
    """
    if not questions:
        raise ValueError("No questions to render")
    try:
        pdf_mode = int(pdf_mode)
    except (TypeError, ValueError):
        pdf_mode = DEFAULT_PDF_MODE
    if pdf_mode not in (50, 100):
        raise ValueError("pdf_mode must be 50 or 100")
    page_question_limit = 25 if pdf_mode == 50 else 50
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    groups = [questions[i:i + page_question_limit]
              for i in range(0, len(questions), page_question_limit)]
    pages = ''.join(_page_html(group, set_no, watermark, subject, lesson, topic, class_name, pdf_mode) for group in groups)
    html = f'''<!doctype html><html><head><meta charset="utf-8"><style>
@font-face {{ font-family: NotoDev; src: url("{REGULAR.as_uri()}") format("truetype"); font-weight:400; }}
@font-face {{ font-family: NotoDev; src: url("{BOLD.as_uri()}") format("truetype"); font-weight:700; }}
@page {{ size:A4; margin:0; }}
* {{ box-sizing:border-box; }}
html, body {{ margin:0; padding:0; font-family:NotoDev,"DejaVu Sans",sans-serif; color:#111; }}
.paper-page {{ width:210mm; height:297mm; padding:7mm 9mm 5mm; position:relative; display:block; page-break-after:always; break-after:page; overflow:hidden; }}
.paper-page:last-child {{ page-break-after:auto; break-after:auto; }}
.watermark {{ position:absolute; z-index:0; top:52%; left:50%; transform:translate(-50%,-50%) rotate(-35deg); white-space:nowrap; font-size:30pt; font-weight:700; letter-spacing:1px; color:rgba(0,0,0,.15); pointer-events:none; }}
.header {{ position:relative; z-index:1; padding:1mm 0 0; min-height:27mm; }}
.header-row {{ display:flex; align-items:flex-start; justify-content:space-between; width:100%; padding:0 5mm; }}
.meta-left,.meta-right {{ width:34mm; min-width:34mm; border:0; padding-top:1.2mm; background:transparent; font-size:8.4pt; line-height:1.32; font-weight:700; white-space:nowrap; }}
.meta-left {{ text-align:left; }}
.meta-right {{ text-align:right; }}
.center-head {{ flex:1 1 auto; text-align:center; padding:0 3mm; min-width:0; }}
.title-line {{ display:flex; align-items:center; justify-content:center; gap:2.2mm; white-space:nowrap; }}
.orange-mark {{ color:#f28c00; font-family:"DejaVu Sans",sans-serif; font-size:25pt; font-weight:900; line-height:1; }}
.headline {{ font-family:"DejaVu Serif",serif; font-size:24pt; font-weight:900; line-height:1.02; letter-spacing:.1px; white-space:nowrap; }}
.school-name {{ font-family:"DejaVu Serif",serif; font-size:15pt; font-weight:800; line-height:1.1; margin-top:.8mm; }}
.phone {{ font-family:"DejaVu Sans",sans-serif; font-size:10.5pt; font-weight:700; line-height:1.08; margin-top:.5mm; }}
.rule {{ position:relative; z-index:1; border-top:1px solid #333; margin:2.2mm 0 1.5mm; }}
/* Keep all content in normal page flow. Absolute-positioned columns could
   fragment at the page boundary and paint Q25/Q50 above the next page header.
   The rule is followed immediately by two fixed-width columns; compact spacing
   leaves enough room for 25 questions per column without clipping. */
.columns {{ position:relative; z-index:1; display:grid; grid-template-columns:minmax(0,1fr) minmax(0,1fr); column-gap:7mm; height:242mm; min-height:0; overflow:visible; }}
.column {{ min-width:0; min-height:0; height:100%; overflow:visible; display:grid; align-content:stretch; gap:0; }}
.question {{ flex:none; break-inside:avoid; page-break-inside:avoid; margin:0; font-size:6.35pt; line-height:1.02; }}
.question-text {{ margin:0 0 .12mm; font-weight:600; overflow-wrap:anywhere; }}
.options {{ display:grid; grid-template-columns:minmax(0,1fr) minmax(0,1fr); column-gap:2mm; margin-left:1mm; }}
.question-text, .option {{ hyphens:none; }}
.option {{ font-size:6.0pt; line-height:1.0; overflow-wrap:anywhere; margin:0; }}
.mode-50 .columns {{ height:242mm; column-gap:9mm; }}
.mode-50 .column {{ gap:0; }}
.mode-50 .question {{ font-size:9.0pt; line-height:1.14; padding:0 0 1.2mm; align-self:start; }}
.mode-50 .question-text {{ margin-bottom:.5mm; }}
.mode-50 .option {{ font-size:8.4pt; line-height:1.08; }}
.mode-50 .options {{ column-gap:4mm; margin-left:1.5mm; }}
.mode-100 .question {{ font-size:6.35pt; line-height:1.02; padding:0 0 .65mm; align-self:start; }}
.mode-100 .option {{ font-size:6.0pt; line-height:1.0; }}

</style></head><body>{pages}</body></html>'''
    HTML(string=html, base_url=str(BASE)).write_pdf(str(output_path))
