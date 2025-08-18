import re

def _clean(s: str | None) -> str:
    return re.sub(r"\s+", " ", s or "").strip()

def _as_list(x):
    if x is None: return []
    if isinstance(x, list): return x
    if isinstance(x, dict): return [x]
    return []

def _is_nonempty(x): return x not in (None, "", [], {})

def _coerce_images(v) -> list[str]:
    if v is None: return []
    if isinstance(v, str):
        v = v.strip()
        return [v] if v else []
    if isinstance(v, list):
        out = []
        for it in v:
            if isinstance(it, str) and it.strip():
                out.append(it.strip())
        return out
    return []

def _tuple_images(v) -> tuple[str, ...]:
    if not v: return ()
    if isinstance(v, list):
        return tuple([s.strip() for s in v if isinstance(s, str) and s.strip()])
    if isinstance(v, str):
        s = v.strip()
        return (s,) if s else ()
    return ()


def _prune(obj):
    """재귀적으로 None/''/[]/{ } 제거."""
    if isinstance(obj, dict):
        cleaned = {}
        for k, v in obj.items():
            pv = _prune(v)
            if pv not in (None, "", [], {}):
                cleaned[k] = pv
        return cleaned
    if isinstance(obj, list):
        arr = [_prune(v) for v in obj]
        return [v for v in arr if v not in (None, "", [], {})]
    return obj

