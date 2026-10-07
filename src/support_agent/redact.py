"""Mask personal data before text reaches a trace, a handoff note or a model."""
from .pii import find, mask


def redact(text: str) -> str:
    if not isinstance(text, str):
        return text
    out, last = [], 0
    for f in find(text):
        out.append(text[last:f.start])
        out.append(mask(f))
        last = f.end
    out.append(text[last:])
    return "".join(out)
