# public_cert_api/normalizers/v1_core/build_trace.py
from __future__ import annotations
from pathlib import Path
from typing import Dict, List, Tuple
import json
import re

from ..utils.regexes import now_iso
from .build import build_norm  # 네가 쓰는 기존 함수 (교체/수정 없이 그대로 사용)

# ──────────────────────────────────────────────────────────────────────────────
# 내부 유틸 (norm에서 요약값 뽑기)
# ──────────────────────────────────────────────────────────────────────────────
def _fees_meta(norm_exam_info: Dict) -> Dict:
    fees = (norm_exam_info or {}).get("수수료")
    if isinstance(fees, dict):
        w = fees.get("필기")
        p = fees.get("실기")
        matched = []
        if w not in (None, "", []): matched.append("필기")
        if p not in (None, "", []): matched.append("실기")
        return {
            "matched_labels": matched,
            "unmatched_labels": [x for x in ["필기", "실기"] if x not in matched],
            "raw_values": {"필기": w, "실기": p},
            "normalized": {"written": _to_int(w), "practical": _to_int(p)},
            "errors": [] if matched else ["fees_empty"]
        }
    # 문자열 등 기타 케이스
    return {
        "matched_labels": [],
        "unmatched_labels": ["필기","실기"],
        "raw_values": {"raw": fees},
        "normalized": {},
        "errors": ["fees_empty"]
    }

def _to_int(v):
    try:
        if v is None: return None
        s = str(v)
        if not re.search(r"\d", s): return None
        return int(re.sub(r"[^\d]", "", s))
    except:
        return None

def _method_meta(norm_exam_info: Dict) -> Dict:
    txt = (norm_exam_info or {}).get("시험방법") or ""
    phases = []
    if isinstance(txt, str):
        if "필기" in txt: phases.append("필기")
        if "실기" in txt or "면접" in txt: phases.append("실기")
    # 표 영역에도 있을 수 있음
    tbls = ((norm_exam_info or {}).get("표") or {}).get("시험방법") or []
    if tbls and "필기" not in phases: phases.append("필기")
    if tbls and "실기" not in phases: phases.append("실기")

    meta = {
        "phases_found": phases,
        "phase_details": {},               # (정밀 매핑은 추후 확장)
        "unparsed_fragments": [],
        "errors": [] if phases else ["phase_none_payload"]
    }
    return meta

def _sections_meta(norm_exam_info: Dict) -> Dict:
    keys = list((norm_exam_info or {}).keys())
    # 우리가 주요하게 보는 텍스트 섹션이 실제로 있는지
    watched = ["출제경향","관련학과","응시자격","합격기준","시험과목및배점"]
    matched = [k for k in watched if (norm_exam_info or {}).get(k)]
    missed  = [k for k in watched if k not in matched]
    return {"matched_titles": matched, "missed_titles": missed, "notes": []}

def _schedule_meta(norm_obj: Dict) -> Dict:
    sched = (norm_obj or {}).get("시험일정", {})
    table = sched.get("정기검정일정")
    rows = 0
    if isinstance(table, list):
        rows = len(table)
    elif isinstance(table, dict) and "rows" in table:
        rows = len(table.get("rows") or [])
    return {
        "tables_seen": 1 if table else 0,
        "rows_parsed": rows,
        "round_header_hit": bool(rows),
        "date_cells_parsed": 0
    }

# ──────────────────────────────────────────────────────────────────────────────
# 외부로 제공: build_norm_with_trace
# ──────────────────────────────────────────────────────────────────────────────
def build_norm_with_trace(raw: dict, jmcd: str,
                          name: str | None,
                          type_str: str | None,
                          issued_by: str | None) -> Tuple[dict, dict, List[str]]:
    """
    기존 build_norm을 호출해 norm을 만든 뒤,
    norm 기반으로 trace와 issue_tags를 후처리 생성한다.
    """
    norm = build_norm(raw, jmcd, name, type_str, issued_by)

    # 기본 trace 뼈대
    trace = {
        "jmcd": jmcd,
        "timestamp": now_iso(),
        "source_files": {
            "basic_info_html": "basic_info.html.gz",
            "exam_info_html": "exam_info.html.gz",
            "preference_html": "preference.html.gz",
            "raw": "raw.json"
        },
        "basic_info": {},
        "exam_schedule": {},
        "exam_info": {"fees": {}, "exam_method": {}, "sections": {}},
        "preference": {},
        "issues": []
    }
    issues: List[str] = []

    # basic_info
    bi = norm.get("기본정보", {}) or {}
    history = bi.get("변천과정") or []
    trace["basic_info"]["history"] = {
        "rows_parsed": len(history) if isinstance(history, list) else 0,
        "errors": []
    }
    # sections_detected는 현재 스키마에 명시 섹션 키를 바로 사용
    trace["basic_info"]["sections_detected"] = [k for k in ["개요","실시기관","소관부처명","수행직무","진로및전망","종목별검정현황"] if bi.get(k) is not None]

    # exam_schedule
    trace["exam_schedule"] = _schedule_meta(norm)
    if trace["exam_schedule"]["rows_parsed"] == 0:
        issues.append("schedule_empty")

    # exam_info
    ex = norm.get("시험정보", {}) or {}
    trace["exam_info"]["fees"] = _fees_meta(ex)
    if "fees_empty" in (trace["exam_info"]["fees"].get("errors") or []):
        issues.append("fees_empty")

    trace["exam_info"]["exam_method"] = _method_meta(ex)
    if "phase_none_payload" in (trace["exam_info"]["exam_method"].get("errors") or []):
        issues.append("phase_none_payload")

    trace["exam_info"]["sections"] = _sections_meta(ex)

    # preference
    pref = norm.get("우대현황") or {}
    trace["preference"] = {
        "blocks_found": sum(1 for v in (pref.values() if isinstance(pref, dict) else []) if v),
        "issues": []
    }

    trace["issues"] = sorted(set(issues)) or ["none"]
    return norm, trace, sorted(set(issues))
