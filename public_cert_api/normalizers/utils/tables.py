from .text import clean, norm_for_cmp
import re

def table_sig(rows: list[list[str]], top=3) -> str:
    head = [" ".join(rows[i]) if i < len(rows) else "" for i in range(min(top, len(rows)))]
    return " | ".join(norm_for_cmp(" ".join(head)))

def to_int(s: str | None) -> int | None:
    if not s: return None
    v = re.sub(r"[^\d]", "", s)
    return int(v) if v else None
