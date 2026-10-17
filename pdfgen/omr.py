"""Generate printable OMR answer sheets with configurable question numbers."""
from pathlib import Path
from html import escape
from weasyprint import HTML


def generate_omr_pdf(start: int, end: int, output_path: Path) -> None:
    if start < 1 or end < start:
        raise ValueError("Invalid question range")
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    numbers = list(range(start, end + 1))
    groups = [numbers[i:i + 100] for i in range(0, len(numbers), 100)]
    pages = []
    for page_index, group in enumerate(groups, 1):
        columns = [group[i:i + 20] for i in range(0, len(group), 20)]
        col_html = []
        for col_index, col in enumerate(columns):
            rows = ''.join(
                '<div class="qrow"><span class="qnum">{}</span><span class="bubbles">{}</span></div>'.format(
                    n, ''.join('<span class="bubble"></span>' for _ in 'ABCD')
                ) for n in col
            )
            col_html.append(f'<div class="col"><div class="colhead"><b class="range">{col[0]}–{col[-1]}</b><span class="targets"><i></i><i></i><i></i><i></i></span></div>{rows}</div>')
        pages.append(f'''<section class="page">
          <div class="outer">
            <div class="fields"><div>NAME : <span></span></div><div>EXAM : <span></span></div><div>DATE : <span></span></div></div>
            <h1>OMR ANSWER SHEET</h1>
            <div class="sub">Questions {group[0]}–{group[-1]} &nbsp; | &nbsp; Page {page_index} of {len(groups)}</div>
            <div class="roll"><span>Roll No.: <i></i></span><span>Instructions: Fill one bubble per question.</span></div>
            <div class="grid">{''.join(col_html)}</div>
            <div class="foot">Use a dark blue or black pen/pencil. Do not tick or cross the bubbles.</div>
          </div>
        </section>''')
    html = '''<!doctype html><html><head><meta charset="utf-8"><style>
@page{size:A4 portrait;margin:0}*{box-sizing:border-box}body{margin:0;font-family:Arial,sans-serif;color:#111}
.page{width:210mm;height:297mm;padding:7mm;page-break-after:always;break-after:page}.page:last-child{page-break-after:auto;break-after:auto}
.outer{height:100%;border:1.2px solid #d2d2d2;border-radius:4mm;padding:12mm 6mm 5mm;display:flex;flex-direction:column}
.fields{display:grid;grid-template-columns:1.2fr 1fr .7fr;margin-bottom:5mm}.fields div{border:1px solid #888;height:9mm;padding:2mm;font-size:9pt}.fields div+div{border-left:0}.fields span{display:inline-block}
h1{text-align:center;font-size:15pt;margin:0 0 1mm;font-weight:700}.sub{text-align:center;font-size:9pt;margin-bottom:4mm}
.roll{display:flex;justify-content:space-between;align-items:center;font-size:8pt;margin-bottom:3mm}.roll i{display:inline-block;width:34mm;height:5mm;border:1px solid #555;vertical-align:middle;margin-left:2mm}
.grid{display:grid;grid-template-columns:repeat(5,minmax(0,1fr));flex:1;min-height:0}.col{padding:0 2mm;display:flex;flex-direction:column;border-right:1px solid #eee}.col:last-child{border-right:0}.colhead{height:6mm;display:flex;align-items:flex-start;justify-content:space-between;gap:1mm}.range{font-size:8pt;white-space:nowrap}.targets{display:flex;gap:1mm}.targets i{display:inline-block;width:3.2mm;height:3.2mm;border:1px solid #555;border-radius:50%;position:relative}.targets i:after{content:'';position:absolute;width:1mm;height:1mm;border:0.5px solid #777;border-radius:50%;left:0.55mm;top:0.55mm}.qrow{display:flex;align-items:center;justify-content:flex-end;gap:1mm;flex:1;min-height:0;font-size:8pt}.qnum{width:8mm;text-align:right;font-weight:500}.bubbles{display:flex;gap:1mm}.bubble{width:4.2mm;height:4.2mm;flex:0 0 4.2mm;border:1.1px solid #555;border-radius:50%;display:inline-block}.foot{text-align:center;font-size:7pt;color:#666;margin-top:3mm}
</style></head><body>''' + ''.join(pages) + '</body></html>'
    HTML(string=html).write_pdf(str(output_path))
