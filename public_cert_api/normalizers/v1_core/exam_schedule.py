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

ROUND_FROM_WORDY = re.compile(
    r"(?:\d{4}\s*년\s*)?정기\s*(?:기능사|기사|산업기사)?\s*([0-9一二三四五六七八九十Ⅰ-Ⅻ]+)\s*회",
    re.I
)
ROUND_TOKEN  = re.compile(r"(상시)|(?:제?\s*([0-9一二三四五六七八九十Ⅰ-Ⅻ]+)\s*(?:회|회차|차))", re.I)
CHASU_TOKEN  = re.compile(r"(?:^|[^0-9一二三四五六七八九十Ⅰ-Ⅻ])([0-9一二三四五六七八九十Ⅰ-Ⅻ]+)\s*차", re.I)

DATE_ANY     = re.compile(r"\d{4}\.\d{1,2}\.\d{1,2}")
DATE_RANGE   = re.compile(r"\d{4}\.\d{2}\.\d{2}\s*[~\-]\s*\d{4}\.\d{2}\.\d{2}")
DATE_SINGLE  = re.compile(r"\d{4}\.\d{2}\.\d{2}")

MERGE_FIELDS = {"접수기간","추가접수기간","서류제출기간","의견제시기간","시험일","발표","정답발표"}

# ── 보조 유틸 ─────────────────────────────────────────────────────────────────
def norm(s: Optional[str]) -> str:
    return clean(s or "").replace(" ", "")

def classify(header_text: str) -> Tuple[Optional[str], Optional[str]]:
    return classify_from_yaml(norm(header_text), ROW_PHASE_RX, RX)

def _header_has_chasu(headers: List[str]) -> bool:
    ht = "".join(norm(h) for h in headers)
    return ("차수" in ht) or ("시험차수" in ht) or ("차수(구분)" in ht)

def _value_has_chasu(v: Optional[str]) -> bool:
    return bool(v and CHASU_TOKEN.search(norm(v)))

def detect_row_phase(text: str) -> Optional[str]:
    t = norm(text)
    for ph, patt in ROW_PHASE_RX.items():
        if patt.search(t): return ph
    return None

def _round_num(tok: Optional[str]) -> Optional[int]:
    if not tok: return None
    if tok.isdigit(): return int(tok)
    if tok in KNUM: return KNUM[tok]
    if tok in RNUM: return RNUM[tok]
    if len(tok) == 2 and tok[0] == "十" and tok[1] in KNUM: return 10 + KNUM[tok[1]]
    return None

def extract_round(text: Optional[str]) -> Optional[str]:
    if not text: return None
    s = norm(text)
    m = ROUND_FROM_WORDY.search(s)
    if m:
        n = _round_num(m.group(1))
        if n: return f"제{n}회"
    m = ROUND_TOKEN.search(s)
    if m:
        if m.group(1): return "상시"
        n = _round_num(m.group(2))
        if n: return f"제{n}회"
    return None

def _dateish(s: Optional[str]) -> bool:
    return bool(s and DATE_ANY.search(s))

def _coalesce_date_field(value: Optional[str]) -> Optional[str]:
    if not value: 
       return None
    s = value.strip()
    dates = DATE_SINGLE.findall(s)
    if not dates: 
       return None
    
    if "~" in s and len(dates) == 1: 
        return f"{dates[0]} ~"
    
    if len(dates) == 1:
        return dates[0]

    return f"{dates[0]} ~ {dates[-1]}"

def _sanitize_dates(rec: Dict) -> None:
    if rec.get("시험일") and not _dateish(rec["시험일"]):
        rec["시험일"] = None
    for k in ("접수기간","추가접수기간","서류제출기간","의견제시기간","발표","정답발표"):
        v = rec.get(k)
        if v and not _dateish(v):
            rec[k] = None

def _merge_assign(rec: Dict, key: str, val: str) -> None:
    if not val: return
    if key in MERGE_FIELDS:
        prev = rec.get(key) or ""
        if prev:
            if val not in prev: rec[key] = f"{prev} {val}".strip()
        else:
            rec[key] = val
    else:
        rec[key] = val

# ── 라운드/차수 확장 ──────────────────────────────────────────────────────────
def normalize_rounds(raw: Optional[str]) -> List[str | int]:
    if not raw: return []
    s = re.sub(r"[·、/]+", ",", str(raw)).replace("~","-").replace("–","-")
    s = re.sub(r"\s+","", s)
    out: List[str | int] = []
    rng = re.search(r"(\d+)\s*-\s*(\d+)", s)
    if rng:
        a, b = int(rng.group(1)), int(rng.group(2))
        out.extend(range(min(a,b), max(a,b)+1))
    for part in re.split(r"[,\-]", s):
        m = ROUND_TOKEN.search(part)
        if not m: continue
        if m.group(1): out.append("상시"); continue
        n = _round_num(m.group(2))
        if n: out.append(n)
    uniq: List[str | int] = []
    for x in out:
        if x not in uniq: uniq.append(x)
    uniq.sort(key=lambda x: (999 if x=="상시" else int(x)))
    return uniq

def normalize_chasus(raw: Optional[str]) -> List[int]:
    if not raw: return []
    s = re.sub(r"[·、/]+", ",", str(raw)).replace("~","-").replace("–","-")
    s = re.sub(r"\s+","", s)
    out: List[int] = []
    rng = re.search(r"(\d+)\s*-\s*(\d+)\s*차", s)
    if rng:
        a, b = int(rng.group(1)), int(rng.group(2))
        out.extend(range(min(a,b), max(a,b)+1))
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
    if ES_DEBUG: print(f"[exam_schedule] expand_by_round raw={rec.get('회차')} -> {rounds}")
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
    chasus = normalize_chasus(raw)
    if not chasus:     return expand_by_round(rec)
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
    if   not dates:          extra = None
    elif len(dates) == 1:    extra = dates[0]
    else:                    extra = f"{dates[0]} ~ {dates[-1]}"
    return (main or None), extra

def fix_spillover_in_signup(rec: Dict) -> None:
    txt = rec.get("접수기간") or ""
    if not txt: return
    if "발표" in txt.replace(" ","") and not rec.get("발표"):
        singles = DATE_SINGLE.findall(txt)
        if singles: rec["발표"] = singles[-1]
        txt = re.sub(r"발표[^0-9]*\d{4}\.\d{2}\.\d{2}", "", txt)
    ranges = DATE_RANGE.findall(txt)
    if len(ranges) >= 2:
        rec["접수기간"] = ranges[0]
        if not rec.get("시험일"): rec["시험일"] = ranges[1]
        rest = DATE_RANGE.sub("", txt)
        singles = DATE_SINGLE.findall(rest)
        if singles and not rec.get("발표"):
            rec["발표"] = singles[-1]
    else:
        rec["접수기간"] = txt or rec.get("접수기간")

def rescue_misplaced_announce_or_exam(rec: Dict) -> None:
    s = (rec.get("접수기간") or "").strip()
    if s and DATE_SINGLE.fullmatch(s) and not rec.get("시험일") and not rec.get("발표"):
        rec["발표"] = s
        rec["접수기간"] = None

def _date_tuple(d: str) -> tuple[int,int,int]:
    y, m, dd = d.split("."); return int(y), int(m), int(dd)

def _range_end(r: str) -> tuple[int,int,int]:
    ds = DATE_SINGLE.findall(r)
    if not ds: return (0,0,0)
    return _date_tuple(ds[-1])

def fill_missing_practical_from_row(rec: Dict, row_text: str) -> None:
    if rec.get("phase") != "실기": return
    if rec.get("접수기간") or rec.get("시험일"): return
    if not rec.get("발표"): return
    ranges = DATE_RANGE.findall(row_text)
    uniq: list[str] = []
    for rg in ranges:
        if rg not in uniq: uniq.append(rg)
    if len(uniq) >= 2:
        a, b = uniq[0], uniq[1]
        later, earlier = (a, b) if _range_end(a) > _range_end(b) else (b, a)
        rec["시험일"]   = _coalesce_date_field(later)
        rec["접수기간"] = _coalesce_date_field(earlier)

# ── 테이블/행 필터 ─────────────────────────────────────────────────────────────
def is_banner_row(cells: List[str]) -> bool:
    text  = " ".join(cells or [])
    first = (cells[0] if cells else "")
    tnorm = norm(text); fnorm = norm(first)
    dates_in_row = len(DATE_ANY.findall(text))
    has_round_token = bool(extract_round(first) or ROUND_TOKEN.search(tnorm))

    rc = BANNERS.get("first_cell_contains")
    if rc and rc.search(fnorm):
        rx_ex = BANNERS.get("first_cell_excludes")
        if not (rx_ex and rx_ex.search(fnorm)) and not has_round_token and dates_in_row == 0:
            return True

    r = BANNERS.get("contains_any")
    if r and r.search(tnorm):
        if not has_round_token and dates_in_row == 0:
            return True

    thr = int(BANNERS.get("min_dates_in_row") or 0)
    if thr > 0 and dates_in_row >= thr:  # (선택적) 일정아님 배너에 날짜가 다수 찍혀있을 때
        return True
    return False

def is_fee_only_table(headers: List[str]) -> bool:
    """수수료/응시료 표(필기/실기만)인지 판별."""
    hdr_norms = [norm(h) for h in headers]
    joined = "".join(hdr_norms)
    has_schedule_cols = any(k in joined for k in ("원서","접수","시험","발표","의견","서류","회차","구분","일정"))
    only_fee_phases = (
        ("수수료" in hdr_norms[0] or "응시료" in joined) and
        all(any(x in h for x in ("필기","실기","면접","수수료","응시료")) for h in hdr_norms)
    )
    return (only_fee_phases and not has_schedule_cols)

# ── 메인 파서 ─────────────────────────────────────────────────────────────────
def parse_schedule_tables(tables: List[Dict]) -> List[Dict]:
    out: List[Dict] = []
    last_round: Optional[str] = None

    for t in tables or []:
        rows = t.get("rows") or []
        if len(rows) < 2:
            continue

        headers  = [str(x) for x in rows[0]]
        col_info = [classify(h) for h in headers]
        phased_table = any(ph for ph, _ in col_info)

        # 정답발표 헤더 즉시 재매핑
        for i, h in enumerate(headers):
            tt = norm(h)
            if ("발표" in tt) and ("정답" in tt):
                ph, _ = col_info[i]
                col_info[i] = (ph, "정답발표")

        # === 수수료 전용 표 스킵 ===
        if is_fee_only_table(headers):
            if ES_DEBUG: print("[skip] fee-only table (no schedule columns)")
            continue

        header_text = "".join(norm(x) for x in headers)
        if not any(k in header_text for k in ("원서","접수","필기","실기","면접","1차", "2차", "발표","회차","구분","시험일정","서류","의견제시")):
            continue

        header_has_chasu = _header_has_chasu(headers)

        # ── 행 처리 ───────────────────────────────────────────────
        for r in rows[1:]:
            cells = [clean(c) for c in r]  # JSON 경로
            if not cells:
                if ES_DEBUG: print("[skip] empty row")
                continue
            if is_banner_row(cells):
                if ES_DEBUG: print("[skip] banner row:", cells[:2])
                continue

            row_text_norm = norm(" ".join(cells))
            suppress_phases: set[str] = set()
            if ("필기" in row_text_norm) and ("면제" in row_text_norm):
                suppress_phases.add("필기")

            # 수수료 내용만 있고 날짜가 전혀 없으면 행 스킵
            if ("수수료" in row_text_norm or "응시료" in row_text_norm) and not DATE_ANY.search(" ".join(cells)):
                if ES_DEBUG: print("[skip] fee row without dates")
                continue

            first_cell_raw = cells[0] if len(cells) > 0 else ""
            row_phase = detect_row_phase(first_cell_raw) or detect_row_phase(" ".join(cells))
            if ES_DEBUG:
                print("[ROWPHASE]", first_cell_raw, "->", row_phase, "| phased_table=", phased_table)

            base = {"회차":None,"phase":None,
                    "접수기간":None,"추가접수기간":None,"서류제출기간":None,
                    "시험일":None,"의견제시기간":None,"발표":None,"정답발표":None}
            bucket = {None: base.copy(), "필기": base.copy(), "실기": base.copy(), "면접": base.copy(), "1차":base.copy(), "2차":base.copy()}
            phase_touch = {None:0, "필기":0, "실기":0, "면접":0, "1차":0, "2차":0}

            # 1) 첫 셀에서 회차 추출
            first_cell_round = extract_round(first_cell_raw)
            if first_cell_round:
                bucket[None]["회차"] = first_cell_round
            elif "정기" in norm(first_cell_raw):
                bucket[None]["회차"] = clean(first_cell_raw)

            # 2) 열 매핑
            for i, (phase, field) in enumerate(col_info):
                if field is None: continue
                val = cells[i] if i < len(cells) else ""

                if field == "회차":
                    vr = extract_round(val) or clean(val)
                    bucket[None]["회차"] = vr
                    txt = norm(vr)
                    if "필기" in txt: bucket["필기"]["회차"] = vr
                    if "실기" in txt: bucket["실기"]["회차"] = vr
                    if "면접" in txt: bucket["면접"]["회차"] = vr
                    if "1차" in txt: bucket["1차"]["회차"] = vr
                    if "2차" in txt: bucket["2차"]["회차"] = vr
                    continue

                eff_phase = phase if phased_table else None
                ht = norm(headers[i]); vt = norm(val)
                field_eff = field
                if ("발표" in ht or "발표" in vt) and ("정답" in ht or "정답" in vt):
                    field_eff = "정답발표"
                elif "발표" in ht:
                    field_eff = "발표"
                if ES_DEBUG:
                    print(f"[COL] hdr='{headers[i]}' val='{val}' -> eff_phase={eff_phase} field_eff={field_eff} row_phase={row_phase}")

                # 중립헤더 + 행 phase 라우팅
                if eff_phase is None and row_phase in ("필기","실기","면접", "1차", "2차"):
                    target_bucket = bucket[row_phase]; target_phase = row_phase
                else:
                    target_bucket = bucket[eff_phase] if eff_phase in bucket else bucket[None]
                    target_phase  = eff_phase
                if ES_DEBUG:
                    print(f"[PUT] -> target_phase={target_phase} field={field_eff} has_date={bool(DATE_ANY.search(val or ''))}")

                _merge_assign(target_bucket, field_eff, clean(val))
                if DATE_ANY.search(val or ""):
                    phase_touch[target_phase if target_phase in phase_touch else None] += 1

            # 2.5) 우세 phase → None 버킷 보정 이동
            dominant_phase = max(("필기","실기","면접"), key=lambda ph: phase_touch.get(ph,0))
            if phase_touch.get(dominant_phase,0) == 0: dominant_phase = None
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
                has_payload = any(rec.get(k) for k in ("접수기간","추가접수기간","서류제출기간","시험일","의견제시기간","발표","정답발표"))
                if not has_payload: continue
                if ph in suppress_phases: continue
                if phased_table and ph in ("필기","실기","면접","1차","2차") and phase_touch.get(ph,0) == 0:
                    continue

                rec["phase"] = ph

                if not rec.get("회차"):
                    base_round = bucket[None].get("회차") or last_round
                    if base_round: rec["회차"] = base_round
                    if rec.get("회차") and ph:
                        rec["회차"] = rec["회차"].replace("필기",ph).replace("실기",ph).replace("면접",ph)

                main, extra = split_extra(rec.get("접수기간"))
                if main is not None: rec["접수기간"] = main
                if extra and not rec.get("추가접수기간"): rec["추가접수기간"] = extra
                fix_spillover_in_signup(rec)
                rescue_misplaced_announce_or_exam(rec)
                fill_missing_practical_from_row(rec, " ".join(cells))

                for k in ("접수기간","추가접수기간","서류제출기간","의견제시기간","시험일","발표","정답발표"):
                    rec[k] = _coalesce_date_field(rec.get(k))
                _sanitize_dates(rec)

                use_chasu = phased_table or header_has_chasu or _value_has_chasu(rec.get("회차"))
                expanded = expand_by_round_and_chasu(rec) if use_chasu else expand_by_round(rec)
                phase_records.extend(expanded)

            has_real = any(r["phase"] in ("필기","실기","면접","1차","2차") for r in phase_records)
            if phased_table and has_real and row_phase:
                phase_records = [r for r in phase_records if r["phase"] in ("필기","실기","면접","1차","2차")]

            for rr in phase_records:
                if rr.get("회차"):
                    last_round = rr["회차"]; break

            out.extend(phase_records)

    cleaned = [
        r for r in out
        if any(r.get(k) for k in ("접수기간","추가접수기간","서류제출기간","시험일","의견제시기간","발표","정답발표"))
    ]
    return cleaned
