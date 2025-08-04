# tabs/training.py
import time
from bs4 import BeautifulSoup

def get_data(driver):
    driver.get("https://www.ihd.or.kr/introducesubject1.do")
    time.sleep(2)

    soup = BeautifulSoup(driver.page_source, "html.parser")
    tab05 = soup.find("div", id="tab05")

    if not tab05:
        return {"training": []}

    table = tab05.find("table")
    if not table:
        return {"training": []}

    # tbody > tr 전체 가져오기
    #trs = table.find("tbody").find_all("tr")

    tbody = table.find("tbody")
    rows = tbody.find_all("tr")
    training_data = []

    # 3개씩 끊어서 parsing
    for row in rows:
        cols = row.find_all("td")
        if len(cols) < 3:
            continue
        
        기관명 = cols[0].get_text(strip=True)
        교육과목= cols[1].get_text(strip=True)
        연락처= cols[2].get_text(strip=True)

        training_data.append({
            "기관명": 기관명,
            "교육과목": 교육과목,
            "연락처": 연락처
        })

    return {"training": training_data}
