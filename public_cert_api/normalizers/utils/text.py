import re, unicodedata

WS = re.compile(r"\s+")
def clean(s: str | None) -> str:
    return WS.sub(" ", (s or "").strip())

def norm_for_cmp(s: str) -> str:
    s = unicodedata.normalize("NFKC", s or "")
    s = re.sub(r"\s+", " ", s).strip()
    return re.sub(r"[\d,%.~\-:/()]+", "#", s)

def dedupe_keep_order(lines: list[str]) -> list[str]:
    seen, out = set(), []
    for t in lines or []:
        key = norm_for_cmp(t)
        if key and key not in seen:
            seen.add(key); out.append(clean(t))
    return out

def first_long(paras: list[str], minlen=20) -> str | None:
    for t in paras or []:
        tt = clean(t)
        if len(tt) >= minlen: return tt
    return clean(paras[0]) if paras else None

def merge_links(*lists):
    out, seen = [], set()
    for lst in lists:
        for a in lst or []:
            text = clean(a.get("text")); href = clean(a.get("href"))
            key = (text, href)
            if href and key not in seen:
                seen.add(key); out.append({"text": text, "href": href})
    return out
