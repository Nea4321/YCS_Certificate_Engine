# -*- coding: utf-8 -*-
# CS_Leaders/tabs/syllabus.py  (compact)

import re
from html import unescape
from bs4 import BeautifulSoup
from typing import List, Dict, Any, Optional, Tuple
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException, NoSuchElementException, StaleElementReferenceException

TABLE_SEL = "table.table1"

# ---------- fetch (default → all iframes) ----------
def _select_table_in_context(driver, timeout=2) -> Optional[str]:
    try:
        WebDriverWait(driver, timeout).until(EC.presence_of_element_located((By.CSS_SELECTOR, TABLE_SEL)))
    except Exception:
        return None
    for t in driver.find_elements(By.CSS_SELECTOR, TABLE_SEL):
        html = t.get_attribute("outerHTML")
        head = (html.split("</thead>", 1)[0] if "<thead" in html else html[:800]).replace(" ", "").lower()
        if (("시험종목" in head or "시험과목" in head or "과목" in head)
                and ("세부항목" in head or "세부" in head)
                and ("내용" in head or "주요내용" in head or "평가범위" in head or "출제범위" in head)):
            return html
    return None

def _scan_iframes(driver, depth=0, max_depth=5, timeout=2) -> Optional[str]:
    if depth > max_depth: return None
    html = _select_table_in_context(driver, timeout)
    if html: return html
    for f in driver.find_elements(By.TAG_NAME, "iframe"):
        try:
            driver.switch_to.frame(f)
            html = _scan_iframes(driver, depth+1, max_depth, timeout)
            if html: return html
        except (StaleElementReferenceException, NoSuchElementException):
            pass
        finally:
            driver.switch_to.default_content()
    return None

def get_exam_scope_table_html(driver, timeout=15) -> str:
    driver.get("https://www.kie.or.kr/kiehomepage/fc/licenceCSLeadersG1?licence=")
    WebDriverWait(driver, timeout).until(EC.presence_of_element_located((By.TAG_NAME, "body")))
    html = _select_table_in_context(driver, 3) or _scan_iframes(driver, 0, 5, 3)
    if not html:
        raise TimeoutException("시험종목/세부항목/내용 헤더를 가진 표를 찾지 못함.")
    return html

# ---------- tiny text utils ----------
_clean = lambda s: re.sub(r"[ \t\r\f\v]+"," ", unescape((s or "").replace("\xa0"," "))).replace("“","").replace("”","").strip()
def _txt(el): return _clean(el.get_text(separator="\n", strip=True)) if el else ""
def _split(text): return [p.strip() for p in re.split(r"\n+", _clean(text)) if p.strip()]

def _parse_subject(s:str)->Tuple[Optional[str],Optional[int]]:
    s=_clean(s); m=re.search(r"(.+?)\s*\(\s*(\d+)\s*문항\s*\)",s)
    return (m.group(1).strip(), int(m.group(2))) if m else (s or None, None)
def _parse_major(s:str)->Tuple[Optional[str],Optional[int]]:
    s=_clean(s); m=re.search(r"(.+?)\s*\(\s*(\d+)\s*%\s*\)",s)
    return (m.group(1).strip(), int(m.group(2))) if m else (s or None, None)

# ---------- grid & header ----------
def _visible(tr): return [td for td in tr.find_all(["th","td"]) if "display:none" not in (td.get("style","").replace(" ","").lower())]

def _grid(table):
    tbody = table.find("tbody") or table
    grid, cellmap, r = [], {}, 0
    for tr in tbody.find_all("tr"):
        if len(grid) <= r: grid.append([])
        row, c, cells, i = grid[r], 0, _visible(tr), 0
        while i < len(cells):
            while c < len(row) and row[c] is not None:
                c += 1
            if c == len(row):
                row.append(None)

            # ✅ 여기 3줄로 분리 (버그 수정)
            el = cells[i]
            rs = int(el.get("rowspan", 1) or 1)
            cs = int(el.get("colspan", 1) or 1)

            info = {"el": el, "rowspan": rs, "colspan": cs, "r0": r, "c0": c}
            for rr in range(r, r + rs):
                while len(grid) <= rr:
                    grid.append([])
                while len(grid[rr]) < c + cs:
                    grid[rr].extend([None] * ((c + cs) - len(grid[rr])))
                for cc in range(c, c + cs):
                    grid[rr][cc] = info
                    cellmap[(rr, cc)] = el
            i += 1
            c += cs
        r += 1
    return grid, cellmap


def _header_indexes(table)->dict:
    thead = table.find("thead")
    header_tr = (thead.find("tr") if thead else table.find("tr")) or None
    labels = [_txt(th) for th in header_tr.find_all(["th","td"])] if header_tr else []
    def find(*keys):
        for i,h in enumerate(labels):
            hh=h.replace(" ","")
            if any(k in hh for k in keys): return i
        return None
    return {
        "subject": find("시험종목","시험과목","과목"),
        "major":   find("주요과목","배점","배점비율"),
        "detail":  find("세부항목","세부"),
        "content": find("주요내용","내용","평가범위","출제범위"),
    } if labels else {"subject":0,"major":None,"detail":1,"content":-1}

# ---------- parse ----------
def parse_exam_scope_table_html(table_html:str)->List[Dict[str,Any]]:
    soup = BeautifulSoup(table_html, "html.parser")
    table = soup.find("table");  grid, cellmap = _grid(table);  col = _header_indexes(table)
    out=[]
    for r in range(len(grid)):
        def pick(c):
            if c is None: return None
            if c == -1: c = len(grid[r])-1
            return cellmap.get((r,c))
        subj_raw, major_raw, detail_raw, content_raw = map(_txt, [pick(col.get("subject")), pick(col.get("major")), pick(col.get("detail")), pick(col.get("content"))])
        if col.get("major") is None and not major_raw and subj_raw:
            _,pct=_parse_major(subj_raw);  major_raw=subj_raw if pct is not None else major_raw
        if not content_raw and detail_raw: content_raw = detail_raw
        if not (subj_raw or major_raw or detail_raw or content_raw): continue
        if "문제유형" in (subj_raw or ""): continue
        subj, cnt = _parse_subject(subj_raw);  major, pct = _parse_major(major_raw);  bullets=_split(content_raw)
        if not (detail_raw or bullets): continue
        out.append({"시험종목":subj,"문항수":cnt,"주요과목":major,"배점비율":pct,"세부항목":detail_raw or None,"내용":bullets})
    return out

# ---------- to standard keys for normalizer ----------
def _to_std_coverage(rows:List[Dict[str,Any]])->List[Dict[str,Any]]:
    std=[]
    for it in rows:
        subj,cnt,major,pct,detail,lines = it.get("시험종목"),it.get("문항수"),it.get("주요과목"),it.get("배점비율"),it.get("세부항목"),(it.get("내용") or [])
        s = f"{subj} ({cnt}문항)" if subj and isinstance(cnt,int) else subj
        g = f"{major}({pct}%)" if major and isinstance(pct,int) else major
        bullets = " · ".join(lines)
        scope = f"{detail} : {bullets}" if detail and bullets else (detail or bullets)
        std.append({
            "종목": s,
            "구분": g,
            "평가범위": scope,

            # ↓ 보조(원본) 필드: prefix를 붙여 충돌 방지
            "_시험종목": subj,
            "_문항수": cnt,
            "_주요과목": major,
            "_배점비율": pct,
            "_세부항목": detail,
            "_내용": lines,
        })
    return std

# ---------- entry ----------
def get_data(driver)->Dict[str,Any]:
    html = get_exam_scope_table_html(driver)
    rows = parse_exam_scope_table_html(html)
    return {"시험내용": {"coverage": _to_std_coverage(rows)}}
