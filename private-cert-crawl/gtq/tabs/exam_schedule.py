import os, re, time
from bs4 import BeautifulSoup
from html import unescape
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

URL = "https://license.kpc.or.kr/nasec/qlfint/qlfint/selectGtqinfomg.do"

def _txt(el):
    s = unescape(el.get_text("", strip=True) if el else "")
    return re.sub(r"\s+"," ", s.replace("\xa0", " " ).strip())
#BeautifulSoup의 메서드인 el.get_text("", strip=True)로 td의 내용 텍스트를 뽑고 앞 뒤 공백 제거하고 unescape로 특수문자 제거
#정규식으로 연속된 모든 공백 문자 \s+를 단일 공백으로 치환함 ex) "안녕 세계\n텍스트" -> "안녕 세계 텍스트"

ROUND_IN_TITLE_RE = re.compile(r"제\s*(\d+)\s*회")
YMD_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
MMDD_RANGE_RE=re.compile(r"(\d{1,2})\.(\d{1,2})\s*~\s*(\d{1,2})\.(\d{1,2})")
#re.compile은 미리 컴파일해서 패턴 객체룰 만들고, r은 raw string(원시 문자열)의 약자이다 이걸 쓰면 \(백슬래시)를 두 번 써서 인식 안 시켜도 됨
#숫자 하나를 넣을 때 \d를 넣어야 숫자라는 것이 되고, ^ 기호는 시작한다는 뜻


def _looks_time_header(th_texts:list[str]) -> bool:
    wants = [
        ("교시",), ("등급",),("입실시간","입실완료시간"),
        ("시험시간",),
    ]
    for alts in wants:
        if not any(any(w in t for w in alts) for t in th_texts):
            return False
    return True
#any(any(w in t for w in alts) for t in th_texts) -> 이건 실제 데이터인 th_texts인 list[str]에서 wants 리스트안에서 튜플 조건을 서로 비교하는
#식으로 any를 이용해 하나라도 맞다면 필요할 때까지 돌다가 True가 나온다.
#th_texts는 th 텍스트 즉 html에서 갖고 온 텍스트 코드이고, wants 리스트안에 alts의 튜플을 각각 꺼내고
#for t in th_texts -> 이걸 통해 헤더의 값들을 꺼내고 ex) "교시", "등급"등등 그 헤더 t 안에 alits가 포함돼있는지 확인
#헤더 t 안에 alts가 있으면 통과 
#여기서 all이 아니라 any를 쓰는데 all을 쓰면 모든 헤더인 th_texts가 각각의 튜플과 값이 같아야 되므로 하나만 같으면 문제 없는 any를 쓴다.
#튜플을 써서 하나의 조건 그룹을 만들고, 불변의 값이라는 걸 알려주기 위해서이다. any로 바꿔서 조건을 좀 더 유연하게 한다.(입실시간, 입실완료시간) -> 얘네 때문이다.

def parse_gtq_exam_times_html(page_html:str) -> list[dict]:
    soup = BeautifulSoup(page_html, "html.parser")

    cand_tables=[]
    for h in soup.find_all(["h3","h4"]):
        if "시험시간" in _txt(h):
            t = h.find_next("table")
            if t:
                cand_tables.append(t)

    if not cand_tables:
        for t in soup.find_all("table"):
            heads = [_txt(th) for th in t.find_all("th")] 
            if _looks_time_header(heads):
                cand_tables.append(t)

    if not cand_tables:
        return []

    table = cand_tables[0]
    tbody = table.find("tbody") or table
    out = []

    cur_period = None
    cur_admit = None
    cur_note = None

    for tr in tbody.find_all("tr"):
        tds = tr.find_all("td")
        if not tds:
            continue
        cells =[_txt(td) for td in tds]

        if len(cells) >= 4:
            cur_period = cells[0] or cur_period
            grade=cells[1]
            cur_admit = cells[2] or cur_admit
            time_disp= cells[3]
            if len(cells) >= 5 and cells[4]:
                cur_note = cells[4]    
        elif len(cells) == 2:
            grade = cells[0]
            time_disp = cells[1]
            cur_note = cur_note
        else: 
            continue 

        out.append({
            "교시":cur_period,
            "등급": grade,
            "입실완료시간":cur_admit,
            "시험시간표시":time_disp,
            "비고": cur_note,
        })   
    
    return out
#soup.find_all(["h3", "h4"])는 리스트로 묶어서 한 번에 쓰는게 더 편하므로 이렇게 묶은것이고
#별 다른 의미는 없다. 그리고 note = cells[4] if len(cells) >= 5 else None 이건 
#cur_period는 rowspan으로 교시의 값을 그대로 받아들일 때 예전 값을 써야 했으므로 cur_period를 썼고
#테이블 셀이 5개 이상일 때 cells[4]의 note가 들어가고 아니라면 None을 반환함 


def _parse_mmdd_range_with_year(s: str, ref_year: int, pivot_month: int):
    m = MMDD_RANGE_RE.search(s or "")
    if not m: return (None, None)
    sm, sd, em, ed = map(int, m.groups())
    sy, ey = ref_year, ref_year
    # 1) 일반적인跨年: 시작 월 > 종료 월이면 종료는 다음 해
    if sm > em: ey = ref_year + 1
    # 2) 같은 월인데 일만 뒤로 가는 비정형 케이스도跨年 간주 (선택)
    elif sm == em and sd > ed: ey = ref_year + 1

    # 3) 연말 문맥 보정: 11–12월 공지에서 1–2월 구간은 다음 해(둘 다 초봄이면 시작도 다음 해로)
    if pivot_month >= 11 and sm <= 2 and em <= 2:
        sy = ref_year + 1
        ey = ref_year + 1

    return (f"{sy:04d}-{sm:02d}-{sd:02d}", f"{ey:04d}-{em:02d}-{ed:02d}")

#MMDD_RANGE_RE로 정리한 날짜(09.12 ~10.23)를 search로 처음 발견한 정규식을 찾고 두 개의 날짜를
#m이 아닐 경우 각각의 날짜를 None으로 반환한다. 그 후 각각의 날짜를 
#튜플로 반환하기위해 groups()를 쓰고 int형을 반환하는 map을 써서 int 갹체를 쓴다.
#각각의 조건은 시작월이 끝나는 월보다 클 때 기본적으로 끝나는 년도를 하나씩 늘리고 
#pivot_month를 기준으로 11 이상이고 시작 달이 2 이하, 끝나는 달이 2 이하일때
#각각 시작 년도 끝나는 년도를 1씩 더하고 f를 넣으면 파이썬 문법을 써서 {} -> 중괄호를 이용해
#날짜를 마음대로 쓸 수 있다. if pivot_month >= 11 and sm <= 2 and em <= 2: -> 이건 pivot_month를 기준으로
#잡고 1월 16일 ~ 1월 23일일때 원래 있던 ref_year에 1을 안 더하면 다음 년도로 안 넘어가기에 무조건 1을 더한다.

def _get_table(soup:BeautifulSoup):
    t = soup.find("table", id="testScheduleList")
    if t: return t
    for tbl in soup.find_all("table"):
        heads = "".join(_txt(th) for th in tbl.find_all("th"))
        if all(k in heads for k in["시험일", "시험명", "온라인원서접수", "방문접수", "수험표공고", "성적공고"]):
            return tbl
    return None
#all로 모든 조건을 확인하고 옳다면 tbl 반환    


def parse_gtq_schedule_html(html:str):
    soup = BeautifulSoup(html, "html.parser")
    table = _get_table(soup)
    if not table:
        return {"시험일정": {"정기검정일정": []}}
    
    items=[]
    for tr in (table.find("tbody") or table).find_all("tr"):
        tds = tr.find_all("td")
        if len(tds) < 6:
            continue
        
        exam_date_str= _txt(tds[0])
        title = _txt(tds[1])
        online_disp=_txt(tds[2])
        offline_disp=_txt(tds[3])
        admit_disp=_txt(tds[4])
        result_disp=_txt(tds[5])
        if not YMD_RE.match(exam_date_str):
            continue
        
        m_round = ROUND_IN_TITLE_RE.search(title)
        round_level = f"제{m_round.group(1)}회" if m_round else None
        ref_y = int(exam_date_str[:4]); ref_m = int(exam_date_str[5:7])

        on_s,on_e = _parse_mmdd_range_with_year(online_disp, ref_y, ref_m)
        off_s, off_e = _parse_mmdd_range_with_year(offline_disp, ref_y, ref_m)
        ad_s, ad_e = _parse_mmdd_range_with_year(admit_disp, ref_y, ref_m)
        rs_s, rs_e = _parse_mmdd_range_with_year(result_disp, ref_y, ref_m)

        items.append({
            "회차": round_level,
            "시험명":title,
            "시험일": exam_date_str,
            "온라인원서접수표시": online_disp,
            "방문접수표시": offline_disp,
            "수험표공고표시": admit_disp,
            "성적공고표시": result_disp,
            "examDate": exam_date_str,
            "onlineRegisterStart": on_s, "onlineRegisterEnd": on_e,
            "offlineRegisterStart": off_s, "offlineRegisterEnd": off_e,
            "admitCardStart": ad_s, "admitCardEnd": ad_e,
            "resultStart": rs_s, "resultEnd": rs_e,
        })

    # dedupe + sort
    dedup = {}
    for i in items:
        dedup[(i["examDate"], i.get("회차"))] = i
    items = sorted(dedup.values(), key=lambda x : x["examDate"])
    return {"시험일정": {"정기검정일정": items}} 
    #dedup는 딕셔너리로 저장하고, items는 리스트로 저장을 했으니 i는 전체의 값을
    #기준으로 딕셔너리의 값인 i를 넣어서 ("2025-05-24", "제5회"): {"examDate": "2025-05-24", "회차": "제5회", "시험명": "...", ...} -> 이런 식으로
    #튜플의 불변값을 이용해서 값을 넣는다. items인 리스트안에 있는 값들은 각각 딕셔너리인 i이고,
    #(날짜,회차) 불변의 튜플을 기준으로 반복을 하고 딕셔너리에 저장하면 딕셔너리가 덮어씌워서 중복 제거하는 과정이 반복한다.
    #다시 말해 튜플인 (날짜,회차)를 기준으로 중복제거를 한다.
    #그 이후 examDate를 기준으로 오름차순을 한다.

def _click_tab(driver, text):
    locs = [
        (By.XPATH, f"//a[normalize-space(.)='{text}']"),
        (By.XPATH, f"//a[contains(normalize-space(.),'{text}')]"),
        (By.XPATH, f"//li[a[contains(normalize-space(.), '{text}')]]/a"),
    ]
    for by,sel in locs:
        try:
           el = WebDriverWait(driver,5).until(EC.presence_of_element_located((by,sel)))
           driver.execute_script("arguments[0].scrollIntoView({block:'center'});", el)
           time.sleep(0.05)
           driver.execute_script("arguments[0].click();", el)
           return True
        except Exception:
            pass
    return False       
#f 문자열을 통해 변수인 {text}를 바로 넣을수 있게 하고    
#locs를 이용해 탐색방법(By.XPATH)과 선택자 문자열(f"...")을 써서 선택자 문자열들을 순차적으로 실행하기 위해 리스트로 감싸고
#각각의 요소들은 튜플(불변)화 시킴
#for 반복문을 이용해서 1번째 XPATH에서 못 찾으면 2번째 XPATH로 넘어가는 식으로 계속 반복하는 형식이다.
#탭 요소가 나타날떄까지 5초 기다렸다가 el 변수에 할당하고, 찾은 요소인 el이 화면 중앙에 보이도록 스크롤 시킨 후, 0.05초 기다리고, 탭 클릭을 실행하고 성공적으로 찾으면 True이고 아니면 False이다.
#예외가 뜨면 그냥 패스하고 다음 locs 후보로 넘어가고 싹 다 아니면 False값 넘김

def _selenium_fetch_table_html(driver, debug_dir=None) -> str | None:
    driver.set_window_size(1280,900)
    driver.get(URL)

    if not _click_tab(driver, "시험일정"):
        driver.get(URL + "?pagekind=testSchedule")
        time.sleep(0.8)

    try:
        btn = WebDriverWait(driver,5).until(EC.presence_of_element_located((By.XPATH, "//button[contains(normalize-space(.), '검색')]")))
        driver.execute_script("arguments[0].scrollIntoView({block:'center'});", btn)
        time.sleep(0.1)
        driver.execute_script("arguments[0].click();", btn)
    except Exception:
        pass

    WebDriverWait(driver,20).until(EC.presence_of_element_located((By.CSS_SELECTOR, "table#testScheduleList")))

    for _ in range(20):
        rows = driver.find_elements(By.CSS_SELECTOR, "table#testScheduleList tbody tr")
        if len(rows) > 0:
            break
        time.sleep(0.25)

    table_html = driver.execute_script("""
        const t = document.querySelector('#testScheduleList');
        return t ? t.outerHTML : null;                               
    """)

    return table_html   
#브라우저 창 크기를 지정하고 url에 접속해서 검색 버튼이 있으면 클릭하고 표가 나타날 때까지 기다리고 표의 <table> html을 추출한다. 그 후 table_html을 반환
#for _ in range(20) -> 변수는 없이 총 20번 반복한다는 의미이다. 

def get_data(driver=None, debug_dir=None):
    if driver is None:
        return {"시험일정": {"정기검정일정": [], "시험시간": []}}
    
    table_html = _selenium_fetch_table_html(driver, debug_dir=debug_dir)
    if not table_html:
       return {"시험일정": {"정기검정일정": [], "시험시간": []}}

    data = parse_gtq_schedule_html(table_html)

    times = []
    try:
        clicked = _click_tab(driver, "시험안내")
        if clicked:
            time.sleep(0.3)
            try:
                WebDriverWait(driver, 3).until(
                    EC.presence_of_element_located((By.XPATH, "//*[self::h3 or self::h4][contains(., '시험시간')]"))
                )
            except Exception:
                pass
            
            page_html = driver.page_source        
            times = parse_gtq_exam_times_html(page_html)
        
    except Exception:
        times = []


    data["시험일정"]["시험시간"] = times or []
    return data
#이제 시험일정, 시험시간의 탭을 각각 잘 실행하기만 하면 된다.        

 