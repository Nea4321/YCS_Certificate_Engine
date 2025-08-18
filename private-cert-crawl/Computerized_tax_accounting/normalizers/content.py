from .utils_text import _as_list, _is_nonempty, _coerce_images, _prune
from .utils_dedupe import (
    _parse_weights, _looks_like_coverage,
    _signature_syllabus, _signature_coverage, _dedupe_by_signature
)

def normalize_content(raw: dict) -> dict:
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

    # 트리 탐색
    def _walk(node):
        if node is None:
            return
        obj_id = id(node)
        if obj_id in seen_objs:
            return
        seen_objs.add(obj_id)
        
        if isinstance(node, dict):
            # 명시적 키 우선
            if "syllabus" in node and isinstance(node["syllabus"], (list, dict)):
                syllabus_nodes.extend(_as_list(node["syllabus"]))
            if "coverage" in node and isinstance(node["coverage"], (list, dict)):
                coverage_nodes.extend(_as_list(node["coverage"]))
            if "시험종목 및 평가범위" in node and isinstance(node["시험종목 및 평가범위"], (list, dict)):
                coverage_nodes.extend(_as_list(node["시험종목 및 평가범위"]))
            # 시험내용 중첩
            if "시험내용" in node:
                _walk(node["시험내용"])

            # 휴리스틱(명시적 키가 없을 때만 후보로 추가)
            if not ("syllabus" in node or "coverage" in node or "시험종목 및 평가범위" in node):
                if _looks_like_coverage(node):
                    coverage_nodes.append(node)

            for v in node.values():
                _walk(v)

        elif isinstance(node, list):
            for v in node:
                _walk(v)

    _walk(raw)

    # 루트에 바로 syllabus가 있을 수도 있음
    if not syllabus_nodes and isinstance(raw, dict) and "syllabus" in raw:
        syllabus_nodes = _as_list(raw["syllabus"])

    # ---- syllabus 아이템 만들기 ----
    syllabus_out = []
    for item in syllabus_nodes:
        if not isinstance(item, dict):
            continue
        std_keys = ("등급", "과목", "검정항목", "검정내용", "상세검정내용")

        std = {k: (item.get(k) if _is_nonempty(item.get(k)) else None) for k in std_keys}

        image_keys = [k for k in item.keys()
                      if ("이미지" in k) or (k.lower() in ("images", "image", "img", "imgs", "picture", "pictures", "pics", "photos"))]
        images = []
        for ik in image_keys:
            images.extend(_coerce_images(item.get(ik)))

        exclude = set(std_keys) | set(image_keys) | {"section"}
        ext = {k: v for k, v in item.items() if k not in exclude and _is_nonempty(v)}

        syllabus_out.append(_prune({
            **std,
            "images": images if images else None,
            "ext": ext if ext else None,
        }))

    # ---- coverage 아이템 만들기 ----
    coverage_out = []
    for item in coverage_nodes:
        if not isinstance(item, dict):
            continue

        # 널리 쓰이는 필드들만 표준화
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

        # parsedWeights: 원문에 이미 있으면 사용, 없으면 텍스트에서 파싱
        parsed = None
        if isinstance(item.get("parsedWeights"), list) and item.get("parsedWeights"):
            parsed = item["parsedWeights"]
        else:
            text = (item.get("평가범위") or
                    next((v for v in item.values() if isinstance(v, str) and "%" in v), None))
            pw = _parse_weights(text)
            if pw:
                parsed = pw

        exclude = set(std.keys()) | set(image_keys) | {"parsedWeights", "section"}
        ext = {k: v for k, v in item.items() if k not in exclude and _is_nonempty(v)}

        coverage_out.append(_prune({
            **std,
            "parsedWeights": parsed,
            "images": images if images else None,
            "ext": ext if ext else None,
        }))

    # 🔒 최종 중복 제거 (idempotent 보장)
    syllabus_out = _dedupe_by_signature(syllabus_out, _signature_syllabus)
    coverage_out = _dedupe_by_signature(coverage_out, _signature_coverage)    

    return _prune({
        "syllabus": syllabus_out,
        "coverage": coverage_out
    })
