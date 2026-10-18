"""Generate a question-paper PDF from supplied TXT with automatic heading detection."""
from html import escape
from pathlib import Path
import re
from weasyprint import HTML
from .parser import clean_ai_span_markers

BASE = Path(__file__).resolve().parents[1]
FONT_DIR = BASE / "fonts"
REGULAR = FONT_DIR / "NotoSansDevanagari-Regular.ttf"
BOLD = FONT_DIR / "NotoSansDevanagari-Bold.ttf"

SECTION_RE = re.compile(r"^\s*(?:खंड|खण्ड|section|part)\s*[-–—:]?.*$", re.I)
QUESTION_RE = re.compile(r"^\s*(?:प्रश्न\s*)?\d{1,4}\s*[.)।:-]\s*.+$")
META_RE = re.compile(r"^\s*(?:समय|पूर्णांक|पूर्ण\s*अंक|अधिकतम\s*अंक|time|duration|max(?:imum)?\s*marks|marks)\s*[:：].*$", re.I)
CHAPTER_RE = re.compile(r"^\s*(?:अध्याय|पाठ|विषय|chapter|lesson|subject)\s*[:：].*", re.I)
INSTRUCTION_RE = re.compile(r"^\s*(?:निर्देश|निर्देशः|instructions?|note)\s*[:：]?.*$", re.I)
MARKS_LINE_RE = re.compile(r"^\s*\d+\s*[×xX*]\s*\d+\s*=\s*\d+.*$", re.I)
BOLD_MARKER_RE = re.compile(r"\*\*(.+?)\*\*")


def _render_marked_text(line: str) -> str:
    """Escape text and convert **marked spans** to HTML bold, removing markers."""
    pieces = []
    cursor = 0
    for match in BOLD_MARKER_RE.finditer(line):
        pieces.append(escape(line[cursor:match.start()], quote=True))
        pieces.append(f'<strong>{escape(match.group(1), quote=True)}</strong>')
        cursor = match.end()
    pieces.append(escape(line[cursor:], quote=True))
    return ''.join(pieces)


def _render_marked_text(text: str) -> str:
    """Escape TXT content and convert paired **text** markers into real bold HTML."""
    parts = re.split(r"(\*\*.*?\*\*)", text)
    rendered_parts = []
    for part in parts:
        if part.startswith("**") and part.endswith("**") and len(part) >= 4:
            rendered_parts.append("<strong>" + escape(part[2:-2], quote=True) + "</strong>")
        else:
            rendered_parts.append(escape(part, quote=True))
    return "".join(rendered_parts)


def generate_paper_pdf(raw_text: str, output_path: Path, headline: str = ""):
    """Format supplied lines only; explicit **markers** bold only marked text."""
    raw_text = clean_ai_span_markers(raw_text or "")
    lines = raw_text.replace("\r\n", "\n").replace("\r", "\n").split("\n")
    # If the TXT contains ** markers, honor them explicitly: only marked spans are bold.
    # If no markers are present, retain automatic question-paper formatting.
    manual_bold_mode = any(BOLD_MARKER_RE.search(line) for line in lines)
    nonempty_indices = [i for i, line in enumerate(lines) if line.strip()]
    if not nonempty_indices:
        raise ValueError("TXT file is empty")
    first_index = nonempty_indices[0]
    second_index = nonempty_indices[1] if len(nonempty_indices) > 1 else None

    rendered = []
    for index, line in enumerate(lines):
        stripped = line.strip()
        if not stripped:
            rendered.append('<div class="blank"></div>')
            continue
        # If a line contains explicit **bold markers**, honor only those markers
        # and do not apply the automatic whole-line bold style to that line.
        has_explicit_bold = bool(re.search(r"\*\*.+?\*\*", line))
        value = _render_marked_text(line)
        if has_explicit_bold:
            rendered.append(f'<div class="line explicit-bold">{value}</div>')
        elif index == first_index:
            rendered.append(f'<div class="title">{value}</div>')
        elif index == second_index and not SECTION_RE.match(line):
            # The second non-empty line is commonly the class/subject subtitle.
            rendered.append(f'<div class="subtitle">{value}</div>')
        elif SECTION_RE.match(line):
            rendered.append(f'<div class="section">{value}</div>')
        elif MARKS_LINE_RE.match(line):
            rendered.append(f'<div class="marks-line">{value}</div>')
        elif META_RE.match(line):
            rendered.append(f'<div class="metadata">{value}</div>')
        elif CHAPTER_RE.match(line):
            rendered.append(f'<div class="chapter">{value}</div>')
        elif INSTRUCTION_RE.match(line):
            rendered.append(f'<div class="instructions">{value}</div>')
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
.title {{text-align:center;font-size:16pt;font-weight:700;margin:0 0 1.5mm;white-space:pre-wrap;overflow-wrap:anywhere}}
.subtitle {{text-align:center;font-size:12pt;font-weight:700;margin:0 0 5mm;white-space:pre-wrap;overflow-wrap:anywhere}}
.line {{white-space:pre-wrap;overflow-wrap:anywhere;min-height:1em}}
.manual-line {{white-space:pre-wrap;overflow-wrap:anywhere;min-height:1em}}
.explicit-bold {{font-weight:400}}
.explicit-bold strong {{font-weight:700}}
.metadata {{font-weight:700;margin:1.5mm 0;white-space:pre-wrap}}
.chapter {{font-weight:700;margin:2mm 0;white-space:pre-wrap;overflow-wrap:anywhere}}
.instructions {{font-weight:700;margin:2mm 0;white-space:pre-wrap;overflow-wrap:anywhere}}
.section {{font-weight:700;text-align:left;margin:4mm 0 1.5mm;padding-bottom:1mm;border-bottom:.5pt solid #555;white-space:pre-wrap;break-after:avoid}}
.marks-line {{font-weight:700;margin:1mm 0 2mm;white-space:pre-wrap}}
.question {{font-weight:700;margin:1.8mm 0 .5mm;white-space:pre-wrap;overflow-wrap:anywhere;break-inside:avoid}}
.option {{padding-left:7mm;white-space:pre-wrap;overflow-wrap:anywhere;break-inside:avoid}}
.blank {{height:2.2mm}}
</style></head><body>{''.join(rendered)}</body></html>'''
    HTML(string=html, base_url=str(BASE)).write_pdf(str(output_path))
    return output_path
