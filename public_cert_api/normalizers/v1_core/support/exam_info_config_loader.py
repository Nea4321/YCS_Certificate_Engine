# -*- coding: utf-8 -*-
from __future__ import annotations
from pathlib import Path
from typing import Tuple, Dict, Any, List
import itertools, yaml

def _dedupe(xs: List[str]) -> List[str]:
    seen, out = set(), []
    for x in xs or []:
        if x not in seen:
            seen.add(x); out.append(x)
    return out

def _defaults() -> Dict[str, Any]:
    return {
        "fee_headers": ["수수료","검정수수료","응시료","응시수수료","검정료"],
        "written_keys": ["필기"],
        "practical_keys": ["실기","면접","작업형","필답형"],  # 보강
        "extra_tips_keywords": ["원서접수","접수시간","발표","발표시간","상이","참조","유의","안내","공지","문의"],
        "section_map": {
            "출제경향": ["출제경향","출제 경향"],
            "공개문제": ["공개문제","공개 문제","공개문항","공개 문항"],
            "출제기준": ["출제기준","출제 기준","시험기준","시험 기준"],
            "취득방법": ["취득방법","취득 방법","응시방법","응시 방법"],
        },
    }


def _merge(base: Dict[str,Any], user: Dict[str,Any]) -> Dict[str,Any]:
    if not isinstance(user, dict): return base
    out = dict(base)
    for k,v in user.items():
        if isinstance(v, list): out[k] = _dedupe(v)
        elif isinstance(v, dict):
            nv = dict(out.get(k, {})); nv.update(v or {}); out[k] = nv
        else: out[k] = v
    return out

def _derive(data: Dict[str,Any]) -> Dict[str,Any]:
    sm: Dict[str, List[str]] = data.get("section_map") or {}
    # 기존 코드 호환용(3개만 쓰는 함수에도 공급)
    data["section_titles"] = {
        "tendency": sm.get("출제경향", ["출제경향"]),
        "acquire":  sm.get("취득방법", ["취득방법"]),
        "standard": sm.get("출제기준", ["출제기준"]),
    }
    # 경계 후보: 모든 섹션 동의어 + 수수료 계열 + 약간의 일반 토큰
    all_alias = list(itertools.chain.from_iterable(sm.values())) if sm else []
    common = ["시험정보","응시","합격기준","유의사항"]
    data["nxt_titles"] = tuple(_dedupe(all_alias + data["fee_headers"] + common))
    return data

def load_exam_info_config() -> Tuple[tuple, tuple, tuple, tuple, Dict[str, list], tuple, Dict[str, list]]:
    here = Path(__file__).resolve().parents[1]
    yml = here / "configs" / "exam_info_headers.yaml"

    data = _defaults()
    try:
        if yml.exists():
            with yml.open("r", encoding="utf-8") as f:
                user = yaml.safe_load(f) or {}
            data = _merge(data, user)
    except Exception:
        pass

    data = _derive(data)
    # 반환: FEE, WRIT, PRACT, TIP, SEC_TITLES(3개용), NXT_TITLES, SEC_MAP(전체)
    return (
        tuple(data["fee_headers"]),
        tuple(data["written_keys"]),
        tuple(data["practical_keys"]),
        tuple(data["extra_tips_keywords"]),
        data["section_titles"],
        tuple(data["nxt_titles"]),
        data["section_map"],   # ★ 추가
    )
