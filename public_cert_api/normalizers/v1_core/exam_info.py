# -*- coding: utf-8 -*-
from __future__ import annotations
import re
from typing import List, Dict
from ..utils.text import clean, dedupe_keep_order
from .support.exam_info_config_loader import load_exam_info_config

__all__ = ["extract_fees", "extract_sections"]

# YAML 설정 수신
FEE_KEYS, WRIT_KEYS, PRACT_KEYS, TIP_KEYS, SEC_TITLES, NXT_TITLES, SEC_MAP = load_exam_info_config()

_BULLET = r"[·•○\-\u25CF\u25E6\u2022]"  # 글머리표 후보

def _anchor_regex(tokens: List[str]) -> re.Pattern:
    # 문단 "시작"에서만 제목 인식 (글머리표 허용, 콜론/대시 허용)
    pat = "|".join(map(re.escape, tokens))
    return re.compile(rf"^\s*(?:{_BULLET}\s*)?(?:{pat})\s*(?:[:：\-]\s*)?(.*)$")

# ── 수수료 ───────────────────────────────────────────────────────
# exam_info.py
def extract_fees(paras: List[str], tables: List[Dict]) -> Dict | str:
    fees: Dict[str, str] = {}

    def clean_amt(x: str) -> str | None:
        s = clean(x)
        m = re.search(r"([0-9][\d,]*)\s*원", s)
        if m:
            n = re.sub(r"[^\d]", "", m.group(1))
            return f"{int(n):,}원"
        m = re.search(r"([0-9]+)\s*만\s*원?", s)
        if m:
            return f"{int(m.group(1))*10000:,}원"
        return None

    # ── 1) 표 우선
    for t in tables or []:
        rows = [[clean(c) for c in (r or [])] for r in (t.get("rows") or [])]
        if not rows:
            continue
        head = rows[0]
        flat = " ".join(" ".join(r) for r in rows)
        has_fee_word = any(k in flat for k in FEE_KEYS)
        has_w = any(any(w in h for w in WRIT_KEYS) for h in head)
        has_p = any(any(p in h for p in PRACT_KEYS) for h in head)
        if not (has_fee_word or (has_w and has_p)):
            continue

        if has_w and has_p:  # 가로형
            if len(rows) >= 2:
                idx = {}
                for i, h in enumerate(head):
                    if any(w in h for w in WRIT_KEYS): idx["필기"] = i
                    if any(p in h for p in PRACT_KEYS): idx["실기"] = i
                for k, i in idx.items():
                    if k in fees:
                        continue
                    for r in rows[1:]:
                        if i < len(r):
                            v = clean_amt(r[i])
                            if v:
                                fees[k] = v
                                break
        else:  # 세로형
            for r in rows[1:] if len(rows) > 1 else rows:
                if not r:
                    continue
                c0 = r[0]
                if any(w in c0 for w in WRIT_KEYS):
                    v = next((clean_amt(c) for c in r[1:] if clean_amt(c)), None)
                    if v: fees["필기"] = v
                if any(p in c0 for p in PRACT_KEYS):
                    v = next((clean_amt(c) for c in r[1:] if clean_amt(c)), None)
                    if v: fees["실기"] = v

        if "필기" in fees or "실기" in fees:
            return fees  # 표에서 뭘 찾았으면 즉시 반환

    # ── 2) 표가 없으면: 본문 한 덩어리 원문 그대로 반환
    #      '응시수수료'로 시작하는 줄에 이어지는 같은 블록까지 이어 붙임(다음 제목/불릿 전까지)
    block = []
    started = False
    for s in [clean(p) for p in (paras or [])]:
        if not started and ("응시수수료" in s or s.startswith("응시 수수료") or s.startswith("수수료")):
            started = True
        if started:
            # 다음 섹션/제목 신호 만나면 중단
            if re.match(r"^(합격기준|시험과목|시험 방법|시험방법|응시자격|출제경향|공개문제)\b", s):
                break
            block.append(s)
    if block:
        return " ".join(block)

    # 못 찾았으면 빈 dict
    return {}



# ── 섹션 ─────────────────────────────────────────────────────────
def extract_sections(paras: List[str], link_texts: List[str] | None = None) -> Dict[str, str | None]:
    """
    문단(P)만으로 섹션을 우선 추출.
    출제기준은 필요 시 링크 텍스트(L)로 보조.
    공개문제만 인라인 허용(취득방법 인라인 금지).
    """
    P = [clean(p).strip() for p in (paras or []) if clean(p).strip()]
    L = [clean(t).strip() for t in (link_texts or []) if clean(t).strip()]  # 출제기준 보조만

    out: Dict[str, str | None] = {}
    used: set[int] = set()

    compiled = {name: _anchor_regex(aliases) for name, aliases in SEC_MAP.items()}

    # 제목 줄 인덱스 맵 (P 기준)
    heading_at: Dict[int, str] = {}
    for i, s in enumerate(P):
        for name, rx in compiled.items():
            if rx.match(s):
                heading_at[i] = name
                break

    INLINE_OK = {"공개문제"}  # 취득방법 인라인 금지

    for name, rx in compiled.items():
        # 1) 제목 줄 블록
        start_idx = next((i for i, n in heading_at.items() if n == name), None)
        if start_idx is not None:
            m = rx.match(P[start_idx])
            body_first = (m.group(1) or "").strip() if m else ""
            end_idx = start_idx + 1
            while end_idx < len(P) and end_idx not in heading_at:
                end_idx += 1
            chunk = [t for t in [body_first] if t] + P[start_idx + 1:end_idx]
            out[name] = " ".join(chunk).strip() or None
            used.update(range(start_idx, end_idx))
            continue

        # 2) 한 줄형(줄 시작 앵커)
        for i, s in enumerate(P):
            if i in used: continue
            m = rx.match(s)
            if m:
                body = (m.group(1) or "").strip()
                if not body and (i + 1) < len(P) and (i + 1) not in heading_at:
                    body = P[i + 1].lstrip("·•○- ").strip()
                    used.add(i + 1)
                out[name] = body or None
                used.add(i)
                break
        if out.get(name) is not None:
            continue

        # 3) 인라인 허용(공개문제만, P에서만)
        if name in INLINE_OK:
            for i, s in enumerate(P):
                if i in used: continue
                if any(tok in s for tok in SEC_MAP[name]):
                    out[name] = s
                    used.add(i)
                    break

        # 4) 출제기준: P에서 못 찾으면 링크 텍스트(L)에서 보조
        elif name == "출제기준":
            def pick_from(seq: List[str]) -> str | None:
                # 안내문
                for s in seq:
                    if "출제기준" in s and ("고객지원" in s or "메뉴상단" in s):
                        return s
                # 번호목록(연도 포함) 한 줄
                for s in seq:
                    if re.search(r"^\s*\d+\.\s*.+\(\d{4}\.", s):
                        return s
                return None

            out[name] = pick_from(P) or pick_from(L) or None

        out.setdefault(name, None)

    # 5) 남은 문단 중 안내성만 '추가안내'
    rest = [P[i] for i in range(len(P)) if i not in used]
    tips = [p for p in rest if any(k in p for k in TIP_KEYS)]
    out["추가안내"] = " ".join(dedupe_keep_order(tips)) if tips else None

    # 6) 후처리: 제목 프리픽스/중복 라벨 제거 + 공개문제/취득방법 정리
    all_title_tokens = sorted({tok for alias in SEC_MAP.values() for tok in alias})
    head_pat = rf"^\s*(?:{'|'.join(map(re.escape, all_title_tokens))})\s*[:：\-]?\s*"
    for k, v in list(out.items()):
        if isinstance(v, str) and v:
            out[k] = re.sub(head_pat, "", v).strip()

    # '... 출제경향 - ' 같은 2차 접두 제거
    def strip_leading_label(val: str, key: str) -> str:
        pat = rf"^\s*.{{0,60}}{re.escape(key)}\s*[:：\-]\s*"
        return re.sub(pat, "", val).strip()

    for key in ("출제경향", "공개문제", "출제기준"):
        if isinstance(out.get(key), str) and out[key]:
            out[key] = strip_leading_label(out[key], key)

    def looks_like_only_public_question(s: str) -> bool:
        return ("공개문제" in s) and not re.search(r"(접수|원서|방법|절차|응시)", s)

    # 취득방법이 사실상 공개문제 안내뿐이면 비움/이관
    if not out.get("공개문제") and out.get("취득방법") and "공개문제" in out["취득방법"]:
        out["공개문제"] = out["취득방법"]
    if out.get("취득방법") and looks_like_only_public_question(out["취득방법"]):
        out["취득방법"] = None

    return out
