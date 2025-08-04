import sys
import io
sys.stdout = io.TextIOWrapper(sys.stdout.detach(), encoding='utf-8')
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from datetime import datetime
import json

from tabs import overview, syllabus, exam_schedule, qualification, training, apply_fee

def get_driver():
    options = Options()
    #options.add_argument("--headless")
    options.add_argument("--disable-gpu")
    return webdriver.Chrome(options=options)

def main():
    driver = get_driver()
    try:
        full_data = {
            "종목소개": overview.get_data(driver),
            "시험내용": syllabus.get_data(driver),
            "시험일정": exam_schedule.get_data(driver),
            "자격활용사례": qualification.get_data(driver),
            "교육협력기관": training.get_data(driver),
            "응시지역 및 수수료": apply_fee.get_data(driver),
            "crawled_at": datetime.now().isoformat()
        }

        # linux_master/main.py
        output_path = "C:/Graduation_work/YCS_Certificate_Spring/src/main/resources/json/linux_master_full.json"
        print(f"📁 JSON 저장 경로: {output_path}")

        with open(output_path, "w", encoding="utf-8") as f:
             json.dump(full_data, f, ensure_ascii=False, indent=4)

    except Exception as e:
        print("❌ 오류 발생:", e)
        import traceback
        traceback.print_exc()
    finally:
        driver.quit()

if __name__ == "__main__":
    main()
