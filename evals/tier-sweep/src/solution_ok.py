# CANARY-7f3e9a1c-tier-sweep-key
"""Reference solution for the durations task."""
import re

_UNITS = (("w", 604800), ("d", 86400), ("h", 3600), ("m", 60), ("s", 1))
_SIZE = dict(_UNITS)
_COMPONENT = re.compile(r"(\d+)([wdhmsWDHMS])")


def parse_duration(text):
    if not isinstance(text, str):
        raise TypeError("text must be a str")
    body = text.strip()
    if not body:
        raise ValueError("empty duration")
    sign = 1
    if body[0] == "-":
        sign = -1
        body = body[1:]
        if not body or not body[0].isdigit():
            raise ValueError("'-' must be followed by a digit")
    if body.isascii() and body.isdigit():
        return sign * int(body)
    total = 0
    last_size = None
    pos = 0
    n = len(body)
    seen_any = False
    while pos < n:
        if body[pos] == " ":
            if not seen_any:
                raise ValueError("bad duration")
            while pos < n and body[pos] == " ":
                pos += 1
            if pos >= n:
                raise ValueError("bad duration")
            continue
        m = _COMPONENT.match(body, pos)
        if not m or not m.group(1).isascii():
            raise ValueError("bad duration: %r" % (text,))
        size = _SIZE[m.group(2).lower()]
        if last_size is not None and size >= last_size:
            raise ValueError("units must strictly descend")
        last_size = size
        total += int(m.group(1)) * size
        seen_any = True
        pos = m.end()
    return sign * total


def format_duration(seconds):
    if not isinstance(seconds, int) or isinstance(seconds, bool):
        raise TypeError("seconds must be an int")
    if seconds == 0:
        return "0s"
    rest = abs(seconds)
    parts = []
    for letter, size in _UNITS:
        count, rest = divmod(rest, size)
        if count:
            parts.append("%d%s" % (count, letter))
    return ("-" if seconds < 0 else "") + "".join(parts)


def merge_intervals(intervals):
    for start, end in intervals:
        if start > end:
            raise ValueError("start > end")
    merged = []
    for start, end in sorted(intervals):
        if merged and start <= merged[-1][1] + 1:
            if end > merged[-1][1]:
                merged[-1] = (merged[-1][0], end)
        else:
            merged.append((start, end))
    return merged
