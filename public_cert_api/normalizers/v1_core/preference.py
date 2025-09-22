# -*- coding: utf-8 -*-
from __future__ import annotations
from typing import List, Dict
from ..utils.text import clean, dedupe_keep_order

__all__ = ["parse_preference"]

DEF_ALLOW = [
    "종목별 국가기술자격",        # 본 자료는 종목별 국가기술자격...
    "법제처",                    # 법제처(www.law.go.kr) 통해 조사
    "우대현황에 대한 적용",       # 관련법령 담당 부처의 유권해석
    "조문내역을 클릭",            # 국가법령정보센터 확인
]
TABLE_HINTS = ("우대법령", "조문", "활용내용")

def _is_def_line(s: str) -> bool:
    s = clean(s or "")
    if not s:
        return False
    # 안내문 화살표/다이아 기호 포함 시 가중치
    if any(mark in s for mark in ("◇", "※", "▸", "▶")):
        return True
    return any(k in s for k in DEF_ALLOW)

def parse_preference(pr_tabs: Dict, qual_name: str | None) -> Dict:
    """
    우대현황: 정의(문장) + 법령우대(표) 추출
    pr_tabs = {"paragraphs": [...], "tables": [...]}
    """
    paras: List[str] = pr_tabs.get("paragraphs") or []
    tables: List[Dict] = pr_tabs.get("tables") or []

    # --- 정의 추출: 화이트리스트 문장만, 표/제목 만나면 중단 ---
    def_lines: List[str] = []
    for p in paras:
        txt = clean(p)
        if not txt:
            continue
        # 자격명 + '우대현황' 제목을 만나면 정의 수집 종료
        if qual_name and (qual_name in txt and "우대현황" in txt):
            break
        # 표 헤더 힌트가 문장에 섞여 들어오면 정의 수집 종료
        if any(h in txt for h in TABLE_HINTS):
            break
        if _is_def_line(txt):
            def_lines.append(txt)

    definition = " ".join(dedupe_keep_order(def_lines)) or None

    # --- 표(법령우대) 추출 ---
    law_rows: List[Dict] = []
    for t in tables:
        rows = t.get("rows") or []
        if len(rows) < 2:
            continue
        header = [clean(x) for x in rows[0]]
        joined = "".join(header)
        if not any(k in joined for k in TABLE_HINTS):
            continue

        # 안전한 컬럼 인덱스 계산
        i_law = next((i for i, h in enumerate(header) if "법령" in h), 0)
        i_clause = next((i for i, h in enumerate(header) if "조문" in h), 1)
        i_use = next((i for i, h in enumerate(header) if "활용" in h), (2 if len(header) > 2 else 1))

        for r in rows[1:]:
            cells = [clean(c) for c in r]
            if not any(cells):
                continue
            law_rows.append({
                "법령명": cells[i_law] if i_law < len(cells) else None,
                "조문": cells[i_clause] if i_clause < len(cells) else None,
                "활용내용": cells[i_use] if i_use < len(cells) else None
            })

    return {
        "자격명": qual_name,
        "정의": definition,
        "법령우대": law_rows[:200]
    }
