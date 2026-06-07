import re


def sanitize_for_tts(text: str) -> str:
    """Prepare LLM reply text for Inworld TTS-2.

    Strips markdown artifacts, converts numeric shorthand to spoken form,
    and removes any JSON/telemetry fragments that leaked through.
    """
    if not text:
        return text

    text = _strip_markdown(text)
    text = _convert_numbers(text)
    text = _strip_json_fragments(text)
    text = _normalize_whitespace(text)
    return text


def _strip_markdown(text: str) -> str:
    text = re.sub(r"\*{1,2}([^*]+)\*{1,2}", r"\1", text)  # bold / italic
    text = re.sub(r"`([^`]+)`", r"\1", text)  # inline code
    text = re.sub(r"^[-*•]\s+", "", text, flags=re.MULTILINE)  # bullets
    text = re.sub(r"^#{1,6}\s+", "", text, flags=re.MULTILINE)  # headings
    text = re.sub(r"_([^_]+)_", r"\1", text)  # underscore italic
    return text


def _convert_numbers(text: str) -> str:
    # Gaps: 0.28s → "point two eight seconds"
    def _gap(m):
        raw = m.group(1)
        spoken = _decimal_to_words(raw)
        return f"{spoken} seconds"

    text = re.sub(r"\b(\d+\.\d+)s\b", _gap, text)

    # Position: P1–P20 → "position one" … "position twenty"
    _pos_words = {
        1: "one",
        2: "two",
        3: "three",
        4: "four",
        5: "five",
        6: "six",
        7: "seven",
        8: "eight",
        9: "nine",
        10: "ten",
        11: "eleven",
        12: "twelve",
        13: "thirteen",
        14: "fourteen",
        15: "fifteen",
        16: "sixteen",
        17: "seventeen",
        18: "eighteen",
        19: "nineteen",
        20: "twenty",
    }

    def _pos(m):
        n = int(m.group(1))
        return f"position {_pos_words.get(n, m.group(1))}"

    text = re.sub(r"\bP(\d{1,2})\b", _pos, text)

    # Lap counts: "Lap 3" / "lap 3" → "lap three"
    _small = {
        "0": "zero",
        "1": "one",
        "2": "two",
        "3": "three",
        "4": "four",
        "5": "five",
        "6": "six",
        "7": "seven",
        "8": "eight",
        "9": "nine",
        "10": "ten",
        "11": "eleven",
        "12": "twelve",
        "13": "thirteen",
        "14": "fourteen",
        "15": "fifteen",
        "16": "sixteen",
        "17": "seventeen",
        "18": "eighteen",
        "19": "nineteen",
        "20": "twenty",
    }

    def _lap(m):
        n = m.group(1)
        return f"lap {_small.get(n, n)}"

    text = re.sub(r"\b[Ll]ap (\d{1,2})\b", _lap, text)

    # Percentages: 65% → "sixty-five percent"
    def _pct(m):
        n = int(m.group(1))
        return f"{_number_to_words(n)} percent"

    text = re.sub(r"\b(\d{1,3})%", _pct, text)

    # Temperature: 35°C / 35C → "thirty-five degrees"
    def _temp(m):
        n = int(m.group(1))
        return f"{_number_to_words(n)} degrees"

    text = re.sub(r"\b(\d{1,3})\s*°?C\b", _temp, text)

    return text


def _decimal_to_words(value: str) -> str:
    """Convert a decimal string like '0.28' to 'point two eight'."""
    _digits = {
        "0": "zero",
        "1": "one",
        "2": "two",
        "3": "three",
        "4": "four",
        "5": "five",
        "6": "six",
        "7": "seven",
        "8": "eight",
        "9": "nine",
    }
    if "." in value:
        int_part, dec_part = value.split(".", 1)
        int_words = _number_to_words(int(int_part)) if int_part else "zero"
        dec_words = " ".join(_digits.get(d, d) for d in dec_part)
        return f"{int_words} point {dec_words}"
    return _number_to_words(int(value))


def _number_to_words(n: int) -> str:
    """Convert small integers (0–99) to English words."""
    ones = [
        "zero",
        "one",
        "two",
        "three",
        "four",
        "five",
        "six",
        "seven",
        "eight",
        "nine",
        "ten",
        "eleven",
        "twelve",
        "thirteen",
        "fourteen",
        "fifteen",
        "sixteen",
        "seventeen",
        "eighteen",
        "nineteen",
    ]
    tens = ["", "", "twenty", "thirty", "forty", "fifty", "sixty", "seventy", "eighty", "ninety"]
    if n < 20:
        return ones[n]
    if n < 100:
        t = tens[n // 10]
        o = ones[n % 10] if n % 10 else ""
        return f"{t}-{o}" if o else t
    return str(n)


def _strip_json_fragments(text: str) -> str:
    # Remove JSON key-value pairs that leaked through (e.g. {"frontS": 0.28})
    text = re.sub(r'"[a-zA-Z_]+"\s*:\s*["\d\[{].*?(?=[,}]|$)', "", text)
    # Remove bare curly braces left over; preserve [] which are TTS steering tags
    text = re.sub(r"[{}]", "", text)
    return text


def _normalize_whitespace(text: str) -> str:
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{2,}", " ", text)
    return text.strip()
