import re
from dataclasses import dataclass, field


# Remove AI/citation span markers such as [span_95](start_span) and
# [span_95](end_span), including escaped forms like [span_95]\\(start_span).
SPAN_MARKER_RE = re.compile(
    r"[ \t]*\[\s*span_\d+\s*\][ \t]*\\?\([ \t]*(?:start_span|end_span)[ \t]*\)[ \t]*",
    re.IGNORECASE,
)


def clean_ai_span_markers(text: str) -> str:
    """Remove AI-generated span markers from source text before parsing/rendering."""
    previous = None
    while previous != text:
        previous = text
        text = SPAN_MARKER_RE.sub(" ", text)
    return text


@dataclass
class Question:
    number: int
    text: str
    options: list[str] = field(default_factory=list)


# Question number formats: 1. / 1) / 1-
Q_RE = re.compile(r"^\s*(\d{1,4})\s*[.)-]\s*(.*)$")


# Only English option labels: A, B, C, D and a, b, c, d
LABEL_CHARS = r"A-Da-d"


# Supported option formats:
# (A), [A], {A}, A), and lowercase equivalents
OPTION_LABEL_RE = re.compile(
    rf"^(?:"
    rf"\(([{LABEL_CHARS}])\)"
    rf"|\[([{LABEL_CHARS}])\]"
    rf"|\{{([{LABEL_CHARS}])\}}"
    rf"|([{LABEL_CHARS}])\)"
    rf")\s*(.*)$"
)


# Detect inline options in the same question line
INLINE_LABEL_RE = re.compile(
    rf"(?<!\S)(?:"
    rf"\(([{LABEL_CHARS}])\)"
    rf"|\[([{LABEL_CHARS}])\]"
    rf"|\{{([{LABEL_CHARS}])\}}"
    rf"|([{LABEL_CHARS}])\)"
    rf")\s*"
)


OPTION_INDEX = {
    "A": 0,
    "B": 1,
    "C": 2,
    "D": 3,
}


VALID_LABELS = ("A", "B", "C", "D", "a", "b", "c", "d")


def _label_from_match(match):
    """Return the matched English option label."""
    for group in match.groups():
        if group in VALID_LABELS:
            return group
    return None


def split_inline_options(text: str):
    """Split a question containing inline A/B/C/D options."""

    matches = list(INLINE_LABEL_RE.finditer(text))

    if len(matches) < 2:
        return text, []

    labels = [_label_from_match(match) for match in matches]

    sequences = [
        ("A", "B", "C", "D"),
        ("a", "b", "c", "d"),
    ]

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
        if index + 1 < len(chosen):
            end = chosen[index + 1].start()
        else:
            end = len(text)

        options.append(text[match.end():end].strip())

    if stem and all(options):
        return stem, options

    return text, []


def parse_questions(raw: str) -> list[Question]:
    """Parse numbered questions/options after removing AI span markers."""

    raw = clean_ai_span_markers(raw)
    lines = [
        line.replace("\ufeff", "").rstrip()
        for line in raw.replace("\r\n", "\n")
        .replace("\r", "\n")
        .split("\n")
    ]

    found: list[Question] = []
    current = None
    current_opt = None

    def finish():
        nonlocal current, current_opt

        if current is not None:
            current.text = re.sub(
                r"\s+", " ", current.text
            ).strip()

            current.options = [
                re.sub(r"\s+", " ", option).strip()
                for option in current.options
            ]

            # Split inline options if no separate options were parsed.
            if not any(option.strip() for option in current.options):
                current.text, current.options = split_inline_options(
                    current.text
                )

            if current.text:
                found.append(current)

        current = None
        current_opt = None

    for line in lines:
        s = line.strip()

        if not s:
            continue

        # Detect a new question.
        qm = Q_RE.match(s)

        if qm:
            finish()

            current = Question(
                number=int(qm.group(1)),
                text=qm.group(2).strip(),
                options=[],
            )

            current_opt = None
            continue

        # Detect an A/B/C/D option.
        om = OPTION_LABEL_RE.match(s)

        if om and current is not None:
            letter = _label_from_match(om)

            if letter is not None:
                letter = letter.upper()
                idx = OPTION_INDEX.get(letter)

                if idx is not None:
                    while len(current.options) <= idx:
                        current.options.append("")

                    # Group 5 contains the option text.
                    current.options[idx] = om.group(5).strip()
                    current_opt = idx
                    continue

        # Continue a multiline option or question.
        if current is not None:
            if current_opt is not None and current.options:
                current.options[current_opt] += " " + s
            else:
                current.text += " " + s

    finish()

    # Normalize displayed question numbers while preserving source order.
    for i, question in enumerate(found, 1):
        question.number = i

    return found
