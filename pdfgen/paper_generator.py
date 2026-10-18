"""Generate a question-paper PDF from the supplied TXT without inventing content."""
from html import escape
from pathlib import Path
import re
from weasyprint import HTML
from .parser import clean_ai_span_markers

BASE = Path(__file__).resolve().parents[1]
FONT_DIR = BASE / "fonts"
REGULAR = FONT_DIR / "NotoSansDevanagari-Regular.ttf"
BOLD = FONT_DIR / "NotoSansDevanagari-Bold.ttf"

SECTION_RE = re.compile(r"^\s*(?:खंड|खण्ड|section|part)\s*[-–—:]?\s*[अ-अA-Z0-9IVX०-९]+.*$", re.I)
QUESTION_RE = re.compile(r"^\s*(?:प्रश्न\s*)?\d{1,4}\s*[.)।:-]\s*.+$")
META_RE = re.compile(r"^\s*(?:समय|पूर्णांक|पूर्ण\s*अंक|अधिकतम\s*अंक|time|duration|max(?:imum)?\s*marks|marks)\s*[:：].*$", re.I)


def generate_paper_pdf(raw_text: str, output_path: Path, headline: str = ""):
    """Format only supplied lines; no default marks, time, sections, or questions are added."""
    raw_text = clean_ai_span_markers(raw_text or "")
    lines = raw_text.replace("\r\n", "\n").replace("\r", "\n").split("\n")
    if not any(line.strip() for line in lines):
        raise ValueError("TXT file is empty")

    rendered = []
    first_nonempty_seen = False
    for line in lines:
        if not line.strip():
            rendered.append('<div class="blank"></div>')
            continue
        value = escape(line, quote=True)
        if not first_nonempty_seen:
            first_nonempty_seen = True
            rendered.append(f'<div class="first-line">{value}</div>')
        elif SECTION_RE.match(line):
            rendered.append(f'<div class="section">{value}</div>')
        elif META_RE.match(line):
            rendered.append(f'<div class="metadata">{value}</div>')
        elif QUESTION_RE.match(line):
            rendered.append(f'<div class="question">{value}</div>')
        elif re.match(r"^\s*(?:[A-Da-d][).:]|[क-घ][).:])\s*", line):
            rendered.append(f'<div class="option">{value}</div>')
        else:
            rendered.append(f'<div class="line">{value}</div>')

    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    html = f'''<!doctype html><html><head><meta charset="utf-8"><style>
@font-face {{font-family:NotoDev;src:url("{REGULAR.as_uri()}");font-weight:400}}
@font-face {{font-family:NotoDev;src:url("{BOLD.as_uri()}");font-weight:700}}
@page {{size:A4;margin:17mm 16mm 16mm; @bottom-center {{content:counter(page);font:8pt NotoDev;color:#555}}}}
* {{box-sizing:border-box}}
body {{margin:0;color:#111;background:#fff;font-family:NotoDev,"DejaVu Sans",sans-serif;font-size:11pt;line-height:1.45}}
.first-line {{text-align:center;font-size:16pt;font-weight:700;margin:0 0 5mm;white-space:pre-wrap}}
.line {{white-space:pre-wrap;overflow-wrap:anywhere;min-height:1em}}
.metadata {{font-weight:700;margin:1.5mm 0;white-space:pre-wrap}}
.section {{font-weight:700;text-align:left;margin:4mm 0 1.5mm;padding-bottom:1mm;border-bottom:.5pt solid #555;white-space:pre-wrap;break-after:avoid}}
.question {{margin:1.8mm 0 .5mm;white-space:pre-wrap;overflow-wrap:anywhere;break-inside:avoid}}
.option {{padding-left:7mm;white-space:pre-wrap;overflow-wrap:anywhere;break-inside:avoid}}
.blank {{height:2.2mm}}
</style></head><body>{''.join(rendered)}</body></html>'''
    HTML(string=html, base_url=str(BASE)).write_pdf(str(output_path))
    return output_path
