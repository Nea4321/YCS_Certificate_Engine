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
    "outlook":   [r"진로\s*및\s*전망", r"진로및전망", r"취업\s*및\s*진로"],
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


# ── 헤더 감지 / 섹션 추출 ─────────────────────────────────────────────────────
def _cfg_headers(cfg: dict, key: str) -> List[str]:
    try:
        hs = (cfg.get(key) or {}).get("headers") or []
        return [h for h in hs if isinstance(h, str) and h.strip()]
    except Exception:
        return []

def _merge_headers(py_labels: Dict[str, List[str]], cfg: dict) -> Dict[str, List[str]]:
    out = {}
    for k, v in py_labels.items():
        out[k] = list(dict.fromkeys((v or []) + _cfg_headers(cfg, k)))  # 중복 제거 유지
    return out

def _build_header_hits(paras: List[str],
                       HEAD: Dict[str, List[str]]
                       ) -> Tuple[Dict[str, List[int]], List[str], List[str]]:
    """라인 단위에서 헤더 인덱스 후보를 수집 (LABELS+YAML 병합된 HEAD 사용)."""
    hits = {k: [] for k in HEAD.keys()}

    lines_raw = [p for p in (paras or []) if p]
    lines_t   = [norm_title(p) for p in lines_raw]   # 제목 정규화
    lines_norm = [_norm_line(p) for p in lines_t]    # 라인 정규화

    for i, ln in enumerate(lines_norm):
        for key, tokens in HEAD.items():             # ← 반드시 HEAD 사용
            for t in tokens:
                if _header_line_rx(t).search(ln):
                    hits[key].append(i)
                    break
    return hits, lines_raw, lines_norm



def _grab_section_lines(hits: Dict[str, List[int]],
                        lines_norm: List[str],
                        key: str,
                        HEAD: Dict[str, List[str]]
                        ) -> Optional[str]:
    """헤더 라인부터 다음 헤더 전까지 본문을 이어붙여 섹션을 만든다 (HEAD 사용)."""
    idxs = hits.get(key) or []
    if not idxs:
        return None
    i = idxs[0]

    # 같은 줄 tail 확보
    tail = None
    for t in HEAD[key]:                               # ← HEAD 사용
        m = _header_line_rx(t).search(lines_norm[i])
        if m:
            tail = lines_norm[i][m.end():].strip()
            break

    # '...기술사' 같은 제목 에코 컷(선택적)
    if tail and re.fullmatch(r"[가-힣A-Za-z\s]{1,20}기술사", tail):
        tail = None

    buf: List[str] = []
    if tail:
        buf.append(tail)

    # 다음 헤더 전까지 수집
    all_tokens = [tt for v in HEAD.values() for tt in v]  # ← HEAD 전체 토큰
    for j in range(i + 1, len(lines_norm)):
        brk = None
        for t in all_tokens:
            if _header_line_rx(t).search(lines_norm[j]):  # ← 기존 그대로
               brk = t
               break
        if brk:
           if os.getenv("BASIC_INFO_DEBUG"):
              print(f"[dbg] break on token='{brk}' line{j}='{lines_norm[j]}'")
              print(f"[dbg] header='{HEAD[key]}' hit_line='{lines_norm[i]}' tail='{tail}'")
           break
        if lines_norm[j]:
            buf.append(lines_norm[j])

    out = " ".join(buf).strip()
    return out or None


def _slice_blob(blob: str, head_tokens: List[str], all_tokens: List[str]) -> Optional[str]:
    """블랍 기반: 헤더 토큰 ~ 다음 헤더 토큰 전까지 슬라이스.
       - 모든 매치를 수집하고 가장 '본문 같고 충분히 긴' 세그먼트를 고른다.
    """
    if not blob:
        return None

    head = _labels_union(head_tokens)
    nxt  = _labels_union(all_tokens)

    rx = re.compile(
        head + r"\s*[:：\-–—]?\s*(.+?)\s*(?=" + nxt + r"|$)",
        re.S | re.I
    )

    matches = list(rx.finditer(blob))
    if not matches:
        return None

    def _score(seg: str) -> int:
        s = _norm_line(seg or "")
        if not s:
            return -10**9
        pts = len(s)                           # 길이 우선
        # '표/통계' 냄새 패널티
        if s.startswith("종목별 검정") or s.startswith("연도"):
            pts -= 5000
        if re.search(r"\b(연도|필기|실기|응시|합격|합격률)\b", s):
            pts -= 800
        # 문장성 가점
        if re.search(r"(한다|하며|하고|하는|되며|되어|수행|전망|필요|예상)", s):
            pts += 400
        if re.search(r"(을|를|에|에서|으로|와|과|및)\b", s):
            pts += 200
        return pts

    best = ""
    best_pts = -10**9
    for m in matches:
        g = (m.group(1) or "").strip()
        sc = _score(g)
        if sc > best_pts:
            best, best_pts = g, sc

    return best or None


# ── 실시기관 ─────────────────────────────────────────────────────────────────
def _extract_agency(blob: str, lines: List[str],
                    head_tokens: List[str], all_tokens: List[str]) -> Dict[str, Optional[str]]:
    out = {"홈페이지": None, "기관명": None}

    # 0) 먼저 가능한 한 '실시기관' 섹션만 떼어온다
    seg = _slice_blob(blob, head_tokens, all_tokens)  # 실패하면 None
    area = seg if seg else "\n".join(lines)

    # 0-1) 다음 섹션/표가 보이면 그 앞에서 컷
    for stop in ["진로 및 전망", "진로및전망", "취업 및 진로",
                 "종목별 검정현황", "종목별 검정 현황"]:
        k = area.find(stop)
        if k != -1:
            area = area[:k]
            break

    # 0-2) 혹시라도 페이지 전체가 들어왔다면 '실시기관' 첫 등장부터 짧은 윈도만 사용
    m_head = re.search(r"실시\s*기관", area)
    if m_head:
        area = area[m_head.start(): m_head.start()+300]  # 앞쪽 300자만

    # 1) URL 먼저
    m_url = re.search(r"(?:홈페이지|URL)\s*[:：]?\s*(https?://[^\s)\"'>]+|\bwww\.[^\s)\"'>]+)", area)
    if m_url:
        u = m_url.group(1)
        out["홈페이지"] = (u if u.startswith("http") else "http://" + u)
    else:
        mu = re.search(r"https?://[^\s)\"'>]+|\bwww\.[^\s)\"'>]+", blob)
        if mu:
            u = mu.group(0)
            out["홈페이지"] = (u if u.startswith("http") else "http://" + u)

    # 2) '실시기관명/기관명' 표기 라인 최우선
    m_nm = re.search(r"(?:실시\s*기관(?:명)?|기관명)\s*[:：]?\s*([^\n\.]+)", area)
    if m_nm:
        cand = _norm_line(m_nm.group(1))
        # 콤마/슬래시 등으로 여러 값이 붙으면 첫 토큰만
        cand = cand.split()[0]
        out["기관명"] = cand

    # 3) 그래도 없으면 짧은 윈도에서 접미 후보 선택
    if not out["기관명"]:
        window = _norm_line(area)[:160]  # 너무 멀리 나가지 않게
        toks = [w for w in window.split() if 2 <= len(w) <= 30]
        # 접미 후보 (공사, 회의소도 추가)
        suffix_rx = re.compile(r"(부|처|청|원|공단|협회|센터|위원회|재단|진흥원|교육원|연구원|공사|회의소)$")
        cands = [w for w in toks if suffix_rx.search(w)]
        if cands:
            out["기관명"] = max(cands, key=len)

    # 4) HRDK가 화면 어딘가에 있으면 최우선 강제
    whole = _norm_line("\n".join(lines))
    if "한국산업인력공단" in whole:
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

    cfg    = load_basic_info_cfg() or {}
    tables = tables or []

    # ✅ 파이썬 상수 + YAML(headers) 병합
    HEAD = _merge_headers(LABELS, cfg)

    blob = _raw_blob(paras)

    # ✅ HEAD 기반으로 헤더 감지
    hits, _lines_raw, lines_norm = _build_header_hits(paras, HEAD)

    # ✅ 전체 토큰도 HEAD에서 수집
    all_tokens = [tt for v in HEAD.values() for tt in v]

    # 1) 개요
    overview = (
        _grab_section_lines(hits, lines_norm, "overview", HEAD)
        or _slice_blob(blob, HEAD["overview"], all_tokens)
        or _norm_line(re.sub(r"^(?:기본정보\s*)*(?:개요\s*)*", "", (first_long(paras) or "")))
    )
    if overview:
        cuts = (cfg.get("overview_cuts") or [])
        if cuts:
            cut_rx = re.compile("|".join(map(re.escape, cuts)))
            m = cut_rx.search(overview)
            if m:
                overview = overview[:m.start()].strip()

    # 2) 실시기관 (HEAD 사용해도 무방)
    org = _extract_agency(blob, paras, HEAD["agency"], all_tokens)

    # 3) 보조 파서(YAML)
    extra = extract_basic_sections(paras, tables)

    # 4) 소관부처
    ministry = extra.get("ministry")
    if ministry:
        m = MIN_RX.search(ministry)
        ministry = m.group(1) if m else None

    # 5) 변천
    history_paras = extra.get("history_paras") or []

    def _minlen(s, n=20): 
        s = (s or "").strip()
        return s if len(s) >= n else None

    # 6) duties / 7) outlook  ← 로컬 우선 + YAML 보조
    local_duties  = _grab_section_lines(hits, lines_norm, "duties",  HEAD) 
    if local_duties and len(local_duties.strip()) < 12:   # 제목만(너무 짧음) → 무시
       local_duties = None
    if not local_duties:
       local_duties = _slice_blob(_raw_blob(paras), HEAD["duties"],
                                   [tt for v in HEAD.values() for tt in v])

    local_outlook = _grab_section_lines(hits, lines_norm, "outlook", HEAD)
    if local_outlook and len(local_outlook.strip()) < 12: # 제목만(너무 짧음) → 무시
       local_outlook = None
    if not local_outlook:
       local_outlook = _slice_blob(_raw_blob(paras), HEAD["outlook"],
                                   [tt for v in HEAD.values() for tt in v])

    print("[dbg] after_fallback duties_len:", len(local_duties or ""),
      "outlook_len:", len(local_outlook or ""))
    
    # 짧으면(=제목만) blob에서 다시 잘라오기
    if not _minlen(local_duties):
       seg = _slice_blob(_raw_blob(paras), HEAD["duties"],  [tt for v in HEAD.values() for tt in v])
       if _minlen(seg): 
          local_duties = seg

    if not _minlen(local_outlook):
       seg = _slice_blob(_raw_blob(paras), HEAD["outlook"], [tt for v in HEAD.values() for tt in v])
       if _minlen(seg): 
          local_outlook = seg

    duties_from_extra  = extra.get("duties")
    outlook_from_extra = extra.get("outlook")

    def _better(a: str|None, b: str|None) -> str|None:
        def score(s: str|None) -> int:
            if not s: return -1
            ss = _norm_line(s)
            pts = len(ss)
            if re.search(r"(한다|하며|하고|하는|되며|되어|수행)", ss): pts += 200
            if re.search(r"(을|를|에|에서|으로|와|과|및)\b", ss):   pts += 100
            return pts
        return a if score(a) >= score(b) else b

    duties  = _better(local_duties,  duties_from_extra)
    outlook = _better(local_outlook, outlook_from_extra)

    # 제목성 과잉 컷(완화)
    def _is_title_like(s: str) -> bool:
        ss = _norm_line(s or "")
        if len(ss) <= 3: return True
        if re.search(r"[\.!?]|(은|는|이|가|을|를|에|에서|으로|와|과)\b", ss): return False
        if re.fullmatch(r"[가-힣A-Za-z0-9\(\)/]+(기술사|산업기사|기사|기능사)", ss):
            return True
        return bool(re.fullmatch(r"\d+\s*급\s*[가-힣A-Za-z]+", ss))

    if duties and _is_title_like(duties):   duties  = None
    if outlook and _is_title_like(outlook): outlook = None

    # 8) 통계
    stats_tables = _dedup_tables(extra.get("stats_tables"))

    # 9) 콜백들
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
        if hits.get("outlook"):
           i = hits["outlook"][0]
           print("[dbg] outlook line:", lines_norm[i])
        print("[dbg] has '진로 및 전망' in blob?:", "진로 및 전망" in blob)
        print("[dbg] local_outlook(len):", len(local_outlook or ""))  # 라인/블랍 중 선택된 값
        print("[dbg] outlook_from_extra(len):", len((extra.get("outlook") or "") or ""))
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
