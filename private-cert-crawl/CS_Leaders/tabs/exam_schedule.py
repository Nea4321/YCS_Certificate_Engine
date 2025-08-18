# -*- coding: utf-8 -*-
# exam_scheduler_compact.py

import os, re, json, time
from bs4 import BeautifulSoup
from html import unescape
from typing import Optional, List, Dict

# ── tiny helpers ──
_txt = lambda el: re.sub(r"\s+", " ", unescape((el.get_text(" ", strip=True) if el else "")).replace("\xa0", " ")).strip()

ROUND_RE = re.compile(r"^제\s*\d{1,3}\s*-\s*\d{1,2}\s*회$")
RANGE_RE = re.compile(r"\d{4}\s*년\s*\d{1,2}\s*월\s*\d{1,2}\s*일\s*~\s*\d{4}\s*년\s*\d{1,2}\s*월\s*\d{1,2}\s*일$")
MD_RE    = re.compile(r"^\d{1,2}\s*월\s*\d{1,2}\s*일$")

def _parse_ko_date_range(s: str):
    if not s: return (None, None)
    m = re.search(r"(\d{4})\s*년\s*(\d{1,2})\s*월\s*(\d{1,2})\s*일\s*~\s*(\d{4})\s*년\s*(\d{1,2})\s*월\s*(\d{1,2})\s*일", re.sub(r"\s+"," ",s))
    if not m: return (None, None)
    y1,m1,d1,y2,m2,d2 = map(int, m.groups())
    return (f"{y1:04d}-{m1:02d}-{d1:02d}", f"{y2:04d}-{m2:02d}-{d2:02d}")

def _parse_md_with_year(md: str, ref_year: int, ref_month: Optional[int]=None):
    if not md: return None
    m = re.search(r"(\d{1,2})\s*월\s*(\d{1,2})\s*일", md)
    if not m: return None
    mm, dd = map(int, m.groups())
    year = ref_year + (1 if (ref_month and ref_month >= 11 and mm <= 2) else 0)
    return f"{year:04d}-{mm:02d}-{dd:02d}"

def _find_table_for_schedule(soup: BeautifulSoup):
    # 1) thead가 있는 표에서 헤더 키워드 검사
    for tbl in soup.find_all("table"):
        thead = tbl.find("thead")
        if thead:
            heads = " ".join(_txt(th) for th in thead.find_all(["th","td"]))
            if all(k in heads for k in ["회차"]) and any(k in heads for k in ["접수","원서접수"]) \
               and any(k in heads for k in ["시험","시험일자"]) and any(k in heads for k in ["발표","합격자"]):
                return tbl
    # 2) thead 없으면 첫 tr(th) 헤더 검사
    for tbl in soup.find_all("table"):
        first_tr = tbl.find("tr")
        heads = " ".join(_txt(th) for th in (first_tr.find_all("th") if first_tr else []))
        if heads and ("회차" in heads) and (("접수" in heads) or ("원서접수" in heads)) \
           and (("시험" in heads) or ("시험일자" in heads)) and (("발표" in heads) or ("합격자" in heads)):
            return tbl
    # 3) fallback
    for tbl in soup.find_all("table"):
        if tbl.find("tbody"): return tbl
    return soup.find("table")

# ── core ──
def parse_exam_schedule_html(html: str) -> Dict[str, List[Dict]]:
    soup = BeautifulSoup(html, "html.parser")
    table = _find_table_for_schedule(soup)
    if not table: return {"시험일정": {"정기검정일정": []}}

    tbody = table.find("tbody") or table
    def _is_header(tr): return tr.find("th") is not None and tr.find("td") is None

    rows = []
    for tr in tbody.find_all("tr"):
        if _is_header(tr): continue
        tds = tr.find_all("td")
        if len(tds) < 4: continue
        c0, c1, c2, c3 = [_txt(td) for td in tds[:4]]
        if not (ROUND_RE.match(c0) and RANGE_RE.search(c1) and MD_RE.match(c2) and MD_RE.match(c3)): continue
        rows.append((c0, c1, c2, c3))

    out = []
    for round_label, recv_str, exam_str, res_str in rows:
        rs, re_ = _parse_ko_date_range(recv_str)
        ref_y, ref_m = (int(re_[:4]), int(re_[5:7])) if re_ else (int(rs[:4]), int(rs[5:7]))
        out.append({
            "회차": round_label,
            "원서접수표시": recv_str,
            "시험일자표시": exam_str,
            "발표표시": res_str,
            "registerStart": rs,
            "registerEnd":   re_,
            "examDate":      _parse_md_with_year(exam_str, ref_y, ref_m),
            "resultDate":    _parse_md_with_year(res_str,  ref_y, ref_m),
        })

    # 중복 제거 + 정렬
    seen, uniq = set(), []
    for it in out:
        k = (it["회차"], it["registerStart"], it["registerEnd"], it["examDate"])
        if k in seen: continue
        seen.add(k); uniq.append(it)
    uniq.sort(key=lambda x: (x["examDate"] is None, x["examDate"] or "9999-12-31"))

    return {"시험일정": {"정기검정일정": uniq}}

# ── selenium entry (optional) ──
def get_data(driver, debug_dir=None):
    url = "https://www.kie.or.kr/kiehomepage/fc/licenceSchedule?licence="
    driver.get(url); time.sleep(1.0)
    html = driver.page_source
    data = parse_exam_schedule_html(html)

    if debug_dir and not data["시험일정"]["정기검정일정"]:
        os.makedirs(debug_dir, exist_ok=True)
        with open(os.path.join(debug_dir, "page.html"), "w", encoding="utf-8") as f: f.write(html)
        tbl = _find_table_for_schedule(BeautifulSoup(html, "html.parser"))
        if tbl:
            with open(os.path.join(debug_dir, "table.html"), "w", encoding="utf-8") as f: f.write(str(tbl))
    return data
