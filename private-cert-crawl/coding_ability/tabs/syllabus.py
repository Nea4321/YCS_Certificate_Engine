import time
import re
from bs4 import BeautifulSoup
from urllib.parse import urljoin
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

BASE = "https://www.ihd.or.kr"

# --- helpers ---
def _txt_and_imgs(cell):
    # 텍스트 + 이미지 src
    txt = cell.get_text(separator="\n", strip=True)
    imgs = [urljoin(BASE, img.get("src", "")) for img in cell.find_all("img")]
    #imgs = [img.get("src", "") for img in cell.find_all("img")]
    # 텍스트가 없고 이미지만 있으면 표시 텍스트를 만들어 준다
    if not txt and imgs:
        txt = f"(이미지 {len(imgs)}장)"
    return txt, imgs

def _txt(cell):
    # 텍스트만 필요할 때
    return cell.get_text(separator="\n", strip=True)

def _consume_row(row, cols, prev, left, collect_content_imgs=False):
    """
    cols: ["등급","과목","항목","내용","상세"] 또는 ["등급","과목","항목","내용","비고"]
    collect_content_imgs=True 이면 '내용' 열의 이미지 src 리스트를 함께 반환
    """
    row_vals = {}
    row_imgs = []
    cells = row.find_all(["th", "td"])
    i = 0
    for key in cols:
        if left[key] > 0:
            row_vals[key] = prev[key]
            left[key] -= 1
        else:
            if i < len(cells):
                if key == "내용" and collect_content_imgs:
                    t, imgs = _txt_and_imgs(cells[i])
                    row_vals[key] = "" if t == "-" else t
                    row_imgs = imgs
                else:
                    t = _txt(cells[i])
                    row_vals[key] = "" if t == "-" else t
                rs = int(cells[i].get("rowspan", 1) or 1)
                left[key] = max(0, rs - 1)
                i += 1
            else:
                row_vals[key] = prev[key]
        prev[key] = row_vals[key]
    return (row_vals, row_imgs) if collect_content_imgs else (row_vals, None)

def parse_syllabus_from_criteria_section(soup: BeautifulSoup):
    # 섹션 경계: '출제기준' h3 ~ 다음 h3
    h3 = soup.find("h3", string=lambda t: t and "출제기준" in t)
    if not h3:
        return []

    tables = []
    for node in h3.find_all_next():
        if node.name == "h3" and node is not h3:
            break
        if node.name == "table":
            tables.append(node)
    if not tables:
        return []

    results = []

    # ── 1) 첫 번째 표 (1급) ─────────────────────────────────
    if len(tables) >= 1:
        t1 = tables[0]
        cols1 = ["등급","과목","항목","내용","상세"]  # 고정 위치
        prev = {k: None for k in cols1}
        left = {k: 0    for k in cols1}
        tbody = t1.find("tbody") or t1

        for tr in tbody.find_all("tr"):
            vals, _ = _consume_row(tr, cols1, prev, left, collect_content_imgs=False)
            if vals["등급"] and vals["과목"] and vals["항목"] and (vals["내용"] or vals["상세"]):
                results.append({
                    "등급": vals["등급"],
                    "과목": vals["과목"],
                    "검정항목": vals["항목"],
                    "검정내용": vals["내용"],
                    "상세검정내용": vals["상세"] or ""
                })

    # ── 2) 두 번째 표 (2‧3급) ──────────────────────────────
    if len(tables) >= 2:
        t2 = tables[1]
        cols2 = ["등급","과목","항목","내용","비고"]  # 마지막 열이 '비고'
        prev = {k: None for k in cols2}
        left = {k: 0    for k in cols2}

        tbody = t2.find("tbody") or t2
        for tr in tbody.find_all("tr"):
            vals, imgs = _consume_row(tr, cols2, prev, left, collect_content_imgs=True)

            # 내용이 비어도 (이미지 존재 or 비고 존재)이면 유효
            has_content = bool(vals["내용"]) or (imgs and len(imgs) > 0)
            has_remark  = bool(vals["비고"])
        
            if vals["등급"] and vals["과목"] and vals["항목"] and (has_content or has_remark):
                row = {
                    "등급": vals["등급"],
                    "과목": vals["과목"],
                    "검정항목": vals["항목"],
                    "검정내용": vals["내용"],
                    "비고": vals["비고"] or ""  # 비고를 상세로 매핑
                }

                if imgs:
                    row["검정내용_이미지"] =imgs
                results.append(row)    

    return results

def get_data(driver):
    driver.get("https://www.ihd.or.kr/introducesubject8.do")
    wait = WebDriverWait(driver, 10)
    try:
        el = wait.until(EC.element_to_be_clickable((By.XPATH, "//a[normalize-space()='시험내용']")))
        driver.execute_script("arguments[0].click();", el)
        wait.until(EC.presence_of_element_located((By.TAG_NAME, "table")))
        time.sleep(0.4)
    except Exception as e:
        return {"시험내용": {"syllabus": [], "error": f"탭 클릭 실패: {e}"}}

    soup = BeautifulSoup(driver.page_source, "html.parser")
    syllabus = parse_syllabus_from_criteria_section(soup)
    return {"시험내용": {"syllabus": syllabus}}
