import re
from html import unescape
from bs4 import BeautifulSoup
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

# ───────────────────────── helpers ─────────────────────────
def _txt(el):
    """텍스트 추출 + 엔티티 복원 + 공백 정리"""
    if not el:
        return ""
    s = unescape(el.get_text(separator="\n", strip=True))
    # 줄바꿈/연속 공백을 한 칸으로
    s = re.sub(r"[ \t\r\f\v]+", " ", s.replace("\xa0", " ")).strip()
    return s

def _consume_row(row, cols, prev, left):
    """
    위치 기반 + rowspan 트래커
    - cols: 각 열의 '의미 이름' 리스트
    - prev: 직전 행의 값들
    - left: 열별 남은 rowspan 카운트
    """
    out = {}
    cells = row.find_all(["th", "td"])
    i = 0
    for key in cols:
        if left[key] > 0:
            out[key] = prev[key]
            left[key] -= 1
        else:
            if i < len(cells):
                val = _txt(cells[i])
                out[key] = val
                rs = int(cells[i].get("rowspan", 1) or 1)
                left[key] = max(0, rs - 1)
                i += 1
            else:
                out[key] = prev[key]
        prev[key] = out[key]
    return out

def _find_table_with_headers(soup: BeautifulSoup, required_keywords):
    """
    thead > th 텍스트를 보고 원하는 표를 찾는다(부분일치 허용).
    """
    for tbl in soup.find_all("table"):
        heads = [ _txt(th) for th in tbl.select("thead th") ]
        if not heads:
            continue
        ok = True
        for kw in required_keywords:
            if not any(kw in h for h in heads):
                ok = False
                break
        if ok:
            return tbl
    return None

def _find_table_after_text(soup: BeautifulSoup, keyword: str):
    """
    '시험시간' 같은 섹션 제목(예: div.title_big, h2/h3/strong) 바로 뒤의 첫 table만 잡는다.
    """
    title = soup.select_one(
        "div.title_big:-soup-contains('시험시간'), "
        "h2:-soup-contains('시험시간'), "
        "h3:-soup-contains('시험시간'), "
        "strong:-soup-contains('시험시간')"
    )

    if not title:
        # 폭넓게 찾되, 너무 앞의 텍스트에 걸리지 않도록 soup 전체에서 첫 매치가 아닌
        # 섹션 제목 후보들 위주로만 찾음
        node = soup.find(lambda t: hasattr(t, 'get_text') and keyword in t.get_text())
        return node.find_next("table") if node else None

    # 제목 바로 다음 형제에서 table을 우선 탐색
    sib = title.find_next_sibling()
    while sib and getattr(sib, "name", None) not in ("table", "div"):
        sib = sib.find_next_sibling()
    if getattr(sib, "name", None) == "table":
        return sib
    if getattr(sib, "name", None) == "div":
        t = sib.find("table")
        if t:
            return t

    # 그래도 못 찾으면 일반 next 탐색
    return title.find_next("table")


def _compact_level_name(s: str):
    """'전산\\n세무1급' -> '전산세무1급' 식으로 정리"""
    return re.sub(r"\s+", "", s)

# ───────────────────── parse: 정기검정일정 ───────────────────
def parse_regular_schedule(soup: BeautifulSoup):
    """
    표 헤더: 종목 및 등급 | 회차 | 원서접수 | 장소공고 | 시험일자 | 발표
    """
    table = _find_table_with_headers(
        soup, ["종목", "회차", "원서접수", "장소공고", "시험일자", "발표"]
    )
    if not table:
        return []

    cols = ["종목및등급", "회차", "원서접수", "장소공고", "시험일자", "발표"]
    prev = {k: None for k in cols}
    left = {k: 0    for k in cols}

    results = []
    tbody = table.find("tbody") or table
    for tr in tbody.find_all("tr"):
        row = _consume_row(tr, cols, prev, left)

        # 회차/시험일자 없는 빈 줄은 스킵
        if not (row["회차"] and row["시험일자"]):
            continue

        results.append({
            # 이 표는 '전산세무 1,2급 / 전산회계 1,2급' 공통 일정이라 등급을 별도로 중복 생성하지 않고 공통으로 둠
            "대상등급": row["종목및등급"],   # 예: '전산세무 1,2급 / 전산회계 1,2급'
            "회차": row["회차"],
            "원서접수": row["원서접수"],   # 예: '01.02 ~ 01.08'
            "장소공고": row["장소공고"],   # 예: '02.03 ~ 02.09'
            "시험일자": row["시험일자"],   # 예: '02.09(일)'
            "발표": row["발표"],           # 예: '02.27(목)'
        })
    return results

# ───────────────────── parse: 시험시간 표 ────────────────────
def parse_exam_time_table(soup: BeautifulSoup):
    table = _find_table_after_text(soup, "시험시간")
    if not table:
        # 폴백: thead에 '종목'만 있어도 허용 (이 표는 '급수'가 thead에 없음)
        table = _find_table_with_headers(soup, ["종목"])
        if not table:
            return []

    # 왼쪽 구분 + 4등급 열 구조
    cols = ["구분", "C1", "C2", "C3", "C4"]
    prev = {k: None for k in cols}
    left = {k: 0    for k in cols}

    tbody = table.find("tbody") or table

    header_levels = None         # 등급 라벨들
    time_row = None              # 'HH:MM ~ HH:MM'
    duration_row = None          # '90분' 등

    # 구분 라벨 매칭을 느슨하게 (개행/공백/붙임표 대응)
    is_level_row = lambda s: bool(s) and re.search(r"급\s*수", s) is not None
    is_time_label = lambda s: bool(s) and re.search(r"시험\s*시간?", s) is not None

    for tr in tbody.find_all("tr"):
        row = _consume_row(tr, cols, prev, left)

        # ① 등급 라벨 행(‘급수’) 찾기
        if header_levels is None and is_level_row(row["구분"]):
            header_levels = [
                _compact_level_name(row["C1"]),
                _compact_level_name(row["C2"]),
                _compact_level_name(row["C3"]),
                _compact_level_name(row["C4"]),
            ]
            continue

        # ② 시험시간(좌측 rowspan=2) 행
        if time_row is None and is_time_label(row["구분"]):
            time_row = [row["C1"], row["C2"], row["C3"], row["C4"]]
            continue

        # ③ 바로 다음 행: 소요시간
        if time_row is not None and duration_row is None:
            duration_row = [row["C1"], row["C2"], row["C3"], row["C4"]]
            break

    # 폴백: 간혹 '급수' 라벨이 누락되면, 첫 행의 4개 셀을 등급으로 간주
    if not header_levels:
        first_tr = tbody.find("tr")
        if first_tr:
            r = _consume_row(first_tr, cols, {k: None for k in cols}, {k: 0 for k in cols})
            cand = [_compact_level_name(r["C1"]), _compact_level_name(r["C2"]),
                    _compact_level_name(r["C3"]), _compact_level_name(r["C4"])]
            if all(cand):
                header_levels = cand

    if not (header_levels and time_row and duration_row):
        return []

    return [
        {"등급": header_levels[i], "시험시간": time_row[i], "소요시간": duration_row[i]}
        for i in range(min(4, len(header_levels)))
    ]

# ─────────────────────── orchestrator ──────────────────────
def get_data(driver):
    """
    전산회계/전산세무 자격 페이지에서
      - 정기검정일정(표1)
      - 시험시간(표2)
    을 파싱해 가벼운 JSON으로 반환.
    """
    # ▶▶ 여기 URL은 실제 전산세무회계 일정 페이지로 교체하세요.
    driver.get("https://license.kacpta.or.kr/m/info/info_diary.aspx")
    # 필요 시 특정 탭 클릭이 있으면 아래에 넣기
    # WebDriverWait(driver, 10).until(EC.element_to_be_clickable((By.XPATH, "..."))).click()

    # 표 로딩 대기(선택)
    try:
        WebDriverWait(driver, 10).until(EC.presence_of_element_located((By.CSS_SELECTOR, "table")))
    except Exception:
        pass

    soup = BeautifulSoup(driver.page_source, "html.parser")

    regular = parse_regular_schedule(soup)
    exam_time = parse_exam_time_table(soup)

    return {
        "시험일정": {
            "정기검정일정": regular,              # 회차별 일정 (공통)
            "시험시간": exam_time  
        }
    }
