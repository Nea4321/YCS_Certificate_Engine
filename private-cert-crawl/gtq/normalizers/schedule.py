# gtq/normalizers/schedule.py
from __future__ import annotations
from typing import Dict, Any, List, Tuple, Optional
from engine_common.utils_text import _prune

# ───────────────────────────────── helpers ───────────────────────────────── #

def _pick_min(a: Optional[str], b: Optional[str]) -> Optional[str]:
    if a and b:
        return a if a <= b else b
    return a or b

def _pick_max(a: Optional[str], b: Optional[str]) -> Optional[str]:
    if a and b:
        return a if a >= b else b
    return a or b

def _split_time_range(s: str) -> Tuple[Optional[str], Optional[str]]:
    # "09:00~10:30" → ("09:00","10:30")
    import re
    m = re.search(r"(\d{1,2}:\d{2})\s*~\s*(\d{1,2}:\d{2})", s or "")
    return (m.group(1), m.group(2)) if m else (None, None)

def _hm_to_minutes(hm: Optional[str]) -> Optional[int]:
    if not hm or ":" not in hm:
        return None
    try:
        h, m = hm.split(":", 1)
        return int(h) * 60 + int(m)
    except Exception:
        return None

def _duration_minutes(start: Optional[str], end: Optional[str]) -> Optional[int]:
    s = _hm_to_minutes(start); e = _hm_to_minutes(end)
    if s is None or e is None:
        return None
    if e < s:  # 방어코드(자정 교차 등은 없겠지만)
        return None
    return e - s

# ──────────────────────────────── normalizer ─────────────────────────────── #

def normalize_schedule(raw: Dict[str, Any], base_year: int | None = None) -> Dict[str, Any]:
    """
    GTQ 전용 1차 정규화.
    반환 스키마(필수):
      { "정기검정일정": [...], "시험시간": [...] }
    - 정기검정일정: 러너의 필드를 보수적으로 흡수
    - 시험시간: 교시/등급/입실완료시간/시험시간표시 → start/end/durationMin 계산
    """

    root = (raw or {}).get("시험일정", {}) or {}

    # ── 1) 정기검정일정 ──────────────────────────────────────────────────────
    rounds_src = (
        root.get("정기검정일정")                     # 권장(현재 러너)
        or root.get("exam_schedule", {}).get("정기검정일정")  # 과거 호환
        or root.get("exam_schedule")                # 더 옛 포맷
        or []                                       # fallback
    )

    # dict 로 내려오는 과거 포맷 방어
    if isinstance(rounds_src, dict):
        rounds_in: List[Dict[str, Any]] = rounds_src.get("정기검정일정", []) or []
    else:
        rounds_in = rounds_src or []

    out_rounds: List[Dict[str, Any]] = []
    for r in rounds_in:
        if not isinstance(r, dict):
            continue

        # 표시용 문자열(로그/뷰): 다양한 별칭 흡수
        disp_online  = r.get("온라인원서접수표시") or r.get("원서접수표시")
        disp_offline = r.get("방문접수표시")
        disp_admit   = r.get("수험표공고표시")
        disp_result  = r.get("성적공고표시")

        # 시험일(표시용) 별칭 흡수
        disp_exam = (
            r.get("시험일")
            or r.get("시험일자")
            or r.get("시험일자표시")
        )

        # 러너가 제공한 표준 ISO 필드
        on_s, on_e   = r.get("onlineRegisterStart"),  r.get("onlineRegisterEnd")
        off_s, off_e = r.get("offlineRegisterStart"), r.get("offlineRegisterEnd")
        admit_s, admit_e = r.get("admitCardStart"), r.get("admitCardEnd")
        res_s, res_e     = r.get("resultStart"),    r.get("resultEnd")
        exam_iso         = r.get("examDate")

        # 프로젝트 공통: registerStart/End = 온라인/오프라인 접수 범위의 전체합
        reg_s = r.get("registerStart") or _pick_min(on_s, off_s)
        reg_e = r.get("registerEnd")   or _pick_max(on_e, off_e)

        item = _prune({
            "회차": r.get("회차"),
            "시험명": r.get("시험명"),
            "시험일": disp_exam,  # 표시용(YYYY-MM-DD가 내려오므로 그대로 노출)
            "온라인원서접수표시": disp_online,
            "방문접수표시": disp_offline,
            "수험표공고표시": disp_admit,
            "성적공고표시": disp_result,
            # ISO 표준 필드
            "registerStart": reg_s,
            "registerEnd":   reg_e,
            "examDate":      exam_iso,
            "admitCardStart": admit_s,
            "admitCardEnd":   admit_e,
            "resultStart":    res_s,
            "resultEnd":      res_e,
        })

        # 최소 요건 충족 시만 채택
        if item.get("examDate"):
            out_rounds.append(item)

    # ── 2) 시험시간 ─────────────────────────────────────────────────────────
    times_src = (
        root.get("시험시간")          # 현재 러너가 붙이는 위치
        or (raw or {}).get("시험시간")  # 혹시 상위 루트에 있을 수도 있음
        or []
    )

    out_times: List[Dict[str, Any]] = []
    for t in (times_src or []):
        if not isinstance(t, dict):
            continue

        # 입력 가능 키들 흡수
        period  = t.get("교시") or t.get("차수")
        grade   = t.get("등급")
        admit   = t.get("입실완료시간") or t.get("입실")
        display = t.get("시험시간표시") or t.get("시험시간")
        note    = t.get("비고")

        start = t.get("start")
        end   = t.get("end")
        if (not start or not end) and display:
            start, end = _split_time_range(display)

        out_times.append(_prune({
            "교시": period,
            "등급": grade,
            "입실완료시간": admit,
            "시험시간표시": display,
            "start": start,
            "end": end,
            "durationMin": _duration_minutes(start, end),
            "비고": note,
        }))

    return {
        "정기검정일정": out_rounds,
        "시험시간": out_times,
    }
