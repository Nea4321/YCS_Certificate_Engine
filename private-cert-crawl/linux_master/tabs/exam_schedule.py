from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from bs4 import BeautifulSoup
import time

def get_data(driver):
    driver.get("https://www.ihd.or.kr/guidecert1.do")
    time.sleep(2)

    try:
        # 리눅스마스터 탭 클릭
        tab_element = WebDriverWait(driver, 10).until(
            EC.presence_of_element_located((By.XPATH, "//a[text()='리눅스마스터']"))
        )
        driver.execute_script("arguments[0].click();", tab_element)

        # 테이블 로딩 대기
        WebDriverWait(driver, 10).until(
            EC.presence_of_element_located((By.CSS_SELECTOR, "table"))
        )
    except Exception as e:
        return {"exam_schedule": f"❌ 리눅스마스터 탭 클릭 또는 표 로딩 실패: {str(e)}"}

    soup = BeautifulSoup(driver.page_source, "html.parser")
    tables = soup.find_all("table")
    if len(tables) < 2:
        return {"exam_schedule": "❌ 테이블 수 부족"}

    # ✅ 첫 번째 테이블: 정기검정일정
    result = []
    tbody = tables[0].find("tbody")
    rows = tbody.find_all("tr") if tbody else []

    current_grade = None
    current_round = None

    for tr in rows:
        tds = tr.find_all("td")
        texts = [td.get_text(strip=True) for td in tds]

        if not texts:
            continue
        
        #현재 등급과 회차는 rowspan이어서 상태를 저장하는 방식의 구조가 반드시 필요하다고 할 수 있다.
        # 등급 추적
        if any("급" in t for t in texts):
            current_grade = next((t for t in texts if "급" in t), current_grade)
            texts = [t for t in texts if "급" not in t]

        # 회차 추적
        if any("회" in t for t in texts):
            current_round = next((t for t in texts if "회" in t), current_round)
            texts = [t for t in texts if "회" not in t]

        if len(texts) >= 4:
            result.append({
                "등급": current_grade,
                "회차": current_round,
                "차수": texts[0],
                "접수일자": texts[1],
                "시험일자": texts[2],
                "합격자 발표": texts[3]
            })

    # ✅ 두 번째 테이블: 입실 및 시험시간
    time_data = []
    tbody2 = tables[1].find("tbody")

    current_grade = None
    current_round = None
    current_arrival = None
    current_exam_time = None

    if tbody2:
        for tr in tbody2.find_all("tr"):
            cells = tr.find_all(["th", "td"])
            texts = [c.get_text(strip=True) for c in cells]

            if not texts:
                continue

            if len(texts) == 4:
                current_grade = texts[0]
                current_round = texts[1]
                current_arrival = texts[2]
                current_exam_time = texts[3]

            #현재의 rowspan으로 봤을 떄 texts가 3일때는 없어도 되지만 확장성을 위해 쓴다.
            elif len(texts) == 3:
                current_round = texts[0]
                current_arrival = texts[1]
                current_exam_time = texts[2]    

            elif len(texts) == 2:
                # 2개짜리인데 첫 번째 값이 '급'이면 등급으로 간주
                if "급" in texts[0]:
                    current_grade = texts[0]
                    current_round = texts[1]
                else:
                    current_round = texts[0]
                    current_arrival = texts[1]

            elif len(texts) == 1:
                if "급" in texts[0]:
                    current_grade = texts[0]
                elif "차" in texts[0]:
                    current_round = texts[0]
                elif ":" in texts[0]:
                    current_arrival = texts[0]
                elif "~" in texts[0]:
                    current_exam_time = texts[0]

            if current_grade and current_round and current_arrival and current_exam_time:
                time_data.append({
                    "급수": current_grade,
                    "차수": current_round,
                    "입실완료시간": current_arrival,
                    "시험시간": current_exam_time
                })
                current_round = None  # 등급은 유지, 회차만 초기화 가능

    return {
        "시험일정": {
            "exam_schedule": {
                "정기검정일정": result,
                "입실 및 시험시간": time_data
            }
        }
    }
