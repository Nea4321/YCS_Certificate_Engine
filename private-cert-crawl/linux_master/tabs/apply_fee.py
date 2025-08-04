from bs4 import BeautifulSoup
import time

def get_data(driver):
    driver.get("https://www.ihd.or.kr/introducesubject1.do")
    time.sleep(2)

    # 리눅스마스터 탭 클릭
    driver.find_element("xpath", "//a[text()='리눅스마스터']").click()
    time.sleep(2)

    soup = BeautifulSoup(driver.page_source, "html.parser")
    fee_section = soup.find("h3", string=lambda t: t and "응시지역" in t)
    structured_data = {}

    if not fee_section:
        return {"apply_fee": structured_data}

    table = fee_section.find_next("table")
    if not table:
        return {"apply_fee": structured_data}

    # ✅ 응시자격 공통 텍스트 추출 (rowspan=4)
    qualification_text = ""
    q_cell = table.find("td", {"rowspan": "4"})
    if q_cell:
        qualification_text = " ".join(q_cell.stripped_strings)

    current_grade = None
    current_location = None
    for row in table.select("tbody tr"): #tbody에 tr이 있는지 확인하는 코드이다.
        cells = row.find_all(["td", "th"])
        texts = [cell.get_text(strip=True) for cell in cells]
        if not texts:
            continue

        if cells[0].name == "th" and "rowspan" in cells[0].attrs:#일반적으로 등급의 th엔 rowspan이 되서 합쳐지는 행이 있는경우가 있기에 attrs를 이용해 알아본다 즉 등급이 있고 없고의 차이를 조건으로 썼다
            if len(texts) < 4:
                continue
            grade, round_, fee, location = texts[:4]
            current_grade = grade
            current_location = location
        else:
            if len(texts) < 2:
                continue
            grade = current_grade
            round_ = texts[0]
            fee = texts[1]
            if len(texts) >= 3:
                location = texts[2]
                current_location = location
            else:
                location = current_location    

        if grade not in structured_data:
            structured_data[grade] = {}

        structured_data[grade][round_] = {
            "fee": fee,
            "location": location,
            "qualification": qualification_text  # 공통 값 적용
        }

    return {
        "apply_fee": structured_data
    }
