from bs4 import BeautifulSoup
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException
from datetime import datetime
import time

def get_data(driver):
    driver.get("https://www.ihd.or.kr/introducesubject1.do")
    time.sleep(2)

    # 리눅스마스터 탭 클릭
    WebDriverWait(driver, 10).until(
        EC.element_to_be_clickable((By.XPATH, "//a[text()='리눅스마스터']"))
    ).click()
    time.sleep(3)

    soup = BeautifulSoup(driver.page_source, "html.parser")

    # 종목명
    title = soup.select_one("h3.field_subTit.mb_15")
    title = title.text.strip() if title else "N/A"

    # 종목 설명
    def get_full_description():
        h3 = soup.find("h3", class_ = "field_subTit mb_15")
        if not h3:
            print("[DEBUG] h3 태그를 찾지 못했습니다.")
            return "N/A"
        
        container_div = h3.find_parent("div", class_ = "pType01 bdBox mb_40")

        if not container_div:
            return "N/A"
        
        texts = []
        h3_found = False

        for elem in container_div.children:
            if not h3_found:
                if elem == h3 or (hasattr(elem, "find") and elem.find("h3")):
                    h3_found = True
                continue

            if hasattr(elem, "get_text"):
               text = elem.get_text(strip=True)
               if text and text != h3.text.strip():
                   texts.append(text)    

        return "\n".join(texts) if texts else "N/A" 
    
    description = get_full_description()

    # 시험과목 테이블
    def parse_exam_table():
        table = soup.find("table")
        levels, current_level, current_stage = [], None, None
        current_duration, current_score, current_pass_criteria = "", "", ""

        for row in table.select("tbody tr"):
            texts = [cell.get_text(strip=True) for cell in row.find_all(["th", "td"])]
            idx = 0
            if "1급" in texts[0] or "2급" in texts[0]:
                current_level = texts[0]
                levels.append({"level": current_level, "stages": []})
                idx += 1
            if idx < len(texts) and ("1차" in texts[idx] or "2차" in texts[idx]):
                current_stage = texts[idx]
                idx += 1
            rest = texts[idx:] + [""] * (5 - len(texts[idx:]))
            current_duration, current_score, current_pass_criteria = rest[2] or current_duration, rest[3] or current_score, rest[4] or current_pass_criteria
            levels[-1]["stages"].append({
                "stage": current_stage,
                "type": rest[0],
                "questions": rest[1],
                "duration": current_duration,
                "score": current_score,
                "pass_criteria": current_pass_criteria
            })
        return levels

    exam_levels = parse_exam_table()

    # 온라인 시험안내
    notices = []
    header = soup.find(string=lambda t: "온라인 시험안내" in t)
    if header:
        for tag in header.find_all_next():
            if tag.name in ["div", "p"] and "fieldPL20" in tag.get("class", []) and "pType01" in tag.get("class", []):
                spans = tag.find_all("span", class_="listStyle01")
                notices = [span.get_text(strip=True) for span in spans] or list(tag.stripped_strings)
                break

    # 리눅스 환경
    written = "커널 4.x이상"
    practical = "Rocky Linux 8.8 (VirtualBox)"
    env = soup.find("div", class_="grayBox")
    if env:
        for p in env.find_all("p"):
            if "stage_1" in p.text: written = p.text.replace("필기 : ", "").strip()
            if "stage_2" in p.text: practical = p.text.replace("실기 : ", "").strip()
    linux_env = {"written": written, "practical": practical}

    # 응시자격
    eligibility_section = soup.find("h3", string="응시자격")
    eligibility_table = eligibility_section.find_next("table") if eligibility_section else None

    stage_1 = "N/A"
    stage_2 = "N/A"

    if eligibility_table:
        text = eligibility_table.get_text(separator="\n", strip=True)
        lines = [line.strip() for line in text.split("\n") if line.strip()]

        for line in lines:
            if line.startswith("1차"):
                stage_1 = line.replace("1차 :", "").strip()
            elif line.startswith("2차"):
                stage_2 = line.replace("2차 :", "").strip()

    eligibility = {
        "stage_1" : stage_1,
        "stage_2" : stage_2
    }            

    # 최종 JSON
    return {
        "category": "종목소개",
        "title": title,
        "issued_by": "한국정보통신진흥협회",
        "license_type": "민간자격",
        "url": "https://www.ihd.or.kr/introducesubject1.do",
        "description": description,
        "exam": {"levels": exam_levels},
        "online_exam": {"notices": notices},
        "linux_environment": linux_env,
        "eligibility": eligibility,
        "crawled_at": datetime.now().isoformat()
    }
