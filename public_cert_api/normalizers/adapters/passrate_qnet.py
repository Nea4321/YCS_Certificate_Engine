# public_cert_api/normalizers/adapters/passrate_qnet.py
from ..utils.text import clean
from ..utils.tables import to_int
import re
from typing import List, Dict, Tuple

def parse_passrate_tables_qnet(tables: List[Dict]) -> Tuple[List[Dict], float]:
    out = []
    for t in (tables or []):
        if not isinstance(t, dict):   # <<< 방어 코드
            continue
        rows = t.get("rows") or []
        if len(rows) < 3:
            continue
        # 2행 헤더 감지
        head2 = None
        for i in range(min(5, len(rows))):
            h1 = "".join(clean(x) for x in rows[i])
            h2 = "".join(clean(x) for x in rows[i+1]) if i+1 < len(rows) else ""
            if ("필기" in h1 and "실기" in h1) and ("응시" in h2 and "합격" in h2):
                head2 = i + 1
                break
        if head2 is None:
            continue

        for r in rows[head2+1:]:
            cs = [clean(c) for c in r]
            m = re.search(r"\b(\d{4})\b", cs[0] if cs else "")
            if not m:
                continue
            year = int(m.group(1))
            out.append({
                "연도": year,
                "필기응시": to_int(cs[1] if len(cs) > 1 else None),
                "필기합격": to_int(cs[2] if len(cs) > 2 else None),
                "필기합격률": cs[3] if len(cs) > 3 else None,
                "실기응시": to_int(cs[4] if len(cs) > 4 else None),
                "실기합격": to_int(cs[5] if len(cs) > 5 else None),
                "실기합격률": cs[6] if len(cs) > 6 else None,
            })
    return out, (0.9 if out else 0.0)

# 과거 이름을 부른 코드 대비용(선택)
parse_qnet_passrate = parse_passrate_tables_qnet
