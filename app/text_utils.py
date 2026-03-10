import re


def normalize_abstract(raw: str | None) -> str:
    if not raw:
        return ""
    clean = re.sub(r"<[^>]+>", " ", raw)
    return re.sub(r"\s+", " ", clean).strip()


def extract_methods(text: str) -> list[str]:
    if not text:
        return []
    sentences = re.split(r"(?<=[.!?])\s+", text)
    patterns = [
        r"\b(method|methodology|approach|framework|pipeline)\b",
        r"\b(we propose|we present|we develop|our model)\b",
        r"\b(experiment|evaluation|dataset|benchmark)\b",
    ]
    selected: list[str] = []
    for sentence in sentences:
        s = sentence.strip()
        if not s:
            continue
        if any(re.search(pattern, s, flags=re.IGNORECASE) for pattern in patterns):
            selected.append(s)
    return selected[:6]
