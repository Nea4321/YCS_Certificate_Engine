import re
from datetime import datetime
from .utils_text import _clean

_YEAR_2DIGIT = re.compile(r"^[`'’‵′]?(?P<yy>\d{2})\.(?P<mm>\d{2})\.(?P<dd>\d{2})")
_MD          = re.compile(r"(?P<mm>\d{2})\.(?P<dd>\d{2})")

def _to_year(yy: int) -> int: return 2000 + yy

def _parse_one_date(token: str, base_year: int) -> str | None:
    """
    "01.20.(월)" / "'24.11.05.(화)" / "02.27(목)" / "01.02" -> "YYYY-MM-DD"
    """
    if not token:
        return None
    s = token.strip()

    m = _YEAR_2DIGIT.search(s)
    if m:
        yy = int(m.group("yy")); mm = int(m.group("mm")); dd = int(m.group("dd"))
        return f"{_to_year(yy):04d}-{mm:02d}-{dd:02d}"

    m = _MD.search(s)
    if m:
        mm = int(m.group("mm")); dd = int(m.group("dd"))
        return f"{base_year:04d}-{mm:02d}-{dd:02d}"

    return None


def _parse_md_range(s: str, base_year: int) -> tuple[str | None, str | None]:
    """
    "01.20 ~ 02.07" / "'24.12.23 ~ `25.01.01" -> (YYYY-MM-DD, YYYY-MM-DD)
    """
    if not s:
        return (None, None)

    parts = re.split(r"[~∼\-]+", _clean(s))
    if len(parts) < 2:
        d = _parse_one_date(parts[0], base_year)
        return (d, d)

    left_raw, right_raw = parts[0].strip(), parts[1].strip()

    left_yeared  = _YEAR_2DIGIT.search(left_raw)
    right_yeared = _YEAR_2DIGIT.search(right_raw)

    if left_yeared:
        yy = int(left_yeared.group("yy")); y = _to_year(yy)
        left  = _parse_one_date(left_raw,  y)
        right = _parse_one_date(right_raw, y)
        return (left, right)

    if right_yeared:
        yy = int(right_yeared.group("yy")); ry = _to_year(yy)
        left_tmp = _parse_one_date(left_raw, ry)
        right    = _parse_one_date(right_raw, ry)
        if left_tmp and right:
            lm, rm = int(left_tmp[5:7]), int(right[5:7])
            if lm > rm:  # 12월 ~ 다음해 01월
                ly = int(left_tmp[:4]) - 1
                left = f"{ly:04d}{left_tmp[4:]}"
            else:
                left = left_tmp
        else:
            left = left_tmp
        return (left, right)

    left  = _parse_one_date(left_raw,  base_year)
    right = _parse_one_date(right_raw, base_year)
    try:
        if left and right:
            lm, rm = int(left[5:7]), int(right[5:7])
            if rm < lm:
                ry = int(right[:4]) + 1
                right = f"{ry:04d}{right[4:]}"
    except Exception:
        pass
    return (left, right)

def _split_time_range(s: str):
    if not s:
        return (None, None)
    flat = _clean(s)
    m = re.search(r"(\d{1,2}:\d{2}).*?(\d{1,2}:\d{2})", flat)
    return (m.group(1), m.group(2)) if m else (None, None)

def _minutes_ko(s: str | None):
    m = re.search(r"(\d+)\s*분", s or "")
    return int(m.group(1)) if m else None
