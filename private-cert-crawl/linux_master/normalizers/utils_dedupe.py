import re
from .utils_text import _tuple_images

_PERCENT_PAIR = re.compile(r"\s*([^(),%]+?)\s*\(\s*(\d+(?:\.\d+)?)\s*%\s*\)")

def _parse_weights(text: str | None):
    if not text: return []
    pairs = _PERCENT_PAIR.findall(text)
    out = []
    for name, pct in pairs:
        name = name.strip(" ,;/·ㆍ-–—")
        try:
            val = float(pct)
            if val.is_integer():
                val = int(val)
        except Exception:
            continue
        if name:
            out.append({"항목": name, "비율": val})
    return out

def _looks_like_coverage(d: dict) -> bool:
    if "평가범위" in d and isinstance(d["평가범위"], str):
        return len(_PERCENT_PAIR.findall(d["평가범위"])) >= 1
    # 기타 단서
    joined = " ".join([str(v) for v in d.values() if isinstance(v, str)])
    return len(_PERCENT_PAIR.findall(joined)) >= 2

def _signature_syllabus(item: dict) -> tuple:
   return (
        item.get("등급") or "",
        item.get("과목") or "",
        item.get("검정항목") or "",
        item.get("검정내용") or "",
        item.get("상세검정내용") or "",
        tuple(sorted(_tuple_images(item.get("images")))),
    )
def _signature_coverage(item: dict) -> tuple:
    pw = item.get("parsedWeights") or []
    pw_sig = tuple(sorted(
        (str(p.get("항목","")), str(p.get("비율","")))
        for p in pw if isinstance(p, dict)
    ))
    return (
        item.get("종목") or "",
        item.get("등급") or "",
        item.get("구분") or "",
        item.get("평가범위") or "",
        pw_sig,
        tuple(sorted(_tuple_images(item.get("images")))),
    )

def _dedupe_by_signature(items: list, sig_fn):
    seen, out = set(), []
    for it in items:
        if not isinstance(it, dict): 
            continue
        sig = sig_fn(it)
        if sig in seen:
            continue
        seen.add(sig)
        out.append(it)
    return out

