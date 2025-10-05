# fetch_qnet_tabs.py (refactored: flat jmcd layout + centralized img bucket)
from __future__ import annotations
from pathlib import Path, PurePath
import argparse, gzip, random, time, re, csv, hashlib
from urllib.parse import urljoin, urlparse, parse_qs, unquote
from typing import List, Set
import requests
from http.cookiejar import MozillaCookieJar
import os

# ──────────────────────────────────────────────────────────────────────────────
# Config
BASE = "https://q-net.or.kr"
TABS = {
    "basic_info": ("crf00503s01", "A0"),
    "exam_info": ("crf00503s02", "B0"),
    "preference": ("crf00503s03", "C0"),
}
LIST_ENDPOINT = f"{BASE}/crf005.do?id=crf00501s01"
IMG_ACCEPT = "image/avif,image/webp,image/apng,image/*,*/*;q=0.8"

# ──────────────────────────────────────────────────────────────────────────────
# Optional deps
try:
    from selenium import webdriver
    from selenium.webdriver.chrome.options import Options
    from selenium.webdriver.common.by import By
    from selenium.webdriver.support.ui import WebDriverWait
    from selenium.webdriver.support import expected_conditions as EC
except Exception:
    webdriver = None

try:
    from bs4 import BeautifulSoup
except Exception:
    BeautifulSoup = None

# ──────────────────────────────────────────────────────────────────────────────
# IO utils
def save_text(path: Path, text: str):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")

def save_gz(path: Path, text: str):
    path.parent.mkdir(parents=True, exist_ok=True)
    with gzip.open(path, "wb") as f:
        f.write(text.encode("utf-8"))

def log_csv(row: list, log_path: Path):
    log_path.parent.mkdir(parents=True, exist_ok=True)
    new = not log_path.exists()
    with log_path.open("a", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        if new:
            w.writerow(["ts", "inst", "jmcd", "phase", "status", "note"])
        w.writerow(row)

# ──────────────────────────────────────────────────────────────────────────────
# HTTP helpers
def _sleep(min_s=0.25, max_s=0.9):
    time.sleep(random.uniform(min_s, max_s))

def _req_with_retry(fn, max_tries=3, note=""):
    last_err = None
    for i in range(1, max_tries + 1):
        try:
            resp = fn()
            if getattr(resp, "ok", True):
                return resp
        except Exception as e:
            last_err = e
        _sleep(0.4 * i, 0.9 * i)
    raise last_err or RuntimeError(f"request failed: {note}")

def _ensure_abs_https(url: str, base: str) -> str:
    if not url: return url
    u = url.strip()
    if u.startswith("//"):
        u = "https:" + u
    elif u.startswith("/"):
        u = urljoin(base, u)
    elif u.startswith("http://"):
        u = "https://" + u[len("http://"):]
    return u

def _hint_name_from_url(u: str) -> tuple[str, str]:
    try:
        p = urlparse(u)
        q = parse_qs(p.query or "")
        if "fileName" in q and q["fileName"]:
            fn = unquote(q["fileName"][0])
            stem = Path(fn).stem
            ext  = Path(fn).suffix.lstrip(".").lower()
            if stem:
                return stem, (ext or "png")
        stem = Path(p.path).stem
        ext  = Path(p.path).suffix.lstrip(".").lower() or "png"
        if stem:
            return stem, ext
    except:
        pass
    return ("img", "png")

# ──────────────────────────────────────────────────────────────────────────────
# List page → jmCd’s
def fetch_jmcd_list(session: requests.Session, inst: str, qual: str = "T") -> List[str]:
    data = {"div": "3", "examInstiCd": inst, "qualgbCd": qual}
    resp = _req_with_retry(lambda: session.post(
        LIST_ENDPOINT, data=data, timeout=20, headers={"Referer": BASE}
    ), note=f"list {inst}/{qual}")
    html = resp.text

    jmcds: Set[str] = set(re.findall(r"jmCd\s*=\s*['\"]?(\d{4})['\"]?", html))
    if not jmcds and BeautifulSoup is not None:
        soup = BeautifulSoup(html, "html.parser")
        for a in soup.select("a[href*='jmCd=']"):
            m = re.search(r"jmCd=(\d{4})", a.get("href", ""))
            if m:
                jmcds.add(m.group(1))
    return sorted(jmcds)

def _log_cookie_info(sess, cookie_path):
    try:
        p = Path(cookie_path)
        ts = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(p.stat().st_mtime))
        print(f"[cookie] file={p} mtime={ts}")
    except Exception:
        print(f"[cookie] file={cookie_path} (stat failed)")

    jar = getattr(sess, "cookies", None)
    if not jar:
        print("[cookie] NO cookie jar on session")
        return

    all_cookies = list(jar)
    print(f"[cookie] loaded count={len(all_cookies)}")
    for c in all_cookies:
        # 핵심 정보만 한 줄로
        if c.name.upper() in ("JSESSIONID","SESSION","__HOST-","_QNET"):
            print(f"[cookie] {c.domain} {c.path} {c.name}={c.value[:12]}…")

# ──────────────────────────────────────────────────────────────────────────────
# Image downloader & HTML rewriter (stores in out_root/img/<jmcd>/…)
def download_and_rewrite_images(session: requests.Session, html_path: Path, referer: str,
                                jmcd: str, out_root: Path) -> None:
    html = html_path.read_text(encoding="utf-8", errors="ignore")
    img_srcs = re.findall(r'<img[^>]+src=[\'"]([^\'"]+)[\'"]', html, flags=re.IGNORECASE)
    if not img_srcs:
        return

    out_dir = html_path.parent / "images"
    out_dir.mkdir(parents=True, exist_ok=True)

    repl_map = {}  # original → /img/<jmcd>/fname

    for raw in img_srcs:
        abs_u = _ensure_abs_https(raw, BASE)
        stem, ext = _hint_name_from_url(abs_u)
        h = hashlib.sha1(abs_u.encode("utf-8")).hexdigest()[:8]
        local_name = f"{stem}.{h}.{ext}"
        local_path = out_dir / local_name

        if not local_path.exists():
            try:
                r = session.get(
                    abs_u,
                    headers={"Referer": referer or BASE, "Accept": IMG_ACCEPT},
                    timeout=30,
                    stream=True
                )
                r.raise_for_status()
                ctype = (r.headers.get("Content-Type") or "").lower()
                if "image/jpeg" in ctype and not local_name.lower().endswith((".jpg", ".jpeg")):
                    local_name = f"{stem}.{h}.jpg"; local_path = out_dir / local_name
                elif "image/png" in ctype and not local_name.lower().endswith(".png"):
                    local_name = f"{stem}.{h}.png"; local_path = out_dir / local_name

                with open(local_path, "wb") as f:
                    for chunk in r.iter_content(65536):
                        if chunk:
                            f.write(chunk)
                print(f"[img] saved {local_name} <- {abs_u}")
            except Exception as e:
                print(f"[img][warn] fail {abs_u}: {e}")
                continue

        repl_map[raw] = f"/img/{jmcd}/{local_name}"

    if repl_map:
        new_html = re.sub(
            r'(<img[^>]+src=[\'"])([^\'"]+)([\'"])',
            lambda m: m.group(1) + repl_map.get(m.group(2), m.group(2)) + m.group(3),
            html,
            flags=re.IGNORECASE
        )
        html_path.write_text(new_html, encoding="utf-8")

def load_cookies_from_file(session: requests.Session, path: str) -> bool:
    """
    curl이 만든 Netscape 포맷 cookies.txt를 세션으로 주입.
    """
    try:
        cj = MozillaCookieJar()
        cj.load(path, ignore_discard=True, ignore_expires=True)
        # MozillaCookieJar -> requests cookiejar로 옮김
        for c in cj:
            session.cookies.set_cookie(c)
        print(f"[cookies] loaded from {path} ({len(cj)} items)")
        return True
    except Exception as e:
        print(f"[cookies][warn] load failed: {e}")
        return False


def prewarm_session(session: requests.Session) -> bool:
    """
    서버가 WMONID/JSESSIONID를 발급하도록 가벼운 요청 1회.
    """
    try:
        r = session.get(f"{BASE}/crf005.do?id=crf005", timeout=15,
                        headers={"Referer": BASE, "Accept": "text/html,*/*;q=0.01"})
        ok = r.status_code == 200 and len(r.text) > 50
        print(f"[prewarm] status={r.status_code} ok={ok}")
        return ok
    except Exception as e:
        print(f"[prewarm][warn] {e}")
        return False
BAD_MARKERS = ("No service", "서비스 이용 불가")

def looks_like_bad_html(txt: str) -> bool:
    if not txt:
        return True
    t = txt.strip()
    # 길이 임계(너무 짧으면 이상) + 에러 문구 포함 여부
    if len(t) < 800:
        return True
    lo = t.lower()
    return any(m.lower() in lo for m in BAD_MARKERS)


def fetch_tab_with_recovery(session: requests.Session, url: str, data: dict,
                            referer: str, *,
                            allow_prewarm: bool,
                            cookies_path: str | None) -> requests.Response:
    """
    1) 기본 요청
    2) 실패 냄새 나면 prewarm 한번 후 재시도(옵션이면)
    3) 그래도 안 되면 cookies.txt 주입 후 최종 재시도(옵션이면)
    """
    headers = {"Referer": referer, "Origin": BASE}
    # 1차
    resp = _req_with_retry(lambda: session.post(url, data=data, headers=headers, timeout=20),
                           note="tab first try")
    if resp.ok and not looks_like_bad_html(resp.text):
        return resp

    # 2차: prewarm
    if allow_prewarm:
        print("[recover] trying prewarm…")
        prewarm_session(session)
        resp2 = _req_with_retry(lambda: session.post(url, data=data, headers=headers, timeout=20),
                                note="tab after prewarm")
        if resp2.ok and not looks_like_bad_html(resp2.text):
            return resp2

    # 3차: cookies.txt
    if cookies_path:
        print(f"[recover] injecting cookies.txt: {cookies_path}")
        load_cookies_from_file(session, cookies_path)
        resp3 = _req_with_retry(lambda: session.post(url, data=data, headers=headers, timeout=20),
                                note="tab after cookies")
        return resp3

    # 복구 불가 → 그대로 반환
    return resp

# ──────────────────────────────────────────────────────────────────────────────
# Selenium iframe dump (keeps into base_dir)
def dump_frames_with_selenium(doc_url: str, base_dir: Path) -> int:
    if webdriver is None:
        print("[warn] selenium not installed; skip frames")
        return 0

    opt = Options()
    opt.add_argument("--headless=new")
    opt.add_argument("--no-sandbox")
    opt.add_argument("--disable-gpu")
    driver = webdriver.Chrome(options=opt)
    try:
        driver.get(doc_url)
        try:
            WebDriverWait(driver, 5).until(
                EC.presence_of_element_located((By.CSS_SELECTOR, "#contentView .tab a, .tab a"))
            )
            for b in driver.find_elements(By.CSS_SELECTOR, "#contentView .tab a, .tab a"):
                if "시험정보" in (b.text or ""):
                    b.click()
                    break
        except Exception:
            pass

        frs = driver.find_elements(By.CSS_SELECTOR, 'iframe[id^="contents_frame_"]')
        saved = 0
        for fr in frs:
            fr_id = fr.get_attribute("id") or "contents_frame_x"
            idx = fr_id.split("_")[-1]
            src = fr.get_attribute("src") or ""
            if not src:
                try:
                    driver.switch_to.frame(fr)
                    html = driver.page_source
                    driver.switch_to.default_content()
                except Exception:
                    html = ""
            else:
                cur = driver.current_url
                driver.get(src)
                WebDriverWait(driver, 5).until(lambda d: len(d.page_source) > 1000)
                html = driver.page_source
                driver.get(cur)

            if html and ("<img" in html.lower() or "<table" in html.lower()):
                p = base_dir / f"exam_info.frame.{idx}.html"
                save_text(p, html)
                print(f"[frame] saved {p.name} bytes={len(html)}")
                saved += 1
        return saved
    finally:
        driver.quit()

# ──────────────────────────────────────────────────────────────────────────────
# Single jmcd fetch
def run_one_jmcd(session: requests.Session, inst: str, jmcd: str,
                 out_root: Path, frame_mode: str, resume: bool, log_path: Path, args: argparse.Namespace):
    # ★ 저장 경로: 기관 폴더 제거 → chansol_api/<jmcd>
    base_dir = out_root / jmcd
    base_dir.mkdir(parents=True, exist_ok=True)

    # resume: 이미 3탭이 있으면 스킵
    if resume and all((base_dir / f"{t}.html").exists() for t in TABS.keys()):
        print(f"[skip] {jmcd} (already exists)")
        log_csv([time.strftime("%F %T"), inst, jmcd, "all", "skip", "exists"], log_path)
        return

    doc_url = f"{BASE}/crf005.do?jmCd={jmcd}&instCd={inst}"
    try:
        _req_with_retry(lambda: session.get(doc_url, timeout=20), note=f"doc {inst}/{jmcd}")
    except Exception as e:
        print(f"[err] open doc {inst}/{jmcd}: {e}")
        log_csv([time.strftime("%F %T"), inst, jmcd, "open", "error", str(e)], log_path)
        return

    # 탭별 HTML 저장
    for tab, (endpoint, div_code) in TABS.items():
        url = f"{BASE}/crf005.do?id={endpoint}"
        data = {"id": endpoint, "gSite": "Q", "gId": "", "jmCd": jmcd, "jmInfoDivCcd": div_code}
        try:
            resp = fetch_tab_with_recovery(
               session, url, data, referer=doc_url,
               allow_prewarm=args.prewarm,          # ← 옵션에 따라
               cookies_path=args.cookies            # ← 옵션에 따라
            )
            ok = resp.ok and not looks_like_bad_html(resp.text)
            print(f"[{jmcd} {tab:11}] {resp.status_code} bytes={len(resp.text)} ok={ok}")
            if not ok:
               save_text(base_dir / f"{tab}.error.html", resp.text)
               log_csv([time.strftime("%F %T"), inst, jmcd, tab, "error", "bad-html"], log_path)
            else:
               save_text(base_dir / f"{tab}.html", resp.text)
               log_csv([time.strftime("%F %T"), inst, jmcd, tab, "ok", ""], log_path)
        except Exception as e:
            print(f"[err] {tab} {inst}/{jmcd}: {e}")
            log_csv([time.strftime("%F %T"), inst, jmcd, tab, "error", str(e)], log_path)
        _sleep()

    # HTML 내부 이미지 로컬화 + 경로 치환 (/img/<jmcd>/…)
    for stem in ["basic_info", "exam_info", "preference"]:
        p = base_dir / f"{stem}.html"
        if p.exists():
            download_and_rewrite_images(session, p, doc_url, jmcd, out_root)

    # iframes (선택)
    if frame_mode == "selenium":
        try:
            cnt = dump_frames_with_selenium(doc_url, base_dir)
            print(f"[frames] {jmcd} dumped {cnt} frames")
            log_csv([time.strftime("%F %T"), inst, jmcd, "frames", "ok", f"cnt={cnt}"], log_path)
            for fp in base_dir.glob("exam_info.frame.*.html"):
                download_and_rewrite_images(session, fp, doc_url, jmcd, out_root)
        except Exception as e:
            print(f"[err] frames {inst}/{jmcd}: {e}")
            log_csv([time.strftime("%F %T"), inst, jmcd, "frames", "error", str(e)], log_path)

# ──────────────────────────────────────────────────────────────────────────────
# Main
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--jmcd", help="단일 jmCd 디버그용 (없으면 리스트 모드)")
    ap.add_argument("--inst", default="R013",
                    help="기관 코드(쉼표구분): 예) R013,R139,N004,P317")
    ap.add_argument("--qual", default="T",
                    help="자격구분(쉼표구분 가능): 예) T,P,N")
    ap.add_argument("--out", default="data/chansol_api", help="출력 루트")
    ap.add_argument("--frame-mode", choices=["off", "selenium"], default="off",
                    help="iframe 본문 저장 방식")
    ap.add_argument("--resume", action="store_true",
                    help="이미 저장된 jmCd/탭은 스킵")
    # main()의 argparse 설정에 옵션 2개 추가
    ap.add_argument("--prewarm", action="store_true",
                help="시작 시 세션 예열(프리워밍) 1회 수행")
    ap.add_argument("--cookies", help="Netscape 포맷 cookies.txt 경로 (WMONID/JSESSIONID 주입)")
    args = ap.parse_args()

    out_root = Path(args.out).resolve()
    log_path = out_root / "_logs" / "fetch_log.csv"

    s = requests.Session()
    s.headers.update({"User-Agent": "Mozilla/5.0", "Accept": "text/html,*/*;q=0.01"})

    # main()에서 Session 만든 직후에 추가
    if args.cookies:
       load_cookies_from_file(s, args.cookies)
    if args.prewarm:
       prewarm_session(s)

    if os.getenv("FETCH_COOKIE_LOG", "0") == "1":
       _log_cookie_info(s, args.cookies or "<none>")   

    inst_list = [x.strip() for x in args.inst.split(",") if x.strip()]
    qual_list = [x.strip() for x in args.qual.split(",") if x.strip()]

    # 단일 jmcd 모드: inst 후보들로 같은 jmcd를 싹 시도
    if args.jmcd:
        for inst in inst_list:
            run_one_jmcd(s, inst, args.jmcd, out_root, args.frame_mode, args.resume, log_path, args)
        print("[DONE] single jmCd mode")
        return
    


    # 리스트 스윕: 기관 × 자격구분
    seen: Set[str] = set()   # 저장 레이아웃이 jmcd 단일이므로 중복 키는 jmcd만
    for inst in inst_list:
        for qual in qual_list:
            try:
                jmcds = fetch_jmcd_list(s, inst, qual)
            except Exception as e:
                print(f"[err] list {inst}/{qual}: {e}")
                log_csv([time.strftime("%F %T"), inst, "-", "list", "error", f"{qual}:{e}"], log_path)
                continue

            print(f"[list] inst={inst} qual={qual} -> {len(jmcds)} jmCd")
            log_csv([time.strftime("%F %T"), inst, "-", "list", "ok", f"{qual}:{len(jmcds)}"], log_path)

            for jm in jmcds:
                if jm in seen:
                    continue
                seen.add(jm)
                run_one_jmcd(s, inst, jm, out_root, args.frame_mode, args.resume, log_path, args)

    print(f"[DONE] total fetched jmcd: {len(seen)}")

if __name__ == "__main__":
    main()
