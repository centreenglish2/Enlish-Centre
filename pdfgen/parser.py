import re
from dataclasses import dataclass, field

@dataclass
class Question:
    number: int
    text: str
    options: list[str] = field(default_factory=list)

Q_RE = re.compile(r"^\s*(\d{1,4})\s*[.)-]\s*(.*)$")
OPT_RE = re.compile(r"^\s*([A-Da-d])\s*[.)\-:]\s*(.*)$")


def parse_questions(raw: str) -> list[Question]:
    lines = [x.replace("\ufeff", "").rstrip() for x in raw.replace("\r\n", "\n").replace("\r", "\n").split("\n")]
    found: list[Question] = []
    current = None
    current_opt = None

    def finish():
        nonlocal current
        if current is not None:
            current.text = re.sub(r"\s+", " ", current.text).strip()
            current.options = [re.sub(r"\s+", " ", x).strip() for x in current.options]
            if current.text:
                found.append(current)
        current = None

    for line in lines:
        s = line.strip()
        if not s:
            continue
        qm = Q_RE.match(s)
        if qm:
            finish()
            current = Question(int(qm.group(1)), qm.group(2).strip(), [])
            current_opt = None
            continue
        om = OPT_RE.match(s)
        if om and current is not None:
            letter = om.group(1).upper()
            idx = ord(letter) - ord("A")
            while len(current.options) <= idx:
                current.options.append("")
            current.options[idx] = om.group(2).strip()
            current_opt = idx
            continue
        if current is not None:
            if current_opt is not None and current.options:
                current.options[current_opt] += " " + s
            else:
                current.text += " " + s
    finish()

    # If numbering is repeated/irregular, preserve source order but normalize displayed numbers.
    for i, q in enumerate(found, 1):
        q.number = i
    return found
