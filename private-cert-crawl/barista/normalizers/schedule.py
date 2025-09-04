from __future__ import annotations
import re
from datetime import datetime, date
from typing import Any, Dict, Iterable, Tuple, Optional, List
from engine_common.utils_text import _prune
from engine_common.utils_date import _parse_md_range, _parse_one_date, _split_time_range, _minutes_ko

# ---------- 공용 헬퍼 ----------
def _first(src: Dict[str, Any], *keys: Iterable[str]) -> Any:
    for k in keys:
        v = src.get(k)
        if v not in (None, "", [], {}, ()):
            return v
    return None

def _sched_root(raw: Dict[str, Any]) -> Dict[str, Any]:
    s1 = raw.get("시험일정") or {}
    if isinstance(s1, dict):
        s2 = s1.get("시험일정") or s1
        s3 = s2.get("exam_schedule") or s2
        return s3 if isinstance(s3, dict) else {}
    return {}

ALIAS_SHOW_DATE = ("시험일자표시", "일시", "시험일자", "시험일")
ALIAS_TITLE     = ("항목", "제목", "필기_항목", "실기_항목")
ALIAS_REGISTER  = ("원서접수표시", "원서접수", "접수일자", "접수기간")
ALIAS_RESULT    = ("발표표시", "발표", "발표일", "합격자 발표")

_RX_ROUND = re.compile(r"(\d{1,3})\s*회")
def _pick_round(text: str | None) -> str | None:
    if not text: return None
    m = _RX_ROUND.search(text)
    return (m.group(1) + "회") if m else None

def _infer_kind(title: str) -> str:
    t = (title or "").replace(" ", "")
    if "발표" in t or "합격자발표" in t: return "result"
    if "시험" in t:                         return "exam"
    if "추가접수" in t or "추가입금" in t:    return "extra_register"
    if "접수" in t or "원서" in t:           return "register"
    return "unknown"

def _clean_line(s: str | None) -> str | None:
    if not s: return s
    s = s.replace("\xa0", " ").replace("\u200b", "").replace("\n", " ")
    s = re.sub(r"\([월화수목금토일]\)", "", s)   # (월) 제거
    s = re.sub(r",\s*\d{1,2}:\d{2}", "", s)      # ", 09:00" 꼬리 제거
    s = s.replace("∼", "~").replace("–", "~")
    return re.sub(r"\s+", " ", s).strip()

def _maybe_year_hint(s: str | None) -> Optional[int]:
    if not s: return None
    m = re.search(r"(\d{4})\s*년", s)
    return int(m.group(1)) if m else None

def _parse_md_range_slash(s: str | None, by: int) -> Tuple[Optional[str], Optional[str]]:
    if not s: return (None, None)
    t = re.sub(r"[\s\u00A0\u200B]+", "", s)
    m = re.search(r"(\d{1,2})/(\d{1,2})~(\d{1,2})/(\d{1,2})", t)
    if m:
        m1, d1, m2, d2 = map(int, m.groups())
        y1 = by
        y2 = by + 1 if m2 < m1 else by
        try:    return (date(y1, m1, d1).isoformat(), date(y2, m2, d2).isoformat())
        except: return (None, None)
    m = re.search(r"(\d{1,2})/(\d{1,2})", t)
    if m:
        mm, dd = map(int, m.groups())
        try:    return (date(by, mm, dd).isoformat(), None)
        except: return (None, None)
    return (None, None)

# ---------- 라인 표준화(1번의 강건함) ----------
def _normalize_round_line(r: Dict[str, Any], base_year: int) -> Dict[str, Any]:
    title         = _first(r, *ALIAS_TITLE) or ""
    show_date     = _first(r, *ALIAS_SHOW_DATE)      # 혼재 가능(일시)
    show_register = _first(r, *ALIAS_REGISTER)
    show_result   = _first(r, *ALIAS_RESULT)

    rs  = r.get("registerStart")
    re_ = r.get("registerEnd")
    ex  = r.get("examDate")
    res = r.get("resultDate")

    by = _maybe_year_hint(show_register) or _maybe_year_hint(show_date) or _maybe_year_hint(show_result) or base_year

    show_date_c     = _clean_line(show_date)
    show_register_c = _clean_line(show_register)
    show_result_c   = _clean_line(show_result)

    kind = _infer_kind(title or "")

    if kind in ("register","extra_register"):
        label = show_register_c or show_date_c
        if (not rs or not re_) and label:
            rs, re_ = _parse_md_range(label, by)
            if not (rs or re_):
                rs, re_ = _parse_md_range_slash(label, by)

    elif kind == "exam":
        label = show_date_c
        if not ex and label:
            es, ee = _parse_md_range(label, by)
            if not (es or ee):
                es, ee = _parse_md_range_slash(label, by)
            ex = es or ee

    elif kind == "result":
        label = show_result_c or show_date_c
        if not res and label:
            res = _parse_one_date(label, by)
            if not res:
                es, _ = _parse_md_range_slash(label, by)
                res = es or res

    return _prune({
        "회차": r.get("회차") or _pick_round(title),
        "등급": r.get("등급"),
        "차수": r.get("차수"),
        "항목": title or None,
        "구분": r.get("구분"),
        "원서접수표시": show_register or None,
        "표시": show_date or None,     # 2번 스키마에 맞춰 이름 통일
        "발표표시": show_result or None,
        "registerStart": rs,
        "registerEnd":   re_,
        "examDate":      ex,
        "resultDate":    res,
    })

# ---------- 공개 API: 2번 스키마 + 1번의 강건함 ----------
def normalize_schedule(raw: dict, base_year: int | None = None) -> dict:
    """
    반환 스키마(2번과 동일):
    {
      "정기검정일정":[ { 회차, 등급?, 차수?, 원서접수표시?, 시험일자표시?, 발표표시?,
                        registerStart?, registerEnd?, examDate?, resultDate? }, ... ],
      "시험시간":[ { 등급?, 차수?, 교시?, 입실완료시간?, 시험시간표시?, start?, end?, durationMin? }, ... ]
    }
    """
    base_year = base_year or datetime.now().year
    root = _sched_root(raw)

    rounds_in = root.get("정기검정일정") or []
    times_in  = (root.get("시험시간")
                 or root.get("입실 및 시험시간")
                 or [])

    # ✅ 각 라인을 1번 방식으로 강건하게 정규화한 뒤, 2번 스키마로 반환
    rounds = [_normalize_round_line(r, base_year) for r in rounds_in]

    # 시험시간은 2번 로직 재사용
    times = []
    for t in times_in:
        show_time = t.get("시험시간표시") or t.get("시험시간")
        start, end = _split_time_range(show_time or "")
        times.append(_prune({
            "등급": t.get("등급"),
            "차수": t.get("차수"),
            "교시": t.get("교시"),
            "입실완료시간": t.get("입실완료시간"),
            "시험시간표시": show_time,
            "start": start,
            "end": end,
            "durationMin": _minutes_ko(show_time) or _minutes_ko(t.get("소요시간")),
        }))

    return _prune({"정기검정일정": rounds, "시험시간": times})
