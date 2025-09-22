# fetch_qnet_tabs.py
# 사용:  python fetch_qnet_tabs.py --jmcd 1320 --inst R013 --out data/chansol_api
from __future__ import annotations
from pathlib import Path
import requests, argparse

BASE = "https://q-net.or.kr"

# 탭 → (endpoint id, 구분코드)
TABS = {
    "basic_info": ("crf00503s01", "A0"),     # 기본정보
    "exam_info": ("crf00503s02", "B0"),      # 시험정보
    "preference": ("crf00503s03", "C0"),     # 우대현황
}

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--jmcd", required=True)          # 예: 1320
    ap.add_argument("--inst", default="R013")         # 기관코드: 상세화면 주소창에서 보던 값
    ap.add_argument("--out", default="data/chansol_api")
    args = ap.parse_args()

    out_root = Path(args.out).resolve() / args.jmcd
    out_root.mkdir(parents=True, exist_ok=True)

    s = requests.Session()
    s.headers.update({
        "User-Agent": "Mozilla/5.0",
        "Accept": "text/html,*/*;q=0.01",
    })

    # 1) 상세 Doc 먼저 GET 해서 세션/쿠키를 얻는다 (JSESSIONID 등)
    doc_url = f"{BASE}/crf005.do?jmCd={args.jmcd}&instCd={args.inst}"
    r = s.get(doc_url, timeout=20)
    r.raise_for_status()
    # (참고) 여기 응답에는 탭 본문이 없고, 아래 POST가 진짜 본문을 준다.

    # 2) 탭 3개를 POST로 가져오기
    for tab, (endpoint, div_code) in TABS.items():
        url = f"{BASE}/crf005.do?id={endpoint}"
        # DevTools → Payload에서 본 폼필드 최소셋
        data = {
            "id": endpoint,
            "gSite": "Q",
            "gId": "",           # 없어도 됨
            "jmCd": args.jmcd,
            "jmInfoDivCcd": div_code,   # A0/B0/C0
            # "jmNm": "정보처리기사",    # 없어도 동작. 필요시 추가
        }
        hdrs = {
            "Referer": doc_url,
            "Origin": BASE,
        }
        resp = s.post(url, data=data, headers=hdrs, timeout=20)
        ok = resp.ok and ("No service" not in resp.text)
        print(f"[{tab:11}] {resp.status_code} bytes={len(resp.text)} ok={ok}")

        if not ok:
            # 흔한 원인: 세션 만료, 잘못된 inst 코드, 방화벽/보안툴 차단
            (out_root / f"{tab}.error.html").write_text(resp.text, encoding="utf-8")
            continue

        # 3) 저장: {jmcd}/{tab}.html
        (out_root / f"{tab}.html").write_text(resp.text, encoding="utf-8")

    print(f"[DONE] saved to {out_root}")

if __name__ == "__main__":
    main()
