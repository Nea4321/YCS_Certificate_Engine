from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from bs4 import BeautifulSoup
import time

def get_data(driver):
    print("✅ 페이지 접속 중...")
    driver.get("https://www.ihd.or.kr/introducesubject.do")
    time.sleep(1)

    try:
        print("⏳ 시험내용 탭 클릭 준비 중...")
        tab = driver.find_element(By.XPATH, '//a[text()="시험내용"]')
        driver.execute_script("arguments[0].click();", tab)
        print("✅ 시험내용 탭 클릭 완료")

        html = driver.execute_script("""
            const headers = [...document.querySelectorAll('h3')];
            for (const h of headers) {
                if (h.textContent.includes("출제가이드")) {
                    const tableWrap = h.nextElementSibling;
                    return tableWrap ? tableWrap.outerHTML : "";
                }
            }
            return "";
        """)

        if not html:
            print("❌ 출제가이드 테이블을 찾을 수 없습니다.")
            return {"syllabus": "출제가이드 테이블이 존재하지 않습니다."}

        print("✅ 출제가이드 테이블 추출 성공")

        soup = BeautifulSoup(html, "html.parser")
        table = soup.find("table")
        if not table:
            return {"syllabus": "출제가이드 테이블 파싱 실패"}

        result = []

        current_subject = None
        current_section = None
        current_detail = None

        for row in table.select("tbody tr"):
            cells = [td.get_text(strip=True) for td in row.find_all(["th", "td"])]
            if not cells:
                continue

            if len(cells) == 3:
                current_subject, current_section, current_detail = cells

            elif len(cells) == 2:
                current_section, current_detail = cells

            elif len(cells) == 1:
                current_detail = cells[0]

            if current_subject and current_section and current_detail:
                result.append({
                    "과목": current_subject,
                    "검정항목": current_section,
                    "검정내용": current_detail
                })
                current_detail = None

        print(f"✅ 출제기준 {len(result)}개 항목 추출 완료")
        return {"syllabus": result}

    except Exception as e:
        print(f"❌ 에러 발생: {str(e)}")
        return {"syllabus": f"크롤링 실패: {str(e)}"}
