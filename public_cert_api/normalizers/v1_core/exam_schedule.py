# normalizers/v1_core/exam_schedule.py
from __future__ import annotations
import os, re
from typing import List, Dict, Tuple, Optional
from ..utils.text import clean
from .support.config_loader import load_schedule_config, classify_from_yaml

ES_DEBUG = os.environ.get("ES_DEBUG") == "1"

# ── 설정 로드 ─────────────────────────────────────────────────────────────────
ROW_PHASE_RX, RX, BANNERS = load_schedule_config()

# ── 상수/정규식 ───────────────────────────────────────────────────────────────
KNUM = {"一":1,"二":2,"三":3,"四":4,"五":5,"六":6,"七":7,"八":8,"九":9,"十":10}
RNUM = {"Ⅰ":1,"Ⅱ":2,"Ⅲ":3,"Ⅳ":4,"Ⅴ":5,"Ⅵ":6,"Ⅶ":7,"Ⅷ":8,"Ⅸ":9,"Ⅹ":10,"Ⅺ":11,"Ⅻ":12}

# 예: "2025년 정기 기능사 1회", "정기 기능사 3회", "정기 기사 2회"
ROUND_FROM_WORDY = re.compile(
    r"(?:\d{4}\s*년\s*)?정기\s*(?:기능사|기사|산업기사)?\s*([0-9一二三四五六七八九十Ⅰ-Ⅻ]+)\s*회",
    re.I
)

ROUND_TOKEN = re.compile(r"(상시)|(?:제?\s*([0-9一二三四五六七八九十Ⅰ-Ⅻ]+)\s*(?:회|회차|차))", re.I)
CHASU_TOKEN = re.compile(r"(?:^|[^0-9一二三四五六七八九十Ⅰ-Ⅻ])([0-9一二三四五六七八九十Ⅰ-Ⅻ]+)\s*차", re.I)

DATE_ANY    = re.compile(r"\d{4}\.\d{1,2}\.\d{1,2}")
DATE_RANGE  = re.compile(r"\d{4}\.\d{2}\.\d{2}\s*[~\-]\s*\d{4}\.\d{2}\.\d{2}")
DATE_SINGLE = re.compile(r"\d{4}\.\d{2}\.\d{2}")

# 같은 의미의 날짜 필드는 덮어쓰지 말고 합치기
MERGE_FIELDS = {"접수기간", "추가접수기간", "서류제출기간", "의견제시기간", "시험일", "발표", "정답발표"}

# ── 보조 유틸 ─────────────────────────────────────────────────────────────────
def norm(s: Optional[str]) -> str:
    return clean(s or "").replace(" ", "")

def classify(header_text: str) -> Tuple[Optional[str], Optional[str]]:
    # 기본 YAML 분류
    return classify_from_yaml(norm(header_text), ROW_PHASE_RX, RX)

def _header_has_chasu(headers: List[str]) -> bool:
    ht = "".join(norm(h) for h in headers)
    return ("차수" in ht) or ("시험차수" in ht) or ("차수(구분)" in ht)

def _value_has_chasu(v: Optional[str]) -> bool:
    return bool(v and CHASU_TOKEN.search(norm(v)))

def detect_row_phase(text: str) -> Optional[str]:
    t = norm(text)
    for ph, patt in ROW_PHASE_RX.items():
        if patt.search(t):
            return ph
    return None

def _round_num(tok: Optional[str]) -> Optional[int]:
    if not tok: return None
    if tok.isdigit(): return int(tok)
    if tok in KNUM: return KNUM[tok]
    if tok in RNUM: return RNUM[tok]
    if len(tok) == 2 and tok[0] == "十" and tok[1] in KNUM: return 10 + KNUM[tok[1]]
    return None

def extract_round(text: Optional[str]) -> Optional[str]:
    """문장에서 회차를 찾아 '제N회' 또는 '상시'로 표준화."""
    if not text: return None
    s = norm(text)
    m = ROUND_FROM_WORDY.search(s)
    if m:
        n = _round_num(m.group(1))
        if n: return f"제{n}회"
    m = ROUND_TOKEN.search(s)
    if m:
        if m.group(1):  # 상시
            return "상시"
        n = _round_num(m.group(2))
        if n: return f"제{n}회"
    return None

def is_banner_row(cells: List[str]) -> bool:
    """안내/배너 행 필터. 회차 토큰 또는 날짜가 있으면 데이터로 통과시킨다."""
    text  = " ".join(cells or [])
    first = (cells[0] if cells else "")
    tnorm = norm(text)
    fnorm = norm(first)

    dates_in_row = len(DATE_ANY.findall(text))
    has_round_token = bool(extract_round(first) or ROUND_TOKEN.search(tnorm))

    # 1) 첫 셀 기반 배너 규칙
    rc = BANNERS.get("first_cell_contains")
    if rc and rc.search(fnorm):
        rx_ex = BANNERS.get("first_cell_excludes")
        # 회차/날짜가 아예 없을 때만 배너로 인정
        if not (rx_ex and rx_ex.search(fnorm)) and not has_round_token and dates_in_row == 0:
            return True

    # 2) 행 전체 토큰 기반 배너 규칙
    r = BANNERS.get("contains_any")
    if r and r.search(tnorm):
        if not has_round_token and dates_in_row == 0:
            return True

    # 3) 기타 휴리스틱 (필요시 사용)
    thr = int(BANNERS.get("min_dates_in_row") or 0)
    if thr > 0 and dates_in_row >= thr:
        return True

    return False

def _coalesce_date_field(value: Optional[str]) -> Optional[str]:
    """문자열 안의 날짜들을 first ~ last로 접어준다."""
    if not value:
        return None
    dates = DATE_SINGLE.findall(value)
    if not dates:
        return None
    if len(dates) == 1:
        return dates[0]
    return f"{dates[0]} ~ {dates[-1]}"

def _dateish(s: Optional[str]) -> bool:
    return bool(s and DATE_ANY.search(s))

def _sanitize_dates(rec: Dict) -> None:
    if rec.get("시험일") and not _dateish(rec["시험일"]):
        rec["시험일"] = None
    for k in ("접수기간", "추가접수기간", "서류제출기간", "의견제시기간", "발표", "정답발표"):
        v = rec.get(k)
        if v and not _dateish(v):
            rec[k] = None

def _merge_assign(rec: Dict, key: str, val: str) -> None:
    """같은 필드가 여러 컬럼에서 들어올 때 덮어쓰지 말고 합치기."""
    if not val:
        return
    if key in MERGE_FIELDS:
        prev = rec.get(key) or ""
        if prev:
            if val not in prev:
                rec[key] = f"{prev} {val}".strip()
        else:
            rec[key] = val
    else:
        rec[key] = val

# ── 회차/차수 파싱 & 확장 ──────────────────────────────────────────────────────
def normalize_rounds(raw: Optional[str]) -> List[str | int]:
    if not raw: return []
    s = re.sub(r"[·、/]+", ",", str(raw)).replace("~", "-").replace("–", "-")
    s = re.sub(r"\s+", "", s)
    out: List[str | int] = []
    rng = re.search(r"(\d+)\s*-\s*(\d+)", s)
    if rng:
        a, b = int(rng.group(1)), int(rng.group(2))
        out.extend(range(min(a, b), max(a, b) + 1))
    for part in re.split(r"[,\-]", s):
        m = ROUND_TOKEN.search(part)
        if not m: continue
        if m.group(1): out.append("상시"); continue
        n = _round_num(m.group(2))
        if n: out.append(n)
    uniq: List[str | int] = []
    for x in out:
        if x not in uniq: uniq.append(x)
    uniq.sort(key=lambda x: (999 if x == "상시" else int(x)))
    return uniq

def normalize_chasus(raw: Optional[str]) -> List[int]:
    if not raw: return []
    s = re.sub(r"[·、/]+", ",", str(raw)).replace("~", "-").replace("–", "-")
    s = re.sub(r"\s+", "", s)
    out: List[int] = []
    rng = re.search(r"(\d+)\s*-\s*(\d+)\s*차", s)
    if rng:
        a, b = int(rng.group(1)), int(rng.group(2))
        out.extend(range(min(a, b), max(a, b) + 1))
    for part in re.split(r"[,\-]", s):
        m = CHASU_TOKEN.search(part)
        if not m: continue
        n = _round_num(m.group(1))
        if n: out.append(n)
    uniq: List[int] = []
    for x in out:
        if x not in uniq: uniq.append(x)
    uniq.sort()
    return uniq

def expand_by_round(rec: Dict) -> List[Dict]:
    rounds = normalize_rounds(rec.get("회차"))
    if ES_DEBUG:
        print(f"[exam_schedule] expand_by_round raw={rec.get('회차')} -> {rounds}")
    if not rounds: return [rec]
    out: List[Dict] = []
    for r in rounds:
        rr = dict(rec)
        rr["회차"] = "상시" if r == "상시" else f"제{r}회"
        out.append(rr)
    return out

def expand_by_round_and_chasu(rec: Dict) -> List[Dict]:
    raw = rec.get("회차")
    if not raw: return [rec]
    round_nums = normalize_rounds(raw)
    chasus     = normalize_chasus(raw)
    if not chasus:   return expand_by_round(rec)
    if not round_nums: return [rec]
    out: List[Dict] = []
    for r in round_nums:
        base_round = "상시" if r == "상시" else f"제{r}회"
        for c in chasus:
            rr = dict(rec)
            rr["회차"] = f"{base_round} {c}차"
            out.append(rr)
    return out

# ── 접수 텍스트 보정 ──────────────────────────────────────────────────────────
EXTRA_START = re.compile(r"\[?\s*빈자리\s*(?:추가)?\s*접수(?:\s*기간)?\s*[:：]?\s*", re.S)

def split_extra(s: Optional[str]) -> Tuple[Optional[str], Optional[str]]:
    if not s: return None, None
    s = s.strip()
    m = EXTRA_START.search(s)
    if not m: return s.strip().strip("[] "), None
    main = s[: m.start()].strip().strip("[] ,;/")
    tail = s[m.end():].strip()
    close = tail.find("]")
    if close != -1: tail = tail[:close]
    dates = DATE_SINGLE.findall(tail)
    if not dates: extra = None
    elif len(dates) == 1: extra = dates[0]
    else: extra = f"{dates[0]} ~ {dates[-1]}"
    return (main or None), extra

def fix_spillover_in_signup(rec: Dict) -> None:
    """접수칸에 발표/시험일 등이 섞여 들어온 경우를 분리."""
    txt = rec.get("접수기간") or ""
    if not txt: return

    # '발표' 키워드가 접수칸에 섞여 있으면 발표쪽으로 분리 시도
    if "발표" in txt.replace(" ", "") and not rec.get("발표"):
        singles = DATE_SINGLE.findall(txt)
        if singles:
            rec["발표"] = singles[-1]  # 보통 마지막 단일 날짜가 발표일
        txt = re.sub(r"발표[^0-9]*\d{4}\.\d{2}\.\d{2}", "", txt)

    ranges = DATE_RANGE.findall(txt)
    if len(ranges) >= 2:
        rec["접수기간"] = ranges[0]
        if not rec.get("시험일"):
            rec["시험일"] = ranges[1]
        rest    = DATE_RANGE.sub("", txt)
        singles = DATE_SINGLE.findall(rest)
        if singles and not rec.get("발표"):
            rec["발표"] = singles[-1]
    else:
        rec["접수기간"] = txt or rec.get("접수기간")

def rescue_misplaced_announce_or_exam(rec: Dict) -> None:
    """
    컬럼 병합 등으로 발표일/시험일이 접수칸으로 들어온 흔한 오인식을 구출.
    - 접수기간이 '단일 날짜'이고, 시험일/발표가 비어 있으면 → 발표로 이동
    """
    s = (rec.get("접수기간") or "").strip()
    if s and DATE_SINGLE.fullmatch(s) and not rec.get("시험일") and not rec.get("발표"):
        rec["발표"] = s
        rec["접수기간"] = None


def _date_tuple(d: str) -> tuple[int,int,int]:
    y, m, dd = d.split(".")
    return int(y), int(m), int(dd)

def _range_end(r: str) -> tuple[int,int,int]:
    ds = DATE_SINGLE.findall(r)
    if not ds: return (0,0,0)
    return _date_tuple(ds[-1])

def fill_missing_practical_from_row(rec: Dict, row_text: str) -> None:
    """
    (분할표, 실기 phase)에서 '발표'만 있고 '접수기간/시험일'이 비어 있을 때
    행 전체 텍스트의 날짜 범위 2개를 이용해 복원:
      - 더 늦게 끝나는 범위  → '시험일'
      - 더 이른 범위        → '접수기간'
    """
    if rec.get("phase") != "실기":
        return
    if rec.get("접수기간") or rec.get("시험일"):
        return
    if not rec.get("발표"):
        return

    ranges = DATE_RANGE.findall(row_text)
    # 중복 제거(표준화)
    uniq: list[str] = []
    for rg in ranges:
        if rg not in uniq:
            uniq.append(rg)

    if len(uniq) >= 2:
        a, b = uniq[0], uniq[1]
        later, earlier = (a, b) if _range_end(a) > _range_end(b) else (b, a)
        rec["시험일"]   = _coalesce_date_field(later)
        rec["접수기간"] = _coalesce_date_field(earlier)



# ── 메인 파서 ─────────────────────────────────────────────────────────────────
def parse_schedule_tables(tables: List[Dict]) -> List[Dict]:
    out: List[Dict] = []
    last_round: Optional[str] = None   # 직전 회차 기억

    for t in tables or []:
        rows = t.get("rows") or []
        if len(rows) < 2:
            continue

        headers   = [str(x) for x in rows[0]]
        col_info  = [classify(h) for h in headers]
        phased_table = any(ph for ph, _ in col_info)

        # '정답발표' 헤더 즉시 재매핑
        for i, h in enumerate(headers):
            tt = norm(h)
            if ("발표" in tt) and ("정답" in tt):
                ph, _ = col_info[i]
                col_info[i] = (ph, "정답발표")

        header_text = "".join(norm(x) for x in headers)
        if not any(k in header_text for k in ("원서","접수","필기","실기","면접","발표","회차","구분","시험일정","서류","의견제시")):
            continue

        header_has_chasu = _header_has_chasu(headers)

        for r in rows[1:]:
            cells = [clean(c) for c in r]
            if is_banner_row(cells):
                if ES_DEBUG: print("[exam_schedule] banner-row skipped:", cells[:2])
                continue

            # 행 단위 억제 규칙(필기+면제 문구면 필기 억제)
            row_text_norm = norm(" ".join(cells or []))
            suppress_phases: set[str] = set()
            if ("필기" in row_text_norm) and ("면제" in row_text_norm):
                suppress_phases.add("필기")

            row_phase = detect_row_phase(cells[0] if cells else "") or detect_row_phase(" ".join(cells))
            if not phased_table:
                row_phase = None

            base = {
                "회차": None, "phase": None,
                "접수기간": None, "추가접수기간": None, "서류제출기간": None,
                "시험일": None, "의견제시기간": None, "발표": None, "정답발표": None,
            }
            bucket = {None: base.copy(), "필기": base.copy(), "실기": base.copy(), "면접": base.copy()}

            # 이 행에서 각 phase에 '날짜가 든 값'이 실제로 들어왔는지 추적
            phase_touch = {None: 0, "필기": 0, "실기": 0, "면접": 0}

            # 1) 첫 셀(구분)에서 회차 강제 추출
            first_cell_raw = cells[0] if cells else ""
            first_cell_round = extract_round(first_cell_raw)
            if first_cell_round:
                bucket[None]["회차"] = first_cell_round
            elif "정기" in norm(first_cell_raw):
                # 숫자 회차가 없어도 '정기 기능사' 등의 문구 보존
                bucket[None]["회차"] = clean(first_cell_raw)

            # 2) 열 매핑
            for i, (phase, field) in enumerate(col_info):
                if field is None:
                    continue
                val = cells[i] if i < len(cells) else ""

                # 회차 컬럼
                if field == "회차":
                    vr = extract_round(val) or clean(val)
                    bucket[None]["회차"] = vr
                    txt = norm(vr)
                    if "필기" in txt: bucket["필기"]["회차"] = vr
                    if "실기" in txt: bucket["실기"]["회차"] = vr
                    if "면접" in txt: bucket["면접"]["회차"] = vr
                    continue

                eff_phase = phase if phased_table else None

                # 발표/정답발표 강제 가드
                ht = norm(headers[i])
                vt = norm(val)
                field_eff = field
                if ("발표" in ht or "발표" in vt) and ("정답" in ht or "정답" in vt):
                    field_eff = "정답발표"
                elif "발표" in ht:
                    field_eff = "발표"

                # 실제 머지 대상 phase 계산(중립헤더 + 행 phase 라우팅)
                if phased_table and eff_phase is None and row_phase in ("필기","실기","면접"):
                    target_bucket = bucket[row_phase]
                    target_phase  = row_phase
                else:
                    target_bucket = bucket[eff_phase] if eff_phase in bucket else bucket[None]
                    target_phase  = eff_phase  # None 가능

                _merge_assign(target_bucket, field_eff, clean(val))

                # 날짜가 보이면 해당 phase 터치 카운트
                if DATE_ANY.search(val or ""):
                    phase_touch[target_phase if target_phase in phase_touch else None] += 1

            # 2.5) 우세 phase 산출 후, None 버킷의 값들을 우세 phase로 보정 이동
            dominant_phase = max(("필기","실기","면접"), key=lambda ph: phase_touch.get(ph, 0))
            if phase_touch.get(dominant_phase, 0) == 0:
                dominant_phase = None
            if dominant_phase:
                for k in ("접수기간","추가접수기간","서류제출기간","시험일","의견제시기간","발표","정답발표"):
                    v = bucket[None].get(k)
                    if v and not bucket[dominant_phase].get(k):
                        bucket[dominant_phase][k] = v
                if bucket[None].get("회차") and not bucket[dominant_phase].get("회차"):
                    bucket[dominant_phase]["회차"] = bucket[None]["회차"]

            # 3) 레코드 확정
            phase_records: List[Dict] = []
            for ph, rec in bucket.items():
                # 실 payload가 없으면 버림
                has_payload = any(rec.get(k) for k in ("접수기간","추가접수기간","서류제출기간","시험일","의견제시기간","발표","정답발표"))
                if not has_payload:
                    continue
                if ph in suppress_phases:
                    continue

                # 유령 phase 방지: 분할표면 해당 phase로 날짜가 실제로 들어왔을 때만 채택
                if phased_table and ph in ("필기","실기","면접") and phase_touch.get(ph, 0) == 0:
                    continue

                rec["phase"] = ph

                # 회차 채우기
                if not rec.get("회차"):
                    base_round = bucket[None].get("회차")
                    if base_round:
                        rec["회차"] = base_round
                    elif last_round:
                        rec["회차"] = last_round
                    if rec.get("회차") and ph:
                        rec["회차"] = rec["회차"].replace("필기", ph).replace("실기", ph).replace("면접", ph)

                # 접수 텍스트 보정
                main, extra = split_extra(rec.get("접수기간"))
                if main is not None:
                    rec["접수기간"] = main
                if extra and not rec.get("추가접수기간"):
                    rec["추가접수기간"] = extra
                fix_spillover_in_signup(rec)
                rescue_misplaced_announce_or_exam(rec)   # ← 이 줄 추가

                # 🔧 실기 fallback: 발표만 있고 접수/시험이 비었으면 행 전체에서 복원
                fill_missing_practical_from_row(rec, " ".join(cells or []))

                # coalesce + sanitize
                for k in ("접수기간","추가접수기간","서류제출기간","의견제시기간","시험일","발표","정답발표"):
                    rec[k] = _coalesce_date_field(rec.get(k))
                _sanitize_dates(rec)

                # 차수 확장 여부
                use_chasu = phased_table or header_has_chasu or _value_has_chasu(rec.get("회차"))
                expanded = expand_by_round_and_chasu(rec) if use_chasu else expand_by_round(rec)
                phase_records.extend(expanded)

            # 분할표면 진짜 phase만 유지
            has_real = any(r["phase"] in ("필기","실기","면접") for r in phase_records)
            if phased_table and has_real and row_phase:
                phase_records = [r for r in phase_records if r["phase"] in ("필기","실기","면접")]

            # 이번 행에서 회차가 확인되면 last_round 갱신
            for rr in phase_records:
                if rr.get("회차"):
                    last_round = rr["회차"]
                    break

            out.extend(phase_records)

    cleaned = [
        r for r in out
        if any(r.get(k) for k in ("접수기간","추가접수기간","서류제출기간","시험일","의견제시기간","발표","정답발표"))
    ]
    return cleaned
