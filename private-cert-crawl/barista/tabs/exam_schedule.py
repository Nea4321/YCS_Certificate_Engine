# digital_information/… 가 아니라 barista/ 탭용 예시
import re
from html import unescape
from bs4 import BeautifulSoup
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

# ───────────── helpers ─────────────
def _txt(el):
    if not el:
        return ""
    s = unescape(el.get_text(separator="\n", strip=True)).replace("\xa0", " ")
    # 공백 정리
    return re.sub(r"[ \t\r\f\v]+", " ", s).strip()

def _consume_row(tr, cols, prev, left):
    """
    열 의미(cols) 순서대로 셀을 소비하면서 rowspan을 추적하는 위치기반 파서.
    - prev: 직전 행 값 (rowspan으로 이어짐)
    - left: 각 열에 남아있는 rowspan 카운트
    """
    out = {}
    cells = tr.find_all(["th", "td"])
    i = 0
    for key in cols:
        if left[key] > 0:
            out[key] = prev[key]
            left[key] -= 1
        else:
            if i < len(cells):
                c = cells[i]
                val = _txt(c)
                rs = int(c.get("rowspan", 1) or 1)
                out[key] = val
                left[key] = max(0, rs - 1)
                i += 1
            else:
                out[key] = prev[key]
        prev[key] = out[key]
    return out

_RX_ROUND = re.compile(r"(\d{1,3})\s*회")
def _pick_round(text):
    m = _RX_ROUND.search(text or "")
    return (m.group(1) + "회") if m else None

# ───────────── 표 파싱 ─────────────
def parse_barista_schedule_table(soup: BeautifulSoup, grade: str):
    """
    바리스타 1/2급 일정 표(필기/실기 2블록)를 '위치기반 + rowspan 트래커'로 파싱.
    컬럼 의미(왼→오): 월 | [필기] 제목 | [필기] 일시 | [실기] 제목 | [실기] 일시
    """
    # 헤더 텍스트에 '필기','실기','제목','일시'가 섞여 있는 표를 찾음
    target = None
    for tbl in soup.find_all("table"):
        heads = [ _txt(th) for th in tbl.select("thead th") ]
        if heads and any("필기" in h for h in heads) and any("실기" in h for h in heads):
            target = tbl
            break
    if not target:
        return []

    cols = ["월", "필기_항목", "필기_일시", "실기_항목", "실기_일시"]
    prev = {k: "" for k in cols}
    left = {k: 0  for k in cols}

    results = []
    tbody = target.find("tbody") or target
    for tr in tbody.find_all("tr"):
        row = _consume_row(tr, cols, prev, left)

        # 필기 이벤트 생성
        if row["필기_항목"] or row["필기_일시"]:
            title = row["필기_항목"]
            item = {
                "등급": grade,
                "차수": "필기",
                "구분": "필기",
                "월": row["월"],
                "항목": title,
                "시험일자표시": row["필기_일시"],
                "회차": _pick_round(title)
            }
            results.append(item)

        # 실기 이벤트 생성
        if row["실기_항목"] or row["실기_일시"]:
            title = row["실기_항목"]
            item = {
                "등급": grade,
                "차수": "실기",
                "구분": "실기",
                "월": row["월"],
                "항목": title,
                "시험일자표시": row["실기_일시"],
                "회차": _pick_round(title)
            }
            results.append(item)

    # 완전 빈 행(제목/일시 모두 없음)만 필터
    results = [r for r in results if (r["항목"] or r["시험일자표시"])]
    return results

# ───────────── 오케스트레이션 ─────────────
def get_barista_grade_schedule(driver, grade: str):
    """
    grade: '1급' | '2급'
    각 등급 페이지로 이동해 표 하나를 파싱해 돌려줌.
    """
    # 등급별 URL (필요시 조정)
    url_map = {
        "1급": "https://kca-coffee.org/cms/FrCon/index.do?MENU_ID=1220",
        "2급": "https://kca-coffee.org/cms/FrCon/index.do?MENU_ID=610",
    }
    driver.get(url_map[grade])

    # 표 로딩 대기(최소 보장)
    try:
        WebDriverWait(driver, 10).until(EC.presence_of_element_located((By.CSS_SELECTOR, "table")))
    except Exception:
        pass

    soup = BeautifulSoup(driver.page_source, "html.parser")
    return parse_barista_schedule_table(soup, grade)

def get_data(driver):
    """
    바리스타 1급/2급 두 페이지를 각각 방문 → 결과를 하나의 배열로 합침.
    이후 상위 스키마에서 '시험일정.정기검정일정'로 넣어 쓰면 됨.
    """
    all_rows = []
    all_rows += get_barista_grade_schedule(driver, "1급")
    all_rows += get_barista_grade_schedule(driver, "2급")

    return {
        "시험일정": {
            "정기검정일정": all_rows
        }
    }
