import re
from html import unescape
from urllib.parse import urljoin
from bs4 import BeautifulSoup
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

# 바리스타 사이트 기준
BASE = "https://www.kca-coffee.org"
URL  = f"{BASE}/cms/FrCon/index.do?MENU_ID=130"   # 바리스타 시험안내 탭

# ───────────── helpers ─────────────
def _norm(s: str) -> str:
    s = unescape(s).replace("\xa0", " ").replace("\u200b", "")
    s = re.sub(r"[ \t\r\f\v]+", " ", s)
    s = re.sub(r"\s*\n\s*", "\n", s)
    return s.strip()

def _txt(el):
    return _norm(el.get_text(separator="\n", strip=True)) if el else ""

def _bullets(cell):
    """<ul><li>…</li></ul>은 리스트로만 수집"""
    items = [_norm(li.get_text(" ", strip=True)) for li in cell.select("li")]
    if not items:
        t = _txt(cell)
        if t:
            items = [t]
    seen, dedup = set(), []
    for it in items:
        if it and it not in seen:
            seen.add(it)
            dedup.append(it)
    return dedup

def _consume_row(tr, cols, prev, left):
    """
    cols: ["자격종목","등급","종류","출제"] 위치 기반 소비 + rowspan 트래킹
    """
    out = {}
    cells = tr.find_all(["th","td"])
    i = 0
    for key in cols:
        if left[key] > 0:
            out[key] = prev[key]
            left[key] -= 1
        else:
            if i < len(cells):
                c = cells[i]
                if key == "출제":
                    out[key] = _bullets(c)
                else:
                    out[key] = _txt(c)
                rs = int(c.get("rowspan", 1) or 1)
                left[key] = max(0, rs - 1)
                i += 1
            else:
                out[key] = prev[key]
        prev[key] = out[key]
    return out

# ───────────── core ─────────────
def parse_exam_content_table(soup: BeautifulSoup):
    """
    바리스타 시험안내 > 평가방법 표 파싱
    반환: {"시험내용": {"syllabus": [...]}}
    """
    # 헤더 매칭: '자격종목/등급/종류/출제범위 및 평가방법'
    target = None
    for tbl in soup.find_all("table"):
        heads = [_txt(th) for th in tbl.select("thead th")]
        h = " ".join(heads)
        if ("자격" in h and "등급" in h and "종류" in h and ("출제범위" in h or "평가방법" in h)):
            target = tbl
            break
    if not target:
        return []

    cols = ["자격종목","등급","종류","출제"]
    prev = {k: "" for k in cols}
    left = {k:  0 for k in cols}

    rows = []
    tbody = target.find("tbody") or target
    for tr in tbody.find_all("tr"):
        row = _consume_row(tr, cols, prev, left)

        items = row.get("출제") or []
        if row["등급"] and row["종류"] and items:
            rows.append({
                "자격종목": row["자격종목"] or "바리스타",
                "등급": row["등급"],               # "1급"/"2급"
                "차수": row["종류"],               # "필기"/"실기"
                "항목": "출제범위 및 평가방법",
                "검정내용": "\n".join(items),
                "검정내용목록": items,
            })
    return rows

def get_data(driver):
    # 페이지 진입
    driver.get(URL)

    # (모바일/응답형이라 가끔 컨텐츠가 지연되므로) 표 로딩 대기
    try:
        WebDriverWait(driver, 10).until(
            EC.presence_of_element_located((By.CSS_SELECTOR, "table"))
        )
    except Exception:
        pass

    soup = BeautifulSoup(driver.page_source, "html.parser")
    syllabus = parse_exam_content_table(soup)
    return {"시험내용": {"syllabus": syllabus}}
