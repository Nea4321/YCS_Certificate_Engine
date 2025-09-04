# -*- coding: utf-8 -*-

import re
from html import unescape
from typing import List, Dict, Any, Optional
from bs4 import BeautifulSoup
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

URL = "https://license.kpc.or.kr/nasec/qlfint/qlfint/selectItqinfotchnlgyqc.do"

# ───────────── text utils ─────────────
def _clean(s: str) -> str:
    return re.sub(r"[ \t\r\f\v]+", " ", unescape((s or "").replace("\xa0"," "))).strip()

def _txt(el) -> str:
    return _clean(el.get_text(separator=" ", strip=True)) if el else ""

# ───────────── grid (rowspan/colspan aware) ─────────────
def _visible(tr):
    return [cell for cell in tr.find_all(["th", "td"]) if "display:None" not in (cell.get("style", "").replace(" ", "").lower())]
#우선 조건 필터링을 위해 리스트로 반환하고, td를 기준으로 th,td를 싹 다 찾고 style이 display:None이 아닐 때 없으면 빈 값 반환하고, 공백이나 대문자가 섞여있다면 소문자로 변환해서 비교한다.
#즉 diplay:None이 아닌 것만 필터링해서 th,td를 갖고 와야 하기에 리스트로 반환한다.
#display:None이 아닐 때만 하는 이유는 이 때일떄는 브라우저에 숨겨진 데이터이기 때문임
#td for td in tr.find_all(["th", "td"]) -> 이건 th,td를 찾아서 앞에 있는 td란 변수에 넣는다 이떄 이름은 상관없다 

def _grid(table):
    tbody = table.find("tbody") or table
    grid, cellmap, r = [], {}, 0
    for tr in tbody.find_all("tr"):
        if len(grid) <= r: grid.append([])
        row, c, cells, i = grid[r], 0, _visible(tr), 0
        while i < len(cells):
            while c < len(row) and row[c] is not None:
               c += 1
            if c == len(row):
                row.append(None)
            el = cells[i]
            rs = int(el.get("rowspan", 1) or 1)
            cs = int(el.get("colspan", 1) or 1)
            info = {"el": el, "rowspan": rs, "colspan": cs, "r0": r, "c0": c}
            for rr in range(r, r + rs):
                while len(grid) <= rr: grid.append([])
                while len(grid[rr]) < c + cs: grid[rr].extend([None] * ((c + cs) - len(grid[rr])))
                for cc in range(c, c + cs):
                    grid[rr][cc] = info
            i += 1
            c += cs
        r += 1
    # cellmap: 좌표→원소
    cellmap = {(r,c): grid[r][c]["el"] for r in range(len(grid)) for c in range(len(grid[r])) if grid[r][c]} 
    return grid, cellmap                   
#일단 간단하게 tbody에 있는 정보를 갖고오고, len(grid)를 해서 길이를 기준으로 하고 만약 아무것도 없다면 grid 리스트를 추가
#HTML 표를 읽어서 rowspan/colspan까지 전부 풀어낸 2차원 배열과 좌표 매핑을 만들어주는 함수이다.
#cellmap을 써서 좌표로 바로 셀에 접근할 수 있게 한다. ex) cellmap[0][1] -> 무엇무엇 이렇게

def _parse_itq_subject_table(table_html: str) -> List[Dict[str, Any]]:
    soup = BeautifulSoup(table_html, "html.parser")
    table = soup.find("table")
    if not table:
        return []

    # _grid: (grid, cellmap). grid는 각 행의 칸수 배열, cellmap[(r,c)] -> Tag
    grid, cellmap = _grid(table)
    if not grid:
        return []

    nrows = len(grid)
    ncols = max(len(row) for row in grid)

    def tag(r, c):
        return cellmap.get((r, c)) if 0 <= r < nrows and 0 <= c < ncols else None

    def txt(el) -> str:
        return _txt(el) if el else ""

    # 1) 첫 번째 "데이터 행" 찾기: <td>가 하나라도 있는 행부터 데이터를 읽는다.
    r0 = 0
    for r in range(nrows):
        if any((tag(r, c) is not None and tag(r, c).name == "td") for c in range(ncols)):
            r0 = r
            break

    # 2) 내용 기반으로 주요 열 위치(auto-detect)
    def find_col(pred) -> int | None:
        for c in range(ncols):
            for r in range(r0, min(r0 + 16, nrows)):  # 초반 몇 줄만 스캔
                el = tag(r, c)
                if not el or el.name != "td":
                    continue
                t = txt(el)
                if pred(t):
                    return c
        return None

    c_time   = find_col(lambda s: bool(re.search(r"\d+\s*분", s)))
    c_method = find_col(lambda s: "PBT" in s or "CBT" in s or "필기" in s or "실기" in s)
    c_grade  = find_col(lambda s: "등급" in s and ("A등급" in s or "B등급" in s or "\n" in s))

    # grade/method/time가 마지막 3열이라는 가정으로 보완
    if c_grade is None and c_time is not None:
        c_grade  = c_time - 2
        c_method = c_time - 1 if c_method is None else c_method
    if c_time is None and c_grade is not None:
        c_time   = c_grade + 2
        c_method = c_grade + 1 if c_method is None else c_method

    # "프로그램 및 버전" 두 칼럼은 등급 바로 왼쪽 2열
    c_version = (c_grade - 1) if c_grade is not None else None
    c_sw      = (c_grade - 2) if c_grade is not None else None
    c_subject = (c_sw - 1)    if c_sw is not None else None
    c_cate    = (c_subject - 1) if c_subject is not None else None

    out: List[Dict[str, Any]] = []
    cur_cate = None
    cur_sw = None
    cur_ver = None
    cur_grade_list = None
    cur_method = None
    cur_time = None

    for r in range(r0, nrows):
        el_sub = tag(r, c_subject)
        el_cate = tag(r, c_cate)
        el_sw = tag(r, c_sw)
        el_ver = tag(r, c_version)
        el_grade = tag(r, c_grade)
        el_method = tag(r, c_method)
        el_time = tag(r, c_time)

        if el_cate and el_cate.name == "td":
            cur_cate = txt(el_cate)

        if el_sw and el_sw.name == "td":
            cur_sw = txt(el_sw)

        # colspan=2(인터넷 행): sw 셀 하나가 sw+version을 덮는 경우 → 이번 행은 version 비움
        if el_ver and el_ver is el_sw and int(el_sw.get("colspan", 1) or 1) > 1:
            cur_ver = None
        elif el_ver and el_ver.name == "td":
            cur_ver = txt(el_ver)

        if el_grade and el_grade.name == "td":
            g = [x.strip() for x in txt(el_grade).splitlines() if x.strip()]
            cur_grade_list = g or cur_grade_list

        if el_method and el_method.name == "td":
            cur_method = txt(el_method)

        if el_time and el_time.name == "td":
            cur_time = txt(el_time)

        # 과목 셀이 실제 있는 "새 과목" 행에서만 추가
        if not el_sub or el_sub.name != "td":
            continue
        subject = txt(el_sub).strip()
        if not subject or subject in ("-", "자격종목(과목)"):
            continue

        out.append({
            "과목": subject,
            "ext": {
                "title": cur_cate,          # 예: ITQ정보기술자격
                "S/W": cur_sw,              # 한컴오피스 / MS오피스 / (인터넷은 내장브라우저…)
                "공식버전": cur_ver,        # "2020/2022 병행" 등
                "등급목록": cur_grade_list, # ["A등급","B등급","C등급"]
                "시험방식": cur_method,     # PBT
                "시험시간": cur_time,       # 60분
            }
        })

    # dedup(과목, S/W, 공식버전)
    seen, dedup = set(), []
    for it in out:
        k = (it["과목"], it["ext"].get("S/W"), it["ext"].get("공식버전"))
        if k in seen:
            continue
        seen.add(k)
        dedup.append(it)
    return dedup



def _wait_subject_table_contains(driver, keyword: str, timeout: int = 10):
    """현재 보이는 '시험과목' 섹션 안의 table 텍스트에 keyword가 등장할 때까지 대기"""
    kw = keyword.lower()

    def _cond(drv):
        return drv.execute_script("""
            function isVisible(el){
              const s = el ? getComputedStyle(el) : null;
              return !!(el && s && s.display !== 'none' && s.visibility !== 'hidden' && el.offsetParent !== null);
            }
            const headers = [...document.querySelectorAll('h4,h3')]
                .filter(h => h.textContent.includes('시험과목') && isVisible(h));
            for (const h of headers) {
              const candidates = [];
              if (h.parentElement) candidates.push(...h.parentElement.querySelectorAll('table'));
              if (h.nextElementSibling) candidates.push(...h.nextElementSibling.querySelectorAll('table'));
              const vis = candidates.find(t => isVisible(t));
              if (vis) {
                return vis.innerText.toLowerCase().includes(arguments[0]);
              }
            }
            return false;
        """, kw)

    WebDriverWait(driver, timeout).until(_cond)



# ───────────── 탭 클릭 & 표 추출 ─────────────
def _click_tab(driver, text: str) -> bool:
    locs = [
        (By.XPATH, f"//button[normalize-space(.)='{text}']"),
        (By.XPATH, f"//button[contains(normalize-space(.), '{text}')]"),
        (By.XPATH, f"//a[normalize-space(.)='{text}']"),
        (By.XPATH, f"//a[contains(normalize-space(.), '{text}')]"),
    ]
    for by, sel in locs:
        try:
            el = WebDriverWait(driver, 5).until(EC.element_to_be_clickable((by, sel)))
            driver.execute_script("arguments[0].scrollIntoView({block:'center'});", el)
            driver.execute_script("arguments[0].click();", el)
            # 활성화 표시(aria-selected) 있으면 기다리기 (옵션)
            try:
                WebDriverWait(driver, 3).until(lambda d: el.get_attribute("aria-selected") in ("true","1"))
            except Exception:
                pass
            return True
        except Exception:
            pass
    return False


def _wait_subject_table(driver, timeout=10):
    WebDriverWait(driver, timeout).until(
        EC.presence_of_element_located((By.XPATH, "//h4[contains(.,'시험과목')]"))
    )

def _extract_subject_table_html(driver) -> str | None:
    # "시험과목" 제목 바로 아래 table 1개
    h4 = WebDriverWait(driver, 10).until(
        EC.presence_of_element_located((By.XPATH, "//h4[contains(normalize-space(),'시험과목')]"))
    )
    tables = driver.find_elements(By.XPATH, "//h4[contains(normalize-space(),'시험과목')]/following::table[1]")
    return tables[0].get_attribute("outerHTML") if tables else None


# ───────────── entry ─────────────
def get_data(driver, debug_dir: Optional[str] = None) -> Dict[str, Any]:
    driver.set_window_size(1280, 900)
    driver.get(URL)
    WebDriverWait(driver, 10).until(EC.presence_of_element_located((By.TAG_NAME, "body")))

    # 상위 서브탭(시험안내) 보장 (안 눌려도 무해)
    _click_tab(driver, "시험안내")

    #제품 탭 순회
    tabs = [("ITQ",)]

    all_syllabus = []
    for (label,) in tabs:
        _click_tab(driver, label)
        _wait_subject_table(driver, 10)                 # 제목 등장 대기
        _wait_subject_table_contains(driver, "ITQ정보기술자격", 10)    # 해당 제품 키워드 대기
        html = _extract_subject_table_html(driver)
        if not html:
           continue
        all_syllabus.extend(_parse_itq_subject_table(html))

    print("DEBUG html len:", len(html) if html else None)

    items = _parse_itq_subject_table(html or "")
    print("DEBUG parsed items:", len(items))    


    return {"syllabus": all_syllabus, "coverage": []}