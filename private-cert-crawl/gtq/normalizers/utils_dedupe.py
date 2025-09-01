import re
from .utils_text import _tuple_images

_PERCENT_PAIR = re.compile(r"\s*([^(),%]+?)\s*\(\s*(\d+(?:\.\d+)?)\s*%\s*\)")
#\s*은 공백을 0개 이상 허용하고 앞뒤 띄어쓰기 무시하고, ([^(),%]+?)은 이 안에 들어있는 문자 제외하고
#잡으라는 뜻과 \s*\(은 괄호 여는 ( 앞 뒤로 공백 허용, (\d+(?:\.\d+)?)은 숫자 부분은 정수 또는 소수
#\d+는 숫자 1개 이상이고 (?:\.\d+)?은 선택적으로 소수점 이하 포함한다는 뜻이고
#\s*%\s* 은 퍼센트 기호 % 앞뒤 공백 허용하고 \)은 괄호 닫기이다.

def _parse_weights(text:str | None):
    if not text: return []
    pairs = _PERCENT_PAIR.findall(text)
    out = []
    for name,pct in pairs:
        name = name.strip(" ,;/·ㆍ-–—")
        try:
            val = float(pct)
            if val.is_integer():
                val = int(val)
        except Exception:
            continue
        if name:
            out.append({"항목": name, "비율": val})
    return out        
                
def _looks_like_coverage(d:dict) -> bool:
    if "평가범위" in d and isinstance(d["평가범위"],str):
        return len(_PERCENT_PAIR.findall(d["평가범위"])) >= 1
    #기타단서
    joined = " ".join([str(v) for v in d.values() if isinstance(v,str)])
    return len(_PERCENT_PAIR.findall(joined)) >= 2
#-> bool(반환타입 힌트로 이걸로 동작을 바꾸는건 아니고 개발자가 읽을 때 편하게 쓰기 위해 함)
#평가범위 키가 있을 떄 len(_PERCENT_PAIR.findall(d["평가범위"])) >= 1 -> 이건 _PERCENT_PAIR을 최소 1개 이상 찾으면 True란 뜻
#마찬가지로 그 아래는 평가범위키가 없거나 값이 문자열이 아닐 경우에 실행하고 문자열에서 _PERCENT_PAIR을 최소 2개 찾으면 True

def _signature_syllabus(item:dict) -> tuple:
    return(
        item.get("등급") or "",
        item.get("과목") or "",
        item.get("검정항목") or "",
        item.get("검정내용") or "",
        item.get("상세검정내용") or "",
        tuple(sorted(_tuple_images(item.get("images")))),
    )
#이제 딕셔너리에 있는 요소들은 고정돼야 하기에 불변인 튜플로 두고 그 이후에 딕셔너리 + 리스트로 바꾼다
#즉 내부 로직은 tuple로 두고 외부는 딕셔너리 + 리스트로 둔다.
#tuple(sorted(_tuple_images(item.get("images")))) -> 이건 이미지가 문자열이나 리스트로 반환되기에 이걸 처리하는
#함수를 따로 만들어서 두고 그 이외의 키,값들은 () -> 이걸로 묶기만 해도 튜플이 된다.
def _signature_coverage(item: dict) -> tuple:
    pw = item.get("parsedWeights") or []
    pw_sig = tuple(sorted(
        (str(p.get("항목","")), str(p.get("비율","")))
        for p in pw if isinstance(p, dict)
    ))
    return (
        item.get("종목") or "",
        item.get("등급") or "",
        item.get("구분") or "",
        item.get("평가범위") or "",
        pw_sig,
        tuple(sorted(_tuple_images(item.get("images")))),
    )

def _dedupe_by_signature(items:list, sig_fn):
    seen,out = set(),[]
    for it in items:
        if not isinstance(it,dict):
            continue
        sig = sig_fn(it)
        if sig in seen:
            continue
        seen.add(sig)
        out.append(it)
    return out    
#sig_fn은 시그니쳐(데이터를 대표하는 불변의 고유한 식별자)를 만드는 함수를 외부에서 주입받는것으로 어떤 기준으로 중복을 판정하는지 정하는 함수이다.
#즉 딕셔너리를 불변값(tuple.str)등으로 바꿔주는 매퍼이다.
#seen은 중복을 허용치않는 집합이고, 순서없이 막 하므로 이미 본 것을 체크한것에 최적화 돼있음
#즉 위에서 튜플로 불변처리하고 마지막에 중복제거까지 해서 최종적으로 정제된 리스트를 반환한다. 
#sig_fn(it)은 위에 잇는 _siginature_syllbas(item:dict)와 똑같은 효과를 내고 그 이유는
#파이썬은 변수가 달라도 같은 효과를 쓰게 할 수 있는 특징이 있다.

#tuple → dict에서 뽑은 불변 시그니처 (중복 판정용)
#set(seen) → tuple 시그니처들의 집합 (중복 여부 체크)
#list(out) → 최종 반환되는 값, 중복 없는 dict들의 리스트
#dict → 실제 데이터의 원래 모습, tuple은 내부 로직에서만 쓰이고 외부 결과는 dict 그대로 유지
