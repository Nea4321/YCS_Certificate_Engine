from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from bs4 import BeautifulSoup
from html import unescape
import time


def _txt(el):
    return unescape(el.get_text(separator="\n", strip=True)) if el else ""

def _consume_row(row, cols, prev, left):
    out = {}
    cells = row.find_all(["th", "td"])
    i = 0

    for key in cols:
        if left[key] > 0:
            out[key] = prev[key]
            left[key] -= 1
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

def get_data(driver):
    driver.get("https://www.ihd.or.kr/guidecert8.do")
    time.sleep(2)

    try:
        # 코딩활용능력 탭 클릭
        tab_element = WebDriverWait(driver, 10).until(
            EC.presence_of_element_located((By.XPATH, "//a[text()='코딩활용능력']"))
        )
        driver.execute_script("arguments[0].click();", tab_element)

        # 테이블 로딩 대기
        WebDriverWait(driver, 10).until(
            EC.presence_of_element_located((By.CSS_SELECTOR, "table"))
        )
    except Exception as e:
        return {"exam_schedule": f"❌ 코딩활용능력 탭 클릭 또는 표 로딩 실패: {str(e)}"}

    soup = BeautifulSoup(driver.page_source, "html.parser")
    tables = soup.find_all("table")
    if len(tables) < 2:
        return {"exam_schedule": "❌ 테이블 수 부족"}

    # ✅ 첫 번째 테이블: 정기검정일정
    cols = ["종목", "등급", "회차", "접수일자", "시험일자", "합격자 발표"]
    prev = {k: None for k in cols}
    left = {k: 0    for k in cols}

    tables_0 = tables[0]
    rows = tables_0.select("tbody tr")

    result = []

    for tr in rows:
        row = _consume_row(tr, cols, prev, left)  # 너가 만든 함수 재사용
        
        # 필요하면 종목은 버리고 등급/회차/날짜만 저장
        if row["회차"] and row["시험일자"]:
            result.append({
                "등급": row["등급"],
                "회차": row["회차"],                     # '특별검정'도 정상 수집
                "접수일자": row["접수일자"],
                "시험일자": row["시험일자"],
                "합격자 발표": row["합격자 발표"],
            })
            

    # ✅ 두 번째 테이블: 입실 및 시험시간
    time_data = []
    tbody2 = tables[1].find("tbody")

    current_period = None
    current_arrival = None
    current_exam_time = None

    if tbody2:
        for tr in tbody2.find_all("tr"):
            cells = tr.find_all(["th", "td"])
            texts = [c.get_text(strip=True) for c in cells]

            if not texts:
                continue

            #현재의 rowspan으로 봤을 떄 texts가 3일때는 없어도 되지만 확장성을 위해 쓴다.
            if len(texts) == 3:
                current_period = texts[0]
                current_arrival = texts[1]
                current_exam_time = texts[2]    

            elif len(texts) == 2:
                # 2개짜리인데 첫 번째 값이 '급'이면 등급으로 간주
                if "교" in texts[0]:
                    current_period = texts[0]
                    current_arrival = texts[1]
                else:
                    current_arrival = texts[0]
                    current_exam_time = texts[1]

            elif len(texts) == 1:
                if "교" in texts[0]:
                    current_period = texts[0]
                elif ":" in texts[0]:
                    current_arrival = texts[0]
                elif "~" in texts[0]:
                    current_exam_time = texts[0]

            if current_period and current_arrival and current_exam_time:
                time_data.append({
                    "교시": current_period,
                    "입실완료시간": current_arrival,
                    "시험시간": current_exam_time
                })

    return {
        "시험일정": {
            "exam_schedule": {
                "정기검정일정": result,
                "입실 및 시험시간": time_data
            }
        }
    }
