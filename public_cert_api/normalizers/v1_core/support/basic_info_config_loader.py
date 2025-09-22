# -*- coding: utf-8 -*-
import os, re, yaml
from pathlib import Path
from ...utils.text import clean

# ──────────────────────────────────────────────────────────────────────────────
# 설정/공통
# ──────────────────────────────────────────────────────────────────────────────
_CFG = None

_BULLETS = "□■◦•\\-·"
_STRIP_HEAD       = r"[□■◦•\-\·\*\#\u3000\s]*"
_STRIP_HEAD_PLUS  = r"(?:[□■◦•\-\·\*\#]|ㅇ)\s*"
_VERB_RX          = re.compile(r"(한다|하며|하고|하는|되며|되어|수행|작성|신청|이행|분류|계산|심사|조사|관리|운영|대리|확인|지도|지원|제공)")
_SENTENCEISH_RX   = re.compile(r"(을|를|에|에서|으로|과|와|및|도|등|하여|하고|하며)")

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

def load_basic_info_cfg():
    """YAML 로드 + 정규식/설정 준비"""
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
def _slice_section(paras: list[str], hdr: re.Pattern, end: re.Pattern) -> list[str]:
    ok, out = False, []
    for raw in paras or []:
        t = clean(raw)
        if not t:
            continue
        if not ok and hdr.match(t):
            ok = True
            tail = t[hdr.match(t).end():].lstrip("：: ").strip()
            if tail:
                out.append(tail)
            continue
        if ok:
            if end.search(t):
                break
            out.append(t)
    return out

def _slice_section_fuzzy(paras: list[str], hdr_pat: re.Pattern, end_pat: re.Pattern) -> list[str]:
    """헤더가 같은 줄에서 시작하는 케이스 포함."""
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

def _has_header(paras: list[str], hdr_pat: re.Pattern) -> bool:
    body_pat = re.compile(hdr_pat.pattern[2:-2])
    for raw in paras or []:
        t = clean(raw) or ""
        if hdr_pat.match(t): return True
        if body_pat.search(t): return True
    return False

# ──────────────────────────────────────────────────────────────────────────────
# 통계표 판정 유틸
# ──────────────────────────────────────────────────────────────────────────────
def _strong_stats_signature(tb) -> bool:
    """연도/지표 다발 + 구분성 라벨 존재 → 통계표로 강하게 인정"""
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
    """연도 2개 이상 + 지표 1개 이상 → 약한(세이프가드)"""
    rows = tb.get("rows") or []
    if not rows:
        return False
    flat = " ".join(" ".join(clean(c) for c in r if c) for r in rows)
    years   = re.findall(r"\b20(1\d|2\d)\b", flat)
    metric1 = re.search(r"(응시|합격|합격률|필기|실기|면접|1차|2차)", flat)
    return len(set(years)) >= 2 and bool(metric1)

# ──────────────────────────────────────────────────────────────────────────────
# 통계표 정규화 파서 (연도/필기/실기 패턴 우선)
# ──────────────────────────────────────────────────────────────────────────────
def _as_int(x: str) -> int | None:
    try:
        return int(str(x).replace(",", "").strip())
    except Exception:
        return None

def _as_pct(x: str) -> str | None:
    if x is None:
        return None
    s = str(x).strip()
    return s or None

def _looks_like_year_token(tok: str) -> bool:
    tok = (tok or "").strip()
    if tok.endswith("년"):
        tok = tok[:-1]
    return (tok.isdigit() and (1970 <= int(tok) <= 2100)) or ("~" in tok) or ("소 계" in tok) or ("소계" in tok)

def _parse_year_header_style(rows: list[list[str]]) -> list[dict] | None:
    """
    형태:
      [연도, 필기, 실기]
      [응시, 합격, 합격률(%), 응시, 합격, 합격률(%)]
      [2024, 13, 4, 30.8%, 8, 3, 37.5%]
      ...
    """
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

def parse_stats_tables(stats_tables: list[dict]) -> list[dict]:
    """
    통계 표들을 '가능하면' 구조화.
    - 연도/필기/실기 패턴 → kind='by_year'로 레코드화
    - 그 외(블록형 등) → kind='raw'로 rows 보존(비어 나오는 일 방지)
    """
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
        out.append({  # 안전 폴백
            "kind": "raw",
            "rows": rows,
            "source": {"caption": tb.get("caption"), "index": tb.get("index")},
        })
    return out


# ──────────────────────────────────────────────────────────────────────────────
# 추가 헬퍼/상수: 섹션 헤더 탐지(ANY), outlook 살균
# ──────────────────────────────────────────────────────────────────────────────
_URL_RX = re.compile(r"(https?://[^\s]+)")
_STATS_CUTOFF_RXS = (
    re.compile(r"종목별\s*검정현황"),
    re.compile(r"^\s*연도\s*$"),
    re.compile(r"(필기|실기)\s*(응시|합격|합격률)"),
)
_NUM_HEAVY_LINE = re.compile(r"^(?:\d{1,3}(?:,\d{3})*|\d{2,})\s*(?:\d{1,3}(?:,\d{3})*|\d{2,})")

def _any_header_regex(C) -> re.Pattern:
    """
    개요/변천/부처/통계/수행직무/진로 등 '다음 섹션' 헤더를 한 번에 잡는 정규식.
    현재 섹션 수집 중, 이게 보이면 flush 후 종료.
    """
    pats = []
    for key in ("history_hdr","ministry_hdr","stats_hdr","duties_hdr","outlook_hdr"):
        rx = C.get(key)
        if hasattr(rx, "pattern"):
            # ^...$ 뜯어내서 바디만 쓰되, 라인 내 등장도 잡히도록
            body = rx.pattern
            if body.startswith(r"^\s*"): body = body[len(r"^\s*"):]
            if body.endswith(r"\s*[:：]?\s*$"): body = body[: -len(r"\s*[:：]?\s*$")]
            pats.append(body)
    if not pats:
        return re.compile(r"(?!x)x")  # never
    return re.compile(r"(?:%s)" % "|".join(pats))

def _sanitize_outlook(txt: str, max_chars: int = 4000) -> str | None:
    """
    진로및전망 블록에서 표/URL/라벨/숫자열 등 '오염' 요소를 잘라냄.
    - URL/홈페이지/기관명 라벨 제거
    - 표 신호(연도, 필기/실기/응시/합격/합격률) 라인에서 컷
    - 과도한 숫자열/콤마 덩어리 라인 제거
    """
    if not txt:
        return None
    lines = []
    for raw in (txt or "").splitlines():
        t = clean(raw) or ""
        if not t:
            continue
        # URL/홈페이지/기관명 같은 라벨 컷
        if _URL_RX.search(t) or re.match(r"^(홈페이지|기관명|실시기관)\s*[:：]?", t):
            continue
        # 표/통계 신호 컷
        if any(rx.search(t) for rx in _STATS_CUTOFF_RXS):
            break
        # 숫자열 과밀 라인 컷 (표 파편 가능성 큼)
        if _NUM_HEAVY_LINE.match(t) and any(k in t for k in ("응시","합격","합격률","필기","실기","연도")):
            break
        lines.append(t)
    out = "\n".join(lines).strip()
    if not out:
        return None
    if len(out) > max_chars:
        out = out[:max_chars].rstrip() + "…"
    return out or None


# ──────────────────────────────────────────────────────────────────────────────
# 메인: 기본정보 섹션 추출
# ──────────────────────────────────────────────────────────────────────────────
def extract_basic_sections(paras: list[str], tables: list[dict]) -> dict:
    C = load_basic_info_cfg()
    dbg = C.get("_debug")
    def _log(*a):
        if dbg: print("[basic-info]", *a)

    has_stats_hdr = _has_header(paras, C["stats_hdr"])

    # 본문 내 '통계' 관련 키워드 유무
    stats_keywords = ("통계", "최근 5년", "최근5년", "통계자료")
    has_stats_kw = any(any(k in (clean(p) or "") for k in stats_keywords) for p in (paras or []))

    # '종목별 검정현황'은 정규화만
    NORMALIZE_CAP_ONLY = ("종목별 검정현황", "종목별검정현황")

    # ── 변천과정 ──
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

    # ── 소관부처 ──
    def _pick_ministry_only(text: str) -> str | None:
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

    # ── 통계표 식별(다층) ──
    stats_tables = []
    normalize_only_candidates = []

    _log("table_count:", len(tables or []))

    # 1) 캡션 직격
    for tb in (tables or []):
        cap = (tb.get("caption") or "").strip()
        if not cap: continue
        if any(x in cap for x in NORMALIZE_CAP_ONLY):
            normalize_only_candidates.append(tb);  continue
        if any(key in cap for key in C["stats_caption"]):
            stats_tables.append(tb)

    # 2) 강 시그널(헤더/키워드 중 하나라도 있을 때만)
    if has_stats_hdr or has_stats_kw:
        for tb in (tables or []):
            if tb in stats_tables or tb in normalize_only_candidates: continue
            if _strong_stats_signature(tb): stats_tables.append(tb)

    # 3) 헤더 감지된 경우 느슨 규칙
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

    # 4) 세이프가드
    if not stats_tables and (has_stats_hdr or has_stats_kw):
        weak = [tb for tb in (tables or []) if (tb not in normalize_only_candidates and _weak_stats_signature(tb))]
        if weak: stats_tables.append(weak[0])

    # 4.5) 마지막 폴백(표가 1개이고 normalize-only 없음)
    if not stats_tables and not normalize_only_candidates and len(tables or []) == 1:
        stats_tables.append(tables[0])

    # 보너스 폴백
    if not stats_tables and not normalize_only_candidates:
        strongs = [tb for tb in (tables or []) if _strong_stats_signature(tb)]
        if strongs: stats_tables.append(strongs[0])

    # ── duties / outlook ──
    def _join_block(lines: list[str]) -> str | None:
        if not lines: return None
        txt = "\n".join(clean(re.sub(r"^" + _STRIP_HEAD_PLUS, "", s)) for s in lines if clean(s)).strip()
        return txt or None

    duties = outlook = None
    mode, buf = None, []

    def _is_good_duties(txt: str) -> bool:
        s = clean(txt or "");  return len(s) >= 12 and bool(_VERB_RX.search(s))

    def _is_good_outlook(txt: str) -> bool:
        s = clean(txt or "");  return len(s) >= 12 and bool(_VERB_RX.search(s) or _SENTENCEISH_RX.search(s))

    def _is_any_header_line(t: str) -> bool:
        # '풀라인 헤더'에만 반응 (문장 중간 키워드는 무시)
        for key in ("history_hdr","ministry_hdr","stats_hdr","duties_hdr","outlook_hdr"):
            rx = C.get(key)
            if rx and rx.match(t):
                return True
        return False

    def flush():
        nonlocal duties, outlook, buf, mode
        block = _join_block(buf)
        if mode == "duties" and block and _is_good_duties(block):
            duties = block
        if mode == "outlook" and block:
            block = _sanitize_outlook(block)
            if block and _is_good_outlook(block):
                outlook = block
        buf, mode = [], None

    for raw in paras or []:
        t = clean(raw)
        if not t: continue

        # ← 수정 포인트: '풀라인 헤더'일 때만 조기 flush
        if mode and _is_any_header_line(t):
            flush()
            # 이어서 새 헤더로 모드 전환 시도

        m_d = C["duties_hdr"].match(t)
        m_o = C["outlook_hdr"].match(t)
        if m_d:
            flush(); mode = "duties"
            tail = t[m_d.end():].lstrip("：: ").strip()
            if tail: buf.append(tail)
            continue
        if m_o:
            flush(); mode = "outlook"
            tail = t[m_o.end():].lstrip("：: ").strip()
            if tail: buf.append(tail)
            continue

        if mode:
            if (mode == "duties"  and C["duties_end"].search(t)) or \
               (mode == "outlook" and C["outlook_end"].search(t)):
                flush();  continue
            if mode == "outlook":
                if any(rx.search(t) for rx in _STATS_CUTOFF_RXS) or \
                   _URL_RX.search(t) or \
                   re.match(r"^(홈페이지|기관명|실시기관)\s*[:：]?", t):
                    flush();  continue
            if any(t.startswith(nz) for nz in (C["duties_noise"] if mode=="duties" else C["outlook_noise"])):
                t = re.sub(r"^" + _STRIP_HEAD, "", t).strip()
            buf.append(t)
    flush()

    # 표 기반 보강(통계성 표는 제외)
    def _looks_like_stats(tb) -> bool:
        rows = tb.get("rows") or []
        flat = " ".join(" ".join(clean(c) for c in r if c) for r in rows[:2])
        return bool(re.search(r"\b20\d{2}\b", flat))

    def table_to_text(rows: list[list[str]]) -> str | None:
        lines=[];  [lines.append(" - " + " ".join(clean(c) for c in r if clean(c))) for r in rows if any(clean(c) for c in r)]
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

    # ── 통계 정규화 ──
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
