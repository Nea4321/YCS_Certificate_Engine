from typing import List, Dict, Tuple, Callable
from .passrate_qnet import parse_passrate_tables_qnet
from .passrate_stage_year import parse_basicinfo_stats_table

# 어댑터 목록: (이름, 파서함수) — 모두 시그니처: fn(tables: List[Dict]) -> Tuple[List[Dict], float] | List[Dict] | None
ADAPTERS: list[tuple[str, Callable]] = [
    ("basicinfo_stats_matrix", parse_basicinfo_stats_table),
    ("qnet_twoheader",        parse_passrate_tables_qnet),
]

def _coerce_tables(x) -> List[Dict]:
    """
    어떤 형태가 오더라도 어댑터에 전달 가능한 List[Dict]('rows' 키 보유)만 반환.
    - dict -> [dict] (rows 없으면 제외)
    - list -> dict만 필터링
    - 그 외(str, None 등) -> []
    """
    out: List[Dict] = []
    if isinstance(x, dict):
        if "rows" in x and isinstance(x["rows"], list):
            out.append(x)
        return out
    if isinstance(x, list):
        for t in x:
            if isinstance(t, dict) and "rows" in t and isinstance(t["rows"], list):
                out.append(t)
        return out
    return out

def run(bi_tables: List[Dict] | None, ex_tables: List[Dict] | None
        ) -> Tuple[List[Dict], list[str], dict]:
    """
    합격통계 테이블 파싱 파이프라인.
    항상 어댑터에는 List[Dict]만 넣는다.
    반환: (rows, adapters_used, meta)
    """
    bi = _coerce_tables(bi_tables)
    ex = _coerce_tables(ex_tables)
    tables = bi + ex

    adapters_used: list[str] = []

    if not tables:  # 전달할 표가 없으면 즉시 종료
        return [], adapters_used, {"confidence": 0.0, "source": None}

    for name, fn in ADAPTERS:
        try:
            r = fn(tables)
        except Exception as e:
            # 어댑터 내부 에러는 삼키고 다음 어댑터로 진행
            # (필요하면 로깅 추가)
            continue

        if not r:
            continue

        if isinstance(r, tuple):
            rows, score = r
            rows = rows or []
            if rows:
                adapters_used.append(name)
                return rows, adapters_used, {"confidence": float(score or 0.0), "source": name}
        else:
            rows = r or []
            if rows:
                adapters_used.append(name)
                return rows, adapters_used, {"confidence": 0.7, "source": name}

    # 아무 어댑터도 매칭 실패
    return [], adapters_used, {"confidence": 0.0, "source": None}
