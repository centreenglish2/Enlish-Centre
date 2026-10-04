import re
from dataclasses import dataclass, field

@dataclass
class Question:
    number: int
    text: str
    options: list[str] = field(default_factory=list)

Q_RE = re.compile(r"^\s*(\d{1,4})\s*[.)-]\s*(.*)$")
OPT_RE = re.compile(r"^\s*\(?([A-Da-dकखगघ])\)?[.)\-:]?\s+(.*)$")
OPTION_INDEX = {"A": 0, "B": 1, "C": 2, "D": 3, "क": 0, "ख": 1, "ग": 2, "घ": 3}


def parse_questions(raw: str) -> list[Question]:
    lines = [x.replace("\ufeff", "").rstrip() for x in raw.replace("\r\n", "\n").replace("\r", "\n").split("\n")]
    found: list[Question] = []
    current = None
    current_opt = None

    def split_inline_options(text: str):
        """Split A) ... B) ... C) ... D) when all options are on one line."""
        # Require option labels in A-B-C-D order and a question stem before A).
        # The whitespace boundary avoids mistaking ordinary words for labels.
        matches = list(re.finditer(r"(?<!\S)\(?([A-Da-dकखगघ])\)\s*", text))
        sequence = []
        for labels in [("A", "B", "C", "D"), ("a", "b", "c", "d"), ("क", "ख", "ग", "घ")]:
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
                sequence = candidate
                break
        if len(sequence) >= 2 and sequence[0].start() > 0:
            stem = text[:sequence[0].start()].strip()
            options = []
            for i, match in enumerate(sequence):
                end = sequence[i + 1].start() if i + 1 < len(sequence) else len(text)
                options.append(text[match.end():end].strip())
            if stem and all(options):
                return stem, options
        return text, []

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
        om = OPT_RE.match(s)
        if om and current is not None:
            letter = om.group(1).upper() if om.group(1).isascii() else om.group(1)
            idx = OPTION_INDEX[letter]
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
