# -*- coding: utf-8 -*-
"""
basic_info.py — Q-Net '기본정보' 탭 파서 (리팩토링)
- 헤더 감지: 라인 기반 + 블랍 기반 2단계
- 라벨 소스: 파이썬 상수 + YAML 구성 모두 병합
- duties/outlook: 라벨 침투 컷, 제목성 문장 컷 완화
- 실시기관: URL/기관명 보강 + HRDK 폴백
- 통계: 디듀프 + 어댑터 콜백 래퍼
"""

from __future__ import annotations

import os, re, hashlib
from typing import Dict, List, Tuple, Optional

from ..utils.text import clean, first_long
from ..utils.regexes import norm_date
from .support.basic_info_config_loader import extract_basic_sections, load_basic_info_cfg

# ── 기본 라벨(파이썬 상수) ────────────────────────────────────────────────────
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

MIN_WHITELIST = [
    "기획재정부","교육부","과학기술정보통신부","외교부","통일부","법무부","행정안전부","문화체육관광부",
    "농림축산식품부","산업통상자원부","보건복지부","환경부","고용노동부","여성가족부","국토교통부",
    "해양수산부","중소벤처기업부","방송통신위원회","공정거래위원회","국민권익위원회",
    "식품의약품안전처","관세청","통계청","조달청","병무청","산림청","해양경찰청",
]
MIN_RX = re.compile("(" + "|".join(map(re.escape, MIN_WHITELIST)) + r")")

ORG_SUFFIX_RX = re.compile(r"(부|처|청|청장|원|공단|협회|센터|위원회|재단|진흥원|교육원|연구원)$")

# ── 유틸 ─────────────────────────────────────────────────────────────────────
BULLETS_RX = re.compile(r"^[\u2022\u00B7\-\•\·\※\*]+\s*")  # •, ·, -, ※, *

def norm_title(s: str) -> str:
    """헤더 후보 텍스트 정규화(앞 불릿/끝 콜론/여백)."""
    s = clean(s)
    s = BULLETS_RX.sub("", s)
    s = re.sub(r"\s*[:：]\s*$", "", s)
    s = re.sub(r"\s+", " ", s)
    return s

def _norm_line(s: str) -> str:
    """일반 본문 라인 정규화."""
    s = clean(s or "")
    s = re.sub(r"\(\s*\d{2,4}-\d{3,4}-\d{3,4}\s*\)", "", s)  # 전화번호 괄호 제거
    s = re.sub(r"[•·○□■▶▷\-\–\—\:\|/]+", " ", s)
    s = s.replace(",", " ")
    s = re.sub(r"\s+", " ", s).strip()
    return s

def _raw_blob(paras: List[str]) -> str:
    return "\n".join(p for p in (paras or []) if p)

def _labels_union(parts: List[str]) -> str:
    return "(?:" + "|".join(parts) + ")"

def _header_line_rx(token: str) -> re.Pattern:
    """헤더 라인 패턴: 불릿/장식 + 임의 문자열 + 토큰."""
    return re.compile(
        rf"^(?:[^\S\r\n]*[•·○□■▶▷\-\–\—]\s*)?(?:[가-힣A-Za-z0-9\s·\-\(\)]*\s*)?{token}\b",
        re.I,
    )

def _collect_all_label_tokens(cfg: dict) -> List[str]:
    """YAML 구성에서 headers/end_markers/cut_markers/table_caption_contains 추출."""
    toks: List[str] = []
    for _, v in (cfg or {}).items():
        if isinstance(v, dict):
            for kk in ("headers", "end_markers", "cut_markers", "table_caption_contains"):
                vv = v.get(kk)
                if isinstance(vv, list):
                    toks.extend([t for t in vv if isinstance(t, str) and t.strip()])
    return toks

def _compile_internal_label_rx(py_labels: Dict[str, List[str]], cfg: dict) -> re.Pattern:
    """본문 안에 다른 섹션 라벨이 끼어드는 걸 잘라내기 위한 정규식(긴 것 우선)."""
    toks = [t for v in py_labels.values() for t in v]
    toks += _collect_all_label_tokens(cfg)
    uniq = sorted(set(toks), key=lambda s: len(s), reverse=True)
    union = "(?:" + "|".join(uniq) + ")"
    return re.compile(union, re.I)


# ── 헤더 감지 / 섹션 추출 ─────────────────────────────────────────────────────
def _build_header_hits(paras: List[str], cfg: dict) -> Tuple[Dict[str, List[int]], List[str], List[str]]:
    """라인 단위에서 헤더 인덱스 후보를 수집."""
    hits = {k: [] for k in LABELS.keys()}
    lines_raw = [p for p in (paras or []) if p]
    # 1차: 제목 정규화 → 2차: 라인 정규화
    lines_t = [norm_title(p) for p in lines_raw]
    lines_norm = [_norm_line(p) for p in lines_t]

    for i, ln in enumerate(lines_norm):
        for key, tokens in LABELS.items():
            for t in tokens:
                if _header_line_rx(t).search(ln):
                    hits[key].append(i)
                    break
    return hits, lines_raw, lines_norm

def _grab_section_lines(hits: Dict[str, List[int]], lines_norm: List[str], key: str) -> Optional[str]:
    """헤더 라인부터 다음 헤더 전까지의 텍스트를 이어붙여 섹션 본문을 만든다."""
    idxs = hits.get(key) or []
    if not idxs:
        return None
    i = idxs[0]

    # 헤더 라인의 꼬리 내용(같은 줄 본문) 확보
    tail = None
    for t in LABELS[key]:
        m = _header_line_rx(t).search(lines_norm[i])
        if m:
            tail = lines_norm[i][m.end():].strip()
            break

    buf: List[str] = []
    if tail:
        buf.append(tail)

    # 다음 헤더 전까지 수집
    all_tokens = [tt for v in LABELS.values() for tt in v]
    for j in range(i + 1, len(lines_norm)):
        if any(_header_line_rx(t).search(lines_norm[j]) for t in all_tokens):
            break
        if lines_norm[j]:
            buf.append(lines_norm[j])

    out = " ".join(buf).strip()
    return out or None

def _slice_blob(blob: str, head_tokens: List[str], all_tokens: List[str]) -> Optional[str]:
    """블랍 기반: 헤더 토큰 ~ 다음 헤더 토큰 전까지 슬라이스."""
    if not blob:
        return None
    head = _labels_union(head_tokens)
    nxt = _labels_union(all_tokens)
    rx = re.compile(head + r"\s*[:：\-–—]?\s*(.+?)\s*(?=" + nxt + r"|$)", re.S | re.I)
    m = rx.search(blob)
    return m.group(1).strip() if m else None

# ── 실시기관 ─────────────────────────────────────────────────────────────────
def _extract_agency(blob: str, lines: List[str], head_tokens: List[str], all_tokens: List[str]) -> Dict[str, Optional[str]]:
    out = {"홈페이지": None, "기관명": None}
    seg = _slice_blob(blob, head_tokens, all_tokens)
    area = seg if seg else "\n".join(lines)

    m_url = re.search(r"(?:홈페이지|URL)\s*[:：]?\s*(https?://[^\s)\"'>]+|\bwww\.[^\s)\"'>]+)", area)
    if m_url:
        u = m_url.group(1)
        out["홈페이지"] = (u if u.startswith("http") else "http://" + u)
    else:
        mu = re.search(r"https?://[^\s)\"'>]+|\bwww\.[^\s)\"'>]+", blob)
        if mu:
            u = mu.group(0)
            out["홈페이지"] = (u if u.startswith("http") else "http://" + u)

    m_nm = re.search(r"(기관명|실시기관명)\s*[:：]?\s*([^\n]+)", area)
    if m_nm:
        out["기관명"] = _norm_line(m_nm.group(2))
    else:
        toks = [w for w in _norm_line(area).split() if 2 <= len(w) <= 30]
        cands = [w for w in toks if ORG_SUFFIX_RX.search(w)]
        if cands:
            out["기관명"] = max(cands, key=len)

    # 화면 어딘가에 HRDK 언급되면 폴백
    if not out["기관명"] and "한국산업인력공단" in " ".join(_norm_line(p) for p in lines):
        out["기관명"] = "한국산업인력공단"

    return out

# ── 변천/통계 폴백 ───────────────────────────────────────────────────────────
def _parse_history_tables_fallback(tables: List[Dict]) -> List[Dict]:
    out: List[Dict] = []
    for tb in tables or []:
        rows = tb.get("rows") or []
        if len(rows) < 2:
            continue
        top = [clean(c) for c in rows[0]]
        bot = [clean(c) for c in rows[1]]

        if not any("대통령령" in x or "현재" in x or re.search(r"\d{4}\.", x) for x in top):
            continue

        mx = max(len(top), len(bot))
        for i in range(mx):
            t0 = clean(top[i] if i < len(top) else "")
            b0 = clean(bot[i] if i < len(bot) else "")
            d = norm_date(t0)
            m = re.search(r"(?:법률|대통령령)\s*제\s*(\d+)\s*호", t0)
            law = (f"제{m.group(1)}호") if m else ("현재" if "현재" in t0 else None)
            if d or law or b0:
                out.append({"date": d, "law": law, "title": (b0 or None), "raw_top": t0})
    return out

def _parse_history_text_fallback(lines: List[str]) -> List[Dict]:
    out: List[Dict] = []
    for tt in lines or []:
        raw = _norm_line(tt)
        if not raw:
            continue
        if DATE_RX.search(raw) or "현재" in raw:
            d = norm_date(raw)
            m = re.search(r"(?:법률|대통령령)\s*제\s*(\d+)\s*호", raw)
            law = (f"제{m.group(1)}호") if m else ("현재" if "현재" in raw else None)
            out.append({"date": d, "law": law, "title": None, "raw": raw})
    return out

def _dedup_tables(tables: List[Dict] | None) -> List[Dict]:
    if not tables:
        return []
    seen, out = set(), []
    for tb in tables:
        rows = tb.get("rows") or []
        blob = "\n".join(",".join(str(x) if x is not None else "" for x in r) for r in rows)
        h = hashlib.md5(blob.encode("utf-8")).hexdigest()
        if h in seen:
            continue
        seen.add(h)
        out.append(tb)
    return out

# ── 메인 엔트리 ──────────────────────────────────────────────────────────────
def split_sections(paras: List[str], tables: List[Dict] | None = None , html: str | None = None) -> Dict:
    if html:
        from .support.basic_info_config_loader import augment_paras_with_virtual_sections
        paras = augment_paras_with_virtual_sections(paras, html)
    
    cfg = load_basic_info_cfg() or {}
    tables = tables or []

    internal_label_rx = _compile_internal_label_rx(LABELS, cfg)

    blob = _raw_blob(paras)
    hits, _lines_raw, lines_norm = _build_header_hits(paras, cfg)
    all_tokens = [tt for v in LABELS.values() for tt in v]

    # 1) 개요 (동일)
    overview = (
        _grab_section_lines(hits, lines_norm, "overview")
        or _slice_blob(blob, LABELS["overview"], all_tokens)
        or _norm_line(re.sub(r"^(?:기본정보\s*)*(?:개요\s*)*", "", (first_long(paras) or "")))
    )
    if overview:
        cuts = (cfg.get("overview_cuts") or [])
        if cuts:
           cut_rx = re.compile("|".join(map(re.escape, cuts)))
           m = cut_rx.search(overview)
           if m:
              overview = overview[:m.start()].strip()

    # 2) 실시기관
    org = _extract_agency(blob, paras, LABELS["agency"], all_tokens)

    # 3) 보조 파서 (YAML)
    extra = extract_basic_sections(paras, tables)

    # 4) 소관부처
    ministry = extra.get("ministry")
    if ministry:
        m = MIN_RX.search(ministry)
        ministry = m.group(1) if m else None

    # 5) 변천
    history_paras = extra.get("history_paras") or []

    # 6) duties / 7) outlook  ←★ 로컬 탐지 우선 + extra와 병합
    local_duties  = _grab_section_lines(hits, lines_norm, "duties") \
                    or _slice_blob(blob, LABELS["duties"], all_tokens)
    local_outlook = _grab_section_lines(hits, lines_norm, "outlook") \
                    or _slice_blob(blob, LABELS["outlook"], all_tokens)

    duties_from_extra  = extra.get("duties")
    outlook_from_extra = extra.get("outlook")

    def _better(a: str|None, b: str|None) -> str|None:
        def score(s: str|None) -> int:
            if not s: return -1
            ss = _norm_line(s)   # ← 여기!  _trim_internal_labels(...) 빼기
            pts = len(ss)
            if re.search(r"(한다|하며|하고|하는|되며|되어|수행)", ss): pts += 200
            if re.search(r"(을|를|에|에서|으로|와|과|및)\b", ss):   pts += 100
            return pts
        return a if score(a) >= score(b) else b

    duties  = _better(local_duties,  duties_from_extra)
    outlook = _better(local_outlook, outlook_from_extra)

    # 제목성 과잉 컷(완화 버전)
    def _is_title_like(s: str) -> bool:
        ss = _norm_line(s or "")
        if len(ss) <= 3: return True
        if re.search(r"[\.!?]|(은|는|이|가|을|를|에|에서|으로|와|과)\b", ss): return False
        return bool(re.fullmatch(r"\d+\s*급\s*[가-힣A-Za-z]+", ss))
    if duties and _is_title_like(duties):   duties  = None
    if outlook and _is_title_like(outlook): outlook = None

    # 8) 통계
    stats_tables = _dedup_tables(extra.get("stats_tables"))

    # 9) 콜백
    parse_history_tables = extra.get("parse_history_tables") or _parse_history_tables_fallback
    parse_history_text   = extra.get("parse_history_text")   or _parse_history_text_fallback

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
