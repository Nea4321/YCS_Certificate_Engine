import time
import requests
import os
from dotenv import load_dotenv

# .env 로드
load_dotenv()

# 환경 변수 가져오기
WEBHOOK_URL = os.getenv("DISCORD_WEBHOOK")
LOG_FILE_PATH = "../Spring/app.log"
KEYWORD = "FATAL: Max client connections reached"

if not WEBHOOK_URL:
    raise ValueError("❌ DISCORD_WEBHOOK 환경 변수가 설정되지 않았습니다.")

def send_discord_alert(message: str):
    """디스코드로 알림 전송"""
    data = {
        "content": f"🚨 **DB 연결 실패 발생!**\n주인님, 빨리 오셔야겠는데요..?",
        "username": f"춘식이S"
    }
    try:
        response = requests.post(WEBHOOK_URL, json=data)
        if response.status_code not in (200, 204):
            print(f"❌ 웹훅 전송 실패: {response.status_code} - {response.text}")
        else:
            print("✅ 디스코드 알림 전송 완료")
    except Exception as e:
        print(f"❌ 알림 중 오류: {e}")

def tail_log(file_path):
    """로그 파일을 실시간 감시"""
    with open(file_path, "r", encoding="utf-8") as f:
        f.seek(0, 2)  # 파일 끝으로 이동
        while True:
            line = f.readline()
            if not line:
                time.sleep(0.5)
                continue
            if KEYWORD in line:
                print(f"⚠️ 감지됨: {line.strip()}")
                send_discord_alert(line.strip())

if __name__ == "__main__":
    print("🟢 app.log 감시 시작...")
    try:
        tail_log(LOG_FILE_PATH)
    except KeyboardInterrupt:
        print("\n🟡 감시 종료됨.")
