from ..utils.text import clean
from ..utils.tables import to_int
import re
from typing import List, Dict, Tuple
import re
from ..utils.text import clean as _c

YEAR = re.compile(r"^(19|20)\d{2}$")

def _to_int(s):
    s = re.sub(r"[^\d]", "", s or "")
    return int(s) if s else None


STAGE_KEYS = ("1차","2차","1 회","2 회","구분","차수")


def parse_basicinfo_stats_table(tables: list[dict]) -> list[dict] | None:
    """
    기본정보 > 통계자료 표(최근 5년)처럼
    헤더에 연도들이 가로로 놓이고, 본문에 '1차/2차' x '응시/합격/합격률'이
    세로로 배치된 표를 [ {연도, 필기응시, 필기합격, 필기합격률, 실기응시, ...} ] 로 변환.
    """
    for t in tables or []:
        if not isinstance(t, dict):   # <<< 방어 코드
            continue
        rows = t.get("rows") or []
        if len(rows) < 3:
            continue

        # 헤더에서 연도 열 찾기
        header = [_c(x) for x in rows[0]]
        years = []
        for j, h in enumerate(header):
            if YEAR.match(h):
                years.append((j, h))
        if len(years) < 2:
            continue  # 연도 헤더가 가로로 2개 이상 있어야 이 어댑터 대상

        # '1차' ~ '2차' 구간을 세로 블록으로 인식
        # (표에 따라 '1 차' 등 공백/스타일 섞이므로 숫자만 본다)
        records = {int(y): {"연도": int(y),
                            "필기응시": None, "필기합격": None, "필기합격률": None,
                            "실기응시": None, "실기합격": None, "실기합격률": None}
                   for _, y in years}

        current_stage = None  # 1 -> 필기, 2 -> 실기
        for r in rows[1:]:
            cells = [_c(c) for c in r]
            if not any(cells):
                continue

            # 왼쪽 두 칸 중 하나에 '1차' 또는 '2차' 표지 존재
            left = "".join(cells[:2])
            if "1차" in left or re.search(r"\b1\s*차\b", left):
                current_stage = 1
                continue
            if "2차" in left or re.search(r"\b2\s*차\b", left):
                current_stage = 2
                continue

            # 라벨 행: 응시 / 합격 / 합격률
            label = cells[0] if cells else ""
            if not current_stage or not label:
                continue

            # 각 연도별 값 채우기
            for j, y in years:
                if j >= len(cells):
                    continue
                v = cells[j]
                if "응시" in label:
                    key = "필기응시" if current_stage == 1 else "실기응시"
                    records[int(y)][key] = _to_int(v)
                elif "합격률" in label:
                    key = "필기합격률" if current_stage == 1 else "실기합격률"
                    # 합격률은 원문 유지(%) 포함)
                    records[int(y)][key] = v if re.search(r"\d", v) else None
                elif "합격" in label:
                    key = "필기합격" if current_stage == 1 else "실기합격"
                    records[int(y)][key] = _to_int(v)

        out = [records[int(y)] for _, y in years]
        # 최소 한 해라도 값이 채워졌으면 성공으로 본다
        if any(any(v is not None for k, v in rec.items() if k != "연도") for rec in out):
            return out

    return None

def parse_stage_year_matrix(tables: List[Dict]) -> Tuple[List[Dict], float]:
    # 연도가 가로헤더로 반복 등장하고, 본문에 1차/2차 행이 있는지 확인
    out = []
    score = 0.0
    for t in tables or []:
        if not isinstance(t, dict):   # <<< 방어 코드
            continue
        rows = t.get("rows") or []
        if len(rows) < 3: continue
        head = [clean(c) for c in rows[0]]
        years = []
        for c in head:
            m = re.fullmatch(r"\s*(\d{4})\s*", c or "")
            if m: years.append(int(m.group(1)))
        if len(years) < 3: continue  # 연도형 헤더가 아니면 skip

        # 본문에서 1차/2차 블록 추출
        for r in rows[1:]:
            cs = [clean(c) for c in r]
            if not cs: continue
            stage = cs[0] if any(k in cs[0] for k in STAGE_KEYS) else None
            if not stage: continue
            # 연도 열을 순회하며 응시/합격/합격률을 순차로 or 슬래시 구분 등에서 추출
            # 최소 구현: 숫자/퍼센트 1쌍만 잡아도 long 레코드 구성
            for j, y in enumerate(years, start=1):
                v = cs[j] if j < len(cs) else ""
                cand = to_int(v)
                rate = re.search(r"(\d+(?:\.\d+)?)\s*%?", v)
                rec = {"연도": y, "차수": stage, "필기응시": cand, "필기합격": None,
                       "필기합격률": (rate.group(1)+"%") if rate else None,
                       "실기응시": None, "실기합격": None, "실기합격률": None}
                if any(rec[k] for k in ("필기응시","필기합격률")):
                    out.append(rec)
        if out:
            score = 0.85; break
    return out, score
