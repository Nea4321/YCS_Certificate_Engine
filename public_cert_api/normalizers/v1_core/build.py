# -*- coding: utf-8 -*-
from ..utils.regexes import now_iso
from .basic_info import split_sections
from .exam_schedule import parse_schedule_tables
from .exam_info import extract_fees, extract_sections
from .preference import parse_preference
from ..adapters import run as run_adapters
from ..utils.text import clean
from .support.basic_info_config_loader import augment_paras_with_virtual_sections

import re
import json
from math import isfinite

# ────────────────────────────────────────────────────────────────────
# Helpers
# ────────────────────────────────────────────────────────────────────

_OUTLOOK_URL_RX = re.compile(r"https?://\S+")
_OUTLOOK_DROP_HEAD_RX = re.compile(r"^(홈페이지|기관명|실시기관|실시기관명)\s*[:：]?", re.I)

# 표/통계 신호: 만나면 pending_cut = True → 문장 종결 나올 때까지 받고 컷
_OUTLOOK_STATS_SIGNALS = (
    re.compile(r"종목별\s*검정\s*현황"),
    re.compile(r"^\s*연도\s*$"),
    re.compile(r"(필기|실기).*(응시|합격|합격률)"),
)
_OUTLOOK_TERM_RX = re.compile(r"[\.!?…]|[다요]\s*$")  # 문장 종결

def patch_outlook_safely(txt: str | None, max_chars: int = 4000) -> str | None:
    if not txt:
        return txt
    lines, cut_pending = [], False
    for raw in (txt or "").splitlines():
        t = (raw or "").strip()
        if not t:
            continue
        if _OUTLOOK_URL_RX.search(t) or _OUTLOOK_DROP_HEAD_RX.search(t):
            # URL/기관 라벨 라인은 버림
            continue
        if any(rx.search(t) for rx in _OUTLOOK_STATS_SIGNALS):
            # 표/통계 신호를 만나면 바로 본문 수집은 중지하고,
            # 문장 종결이 나올 때까지만 이어서 받고 컷
            cut_pending = True
            continue

        lines.append(t)

        if cut_pending and _OUTLOOK_TERM_RX.search(t):
            break

    out = "\n".join(lines).strip()
    if not out:
        return None
    if len(out) > max_chars:
        out = out[:max_chars].rstrip() + "…"
    return out or None

def _make_meta(jmcd: str, name: str | None, type_str: str | None, issued_by: str | None) -> dict:
    """운영 저장용 슬림 메타만 남긴다."""
    meta = {
        "schema_version": "v1",
        "generated_at": now_iso(),
        "jmcd": jmcd,
        "name": name,
        "type": type_str,
        "issued_by": issued_by,
    }
    return {k: v for k, v in meta.items() if v is not None}

def _slim_preference(pref: dict | None) -> dict:
    """우대현황에서 법령우대만 유지."""
    if not isinstance(pref, dict):
        return {"법령우대": []}
    return {"법령우대": pref.get("법령우대") or []}

def _norm_year_cell(y):
    if isinstance(y, int):
        return (y, y, str(y))
    if isinstance(y, str):
        s = y.strip()
        if s == "소계":
            return (None, None, "소계")
        m = re.match(r"^\s*(\d{4})\s*[~\-]\s*(\d{4})\s*$", s)
        if m:
            a, b = int(m.group(1)), int(m.group(2))
            return (a, b, f"{a}~{b}")
        m2 = re.match(r"^\s*(\d{4})\s*$", s)
        if m2:
            a = int(m2.group(1))
            return (a, a, str(a))
    return (None, None, str(y))

def _fix_year_rows(rows):
    if not rows:
        return rows
    norm = []
    ranges_by_start = set()
    for r in rows:
        y0, y1, label = _norm_year_cell(r.get("연도"))
        if y0 is not None and y1 is not None and y0 != y1:
            ranges_by_start.add(y0)
        norm.append((y0, y1, label, r))
    out = []
    for y0, y1, label, r in norm:
        if y0 is not None and y0 == y1 and y0 in ranges_by_start:
            continue
        out.append(r)
    has_total = any(str(x.get("연도")).strip() == "소계" for x in out)
    if not has_total:
        def num(x):
            try:    return float(str(x).replace(",", ""))
            except: return 0.0
        s필응 = s필합 = s실응 = s실합 = 0.0
        for r in out:
            y0, y1, _ = _norm_year_cell(r.get("연도"))
            if y0 is None and y1 is None:
                continue
            s필응 += num(r.get("필기응시"))
            s필합 += num(r.get("필기합격"))
            s실응 += num(r.get("실기응시"))
            s실합 += num(r.get("실기합격"))
        def pct(hit, tot):
            if tot and isfinite(hit) and isfinite(tot):
                return f"{round(hit * 100.0 / tot, 1)}%"
            return None
        out.append({
            "연도": "소계",
            "필기응시": int(s필응),
            "필기합격": int(s필합),
            "필기합격률": pct(s필합, s필응),
            "실기응시": int(s실응),
            "실기합격": int(s실합),
            "실기합격률": pct(s실합, s실응),
        })
    return out

def _postproc_exam_links(links):
    import re
    crit_items, crit_more, downloads = [], None, []
    for L in links or []:
        if not isinstance(L, dict):
            continue
        text = (L.get("text") or L.get("title") or "").strip()
        href = L.get("href")
        action = L.get("action") or {}
        download = L.get("download")
        if re.match(r"^\s*\d+\.\s*.+\(\d{4}\.", text or ""):
            crit_items.append({
                "label": re.sub(r"^\s*\d+\.\s*", "", text).strip(),
                "href": (href if href and href != "#" else None),
                "action": action or None
            })
        if href and "cst006.do" in href:
            crit_more = {"label": text or "출제기준", "href": href}
        if download:
            downloads.append({
                "label": download.get("filename") or text or "공개문제",
                "download": download
            })
    return crit_items, crit_more, downloads

def _append_legacy_band_and_total(pass_rows: list[dict], bi_tables: list[dict]) -> list[dict]:
    if not bi_tables:
        return pass_rows
    rows = []
    for tb in bi_tables:
        r = tb.get("rows") or []
        if len(r) < 2:
            continue
        head = " ".join(clean(c) for c in r[0])
        if not ("필기" in head and "실기" in head):
            continue
        rows = r[1:]
        break
    if not rows:
        return pass_rows
    def to_item(cells: list[str]) -> dict | None:
        cs = [clean(x) for x in cells]
        if not cs:
            return None
        y = cs[0]
        if re.search(r"\d{4}\s*~\s*\d{4}", y) or ("소계" in y):
            def num(s):
                try: return int(re.sub(r"[^\d]", "", s)) if re.search(r"\d", s) else None
                except: return None
            def pct(s): s = clean(s); return s if s else None
            return {
                "연도": y, "필기응시": num(cs[1]), "필기합격": num(cs[2]), "필기합격률": pct(cs[3]),
                "실기응시": num(cs[4]), "실기합격": num(cs[5]), "실기합격률": pct(cs[6]) if len(cs) > 6 else None,
            }
        return None
    tails = []
    for row in rows[-5:]:
        it = to_item(row)
        if it: tails.append(it)
    have = {str(x.get("연도")) for x in pass_rows}
    for t in tails:
        if str(t.get("연도")) not in have:
            pass_rows.append(t)
    return pass_rows

def _dedup_links(links, drop_exam_actions=True):
    out, seen = [], set()
    for L in links or []:
        if not isinstance(L, dict):
            continue
        if drop_exam_actions and (L.get("action") or {}).get("fn") == "cst006Report":
            continue
        key = (
            (L.get("text") or L.get("title") or "").strip(),
            L.get("href") or json.dumps(L.get("action") or {}, sort_keys=True, ensure_ascii=False),
        )
        if key in seen:
            continue
        seen.add(key)
        out.append(L)
    return out


# build.py (outlook 계산 직후에 보강)
_TERM_END_RX = re.compile(r"[\.!?…]|[다요]\s*$")

def _slice_outlook_from_paras(paras: list[str]) -> str | None:
    blob = "\n" + "\n".join(paras or [])
    m = re.search(r"(?:^|\n)\s*(진로\s*및\s*전망|진로및전망|취업\s*및\s*진로|전망)\s*[:：]?\s*", blob, re.I)
    if not m:
        return None
    tail = blob[m.end():]
    stop = re.search(
        r"(?:^|\n)\s*(수행\s*직무|변천\s*과정|소관\s*부처(?:명)?|통계\s*자료|종목별\s*검정\s*현황)\s*[:：]?",
        tail, re.I
    )
    if stop:
        tail = tail[:stop.start()]
    return tail.strip() or None


# ────────────────────────────────────────────────────────────────────
# Main
# ────────────────────────────────────────────────────────────────────
def build_norm(raw: dict, jmcd: str, name: str | None, type_str: str | None, issued_by: str | None) -> dict:
    tabs = raw.get("tabs", {}) or {}
    bi = tabs.get("basic_info", {}) or {}
    ex = tabs.get("exam_info", {}) or {}
    pr = tabs.get("preference", {}) or {}

    bi_paras = bi.get("paragraphs") or []
    ex_paras = ex.get("paragraphs") or []
    pr_paras = pr.get("paragraphs") or []

    bi_tables = bi.get("tables") or []
    ex_tables = ex.get("tables") or []
    pr_tables = pr.get("tables") or []
    ex_links  = ex.get("links") or []

    # ==== 라벨 RX (outlook 보강용 판단에만 사용)
    _DUTIES_RX  = r"(수행\s*직무|주요\s*업무|직무\s*내용|하는\s*일|업무\s*내용)"
    _OUTLOOK_RX = r"(진로\s*및\s*전망|진로및전망|취업\s*및\s*진로|전망)"

    def _has_label(text: str, rx: str) -> bool:
        return bool(re.search(rx, text or "", flags=re.I))

    def _maybe_augment_basic_paras(bi_paras_, bi_html_):
        """
        이미 본문에 라벨이 있으면 건드리지 않고,
        주입 결과가 '라벨 인식 개선'일 때만 채택.
        """
        baseline = "\n".join(bi_paras_ or [])
        has_d0 = _has_label(baseline, _DUTIES_RX)
        has_o0 = _has_label(baseline, _OUTLOOK_RX)
        if has_d0 and has_o0:
            return bi_paras_
        aug = augment_paras_with_virtual_sections(list(bi_paras_ or []), bi_html_ or "")
        after = "\n".join(aug or [])
        improved = (not has_d0 and _has_label(after, _DUTIES_RX)) or \
                   (not has_o0 and _has_label(after, _OUTLOOK_RX))
        return aug if improved else bi_paras_

    # ---- 기본정보 문단 보강(필요할 때만)
    bi_html = bi.get("html") or raw.get("basic_info_html") or raw.get("html_basic_info")
    if bi_html:
        print("[bi] before_has:", _has_label("\n".join(bi_paras), _DUTIES_RX),
                               _has_label("\n".join(bi_paras), _OUTLOOK_RX))
        bi_paras = _maybe_augment_basic_paras(bi_paras, bi_html)
        print("[bi] after_has:",  _has_label("\n".join(bi_paras), _DUTIES_RX),
                               _has_label("\n".join(bi_paras), _OUTLOOK_RX))

    # ---- 시험정보 링크 텍스트
    link_texts = []
    for L in ex_links:
        link_texts.append(L if isinstance(L, str) else (L.get("text") or L.get("title") or "").strip())

    # ---- 기본정보 섹션 파싱
    bi_sec   = split_sections(bi_paras, bi_tables)
    overview = bi_sec.get("overview")

    # ---- name 보강(항상 값 보장)
    name = name or bi_sec.get("title") or (raw.get("title") if isinstance(raw.get("title"), str) else None) or jmcd

    # ---- 변천/기관/부처/통계
    history = []
    parse_tables = bi_sec.get("parse_history_tables")
    if callable(parse_tables):
        history = parse_tables(bi_tables)
    if not history:
        parse_text = bi_sec.get("parse_history_text")
        src_lines = (bi_sec.get("history_paras") or []) or (bi_paras or [])
        if callable(parse_text):
            history = parse_text(src_lines)

    org       = bi_sec.get("org") or {"홈페이지": None, "기관명": None}
    ministry  = bi_sec.get("ministry")
    stats_tbl = bi_sec.get("stats_tables") or []

    # ---- 수행직무 (짧으면 폴백 재그랩)
    duties = bi_sec.get("duties")
    if not duties or len(duties) <= 4:
        full = "\n".join(clean(p) for p in bi_paras or [])
        m = re.search(r"(수행\s*직무)\s*[:：]?\s*(.+?)(?=(변천과정|소관부처명|진로\s*및\s*전망|통계자료|종목별\s*검정현황|$))", full, re.S)
        if m:
            cand = clean(re.sub(r"^[\"“”'‘’]+|[\"“”'‘’]+$", "", m.group(2)))
            if len(cand) > 4 and cand not in {"검수사","기사","산업기사","기능사"}:
                duties = cand

    # ---- 진로및전망 (핵심: 기존값 우선 + 폴백 + 안전 패치)
    # ...
    outlook_raw = bi_sec.get("outlook")
    if outlook_raw and not _TERM_END_RX.search(outlook_raw.strip()[-10:]):
       # 미결 문장으로 끝나면 줄기반 폴백 재슬라이스 시도
       alt = _slice_outlook_from_paras(bi_paras)
       if alt:
          sanitized = patch_outlook_safely(alt)
          if sanitized:
             outlook_raw = sanitized

    # 최종 sanitize (한 번 더 안전망)
    outlook = patch_outlook_safely(outlook_raw) or outlook_raw

    # ---- 합격 통계(어댑터 실행 → 레거시 보강 → 연도 정리)
    pass_rows, adapters_used, meta = run_adapters(bi_tables, ex_tables)
    if adapters_used:
       print(f"[adapters] used={adapters_used} conf={meta.get('confidence')}")
       print(f"[adapters] rows={len(pass_rows)} sample={pass_rows[:2]}")
    else:
       print("[adapters] no match")
    pass_rows = _append_legacy_band_and_total(pass_rows or [], bi_tables)
    pass_rows = _fix_year_rows(pass_rows)

    # ---- 시험정보/수수료
    ex_secs = extract_sections(ex_paras, link_texts) or {}
    fees    = extract_fees(ex_paras, ex_tables) or {}
    if isinstance(fees, dict):
        fee_block = {"필기": fees.get("필기"), "실기": fees.get("실기")}
    elif isinstance(fees, str):
        fee_block = fees
    else:
        fee_block = {"필기": None, "실기": None}

    SEC_KEYS = ("출제경향","공개문제","출제기준","취득방법","응시자격","시험방법","합격기준","시험과목및배점","추가안내")
    TABLE_LABELS = ("시험과목및배점","시험방법","응시자격","합격기준","기타")
    exam_info = {"수수료": fee_block, **{k: None for k in SEC_KEYS}, "표": {k: [] for k in TABLE_LABELS}}
    exam_info["수수료_이미지"] = None

    for k in SEC_KEYS:
        if k in ex_secs:
            exam_info[k] = ex_secs[k]
    for t in ex.get("tables_labeled") or []:
        rows = t.get("rows") or []
        images = t.get("images")
        if not rows and not images:
            continue
        lab = (t.get("label") or "기타").strip()
        if lab == "응시수수료" and images and not rows:
            exam_info["수수료_이미지"] = (exam_info.get("수수료_이미지") or []) + images
        exam_info["표"].setdefault(lab, []).append({
            "rows": rows, "caption": t.get("caption"), "has_th": bool(t.get("has_th")),
            "index": t.get("index"), "images": images,
        })

    crit_items, crit_more, downloads = _postproc_exam_links(ex_links)
    if crit_items:  exam_info["출제기준_목록"]  = crit_items
    if crit_more:   exam_info["출제기준_더보기"] = crit_more
    if downloads:   exam_info["공개문제_자료"]  = downloads

    all_links = (bi.get("links") or []) + (ex_links or []) + (pr.get("links") or [])
    final_links = _dedup_links(all_links, drop_exam_actions=True)

    pref_full = parse_preference({"paragraphs": pr_paras, "tables": pr_tables}, name)
    pref_slim = _slim_preference(pref_full)

    # 2) 시험일정: 리스트로 강제 고정 (또는 dict로 고정 선택)
    events_block = parse_schedule_tables(ex_tables) or {}
    if isinstance(events_block, dict):
       events = events_block.get("events") or []
    elif isinstance(events_block, list):
       events = events_block
    else:
       events = []


    return {
        "_meta": _make_meta(jmcd=jmcd, name=name, type_str=type_str, issued_by=issued_by),
        "기본정보": {
            "개요": overview,
            #"변천과정": history or [],
            "실시기관": org,
            "소관부처명": ministry,
            #"통계자료": stats_tbl,
            "수행직무": duties,
            "진로및전망": outlook,              # ← 최종 정리값 사용
        },
        "시험일정": events,
        "시험정보": exam_info,
        "종목별검정현황": pass_rows or [],
        "우대현황": pref_slim,
        "링크": final_links,
    }
