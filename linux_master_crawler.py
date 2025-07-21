import requests
from bs4 import BeautifulSoup
import json
import urllib3

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

print("🚀 시작됨")
url = "https://www.ihd.or.kr/introducesubject1.do"
headers = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"
}

res = requests.get(url, headers=headers, verify=False)
print("✅ 상태 코드:", res.status_code)

soup = BeautifulSoup(res.text, "html.parser")

info = {}
tab_ids = {
    "종목소개": "tab01",
    "시험내용": "tab02",
    "응시지역 및 수수료": "tab03",
    "자격활용사례": "tab04",
    "교육협력기관": "tab05"
}

for name, tab_id in tab_ids.items():
    div = soup.find("div", id=tab_id)
    if div:
        # ✅ 줄바꿈을 포함해 가독성 있게 저장
        text = div.get_text(separator="\n", strip=True)
        info[name] = text
    else:
        info[name] = "❌ 해당 div를 찾을 수 없음"

with open("linux_master_info.json", "w", encoding="utf-8") as f:
    json.dump(info, f, ensure_ascii=False, indent=4)

print("✅ JSON 저장 완료!")
