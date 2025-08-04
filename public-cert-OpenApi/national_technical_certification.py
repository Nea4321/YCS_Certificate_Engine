import requests
import xml.etree.ElementTree as ET
import json
import math
import time
from datetime import datetime

SERVICE_KEY = "a0k5P95yIy3wa9ybfNiWRceJasYR%2FM1T9%2FvMNUdih%2Fl5F8opLZo6lTfVIOuxaqCqIYXXxsne7PUr2R6poNY8vg%3D%3D"
BASE_URL = "http://openapi.q-net.or.kr/api/service/rest/InquiryAttenQualSVC/getList"
NUM_OF_ROWS = 100


def fetch_page(page_no):
    url = f"{BASE_URL}?serviceKey={SERVICE_KEY}&pageNo={page_no}&numOfRows={NUM_OF_ROWS}"
    try:
        response = requests.get(url, timeout=10)
        response.encoding = 'utf-8'
        if not response.text.strip().startswith("<?xml"):
            print(f"❌ XML 아님 (페이지 {page_no})\n{response.text[:200]}")
            return None
        return ET.fromstring(response.text)
    except Exception as e:
        print(f"⚠️ 예외 발생 (페이지 {page_no}): {e}")
        return None


def parse_items(root):
    items = root.findall(".//item")
    result = []
    for item in items:
        result.append({
            "JmCd": item.findtext("attenJmCd"),
            "certificate_name": item.findtext("jmNm"),
            "recomJmNm1": item.findtext("recomJmNm1"),
            "recomJmNm2": item.findtext("recomJmNm2"),
            "recomJmCd1": item.findtext("recomJmCd1"),
            "recomJmCd2": item.findtext("recomJmCd2"),
            "modiDttm": item.findtext("modiDttm"),#수정일시 이게 null이면 한번도 수정이 안됨
            "regDttm": item.findtext("regDttm"),#등록일시
            "crawled_at": datetime.now().isoformat()
        })
    return result


def crawl_all_pages():
    page_no = 1
    all_data = []
    max_retries = 3
    total_count = 0

    # 첫 페이지에서 totalCount 확인
    # 첫 페이지에서 totalCount 확인
    first_root = fetch_page(1)
    if first_root is None:
       print("❌ 첫 페이지 로딩 실패")
       return []

    total_count_text = first_root.findtext(".//totalCount")
    if total_count_text is None:
       print("❌ totalCount 태그 없음. 응답 확인 필요.")
       print(ET.tostring(first_root, encoding='unicode'))  # 디버깅용
       return []

    total_count = int(total_count_text)
    total_pages = (total_count - 1) // NUM_OF_ROWS + 1


    for page_no in range(1, total_pages + 1):
        for attempt in range(1, max_retries + 1):
            print(f"📄 페이지 {page_no} 요청 중... (시도 {attempt})")
            root = fetch_page(page_no)
            if root is not None:
                items = parse_items(root)
                print(f"📄 페이지 {page_no} → 수신 항목 수: {len(items)}")  # ✅ 추가 
                if items:
                    all_data.extend(items)
                    break  # 성공했으면 다음 페이지로
                else:
                    print(f"⚠️ 페이지 {page_no}에 항목 없음 → 재시도")
            else:
                print(f"⚠️ 페이지 {page_no} 요청 실패 → 재시도")
            time.sleep(1)  # 재시도 간격

    print(f"원본 수집 개수 (중복 포함): {len(all_data)}")
    unique_data = {item['JmCd']: item for item in all_data}
    print(f"중복 제거 후 개수: {len(unique_data)}")
    return all_data


def save_to_json(data):
    if data:
        filename = f"qnet_certificates_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        with open(filename, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        print(f"🎉 총 {len(data)}건 저장 완료 → {filename}")
    else:
        print("⚠️ 저장할 데이터가 없습니다.")


if __name__ == "__main__":
    data = crawl_all_pages()
    save_to_json(data)
