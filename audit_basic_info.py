# -*- coding: utf-8 -*-
import os, re, json, csv, argparse
from pathlib import Path

# --------- 휴리스틱 ----------
URL_RX = re.compile(r"https?://|\bwww\.")
STATS_TOKENS = ("연도", "응시", "합격", "합격률", "필기", "실기")
MANY_NUMS_RX = re.compile(r"(?:\d{1,3}(?:,\d{3})+|\d{4})")
PCT_RX = re.compile(r"\d+\s*%")

def _read_json(p):
    try:
        with open(p, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return None

def looks_like_stats_noise(txt: str) -> bool:
    if not txt: return False
    hit = sum(1 for t in STATS_TOKENS if t in txt)
    many_nums = len(MANY_NUMS_RX.findall(txt)) >= 6
    has_pct = len(PCT_RX.findall(txt)) >= 4
    return hit >= 3 and (many_nums or has_pct)

def short(txt: str, n=80) -> str:
    if not txt: return ""
    s = re.sub(r"\s+", " ", txt).strip()
    return s if len(s) <= n else s[:n] + "…"

def clean_len(txt: str) -> int:
    return len(re.sub(r"\s+", "", txt or ""))

# 중복/깨짐 탐지: 동일 라인 반복, 한 글자 단위 줄쪼개짐 등
def has_dup_or_choppy_lines(txt: str) -> bool:
    if not txt: return False
    lines = [re.sub(r"\s+", "", L) for L in (txt or "").splitlines() if L.strip()]
    if not lines: return False
    dup = len(lines) != len(set(lines))
    choppy = sum(1 for L in lines if len(L) <= 3) >= max(3, len(lines)//4)
    return dup or choppy

# --------- 점검 로직 ----------
def audit_pair(jm_dir: Path):
    """jmcd 디렉터리에서 *.json vs *.norm.json 비교하여 이슈 리스트 반환"""
    jmcd = jm_dir.name
    raw = _read_json(jm_dir / f"{jmcd}.json")
    norm = _read_json(jm_dir / f"{jmcd}.norm.json")
    issues = []

    if not raw or not norm:
        return [{
            "jmcd": jmcd,
            "title": "",
            "issue": "MISSING_FILE",
            "detail": "원본 또는 정규화 JSON 없음",
            "notes": ""
        }]

    bi_raw = (raw or {}).get("기본정보") or {}
    bi_norm = (norm or {}).get("기본정보") or {}

    title = (raw.get("공통") or {}).get("종목명") or (raw.get("title") or "")
    title = title or ""

    # 1) 수행직무 / 진로및전망 길이/결측
    duties = bi_norm.get("수행직무")
    outlook = bi_norm.get("진로및전망")

    if not duties or clean_len(duties) < 40:
        issues.append(("DUTIES_SHORT_OR_EMPTY", f"len={clean_len(duties or '')}", short(duties or "")))
    if not outlook or clean_len(outlook) < 80:
        issues.append(("OUTLOOK_SHORT_OR_EMPTY", f"len={clean_len(outlook or '')}", short(outlook or "")))

    # 2) outlook 오염(통계/URL/숫자난무)
    if outlook:
        if URL_RX.search(outlook):
            issues.append(("OUTLOOK_CONTAINS_URL", "", short(outlook)))
        if looks_like_stats_noise(outlook):
            issues.append(("OUTLOOK_CONTAINS_STATS_FRAGMENT", "", short(outlook)))
        if has_dup_or_choppy_lines(outlook):
            issues.append(("OUTLOOK_DUP_OR_CHOPPY_LINES", "", short(outlook)))

    # 3) duties 깨짐/중복 라인
    if duties and has_dup_or_choppy_lines(duties):
        issues.append(("DUTIES_DUP_OR_CHOPPY_LINES", "", short(duties)))

    # 4) 통계 테이블/정규화 상충
    raw_stats = bi_raw.get("통계자료") or []
    norm_struct = bi_norm.get("종목별검정현황") or bi_norm.get("stats_struct") or []
    norm_tables = bi_norm.get("통계자료") or bi_norm.get("stats_tables") or []

    # a) 헤더/키워드 있음에도 정규화 비어 있음
    #    (본문에 '통계' 키워드나 '종목별 검정현황' 캡션이 있는데 결과 없음)
    raw_text = "\n".join(str(x) for x in (raw.get("기본정보") or {}).values() if isinstance(x, str))
    has_kw = any(k in (raw_text or "") for k in ("통계", "종목별 검정현황", "종목별검정현황", "최근 5년", "최근5년"))

    if has_kw and not norm_struct and not norm_tables:
        issues.append(("STATS_EXPECTED_BUT_MISSING", "", ""))

    # b) 원본 통계자료 없음인데 정규화는 있음(종목별검정현황 강주입 의심)
    if not raw_stats and norm_struct:
        issues.append(("STATS_STRUCT_WITHOUT_RAW_TABLE", f"norm_struct={len(norm_struct)}", ""))

    # c) 테이블은 있는데 정규화 0
    if raw_stats and not norm_struct:
        issues.append(("STATS_TABLE_PRESENT_BUT_NOT_NORMALIZED", f"raw_tables={len(raw_stats)}", ""))

    # 5) 변천과정/부처 결측
    history = bi_norm.get("변천과정") or bi_norm.get("history_paras") or []
    if isinstance(history, list):
        hlen = len(history)
    else:
        hlen = 0
    if hlen == 0:
        issues.append(("HISTORY_EMPTY", "", ""))

    ministry = bi_norm.get("소관부처명") or bi_norm.get("ministry")
    if not ministry:
        issues.append(("MINISTRY_MISSING", "", ""))

    # 6) 실시기관/URL 라벨이 outlook/duties로 새어들어간 흔적
    for key, text in (("OUTLOOK_LABEL_LEAK", outlook), ("DUTIES_LABEL_LEAK", duties)):
        if text and re.search(r"(홈페이지|기관명|실시기관)\s*[:：]?", text):
            issues.append((key, "", short(text)))

    # 결과 변환
    out_rows = []
    for tag, detail, sample in issues:
        out_rows.append({
            "jmcd": jmcd,
            "title": title,
            "issue": tag,
            "detail": detail,
            "sample": sample
        })
    return out_rows

def main():
    ap = argparse.ArgumentParser(description="기본정보(JSON vs norm.json) 이상징후 점검")
    ap.add_argument("--root", required=True, help="루트 폴더 (예: C:/cert-data/chansol_api)")
    ap.add_argument("--out", default="basic_info_audit.csv", help="결과 CSV 경로")
    args = ap.parse_args()

    root = Path(args.root)
    rows = []
    for d in sorted(root.iterdir(), key=lambda p: p.name):
        if not d.is_dir(): continue
        jm = d.name
        # 디렉토리명 숫자형만 대상
        if not jm.isdigit(): continue
        rows.extend(audit_pair(d))

    if not rows:
        print("문제 후보가 발견되지 않았습니다.")
        return

    outp = Path(args.out)
    with open(outp, "w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["jmcd", "title", "issue", "detail", "sample"])
        w.writeheader()
        for r in rows: w.writerow(r)

    # TOP 이슈 카운트 콘솔 요약
    from collections import Counter
    c = Counter(r["issue"] for r in rows)
    print("=== 기본정보 점검 요약 ===")
    for k, v in c.most_common():
        print(f"{k:40s} : {v}")
    print(f"\nCSV 저장: {outp.resolve()}  (총 {len(rows)} rows)")

if __name__ == "__main__":
    main()
