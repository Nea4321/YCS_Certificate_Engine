# -*- coding: utf-8 -*-

import re
from html import unescape
from typing import List, Dict, Any, Optional
from bs4 import BeautifulSoup
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

URL = "https://license.kpc.or.kr/nasec/qlfint/qlfint/selectGtqinfomg.do"

# ───────────── text utils ─────────────
def _clean(s: str) -> str:
    return re.sub(r"[ \t\r\f\v]+", " ", unescape((s or "").replace("\xa0"," "))).strip()

def _txt(el) -> str:
    return _clean(el.get_text(separator=" ", strip=True)) if el else ""

def _join_lines(el) -> str:
    return " ".join([t.strip() for t in el.stripped_strings]) if el else ""

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


def _header_labels(table) -> List[str]:
    thead = table.find("thead")
    header_tr = (thead.find("tr") if thead else table.find("tr") or None)
    return [_txt(cell) for cell in header_tr.find_all(["th", "td"])] if header_tr else []
#th,td를 공백이나 특수문자를 제외하고 새롭게 가지고 오는 함수


def _parse_gtq_subject_table(table_html: str) -> List[Dict[str,Any]]:
    soup = BeautifulSoup(table_html, "html.parser")
    table = soup.find("table")
    grid, cellmap = _grid(table)

    labels = _header_labels(table)
    def find(*keys):
        for i, h in enumerate(labels):
            hh = h.replace(" ", "")
            if any(k in hh for k in keys):
                return i
        return None
    
    idx_subject = find("자격종목", "과목")
    idx_grade = find("등급")
    idx_method = find("문항및시험방법")
    idx_time = find("시험시간")
    idx_ver = find("Version", "버전")

    def pick(r,c):
        if c is None: return None
        return cellmap.get((r,c))
    
    out = []
    current_subject = None
    current_version = None

    for r in range(len(grid)):
        s_el = pick(r, idx_subject)
        g_el = pick(r, idx_grade)
        m_el = pick(r, idx_method)
        t_el = pick(r, idx_time)
        v_el = pick(r, idx_ver)

        if s_el: current_subject = _txt(s_el)
        if v_el: current_version = _join_lines(v_el)

        grade = _txt(g_el) if g_el else None
        method = _join_lines(m_el) if m_el else None
        time_ = _txt(t_el) if t_el else None

        if grade in (None, "", "등급"):
            continue

        # ----- kind / title 분리 -----
        subj = (current_subject or "").strip()
        # 기본값
        kind, title = None, None

        # 1) 괄호 패턴: "GTQi (일러스트)" / "GTQid (인디자인)" 등
        m = re.match(r"^(GTQid|GTQi|GTQ)\s*(?:\(([^)]+)\))?$", subj, flags=re.I)
        if m:
            kind = m.group(1).upper()
            # ()가 있으면 내부를 title로, 없으면 남은 한글/라벨을 title로 추정
            if m.group(2):
                title = m.group(2).strip()
            else:
                # 예: "GTQ 그래픽기술자격" 같이 붙은 라벨 분리
                tail = subj[len(m.group(1)):].strip()
                title = tail if tail else None
        else:
            # 2) 미정형 텍스트: 내부에 키워드가 포함된 경우
            flat = subj.replace(" ", "")
            if "GTQID" in flat.upper():
                kind = "GTQid"
            elif "GTQI" in flat.upper():
                kind = "GTQi"
            elif "GTQ" in flat.upper():
                kind = "GTQ"
            # 남은 한글 라벨을 title로
            title = re.sub(r"^(GTQid|GTQi|GTQ)\s*", "", subj, flags=re.I).strip() or None

        out.append({
            "등급": grade,
            "과목": current_subject,   # 표 원문 그대로 유지
            "ext": {
                "kind": kind,          # GTQ / GTQi / GTQid
                "title": title,        # 그래픽기술자격 / 일러스트 / 인디자인 ...
                "문항및시험방법": method,
                "시험시간": time_,
                "swVersion": current_version,
            }
        })
        
    return out

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

def _extract_subject_table_html(driver) -> Optional[str]:
    return driver.execute_script("""
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
          if (vis) return vis.outerHTML;
        }
        return null;
    """)


# ───────────── entry ─────────────
def get_data(driver, debug_dir: Optional[str] = None) -> Dict[str, Any]:
    driver.set_window_size(1280, 900)
    driver.get(URL)
    WebDriverWait(driver, 10).until(EC.presence_of_element_located((By.TAG_NAME, "body")))

    # 상위 서브탭(시험안내) 보장 (안 눌려도 무해)
    _click_tab(driver, "시험안내")

    # 세 개 제품 탭 순회
    tabs = [
        ("GTQ(그래픽기술자격)",        "Photoshop"),
        ("GTQi(그래픽기술자격 일러스트)", "Illustrator"),
        ("GTQid(그래픽기술자격 인디자인)", "InDesign"),
    ]

    all_syllabus = []
    for label, kw in tabs:
        _click_tab(driver, label)
        _wait_subject_table(driver, 10)                 # 제목 등장 대기
        _wait_subject_table_contains(driver, kw, 10)    # 해당 제품 키워드 대기
        html = _extract_subject_table_html(driver)
        if not html:
           continue
        all_syllabus.extend(_parse_gtq_subject_table(html))


    return {"syllabus": all_syllabus, "coverage": []}