# tabs/qualification.py
import time
from bs4 import BeautifulSoup

def get_data(driver):
    driver.get("https://www.ihd.or.kr/introducesubject1.do")
    time.sleep(2)

    soup = BeautifulSoup(driver.page_source, "html.parser")
    qual_section = soup.find("div", id="tab04")
    if not qual_section:
        return {"qualification": "❌ tab04 섹션을 찾을 수 없습니다."}

    tables = qual_section.find_all("table")
    result = {}

    for idx, table in enumerate(tables):
        headers = [th.get_text(strip=True) for th in table.select("thead th")]
        rows = []
        for tr in table.select("tbody tr"):
            cells = [td.get_text(strip=True) for td in tr.find_all("td")]
            if headers and len(cells) == len(headers):
                row = dict(zip(headers, cells))
                rows.append(row)
            else:
                rows.append(cells)
        
        # 표 제목이 별도로 없기 때문에 인덱스로 구분

        if(idx == 0):
           result["자격활용현황"] = rows

        if(idx == 1):
           result["자격활용처"] = rows    

    return {"qualification": result}
