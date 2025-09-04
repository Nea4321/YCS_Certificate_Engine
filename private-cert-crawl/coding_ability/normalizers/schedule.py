from datetime import datetime
from engine_common.utils_text import _prune
from engine_common.utils_date import _parse_md_range, _parse_one_date, _split_time_range, _minutes_ko

def normalize_schedule(raw: dict, base_year: int | None = None) -> dict:
    """
    반환:
    {
      "정기검정일정":[ { 회차, 등급?, 차수?, 원서접수표시?, 시험일자표시?, 발표표시?,
                        registerStart?, registerEnd?, examDate?, resultDate? }, ... ],
      "시험시간":[ { 등급?, 차수?, 교시?, 입실완료시간?, 시험시간표시?, start?, end?, durationMin? }, ... ]
    }
    -> null/빈값은 제거됨
    """
    base_year = base_year or datetime.now().year

    sched_root = (
        raw.get("시험일정", {}).get("시험일정", {}).get("exam_schedule")
        or raw.get("시험일정", {}).get("exam_schedule")
        or raw.get("시험일정", {})
        or {}
    )

    rounds_in = sched_root.get("정기검정일정") or []
    times_in  = (sched_root.get("시험시간")
                 or sched_root.get("입실 및 시험시간")
                 or [])

    rounds = []
    for r in rounds_in:
        # 표시용 원문(여러 이름 흡수)
        show_register = (r.get("원서접수표시") or r.get("원서접수") or
                         r.get("접수일자") or r.get("접수기간"))
        show_exam   = (r.get("시험일자표시") or r.get("시험일자") or r.get("시험일"))
        show_result = (r.get("발표표시") or r.get("발표") or r.get("발표일") or r.get("합격자 발표"))

        # ISO (이미 있으면 우선 사용)
        rs = r.get("registerStart")
        re_ = r.get("registerEnd")
        ex  = r.get("examDate")
        res = r.get("resultDate")

        if not (rs and re_) and show_register:
            rs, re_ = _parse_md_range(show_register, base_year)
        if not ex and show_exam:
            es, ee = _parse_md_range(show_exam, base_year)
            ex = es or ee
        if not res and show_result:
            res = _parse_one_date(show_result, base_year)

        rounds.append(_prune({
            "회차": r.get("회차"),
            "등급": r.get("등급"),
            "차수": r.get("차수"),
            "원서접수표시": show_register,
            "시험일자표시": show_exam,
            "발표표시": show_result,
            "registerStart": rs,
            "registerEnd": re_,
            "examDate": ex,
            "resultDate": res,
        }))

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
