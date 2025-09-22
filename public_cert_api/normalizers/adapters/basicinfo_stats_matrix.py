from typing import List, Dict, Tuple
from ..utils.text import clean
from ..utils.tables import to_int

def parse_basicinfo_stats_table(tables: List[Dict]) -> Tuple[List[Dict], float]:
    """
    기본정보 > 통계자료(최근 5년) 표에서 연도별 필기/실기 응시·합격·합격률을 추출.
    행: (1차/2차) x (대상/응시/응시율/합격/합격률)
    열: 연도(2020, 2021, ...)
    1차=필기, 2차=실기로 매핑.
    """
    out = []
    for t in tables or []:
        rows = t.get("rows") or []
        if len(rows) < 3:
            continue

        # 헤더에서 연도 후보 추출
        head = [clean(c) for c in rows[0]]
        years = []
        for c in head:
            m = __import__("re").search(r"\b(20\d{2})\b", c)
            if m:
                years.append(int(m.group(1)))
        if not years:
            continue

        joined_head = "".join(head)
        # '통계자료', '최근', '년' 같은 키워드가 있거나, 첫 컬럼이 1차/2차 구조인지 확인
        first_col = [clean(r[0]) if r else "" for r in rows[1:6]]
        if not any(x.startswith("1차") or x.startswith("2차") for x in first_col):
            # 그래도 헤더/셀에 '응시','합격','합격률' 등이 충분히 보이면 계속
            if not any(k in "".join("".join(clean(c) for c in r) for r in rows[:3]) for k in ["응시", "합격", "합격률"]):
                continue

        # 연도별 누적 버킷
        Y = {y: {"연도": y, "필기응시": None, "필기합격": None, "필기합격률": None,
                     "실기응시": None, "실기합격": None, "실기합격률": None} for y in years}

        # 각 데이터 행 파싱
        for r in rows[1:]:
            cs = [clean(c) for c in r]
            if not cs: 
                continue
            stage = cs[0]  # 예: "1차", "응시", "합격", "합격률" 등(행 병합 표에서는 1열이 바뀔 수 있음)

            # 일부 표는 [차수, 항목, year1, year2, ...] 형태
            # 또는 [항목, year1, year2, ...] 형태가 1차 블록/2차 블록으로 이어짐
            # 간단 규칙: 행 블록의 최상단에서 "1차"/"2차"를 기억하여 이후 항목을 그에 매핑
            # 상태 머신
            # ex) ["1차", "대상", 223, 228, ...]
            #     ["", "응시", 191, 191, ...]
            #     ["", "합격", 83, 110, ...]
            #     ["2차", "응시", ...] ...
            is_stage_row = ("1차" in stage) or ("2차" in stage)
            # stage 유지용 static 변수
            if not hasattr(parse_basicinfo_stats_table, "_cur_stage"):
                parse_basicinfo_stats_table._cur_stage = "1차"
            if is_stage_row:
                parse_basicinfo_stats_table._cur_stage = "1차" if "1차" in stage else "2차"
                # 다음 컬럼이 항목일 수 있으니 한 칸 당겨서 재해석
                items = cs[1:]
            else:
                items = cs

            if not items:
                continue

            label = items[0]  # "응시", "합격", "합격률", "응시율", "대상" 등
            vals = items[1:]  # 연도별 값들

            # 맵핑: 1차->필기, 2차->실기
            target = "필기" if parse_basicinfo_stats_table._cur_stage == "1차" else "실기"

            for i, y in enumerate(years):
                v = vals[i] if i < len(vals) else ""
                if not any(ch.isdigit() for ch in v or ""):
                    continue
                if "응시" in label:
                    Y[y][f"{target}응시"] = to_int(v)
                elif "합격률" in label:
                    Y[y][f"{target}합격률"] = v
                elif "합격" in label:
                    Y[y][f"{target}합격"] = to_int(v)
                # "대상", "응시율" 등은 스킵

        # 결과 정리
        ys = sorted(Y)
        for y in ys:
            row = Y[y]
            # 최소 하나라도 값이 있으면 채택
            if any(row[k] is not None for k in row if k != "연도"):
                out.append(row)

    return out, (0.85 if out else 0.0)
