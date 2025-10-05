# -*- coding: utf-8 -*-
"""
basic_info_config_loader (refactored + debug-ready)

CHANGES
- iframe/title + textarea 가상 섹션 주입 로직 유지, _split_to_paras 강화
- '진로및전망' 추출 시 통계/표 신호에서 즉시 자르지 않고 문장 종결(., !, ?, …, '다', '요')까지 수습 후 flush
- 섹션 전환 시 flush 및 cut_pending 초기화 보장
- noise 라인은 '표 시작' 신호가 아님 → cut_pending 건드리지 않음
- 루프 종료 시 무조건 flush
- 통계 헤더(stats_hdr)만 예외 처리하여 '진로및전망' 문장 종결까지 기다린 뒤 마무리
- 전반적인 가독성/함수 분리 및 타입힌트 추가
- DEBUG: 주입 성공/실패, 섹션/표 감지 현황을 표준 출력에 자세히 남김
"""

from __future__ import annotations
import os, re, yaml
from pathlib import Path
from typing import List, Dict, Any, Optional, Tuple
from bs4 import BeautifulSoup
from bs4.element import Tag
from ...utils.text import clean

# ──────────────────────────────────────────────────────────────────────────────
# HTML → 문단
# ──────────────────────────────────────────────────────────────────────────────
def _split_to_paras(txt: str) -> List[str]:
    """HTML 혼합 텍스트를 라인 단위 문단 배열로 변환."""
    txt = (txt or "").replace("\r\n", "\n")
    txt = re.sub(r"</p\s*>", "\n", txt, flags=re.I)
    txt = re.sub(r"<br\s*/?>", "\n", txt, flags=re.I)
    txt = re.sub(r"<[^>]+>", " ", txt)  # 최소한의 태그 제거
    out: List[str] = []
    for raw in (txt.split("\n") if txt else []):
        t = re.sub(r"\s+", " ", raw).strip()
        if t:
            out.append(t)
    return out

# ──────────────────────────────────────────────────────────────────────────────
# Q-Net 특유: iframe ↔ textarea 매칭
# ──────────────────────────────────────────────────────────────────────────────
def _nearest_textarea_for(iframe: Tag) -> Optional[Tag]:
    if not isinstance(iframe, Tag):
        return None
    # contents_frame_N ↔ contents_text_N 직결 매칭
    if iframe.has_attr("id"):
        m = re.search(r"contents_frame_(\d+)", iframe["id"])
        if m:
            wanted = f"contents_text_{m.group(1)}"
            ta = iframe.find_next(lambda x: isinstance(x, Tag) and x.name == "textarea" and x.get("id") == wanted)
            if ta: return ta
            ta = iframe.find_previous(lambda x: isinstance(x, Tag) and x.name == "textarea" and x.get("id") == wanted)
            if ta: return ta
    # 근방 스캔
    walker = iframe
    for _ in range(40):
        walker = walker.next_element
        if not walker: break
        if isinstance(walker, Tag) and walker.name == "textarea" and (walker.get("id", "").startswith("contents_text_")):
            return walker
    walker = iframe
    for _ in range(40):
        walker = walker.previous_element
        if not walker: break
        if isinstance(walker, Tag) and walker.name == "textarea" and (walker.get("id", "").startswith("contents_text_")):
            return walker
    return None

def _label_from_title(title: str) -> Optional[str]:
    t = (title or "").replace(" ", "")
    if ("수행" in t and "직무" in t) or ("업무" in t and "내용" in t):
        return "수행직무"
    if ("진로" in t and "전망" in t) or ("취업" in t and "전망" in t) or ("취업" in t and "진로" in t):
        return "진로및전망"
    return None

def _guess_label_from_context(ta: Tag) -> Optional[str]:
    cand = []
    p = ta
    for _ in range(6):
        p = p.parent
        if not isinstance(p, Tag): break
        b = p.find("b")
        if b and b.get_text(strip=True):
            cand.append(b.get_text(strip=True)); break
    if not cand and isinstance(ta.previous_sibling, Tag):
        txt = ta.previous_sibling.get_text(strip=True) if hasattr(ta.previous_sibling, "get_text") else str(ta.previous_sibling)
        cand.append(txt)
    for c in cand:
        lab = _label_from_title(c)
        if lab: return lab
    return None

def augment_paras_with_virtual_sections(paras: List[str], html: str) -> List[str]:
    """
    - <iframe title=... id=contents_frame_N> + <textarea id=contents_text_N style="display:none">
    - 탐지되면 paras에 '가상 라벨 + 본문'을 문서 순서대로 주입
    - 같은 라벨이 이미 있으면 중복 삽입하지 않음
    """
    soup = BeautifulSoup(html or "", "html.parser")
    injections: List[Tuple[int, List[str]]] = []
    seen_label = set()

    def _add(pos: int, label: str, body_txt: str):
        if any(label in (p or "") for p in (paras or [])):
            return
        body_lines = _split_to_paras(body_txt)
        if not body_lines:
            return
        injections.append((pos, [label] + body_lines))
        seen_label.add(label)

    for idx, iframe in enumerate(soup.select("iframe[title]")):
        title = iframe.get("title", "")
        label = _label_from_title(title)
        if not label or label in seen_label:
            continue
        ta = _nearest_textarea_for(iframe)
        text = ta.get_text("", strip=False) if ta else ""
        if text:
            _add(idx, label, text)

    for idx, ta in enumerate(soup.select('textarea[id^="contents_text_"]')):
        if not isinstance(ta, Tag):
            continue
        label = _guess_label_from_context(ta)
        if not label or label in seen_label:
            continue
        text = ta.get_text("", strip=False)
        if text:
            _add(1000 + idx, label, text)

    for pos, block in sorted(injections, key=lambda x: x[0], reverse=True):
        for line in reversed(block):
            paras.insert(pos, line)
    return paras

# ──────────────────────────────────────────────────────────────────────────────
# 설정 로딩/정규식
# ──────────────────────────────────────────────────────────────────────────────
_CFG: Optional[Dict[str, Any]] = None
_BULLETS = "□■◦•\\-·"
_STRIP_HEAD       = r"[□■◦•\-\·\*\#\u3000\s]*"
_STRIP_HEAD_PLUS  = r"(?:[□■◦•\-\·\*\#]|ㅇ)\s*"

_VERB_RX        = re.compile(r"(한다|하며|하고|하는|되며|되어|수행|작성|신청|이행|분류|계산|심사|조사|관리|운영|대리|확인|지도|지원|제공)")
_SENTENCEISH_RX = re.compile(r"(을|를|에|에서|으로|과|와|및|도|등|하여|하고|하며)")

MIN_WHITELIST = [
    "기획재정부","교육부","과학기술정보통신부","외교부","통일부","법무부","행정안전부","문화체육관광부",
    "농림축산식품부","산업통상자원부","보건복지부","환경부","고용노동부","여성가족부","국토교통부",
    "해양수산부","중소벤처기업부","방송통신위원회","공정거래위원회","국민권익위원회",
    "식품의약품안전처","관세청","통계청","조달청","병무청","산림청","해양경찰청",
]
MIN_RX = re.compile("(" + "|".join(map(re.escape, MIN_WHITELIST)) + r")")

def _mk_header_regex(pats) -> re.Pattern:
    body = pats if isinstance(pats, str) else "|".join(f"(?:{p})" for p in pats)
    return re.compile(r"^\s*(?:[" + _BULLETS + r"]\s*)?(?:" + body + r")\s*[:：]?\s*$")

def load_basic_info_cfg() -> Dict[str, Any]:
    global _CFG
    if _CFG:
        return _CFG
    p = Path(__file__).resolve().parent.parent / "configs" / "basic_info_headers.yaml"
    with open(p, "r", encoding="utf-8") as f:
        y = yaml.safe_load(f)

    _CFG = {
        "duties_hdr":    _mk_header_regex(y["duties"]["headers"]),
        "duties_end":    re.compile("|".join(y["duties"]["end_markers"])),
        "duties_noise":  tuple(y["duties"]["noise"]),

        "history_hdr":   _mk_header_regex(y["history"]["headers"]),
        "history_end":   re.compile("|".join(y["history"]["end_markers"])),

        "ministry_hdr":  _mk_header_regex(y["ministry"]["headers"]),
        "ministry_end":  re.compile("|".join(
            y.get("ministry", {}).get("end_markers") or y["overview"]["cut_markers"]
        )),

        "stats_hdr":     _mk_header_regex(y["stats"]["headers"]),
        "stats_caption": tuple(y["stats"]["table_caption_contains"]),

        "outlook_hdr":   _mk_header_regex(y["outlook"]["headers"]),
        "outlook_end":   re.compile("|".join(y["outlook"]["end_markers"])),
        "outlook_noise": tuple(y["outlook"]["noise"]),

        "table_hints":   y.get("table_hints", {}),
        "overview_cuts": tuple(y["overview"]["cut_markers"]),
    }
    _CFG["_debug"] = bool(os.getenv("BASIC_INFO_DEBUG"))
    return _CFG

# ──────────────────────────────────────────────────────────────────────────────
# 섹션 슬라이서
# ──────────────────────────────────────────────────────────────────────────────
def _slice_section(paras: List[str], hdr: re.Pattern, end: re.Pattern) -> List[str]:
    ok, out = False, []
    for raw in paras or []:
        t = clean(raw)
        if not t:
            continue
        m = hdr.match(t)
        if not ok and m:
            ok = True
            tail = t[m.end():].lstrip("：: ").strip()
            if tail:
                out.append(tail)
            continue
        if ok:
            if end.search(t):
                break
            out.append(t)
    return out

def _slice_section_fuzzy(paras: List[str], hdr_pat: re.Pattern, end_pat: re.Pattern) -> List[str]:
    lines, grabbing = [], False
    body_pat = re.compile(hdr_pat.pattern[2:-2])  # ^...$ 제거한 바디
    for raw in paras or []:
        t = clean(raw)
        if not t:
            continue
        if not grabbing:
            m_full = hdr_pat.match(t)
            if m_full:
                grabbing = True
                tail = t[m_full.end():].lstrip("：: ").strip()
                if tail: lines.append(tail)
                continue
            m = body_pat.search(t)  # 같은 줄 내 변형
            if m:
                tail = t[m.end():].lstrip("：: ").strip()
                if tail: lines.append(tail)
                grabbing = True
                continue
        else:
            if end_pat.search(t):
                break
            lines.append(t)
    return lines

def _has_header(paras: List[str], hdr_pat: re.Pattern) -> bool:
    body_pat = re.compile(hdr_pat.pattern[2:-2])
    for raw in paras or []:
        t = clean(raw) or ""
        if hdr_pat.match(t): return True
        if body_pat.search(t): return True
    return False

# ──────────────────────────────────────────────────────────────────────────────
# 통계 표 시그널/정규화
# ──────────────────────────────────────────────────────────────────────────────
def _strong_stats_signature(tb) -> bool:
    rows = tb.get("rows") or []
    if not rows:
        return False
    flat = " ".join(" ".join(clean(c) for c in r if c) for r in rows)
    years   = re.findall(r"\b20(1\d|2\d)\b", flat)
    metrics = re.findall(r"(응시|합격|합격률|필기|실기|면접|1차|2차)", flat)
    first_row = " ".join(clean(c) for c in rows[0] if c)
    first_col = " ".join(clean(r[0]) for r in rows if r and r[0])
    labels = re.findall(r"(구분|1차|2차|필기|실기|면접|계|소계|급)", first_row + " " + first_col)
    return len(set(years)) >= 4 and len(metrics) >= 4 and len(labels) >= 1

def _weak_stats_signature(tb) -> bool:
    rows = tb.get("rows") or []
    if not rows:
        return False
    flat = " ".join(" ".join(clean(c) for c in r if c) for r in rows)
    years   = re.findall(r"\b20(1\d|2\d)\b", flat)
    metric1 = re.search(r"(응시|합격|합격률|필기|실기|면접|1차|2차)", flat)
    return len(set(years)) >= 2 and bool(metric1)

def _as_int(x: str) -> Optional[int]:
    try:
        return int(str(x).replace(",", "").strip())
    except Exception:
        return None

def _as_pct(x: str) -> Optional[str]:
    if x is None:
        return None
    s = str(x).strip()
    return s or None

def _looks_like_year_token(tok: str) -> bool:
    tok = (tok or "").strip()
    if tok.endswith("년"):
        tok = tok[:-1]
    return (tok.isdigit() and (1970 <= int(tok) <= 2100)) or ("~" in tok) or ("소 계" in tok) or ("소계" in tok)

def _parse_year_header_style(rows: List[List[str]]) -> Optional[List[dict]]:
    if len(rows) < 3: return None
    head1 = [c.strip() for c in rows[0]]
    if not any("연도" in c for c in head1): return None
    head2 = [c.strip() for c in rows[1]]
    has_metrics = (any("응시" in c for c in head2)
                   and any("합격" in c for c in head2)
                   and any("합격률" in c for c in head2))
    if not has_metrics: return None

    out = []
    for r in rows[2:]:
        if not r: continue
        y = r[0].strip()
        if not _looks_like_year_token(y): continue
        out.append({
            "연도": y.replace("년", "").strip(),
            "필기응시": _as_int(r[1]) if len(r) > 1 else None,
            "필기합격": _as_int(r[2]) if len(r) > 2 else None,
            "필기합격률": _as_pct(r[3]) if len(r) > 3 else None,
            "실기응시": _as_int(r[4]) if len(r) > 4 else None,
            "실기합격": _as_int(r[5]) if len(r) > 5 else None,
            "실기합격률": _as_pct(r[6]) if len(r) > 6 else None,
        })
    return out or None

def parse_stats_tables(stats_tables: List[dict]) -> List[dict]:
    out = []
    for tb in stats_tables or []:
        rows = tb.get("rows") or []
        recs = _parse_year_header_style(rows)
        if recs:
            out.append({
                "kind": "by_year",
                "records": recs,
                "source": {"caption": tb.get("caption"), "index": tb.get("index")},
            })
            continue
        out.append({
            "kind": "raw",
            "rows": rows,
            "source": {"caption": tb.get("caption"), "index": tb.get("index")},
        })
    return out

# ──────────────────────────────────────────────────────────────────────────────
# 진로/전망 텍스트 살균
# ──────────────────────────────────────────────────────────────────────────────
_URL_RX = re.compile(r"(https?://[^\s]+)")
_STATS_CUTOFF_RXS = (
    re.compile(r"종목별\s*검정현황"),
    re.compile(r"^\s*연도\s*$"),
    re.compile(r"(필기|실기)\s*(응시|합격|합격률)"),
)
_NUM_HEAVY_LINE = re.compile(r"^(?:\d{1,3}(?:,\d{3})*|\d{2,})\s*(?:\d{1,3}(?:,\d{3})*|\d{2,})")
_TERM_RX = re.compile(r"[\.。!?…]|[다요]\s*$")

def _sanitize_outlook(txt: str, max_chars: int = 4000, force_pending: bool = False) -> Optional[str]:
    if not txt:
        return None
    lines: List[str] = []
    pending_cut = force_pending

    for raw in (txt or "").splitlines():
        t = clean(raw) or ""
        if not t:
            continue
        if _URL_RX.search(t) or re.match(r"^(홈페이지|기관명|실시기관)\s*[:：]?", t):
            continue
        if any(rx.search(t) for rx in _STATS_CUTOFF_RXS) or \
           (_NUM_HEAVY_LINE.match(t) and any(k in t for k in ("응시","합격","합격률","필기","실기","연도"))):
            pending_cut = True
            continue

        lines.append(t)
        if pending_cut and _TERM_RX.search(t):
            break

    out = "\n".join(lines).strip()
    if not out:
        return None
    if len(out) > max_chars:
        out = out[:max_chars].rstrip() + "…"
    return out or None

# ──────────────────────────────────────────────────────────────────────────────
# 메인: 기본정보 섹션 추출
# ──────────────────────────────────────────────────────────────────────────────
def extract_basic_sections(paras: List[str], tables: List[dict]) -> Dict[str, Any]:
    C = load_basic_info_cfg()
    dbg = C.get("_debug")
    def _log(*a):
        if dbg: print("[basic-info]", *a)

    has_stats_hdr = _has_header(paras, C["stats_hdr"])
    stats_keywords = ("통계", "최근 5년", "최근5년", "통계자료")
    has_stats_kw = any(any(k in (clean(p) or "") for k in stats_keywords) for p in (paras or []))
    NORMALIZE_CAP_ONLY = ("종목별 검정현황", "종목별검정현황")

    # 변천과정
    history_paras = _slice_section(paras, C["history_hdr"], C["history_end"])
    if not history_paras:
        hist_inline = _slice_section_fuzzy(paras, C["history_hdr"], C["history_end"])
        if hist_inline:
            parts = []
            for s in hist_inline:
                s = clean(s)
                for ch in re.split(r"(?:\s*[ㅇ\-\•·]\s+)", s):
                    ch = clean(ch)
                    if ch: parts.append(ch)
            history_paras = parts

    # 소관부처 (느슨)
    def _pick_ministry_only(text: str) -> Optional[str]:
        m = MIN_RX.search(text or "")
        return m.group(1) if m else None

    ministry = None
    for raw in paras or []:
        t = clean(raw) or ""
        m = re.search(r"(소관\s*부처(?:명)?|담당\s*부처)\s*[:：]?\s*(.+)", t)
        if not m: continue
        cand = _pick_ministry_only(m.group(2))
        if cand: ministry = cand; break
    if not ministry:
        for i, raw in enumerate(paras or []):
            t = clean(raw) or ""
            if re.fullmatch(r"(?:[" + _BULLETS + r"]\s*)?(소관\s*부처(?:명)?|담당\s*부처)\s*[:：]?", t):
                for j in range(i+1, min(i+4, len(paras or []))):
                    cand = _pick_ministry_only(clean(paras[j]) or "")
                    if cand: ministry = cand; break
                if ministry: break
    if not ministry:
        for raw in paras or []:
            cand = _pick_ministry_only(clean(raw) or "")
            if cand: ministry = cand; break

    # 통계표 후보 수집
    stats_tables: List[dict] = []
    normalize_only_candidates: List[dict] = []
    _log("table_count:", len(tables or []))

    for tb in (tables or []):
        cap = (tb.get("caption") or "").strip()
        if not cap: continue
        if any(x in cap for x in NORMALIZE_CAP_ONLY):
            normalize_only_candidates.append(tb);  continue
        if any(key in cap for key in C["stats_caption"]):
            stats_tables.append(tb)

    if has_stats_hdr or has_stats_kw:
        for tb in (tables or []):
            if tb in stats_tables or tb in normalize_only_candidates: continue
            if _strong_stats_signature(tb): stats_tables.append(tb)

    if has_stats_hdr:
        for tb in (tables or []):
            if tb in stats_tables or tb in normalize_only_candidates: continue
            rows = tb.get("rows") or []
            if rows:
                head = " ".join(clean(c) for c in rows[0] if c is not None)
                has_year   = bool(re.search(r"\b20\d{2}\b", head))
                has_metric = any(k in head for k in ("응시","합격","합격률","1차","2차","필기","실기"))
                if ("구분" in head and has_year) or (has_year and has_metric):
                    stats_tables.append(tb);  continue
            if not rows: continue
            body_flat = " ".join(" ".join(clean(c) for c in r if c) for r in rows[:5])
            if re.search(r"\b20\d{2}\b.*\b20\d{2}\b", body_flat):
                stats_tables.append(tb);  continue
            flat = " ".join(" ".join(clean(c) for c in r if c) for r in rows)
            year_hits   = re.findall(r"\b20\d{2}\b", flat)
            metric_hits = re.findall(r"(응시|합격|합격률|필기|실기|1차|2차)", flat)
            if len(set(year_hits)) >= 3 and len(metric_hits) >= 3:
                stats_tables.append(tb);  continue

    if not stats_tables and (has_stats_hdr or has_stats_kw):
        weak = [tb for tb in (tables or []) if (tb not in normalize_only_candidates and _weak_stats_signature(tb))]
        if weak: stats_tables.append(weak[0])

    if not stats_tables and not normalize_only_candidates and len(tables or []) == 1:
        stats_tables.append(tables[0])

    if not stats_tables and not normalize_only_candidates:
        strongs = [tb for tb in (tables or []) if _strong_stats_signature(tb)]
        if strongs: stats_tables.append(strongs[0])

    # duties / outlook 추출
    def _join_block(lines: List[str]) -> Optional[str]:
        if not lines: return None
        txt = "\n".join(clean(re.sub(r"^" + _STRIP_HEAD_PLUS, "", s)) for s in lines if clean(s)).strip()
        return txt or None

    duties: Optional[str] = None
    outlook: Optional[str] = None
    mode: Optional[str] = None
    buf: List[str] = []
    cut_pending = False

    def _is_good_duties(txt: str) -> bool:
        s = clean(txt or "")
        return len(s) >= 12 and bool(_VERB_RX.search(s))

    def _is_good_outlook(txt: str) -> bool:
        s = clean(txt or "")
        return len(s) >= 12 and bool(_VERB_RX.search(s) or _SENTENCEISH_RX.search(s))

    def _is_full_header_line_except_stats(t: str) -> bool:
        for key in ("history_hdr","ministry_hdr","duties_hdr","outlook_hdr"):
            rx = C.get(key)
            if rx and rx.match(t):
                return True
        return False

    def flush():
        nonlocal duties, outlook, buf, mode, cut_pending
        block = _join_block(buf)
        if mode == "duties" and block and _is_good_duties(block):
            duties = block
        if mode == "outlook" and block:
            block = _sanitize_outlook(block, max_chars=4000, force_pending=cut_pending)
            if block and _is_good_outlook(block):
                outlook = block
        buf, mode, cut_pending = [], None, False

    for raw in paras or []:
        t = clean(raw)
        if not t:
            continue

        # 다른 '풀라인' 헤더(통계 제외)를 만나면 우선 flush
        if mode and _is_full_header_line_except_stats(t):
            flush()

        # 헤더 매칭
        m_d = C["duties_hdr"].match(t)
        m_o = C["outlook_hdr"].match(t)
        if m_d:
            flush(); mode = "duties"
            tail = t[m_d.end():].lstrip("：: ").strip()
            if tail: buf.append(tail)
            continue
        if m_o:
            flush(); mode = "outlook"; cut_pending = False
            tail = t[m_o.end():].lstrip("：: ").strip()
            if tail: buf.append(tail)
            continue

        if not mode:
            continue

        # 섹션 종료 마커
        if (mode == "duties"  and C["duties_end"].search(t)) or \
           (mode == "outlook" and C["outlook_end"].search(t)):
            flush();  continue

        if mode == "outlook":
            # URL/기관 라벨은 스킵만
            if _URL_RX.search(t) or re.match(r"^(홈페이지|기관명|실시기관)\s*[:：]?", t):
                continue
            # 표/통계 시그널 → 문장 종결까지 받고 끊기
            if C["stats_hdr"].match(t) or \
               any(rx.search(t) for rx in _STATS_CUTOFF_RXS) or \
               (_NUM_HEAVY_LINE.match(t) and any(k in t for k in ("응시","합격","합격률","필기","실기","연도"))):
                cut_pending = True
                continue

        # noise 라인 처리(단, cut_pending은 건드리지 않음)
        if any(t.startswith(nz) for nz in (C["duties_noise"] if mode=="duties" else C["outlook_noise"])):
            t = re.sub(r"^" + _STRIP_HEAD, "", t).strip()
            if not t:
                continue

        buf.append(t)

        # outlook에서 cut_pending 중이고 문장 종결을 만나면 flush
        if mode == "outlook" and cut_pending and _TERM_RX.search(t):
            flush()
            continue

    flush()  # 루프 종료 후 잔여 버퍼 처리 (중요)

    # 표 기반 보강(비통계성 표만)
    def _looks_like_stats(tb) -> bool:
        rows = tb.get("rows") or []
        flat = " ".join(" ".join(clean(c) for c in r if c) for r in rows[:2])
        return bool(re.search(r"\b20\d{2}\b", flat))

    def table_to_text(rows: List[List[str]]) -> Optional[str]:
        lines=[]
        for r in rows:
            if any(clean(c) for c in r):
                lines.append(" - " + " ".join(clean(c) for c in r if clean(c)))
        return "\n".join(s[1:] for s in lines) if lines else None

    if not duties:
        for tb in tables or []:
            if _looks_like_stats(tb):  continue
            head = " ".join(clean(c) for c in (tb.get("rows") or [[]])[0])
            if any(h in head for h in C["table_hints"].get("duties", [])):
                tmp = table_to_text(tb.get("rows") or [])
                if tmp: duties = tmp;  break

    if not outlook:
        for tb in tables or []:
            if _looks_like_stats(tb):  continue
            head = " ".join(clean(c) for c in (tb.get("rows") or [[]])[0])
            if any(h in head for h in C["table_hints"].get("outlook", [])):
                tmp = table_to_text(tb.get("rows") or [])
                if tmp: outlook = tmp;  break

    _log("history lines:", len(history_paras))
    _log("ministry:", ministry)
    _log("has_stats_hdr:", has_stats_hdr, "has_stats_kw:", has_stats_kw,
         "cand_norm_only:", len(normalize_only_candidates))

    # 통계 정규화
    all_for_normalize = (stats_tables or []) + (normalize_only_candidates or [])
    try:
        stats_struct = parse_stats_tables(all_for_normalize) or []
    except Exception:
        stats_struct = []

    KEEP_RAW = True
    _log("stats tables:", len(stats_tables), "normalized blocks:", len(stats_struct))
    _log("duties len:", len(duties or ""), "outlook len:", len(outlook or ""))

    return {
        "duties": duties,
        "outlook": outlook,
        "history_paras": history_paras,
        "ministry": ministry,
        "stats_tables": stats_tables if KEEP_RAW else [],
        "stats_struct": stats_struct,
    }

# ──────────────────────────────────────────────────────────────────────────────
# 디버깅 보조 + 로더용 래퍼
# ──────────────────────────────────────────────────────────────────────────────
def _debug_check_virtual_injection(paras: List[str]) -> None:
    def has(label: str) -> bool:
        return any(label in (p or "") for p in (paras or []))
    print("[debug] virtual '진로및전망'  :", "OK" if has("진로및전망") else "NOT FOUND")
    print("[debug] virtual '수행직무'    :", "OK" if has("수행직무") else "NOT FOUND")

def augment_then_extract(paras: List[str], tables: List[dict], raw_html: str, debug: bool = True) -> Dict[str, Any]:
    """
    로더에서 호출하기 좋은 one-shot 함수:
      - iframe/title + textarea 본문을 paras에 주입
      - 주입 성공 여부 디버깅 로그 출력
      - basic-info 섹션 추출 수행
    """
    if debug:
        print("[debug] before augment: len(paras) =", len(paras))
    try:
        paras = augment_paras_with_virtual_sections(paras or [], raw_html or "")
    except Exception as e:
        print("[debug] augment error:", repr(e))
    if debug:
        print("[debug] after augment:  len(paras) =", len(paras))
        _debug_check_virtual_injection(paras)
    return extract_basic_sections(paras, tables or [])
