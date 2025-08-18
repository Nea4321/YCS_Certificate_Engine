import re
from html import unescape
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from bs4 import BeautifulSoup

def get_exam_scope_table_html(driver):
    driver.get("https://license.kacpta.or.kr/m/info/info_diary.aspx")
    # 제목 요소가 보일 때까지 대기
    title_el = WebDriverWait(driver, 10).until(
        EC.presence_of_element_located((
            By.XPATH,
            "//div[contains(@class,'title_big')][contains(.,'시험종목') and contains(.,'평가범위')]"
        ))
    )
    # 제목 바로 다음에 오는 첫 번째 table만 집어옴
    table_el = title_el.find_element(By.XPATH, "following-sibling::table[1]")
    return table_el.get_attribute("outerHTML")

def _txt(el):
    if not el: return ""
    s = unescape(el.get_text(separator="\n", strip=True))
    return re.sub(r"[ \t\r\f\v]+", " ", s.replace("\xa0"," ")).strip()

def _visible_cells(row):
    cells = []
    for c in row.find_all(["th","td"]):
        style = (c.get("style") or "").replace(" ", "").lower()
        if "display:none" in style:   # 숨김 셀은 무시
            continue
        cells.append(c)
    return cells

def _consume_row(row, cols, prev, left):
    out = {}
    cells = _visible_cells(row)
    i = 0
    for key in cols:
        if left[key] > 0:
            out[key] = prev[key]; left[key] -= 1
        else:
            if i < len(cells):
                val = _txt(cells[i])
                out[key] = val
                rs = int(cells[i].get("rowspan", 1) or 1)
                left[key] = max(0, rs - 1)
                i += 1
            else:
                out[key] = prev[key]
        prev[key] = out[key]
    return out

def _split_item_and_grade(text: str):
    s = re.sub(r"\s+", "", text or "")
    m = re.search(r"(전산)(세무|회계)([12]급)", s)
    return (f"{m.group(1)}{m.group(2)}", m.group(3)) if m else (None, None)

def parse_exam_scope_table_html(table_html: str):
    soup = BeautifulSoup(table_html, "html.parser")
    table = soup.find("table")
    # 이 표는 실제로 5열입니다.
    cols = ["종목", "등급", "구분", "평가범위", "비고"]
    prev = {k: None for k in cols}
    left = {k: 0    for k in cols}

    out = []
    tbody = table.find("tbody") or table
    for tr in tbody.find_all("tr"):
        row = _consume_row(tr, cols, prev, left)

        # 등급/종목이 rowspan으로 분리되므로 둘을 합쳐서 판별
        item, grade = _split_item_and_grade((row.get("등급") or "") + (row.get("종목") or ""))
        if item not in ("전산세무", "전산회계"):
            continue
        if grade not in ("1급", "2급"):
            continue
        gv = (row.get("구분") or "").replace(" ", "")
        if not (("이론" in gv) or ("실무" in gv)):
            continue

        out.append({
            "종목": item,
            "등급": grade,
            "구분": row["구분"],              # 이론/실무
            "평가범위": row.get("평가범위", ""),
            "비고": row.get("비고", "")
        })
    return out


def get_data(driver):
    table_html = get_exam_scope_table_html(driver)
    items = parse_exam_scope_table_html(table_html)
    return {
        "시험내용": {
            "시험종목 및 평가범위": items
        }
    }
