import re
from dataclasses import dataclass, field

@dataclass
class Question:
    number: int
    text: str
    options: list[str] = field(default_factory=list)

Q_RE = re.compile(r"^\s*(\d{1,4})\s*[.)-]\s*(.*)$")
LABEL_CHARS = r"A-Da-dकखगघ"
# Accepted option labels: (A), [A], {A}, A), and lowercase equivalents.
OPTION_LABEL_RE = re.compile(
    rf"^(?:\(([{LABEL_CHARS}])\)|\[([{LABEL_CHARS}])\]|\{{([{LABEL_CHARS}])\}}|([{LABEL_CHARS}])\))\s*(.*)$"
)
INLINE_LABEL_RE = re.compile(
    rf"(?<!\S)(?:\(([{LABEL_CHARS}])\)|\[([{LABEL_CHARS}])\]|\{{([{LABEL_CHARS}])\}}|([{LABEL_CHARS}])\))\s*"
)
OPTION_INDEX = {"A": 0, "B": 1, "C": 2, "D": 3, "क": 0, "ख": 1, "ग": 2, "घ": 3}


def _label_from_match(match):
    return next((group for group in match.groups() if group is not None and len(group) == 1 and group in ("A", "B", "C", "D", "a", "b", "c", "d", "क", "ख", "ग", "घ")), None)


def split_inline_options(text: str):
    """Split a question line containing option labels in supported formats."""
    matches = list(INLINE_LABEL_RE.finditer(text))
    if len(matches) < 2:
        return text, []

    labels = [_label_from_match(match) for match in matches]
    sequences = [("A", "B", "C", "D"), ("a", "b", "c", "d"), ("क", "ख", "ग", "घ")]
    chosen = None
    for sequence in sequences:
        candidate = []
        expected = 0
        for match, label in zip(matches, labels):
            if expected < 4 and label == sequence[expected]:
                candidate.append(match)
                expected += 1
                if expected == 4:
                    break
        if len(candidate) >= 2:
            chosen = candidate
            break
    if not chosen or chosen[0].start() == 0:
        return text, []

    stem = text[:chosen[0].start()].strip()
    options = []
    for index, match in enumerate(chosen):
        end = chosen[index + 1].start() if index + 1 < len(chosen) else len(text)
        options.append(text[match.end():end].strip())
    if stem and all(options):
        return stem, options
    return text, []


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
            if not any(x.strip() for x in current.options):
                current.text, current.options = split_inline_options(current.text)
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
        om = OPTION_LABEL_RE.match(s)
        if om and current is not None:
            letter = _label_from_match(om)
            if letter is not None:
                letter = letter.upper() if letter.isascii() else letter
                idx = OPTION_INDEX.get(letter)
                if idx is not None:
                    while len(current.options) <= idx:
                        current.options.append("")
                    # option text is the final capture group
                    current.options[idx] = om.group(5).strip()
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
