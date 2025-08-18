import time
from bs4 import BeautifulSoup
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

def _get_int(v, default=1):
    try:
        return int(v)
    except:
        return default

def get_data(driver):
    driver.get("https://www.ihd.or.kr/guidecert.do")
    wait = WebDriverWait(driver, 10)

    # ✅ 디지털활용능력 탭 클릭 (정확 매칭 실패 시 contains 폴백)
    try:
        try:
            tab_element = wait.until(
                EC.element_to_be_clickable((By.XPATH, "//a[normalize-space()='디지털활용능력']"))
            )
        except:
            tab_element = wait.until(
                EC.element_to_be_clickable((By.XPATH, "//a[contains(normalize-space(),'디지털') and contains(normalize-space(),'활용')]"))
            )
        driver.execute_script("arguments[0].click();", tab_element)
        # 표 로딩 대기
        wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, "table")))
        time.sleep(0.5)
    except Exception as e:
        return {"시험일정": {"error": f"디지털활용능력 탭/표 로딩 실패: {e}"}}

    soup = BeautifulSoup(driver.page_source, "html.parser")

    # ─────────────────────────────────────────────────────────
    # 1) 정기검정 일정
    # ─────────────────────────────────────────────────────────
    table1 = None
    cap = soup.find("caption", string=lambda t: t and "정기검정" in t)
    if cap:
        table1 = cap.find_parent("table")
    if not table1:
        # 혹시 caption이 없으면 첫 번째 표로 폴백
        tables = soup.find_all("table")
        table1 = tables[0] if tables else None

    result = []
    if table1:
        rows = table1.select("tbody tr")

        # rowspan 트래커 (남은 줄 수 카운트)
        tracker = {
            "subject": {"value": "", "left": 0},  # 종목 (디지털정보활용능력)
            "grade":   {"value": "", "left": 0},  # 등급 (초급/중급/고급)
        }

        for tr in rows:
            cells = tr.find_all("td")
            if not cells:
                continue

            idx = 0

            # 같은 행 안에 종목/등급 셀이 함께 올 수도 있으니 순차 체크
            # 종목
            if idx < len(cells):
                txt = cells[idx].get_text(strip=True)
                if "디지털" in txt and "능력" in txt:  # 종목 텍스트 힌트
                    rs = _get_int(cells[idx].get("rowspan", 1))
                    tracker["subject"] = {"value": txt, "left": rs}
                    idx += 1

            # 등급
            if idx < len(cells):
                txt = cells[idx].get_text(strip=True)
                # '초급/중급/고급' or '초급' 등
                if "급" in txt:
                    rs = _get_int(cells[idx].get("rowspan", 1))
                    tracker["grade"] = {"value": txt, "left": rs}
                    idx += 1

            # 일부 페이지는 종목/등급이 **각각 단독 tr**로 내려오므로,
            # 이 행에 실제 데이터가 없으면 continue
            if len(cells) - idx < 3:
                # 다음 행에서 이어서 읽도록 카운터만 줄여 둠
                if tracker["subject"]["left"] > 0:
                    tracker["subject"]["left"] -= 1
                if tracker["grade"]["left"] > 0:
                    tracker["grade"]["left"] -= 1
                continue

            # 여기부터 데이터 열: 회차, 접수일자, 시험일자, 합격자 발표
            round_text = cells[idx].get_text(strip=True); idx += 1
            apply_text = cells[idx].get_text(strip=True); idx += 1
            exam_text  = cells[idx].get_text(strip=True); idx += 1
            result_text = cells[idx].get_text(strip=True) if idx < len(cells) else ""

            subject = tracker["subject"]["value"]
            grade   = tracker["grade"]["value"]

            result.append({
                "종목": subject or "디지털정보활용능력",
                "등급": grade,                  # 예: '초급/중급/고급'
                "회차": round_text,             # 예: '2501회', '특별검정'
                "접수일자": apply_text,         # 예: '24.12.02.(월) ~ 12.11.(수)'
                "시험일자": exam_text,          # 예: '25.01.18.(토)'
                "합격자 발표": result_text,     # 예: '02.07.(금)'
            })

            # 현재 행을 소화했으니 rowspan 남은 줄 감소
            if tracker["subject"]["left"] > 0:
                tracker["subject"]["left"] -= 1
            if tracker["grade"]["left"] > 0:
                tracker["grade"]["left"] -= 1

    # ─────────────────────────────────────────────────────────
    # 2) 입실 및 시험시간
    # ─────────────────────────────────────────────────────────
    table2 = None
    cap2 = soup.find("caption", string=lambda t: t and "입실 및 시험시간" in t)
    if cap2:
        table2 = cap2.find_parent("table")
    else:
        # 캡션 기준이 아니라면 두 번째 표로 폴백
        tables = soup.find_all("table")
        table2 = tables[1] if len(tables) >= 2 else None

    time_data = []
    if table2:
        for tr in table2.select("tbody tr"):
            cols = [c.get_text(strip=True) for c in tr.find_all(["th", "td"])]
            if len(cols) < 3:
                continue
            time_data.append({
                "교시": cols[0],            # '1교시' ...
                "입실완료시간": cols[1],     # '08:50' ...
                "시험시간": cols[2],         # '09:00 ~ 09:40 (40분)' ...
            })

    return {
        "시험일정": {
            "exam_schedule": {
                "정기검정일정": result,
                "입실 및 시험시간": time_data
            }
        }
    }
