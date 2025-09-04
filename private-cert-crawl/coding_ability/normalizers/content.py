from engine_common.utils_text import _as_list, _is_nonempty, _coerce_images, _prune
from engine_common.utils_dedupe import (
    _parse_weights, _looks_like_coverage,
    _signature_syllabus, _signature_coverage, _dedupe_by_signature
)

def normalize_content(raw:dict) -> dict:
    """
    항상 {"syllabus":[...], "coverage":[...]} 반환.
    - section 필드 제거
    - images/ext는 값 있을 때만 생성
    - 빈값은 전부 제거
    - coverage는 퍼센트 패턴에서 parsedWeights 자동 생성
    """

    syllabus_nodes = []
    coverage_nodes = []

    seen_objs = set()

    def _walk(node):
        if node is None:
            return
        obj_id = id(node)
        if obj_id in seen_objs:
            return
        seen_objs.add(obj_id)

        #리스트에서 중첩 리스트를 만들지 않고 하나의 리스트에 쭉 이어갈려면 append가 아니라 extend를 쓴다.
        #ex: images.extend(["b.png","c.png"])
        if isinstance(node, dict):
            if "syllabus" in node and isinstance(node["syllabus"], (list,dict)):
                syllabus_nodes.extend(_as_list(node["syllabus"]))
            if "coverage" in node and isinstance(node["coverage"], (list,dict)):
                coverage_nodes.extend(_as_list(node["coverage"]))
            if "시험종목 및 평가범위" in node and isinstance(node["시험종목 및 평가범위"], (list,dict)):
                coverage_nodes.extend(_as_list(node["시험종목 및 평가범위"]))
            if "시험내용" in node:
                _walk(node["시험내용"])
            if not ("syllabus" in node or "coverage" in node or "시험종목 및 평가범위" in node):
                if _looks_like_coverage(node):
                   coverage_nodes.append(node)

                for v in node.values():
                    _walk(v)

        elif isinstance(node, list):
            for v in node:
                _walk(v)

    _walk(raw)
    #최상위 raw부터 시작해서 딕셔너리의 값들 확인하고 리스트의 원소들을 확인하면서 계속 반복한다.

    if not syllabus_nodes and isinstance(raw, dict) and "syllabus" in raw:
        syllabus_nodes = _as_list(raw["syllabus"])

    syllabus_out = []
    for item in syllabus_nodes:
        if not isinstance(item,dict):
            continue
        std_keys = ("등급", "과목", "검정항목", "검정내용", "상세검정내용")
        #std_keys는 튜플로 불변하는 값을 저장해야 되서 이렇게 저장함.

        std = {k:(item.get(k) if _is_nonempty(item.get(k)) else None) for k in std_keys}
        #for k in std_keys로 std_keys의 튜플 안의 값들을 하나씩 갖고 오고 k:(...)는 딕셔너리의 키로
        #쓴 다는 뜻이다. (item.get(k) if _is_nonempty(item.get(k)) else None)는 키의 value값이다. 당연히 튜플로 묶은게 아니라 그냥 값을 묶은거다

        image_keys = [k for k in item.keys()
                        if ("이미지" in k) or (k.lower() in ("images", "image", "img", "imgs", "picture", "pictures", "pics", "photos"))]
        #item 딕셔너리에서 "이미지 관련"으로 보이는 키 이름들이 들어가고 한글 "이미지" 포함이든 영어 "images"/"img"/"picture"등이든
        #전부 잡히도록 조건을 둠 k를 소문자로 만들고 (k.lower() in) "images"등과 같은 단어를 비교한단 뜻이다.

        images = []
        for ik in image_keys:
            images.extend(_coerce_images(item.get(ik)))
        #딕셔너리의 키를 모아둔 ik를 계속 돌면서 하나의 리스트로 확장시키는 작업을 한다.
        #각각의 이미지들의 공백을 _coerce_images로 지우기 위해     

        exclude = set(std_keys) | set(image_keys) | {"section"}
        ext = {k: v for k, v in item.items() if k not in exclude and _is_nonempty(v)}
        #exlude에서 버릴 키를 집합으로 해서 모으고, if k not in exclude -> 이걸 통해
        #위에서 제외키로 정할 건 버리고 추가로 _is_nonempty(v)를 이용해 None,빈 문자열이면
        #버리고 그 외엔 살린 것을 전부 ext에 넣는다.
        #즉, **표준 키도 아니고, 이미지 키도 아니고, section도 아닌 “그 외 추가 필드들”**을 ext라는 딕셔너리에 모으는 것이다.


        syllabus_out.append(_prune({
            **std,
            "images": images if images else None,
            "ext": ext if ext else None,
        }))
        #**은 딕셔너리 언패킹으로 이걸 안 쓰다면 딕셔너리에 키와 값들을 일일히 다 써야 된다.
        #이걸 쓰면 딕셔너리 내용을 풀어서 다른 딕셔너리에 합친다.

    coverage_out = []
    for item in coverage_nodes:
        if not isinstance(item,dict):
            continue

        std = {
            "종목": item.get("종목"),
            "등급": item.get("등급"),
            "구분": item.get("구분"),
            "평가범위": item.get("평가범위"),
        }  

        # 이미지
        image_keys = [k for k in item.keys()
                    if ("이미지" in k) or (k.lower() in ("images", "image", "img", "imgs", "picture", "pictures", "pics", "photos"))]
        images = []

        for ik in image_keys:
            images.extend(_coerce_images(item.get(ik)))

        parsed = None
        if isinstance(item.get("parsedWeights"), list) and item.get("parsedWeights"):
            parsed = item["parsedWeights"]

        else:
            text = (item.get("평가범위") or next((v for v in item.values() if isinstance(v,str) and "%" in v), None))
            pw = _parse_weights(text)
            if pw:
                parsed = pw
        #item에 이미 파싱된 parsedWeights가 있다면 그걸 쓰고 없다면 "평가범위" 텍스트 또는 문자열 값중에 % 들어간 첫 값을 찾아 _parse_weights(text)로 쓴다.


        exclude = set(std.keys()) | set(image_keys) | {"parsedWeights", "section"}
        ext = {k: v for k,v in item.items() if k not in exclude and _is_nonempty(v)}
        #마찬가지로 제외할 키를 싹 다 모음.

        coverage_out.append(_prune({
            **std,
            "parsedWeights":parsed,
            "images": images if images else None,
            "ext": ext if ext else None,
        }))

    syllabus_out = _dedupe_by_signature(syllabus_out, _signature_syllabus)
    coverage_out = _dedupe_by_signature(coverage_out, _signature_coverage)

    return _prune({
        "syllabus": syllabus_out,
        "coverage": coverage_out
    })                


