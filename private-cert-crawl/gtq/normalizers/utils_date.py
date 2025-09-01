import re
from datetime import datetime
from .utils_text import _clean

_YEAR_2DIGIT = re.compile(r"^[`'’‵′]?(?P<yy>\d{2})\.(?P<mm>\d{2})\.(?P<dd>\d{2})")
_MD =re.compile(r"(?P<mm>\d{2})\.(?P<dd>\d{2})")
#(?P<yy>\d{2}) -> 그룹에 이름을 붙이는 문법으로 2자리 숫자를 잡고 그걸 "yy"로 접근하는게 가능하게 함
#^은 정규식의 시작이고 [`'’‵′] 이건 대괄호 안에서 허용할 문자 집합을 쓴 거다 또한 ?은 0 또는 1개 이상이란 뜻


def _to_year(yy:int) -> int: 
    return 2000 + yy
#뭐 가볍게 yy가 int이면 2000 + yy를 반환한다.


def _parse_one_date(token:str, base_year:int) -> str | None:
    """
    "01.20(월)" / "'24.11.05.(화)" / "02.27(목)" / "01.02" -> "YYYY-MM-DD"
    """

    if not token: 
        return None
    s = token.strip()

    m = _YEAR_2DIGIT.search(s)
    if m:
        yy = int(m.group("yy")); mm = int(m.group("mm")); dd=int(m.group("dd"))
        return f"{_to_year(yy):04d}-{mm:02d}-{dd:02d}"
    
    m = _MD.search(s)
    if m:
        mm = int(m.group("mm")); dd=int(m.group("dd"))
        return f"{base_year:04d}-{mm:02d}-{dd:02d}"
    
    return None
#연 월 일이 있으면 m = _YEAR_2DIGIT.search(s) -> 이 쪽을 반환 월 일이 있으면 m = _MD.search(s)을 반환함
#yy = int(m.group("yy")); mm = int(m.group("mm")); dd=int(m.group("dd")) -> 여기서 ; 세미콜론은 한 줄에서 다 쓰려고 일부러 쓴 것이다 파이썬은 이건 크게 문제 없다

def _parse_md_range(s: str, base_year:int) -> tuple[str | None, str | None]:
    """
    "01.20 ~ 02.07" / "'24.12.23 ~ `25.01.01" -> (YYYY-MM-DD, YYYY-MM-DD)
    """

    if not s:
       return (None,None)
    
    parts = re.split(r"[~~\-]+", _clean(s))
    if len(parts) < 2:
        d =_parse_one_date(parts[0], base_year)
        return (d,d)
    left_raw, right_raw = parts[0].strip(), parts[1].strip()

    left_yeared = _YEAR_2DIGIT.search(left_raw)
    right_yeared = _YEAR_2DIGIT.search(right_raw)

    if left_yeared:
        yy = int(left_yeared.group("yy")); ry = _to_year(yy)
        left = _parse_one_date(left_raw,ry)
        right = _parse_one_date(right_raw,ry)
        return (left,right)
    
    if right_yeared:
        yy = int(right_yeared.group("yy")); ry= _to_year(yy)
        left_tmp = _parse_one_date(left_raw,ry)
        right = _parse_one_date(right_raw,ry)        
        if left_tmp and right:
            lm,rm = int(left_tmp[5:7]), int(right[5:7])
            if lm > rm:
                ly = int(left_tmp[:4]) - 1
                left = f"{ly:04d}{left_tmp[4:]}"
            else:
                left = left_tmp
        else:
            left=left_tmp
        return (left,right)

    left = _parse_one_date(left_raw,base_year)
    right = _parse_one_date(right_raw,base_year)
    try:
        if left and right:
            lm,rm = int(left[5:7]), int(right[5:7])
            if lm < rm:
                ry = int(left[:4]) + 1
                right = f"{ry:04d}{right[4:]}"
    except Exception:
        pass
    return (left,right)            
#s가 빈 문자열이면 None으로 바로 None,None을 반환함
#if len(parts) < 2: d =_parse_one_date(parts[0], base_year) return (d,d) -> 이건 반환 값인 parts = re.split(r"[~~\-]+", _clean(s))이 2025-01-20와 같이 하나만 있을 떄로
#이 경우엔 시작과 끝 날짜가 똑같다는 경우이기에 튜플로 반환해서 불변의 값을 유지한다는 의미로 보이게 한다.
#그러니 시작과 끝이 같은게 맞다.
#그리고 나머진 if left_yeared: yy = int(left_yeared.group("yy")); ry = _to_year(yy) -> 이걸 바탕으로 왼쪽 값을 기준으로 2000을 더하는 행위를 하고
#오른쪽도 마찬가지로 오른쪽 값을 기준으로 2000을 더하는데 이렇게 했을 때 만일 오른쪽이 25년도인데 1월이라면 2025-12-24 ~ 2025-01-01 이런 상태가 벌어지고 이를 막기 위해 오른 쪽에선
#1을 하나 빼는 안전장치를 마련한다.(당연히 왼쪽에 있는 년도가 더 적게 나오므로 1을 뺼 이유가 없어서 1을 안 뺀다.)
#base_year의 년도는 schedule.py와 같은 상위로직이 정해주므로 거길 봐야한다.
#마지막 조건은 12-03 ~ 01-02인 상태에서 2024년을 base_year로 들고 온다치면 오른쪽이 더 적은 수이기에
#오른쪽년도에 1을 더해주면 된다.

def _split_time_ranges(s:str):
    if not s:
        return (None, None)
    flat = _clean(s)
    m = re.search(r"(\d{1,2}:\d{2}).*?(\d{1,2}:\d{2})", flat)
    return (m.group(1), m.group(2)) if m else (None,None)
#(\d{1,2}:\d{2}) -> 시:분 형식으로 14:00 ~ 15:30 -> 이런 식으로 찾고, .*? -> 이건 두 시간 사이의 문자들(공백,~등)을 건너뜀
#최종적으로 m.group(1)은 14:00, m.group(2)는 15:30분 이렇게 된다. 
#여기서 group()은 튜플과 같은 배열이 아니라 매칭함수이기에 첫 인덱스가 1부터 시작하는걸 알고 주의한다.
#정 쓰고 싶으면 뒤에 s 붙여서 쓰면 된다.

def _minutes_ko(s: str | None):
    m = re.search(r"(\d+)\s*분", s or "")
    return int(m.group(1)) if m else None
#이것도 위에 있는 time_range 함수랑 비슷하게 생각하면 된다.