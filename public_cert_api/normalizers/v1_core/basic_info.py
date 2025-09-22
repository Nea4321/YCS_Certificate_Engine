# -*- coding: utf-8 -*-
"""
basic_info.py — Q-Net '기본정보' 탭 파서 (리팩토링版)
- 라벨 변형/혼입 대비: 라인기반 → 블랍기반 2단계
- duties/outlook 동일한 라벨 컷/침투 컷 + 문장성 검사
- 실시기관: URL/기관명 보강, HRDK 폴백
- 통계: 식별은 loader에서 수행, 여기서는 디듀프/파서 콜백만 유지
"""
import os, re, hashlib
from typing import Dict, List, Tuple, Optional

from ..utils.text import clean, first_long
from ..utils.regexes import LAW, norm_date
from .support.basic_info_config_loader import extract_basic_sections, load_basic_info_cfg

LABELS: Dict[str, List[str]] = {
    "overview":  [r"개\s*요"],
    "history":   [r"변천\s*과정", r"변천과정"],
    "duties":    [r"수행\s*직무", r"주요\s*업무", r"직무\s*내용", r"하는\s*일", r"업무\s*내용"],
    "agency":    [r"실시\s*기관(?:명)?", r"시행\s*기관", r"주관\s*기관"],
    "ministry":  [r"소관\s*부처(?:명)?", r"담당\s*부처"],
    "outlook":   [r"진로\s*및\s*전망", r"진로및전망", r"취업\s*및\s*진로", r"전망"],
    "stats":     [r"최근\s*5\s*년\s*간\s*통계\s*자료", r"최근\s*5년간\s*통계\s*자료", r"통계\s*자료"],
    "byitem":    [r"종목별\s*검정\s*현황", r"종목별\s*검정현황"],
}

DATE_RX = re.compile(r"\b\d{4}\.\s*\d{1,2}\.\s*\d{1,2}\b")
_STOP_TK = {"전화","연락처","문의","홈페이지"}

MIN_WHITELIST = [
    "기획재정부","교육부","과학기술정보통신부","외교부","통일부","법무부","행정안전부","문화체육관광부",
    "농림축산식품부","산업통상자원부","보건복지부","환경부","고용노동부","여성가족부","국토교통부",
    "해양수산부","중소벤처기업부","방송통신위원회","공정거래위원회","국민권익위원회",
    "식품의약품안전처","관세청","통계청","조달청","병무청","산림청","해양경찰청",
]
MIN_RX  = re.compile("(" + "|".join(map(re.escape, MIN_WHITELIST)) + r")")

def _labels_union(parts: List[str]) -> str:
    return "(?:" + "|".join(parts) + ")"

def _header_line_rx(token: str) -> re.Pattern:
    return re.compile(
        rf"^(?:[^\S\r\n]*[•·○□■▶▷\-\–\—]\s*)?(?:[가-힣A-Za-z0-9\s·\-\(\)]*\s*)?{token}\b",
        re.I,
    )

def _cut_by_overview_markers(text: str) -> str:
    C = load_basic_info_cfg()
    pat = r"(?:%s)" % "|".join(map(re.escape, C["overview_cuts"]))
    return re.split(pat, text)[0]

INTERNAL_LABEL_RX = re.compile(_labels_union([t for v in LABELS.values() for t in v]), re.I)
ORG_SUFFIX_RX     = re.compile(r"(부|처|청|청장|원|공단|협회|센터|위원회|재단|진흥원|교육원|연구원)$")

def _norm_line(s: str) -> str:
    s = clean(s or "")
    s = re.sub(r"\(\s*\d{2,4}-\d{3,4}-\d{3,4}\s*\)", "", s)
    s = re.sub(r"[•·○□■▶▷\-\–\—\:\|/]+", " ", s)
    s = s.replace(",", " ")
    s = re.sub(r"\s+", " ", s).strip()
    return s

def _raw_blob(paras: List[str]) -> str:
    return "\n".join(p for p in (paras or []) if p)

def _trim_internal_labels(text: str) -> str:
    if not text: return text
    m = INTERNAL_LABEL_RX.search(text)
    return text[:m.start()].strip() if m else text

def _build_header_hits(paras: List[str]) -> Tuple[Dict[str, List[int]], List[str], List[str]]:
    hits = {k: [] for k in LABELS.keys()}
    lines_raw = [p for p in (paras or []) if p]
    lines_norm = [_norm_line(p) for p in lines_raw]
    for i, ln in enumerate(lines_norm):
        for key, tokens in LABELS.items():
            for t in tokens:
                if _header_line_rx(t).search(ln):
                    hits[key].append(i); break
    return hits, lines_raw, lines_norm

def _grab_section_lines(hits: Dict[str, List[int]], lines_raw: List[str], lines_norm: List[str], key: str) -> Optional[str]:
    idxs = hits.get(key) or []
    if not idxs: return None
    i = idxs[0]
    tail = None
    for t in LABELS[key]:
        m = _header_line_rx(t).search(lines_norm[i])
        if m:
            tail = lines_norm[i][m.end():].strip(); break
    buf = []
    if tail: buf.append(tail)
    for j in range(i + 1, len(lines_norm)):
        if any(_header_line_rx(t).search(lines_norm[j]) for t in [tt for v in LABELS.values() for tt in v]):
            break
        if lines_norm[j]:
            buf.append(lines_norm[j])
    out = " ".join(buf).strip()
    return out or None

def _slice_blob(blob: str, head_tokens: List[str]) -> Optional[str]:
    if not blob: return None
    head = _labels_union(head_tokens)
    nxt  = _labels_union([t for v in LABELS.values() for t in v])
    rx   = re.compile(head + r"\s*[:：\-–—]?\s*(.+?)\s*(?=" + nxt + r"|$)", re.S | re.I)
    m = rx.search(blob)
    return m.group(1).strip() if m else None

def _extract_agency(blob: str, lines: List[str]) -> Dict[str, Optional[str]]:
    out = {"홈페이지": None, "기관명": None}
    seg = _slice_blob(blob, LABELS["agency"])
    area = seg if seg else "\n".join(lines)

    m_url = re.search(r"(?:홈페이지|URL)\s*[:：]?\s*(https?://[^\s)\"'>]+|\bwww\.[^\s)\"'>]+)", area)
    if m_url:
        u = m_url.group(1);  out["홈페이지"] = (u if u.startswith("http") else "http://" + u)
    else:
        mu = re.search(r"https?://[^\s)\"'>]+|\bwww\.[^\s)\"'>]+", blob)
        if mu:
            u = mu.group(0);  out["홈페이지"] = (u if u.startswith("http") else "http://" + u)

    m_nm = re.search(r"(기관명|실시기관명)\s*[:：]?\s*([^\n]+)", area)
    if m_nm:
        out["기관명"] = _norm_line(m_nm.group(2))
    else:
        toks = [w for w in _norm_line(area).split() if 2 <= len(w) <= 30]
        cands = [w for w in toks if ORG_SUFFIX_RX.search(w)]
        if cands:
            out["기관명"] = max(cands, key=len)

    if not out["기관명"] and "한국산업인력공단" in " ".join(_norm_line(p) for p in lines):
        out["기관명"] = "한국산업인력공단"
    return out

def _parse_history_tables_fallback(tables: List[Dict]) -> List[Dict]:
    out = []
    for tb in tables or []:
        rows = tb.get("rows") or []
        if len(rows) < 2: continue
        top = [clean(c) for c in rows[0]]
        bot = [clean(c) for c in rows[1]]
        if not any("대통령령" in x or "현재" in x or re.search(r"\d{4}\.", x) for x in top):
            continue
        mx = max(len(top), len(bot))
        for i in range(mx):
            t0 = clean(top[i] if i < len(top) else "")
            b0 = clean(bot[i] if i < len(bot) else "")
            d  = norm_date(t0)
            m  = re.search(r"(?:법률|대통령령)\s*제\s*(\d+)\s*호", t0)
            law = (f"제{m.group(1)}호") if m else ("현재" if "현재" in t0 else None)
            if d or law or b0:
                out.append({"date": d, "law": law, "title": (b0 or None), "raw_top": t0})
    return out

def _parse_history_text_fallback(lines: List[str]) -> List[Dict]:
    out=[]
    for tt in lines or []:
        raw = _norm_line(tt)
        if not raw: continue
        if DATE_RX.search(raw) or "현재" in raw:
            d  = norm_date(raw)
            m  = re.search(r"(?:법률|대통령령)\s*제\s*(\d+)\s*호", raw)
            law = (f"제{m.group(1)}호") if m else ("현재" if "현재" in raw else None)
            out.append({"date": d, "law": law, "title": None, "raw": raw})
    return out

def _dedup_tables(tables: List[Dict] | None) -> List[Dict]:
    if not tables: return []
    seen, out = set(), []
    for tb in tables:
        rows = tb.get("rows") or []
        blob = "\n".join(",".join(str(x) if x is not None else "" for x in r) for r in rows)
        h = hashlib.md5(blob.encode("utf-8")).hexdigest()
        if h in seen:  continue
        seen.add(h);  out.append(tb)
    return out

def split_sections(paras: List[str], tables: List[Dict] | None = None) -> Dict:
    _ = load_basic_info_cfg()
    tables = tables or []
    blob = _raw_blob(paras)

    hits, lines_raw, lines_norm = _build_header_hits(paras)

    # 1) 개요
    overview = _grab_section_lines(hits, lines_raw, lines_norm, "overview") \
               or _slice_blob(blob, LABELS["overview"]) \
               or _norm_line(re.sub(r"^(?:기본정보\s*)*(?:개요\s*)*", "", (first_long(paras) or "")))
    if overview:
        dm = DATE_RX.search(overview)
        if dm: overview = overview[:dm.start()].strip()
        overview = _trim_internal_labels(overview)

    # 2) 실시기관
    org = _extract_agency(blob, paras)

    # 3) 보조 파서
    extra = extract_basic_sections(paras, tables)

    # 4) 소관부처(세이프가드로 정확 명칭만 유지)
    ministry = extra.get("ministry")
    if ministry:
        m = MIN_RX.search(ministry)
        ministry = m.group(1) if m else None

    # 5) 변천과정
    history_paras = extra.get("history_paras") or []

    # 6) 수행직무 / 7) 진로및전망
    duties  = extra.get("duties")
    outlook = extra.get("outlook")

    # 제목만 들어온 오인식 컷
    def _is_title_like(s: str) -> bool:
        s = _norm_line(s or "")
        return bool(re.fullmatch(r"(\d+급\s*[가-힣A-Za-z]+|[가-힣A-Za-z]{2,10})", s))

    if duties and _is_title_like(duties):   duties  = None
    if outlook and _is_title_like(outlook): outlook = None

    # 8) 통계표(디듀프만)
    stats_tables = _dedup_tables(extra.get("stats_tables"))

    # 9) 폴백 콜러블
    parse_history_tables = extra.get("parse_history_tables") or _parse_history_tables_fallback
    parse_history_text   = extra.get("parse_history_text")   or _parse_history_text_fallback

    # 10) 통계 파서 콜러블
    def parse_stats_tables(tables_: List[Dict]) -> List[Dict]:
        try:
            from ..adapters import parse_basicinfo_stats_table as _run
        except Exception:
            return []
        return _run(tables_ or [])

    if os.getenv("BASIC_INFO_DEBUG"):
        print("[split] overview:", (overview or "")[:120])
        print("[split] org:", org)
        print("[split] ministry:", ministry)
        print("[split] duties:", (duties or "")[:120])
        print("[split] outlook:", (outlook or "")[:120])
        print("[split] history_paras:", len(history_paras), "stats:", len(stats_tables))

    return {
        "overview": overview,
        "org": org,
        "parse_history_tables": parse_history_tables,
        "parse_history_text":  parse_history_text,
        "parse_stats_tables":  parse_stats_tables,
        "history_paras": history_paras,
        "duties": duties,
        "outlook": outlook,
        "ministry": ministry,
        "stats_tables": stats_tables,
    }
