# -*- coding: utf-8 -*-
# parse_tabs_min.py — Q-Net 탭 파서 (간결판)
from __future__ import annotations
from pathlib import Path
from bs4 import BeautifulSoup
from urllib.parse import urljoin
import json, argparse, gzip, re, html as _html

# YAML 설정 로드 (섹션 라벨 판정에만 사용)
from public_cert_api.normalizers.v1_core.support.exam_info_config_loader import load_exam_info_config
_, _, _, _, _, _, SEC_MAP = load_exam_info_config()

BASE = "https://q-net.or.kr"

# ──────────────────────────────────────────────────────────────────────────────
# 공통 유틸
# ──────────────────────────────────────────────────────────────────────────────
def clean(s: str) -> str:
    return re.sub(r"\s+", " ", (s or "").strip())

def read_html(p: Path) -> str:
    if p.exists():
        return p.read_text(encoding="utf-8", errors="ignore")
    gz = Path(str(p) + ".gz")
    if gz.exists():
        with gzip.open(gz, "rb") as f:
            return f.read().decode("utf-8", errors="ignore")
    raise FileNotFoundError(p)

def _deep_unescape(s: str, max_rounds: int = 8) -> str:
    """textarea/iframe의 이스케이프 중첩 해제."""
    prev = s or ""
    for _ in range(max_rounds):
        cur = _html.unescape(prev)
        if cur == prev:
            break
        prev = cur
    return (prev.replace("\xa0", " ")
                .replace("&lt;", "<").replace("&gt;", ">")
                .replace("&quot;", '"').replace("&apos;", "'"))

def _bs_tables(html_fragment: str) -> list[dict]:
    out = []
    soup = BeautifulSoup(html_fragment, "html.parser")
    for i, tbl in enumerate(soup.find_all("table")):
        rows = []
        for tr in tbl.find_all("tr"):
            cells = tr.find_all(["th", "td"])
            rows.append([clean(c.get_text(" ")) for c in cells])
        if any(any(c for c in r) for r in rows):
            cap = tbl.find("caption")
            out.append({
                "index": i,
                "caption": clean(cap.get_text()) if cap else None,
                "rows": rows,
            })
    return out

def _gather_tables_from_selectors(soup: BeautifulSoup) -> list[dict]:
    """DOM + textarea + iframe에서 표를 모아 중복 제거."""
    chunks: list[str] = []

    # 1) 전체 DOM
    chunks.append(str(soup))

    # 2) textarea & iframe 본문 (원시 문자열 → 언이스케이프)
    for sel in ('textarea[id^="contents_text_"]', 'iframe[id^="contents_frame_"]'):
        for el in soup.select(sel):
            raw = el.decode_contents() or ""
            raw = raw.strip()
            if raw:
                chunks.append(_deep_unescape(raw))

    # 3) 파싱 + 중복 제거
    seen, tables = set(), []
    for html in chunks:
        for tb in _bs_tables(html):
            key = "\n".join(",".join(r) for r in (tb.get("rows") or []))
            if key and key not in seen:
                seen.add(key)
                tables.append(tb)
    return tables

def collect_links(soup: BeautifulSoup) -> list[dict]:
    out = []
    for el in soup.select("a, button"):
        text = clean(el.get_text(" ", strip=True))
        href = (el.get("href") or "").strip()
        onclick = (el.get("onclick") or "").strip()
        rec = {}
        if text: rec["text"] = text
        if href and href != "#": rec["href"] = urljoin(BASE, href)
        m = re.search(r"cst006Report\('(\d+)'\s*,\s*'(\d+)'\)", onclick)
        if m: rec["action"] = {"fn": "cst006Report", "jmcd": m.group(1), "code": m.group(2)}
        m = re.search(r"fileDown\('([^']+)'\s*,\s*'([^']+)'", onclick)
        if m: rec["download"] = {"fn": "fileDown", "path": m.group(1), "filename": m.group(2)}
        if rec: out.append(rec)

    # dedupe
    seen, uniq = set(), []
    for r in out:
        key = (r.get("text"), r.get("href"),
               tuple(sorted((r.get("action") or {}).items())),
               tuple(sorted((r.get("download") or {}).items())))
        if key not in seen:
            seen.add(key); uniq.append(r)
    return uniq

def collect_paragraphs(soup: BeautifulSoup) -> list[str]:
    """일반 DOM + textarea 텍스트까지 수집."""
    paras: list[str] = []
    for tag in soup.find_all(["p", "li", "div", "td", "th", "a", "span", "b", "strong"]):
        t = clean(tag.get_text(" ", strip=True))
        if t: paras.append(t)
    for ta in soup.select('textarea[id^="contents_text_"]'):
        txt = clean(ta.get_text(" ", strip=True))
        if txt: paras.append(txt)
    # dedupe (순서 유지)
    seen, uniq = set(), []
    for t in paras:
        if t not in seen:
            seen.add(t); uniq.append(t)
    return uniq

# ──────────────────────────────────────────────────────────────────────────────
# 제네릭 탭(기본정보/우대현황) 파서
# ──────────────────────────────────────────────────────────────────────────────
def parse_file(html_path: Path) -> dict:
    html = read_html(html_path)
    soup = BeautifulSoup(html, "html.parser")
    for bad in soup(["script", "style", "noscript"]): bad.decompose()

    body_len = len(soup.get_text(" ", strip=True))
    tables   = _gather_tables_from_selectors(soup)
    paras    = collect_paragraphs(soup)
    links    = collect_links(soup)

    # 출력은 기존과 동일 키 유지
    return {"paragraphs": paras, "tables": tables, "links": links, "body_text_len": body_len}

# ──────────────────────────────────────────────────────────────────────────────
# 시험정보 전용 (라벨 판단 / 표 라벨링)
# ──────────────────────────────────────────────────────────────────────────────
def _title_to_label(ttl: str) -> str | None:
    ttl = (ttl or "").strip()
    if not ttl: return None
    SYL_TOK = ["과목", "배점", "문항", "문항수", "시험시간", "시간"]
    MTH_TOK = ["시험방법", "검정방법", "시험 방식", "시험방식", "검정형태", "시험형태",
               "객관식", "주관식", "필답형", "작업형", "복합형", "면접", "CBT", "PBT"]
    if any(t in ttl for t in SYL_TOK): return "시험과목및배점"
    if any(t in ttl for t in MTH_TOK): return "시험방법"
    # SEC_MAP 기반 가장 많이 맞는 라벨
    cands = []
    for label, tokens in (SEC_MAP or {}).items():
        hit = sum(1 for tok in tokens if tok in ttl)
        if hit: cands.append((label, hit))
    if not cands: return None
    cands.sort(key=lambda x: (-int(x[0] in {"시험과목및배점", "시험방법"}), -x[1]))
    return cands[0][0]

def _heading_text_candidate(node) -> str | None:
    if not getattr(node, "name", None): return None
    cls = " ".join(node.get("class", []))
    if node.name in ("strong", "b", "h3", "h4") or "contTit1" in cls:
        return clean(node.get_text())
    hit = node.find(["strong", "b", "h3", "h4"]) or node.find(class_="contTit1")
    return clean(hit.get_text()) if hit else None

def _nearest_heading_label(el) -> str | None:
    p, cur = el.parent, el
    while p:
        sib = cur.previous_sibling
        while sib:
            if getattr(sib, "name", None):
                txt = _heading_text_candidate(sib)
                if txt:
                    lab = _title_to_label(txt)
                    if lab: return lab
            sib = sib.previous_sibling
        cur, p = p, p.parent
    return None

def _guess_label_from_rows(rows: list[list[str]]) -> str | None:
    flat = " ".join(" ".join(r) for r in rows)
    if re.search(r"(문항수|시험시간|과목|배점)", flat): return "시험과목및배점"
    if re.search(r"(객관식|주관식|필답형|작업형|복합형|면접|서술형|CBT|PBT|검정방법|시험방법)", flat): return "시험방법"
    if re.search(r"(응시자격|결격사유)", flat): return "응시자격"
    if re.search(r"(합격기준|만점|평균|득점)", flat): return "합격기준"
    if re.search(r"(응시수수료|수수료|응시료|원\b)", flat): return "응시수수료"
    return None

def _is_schedule_table(rows: list[list[str]]) -> bool:
    if not rows: return False
    header = " ".join(rows[0])
    schedule = ["접수기간", "서류제출기간", "시험일정", "의견제시기간", "최종정답", "합격자 발표"]
    if any(k in header for k in schedule): return True
    text = " ".join(" ".join(r) for r in rows)
    date_hits = len(re.findall(r"\d{4}\.\d{1,2}\.\d{1,2}", text))
    return date_hits >= 4 and ("필기" in text or "면접" in text or "회" in text)

def parse_exam_info_file(html_path: Path) -> dict:
    html = read_html(html_path)
    soup = BeautifulSoup(html, "html.parser")
    for bad in soup(["script", "style", "noscript"]): bad.decompose()

    # 표 (라벨 포함)
    tables_raw = _gather_tables_from_selectors(soup)
    tables, tables_labeled = [], []
    for idx, tb in enumerate(tables_raw):
        rows = tb.get("rows") or []
        if sum(1 for r in rows for c in r if c) < 2:
            continue
        label = None
        # DOM 테이블에 한해 근접 헤딩 탐색
        dom_tbl = soup.find_all("table")
        if idx < len(dom_tbl):
            label = _nearest_heading_label(dom_tbl[idx]) or _guess_label_from_rows(rows)
        else:
            label = _guess_label_from_rows(rows)

        cap_text = tb.get("caption")
        # '취득방법' 주변 이미지(있으면)도 같이
        img_src = None
        if label == "취득방법":
            img = dom_tbl[idx].find("img") if idx < len(dom_tbl) else None
            box, hop = (dom_tbl[idx].parent if idx < len(dom_tbl) else None), 0
            while not img and box and hop < 3:
                img = box.find("img", recursive=False) or box.find("img")
                box = box.parent; hop += 1
            if img and img.get("src"):
                img_src = urljoin(BASE, img.get("src"))

        tables.append({"rows": rows})
        if not _is_schedule_table(rows):
            tables_labeled.append({
                "index": idx, "label": label, "caption": cap_text,
                "has_th": any(r for r in rows if r and r[0]),
                "rows": rows, "image": img_src
            })

    # 문단: iframe title로 라벨링된 textarea 우선, 없으면 기본 맵
    paras, idx_to_label = [], {}
    for fr in soup.select('iframe[id^="contents_frame_"]'):
        m = re.search(r'contents_frame_(\d+)', fr.get('id', '') or '')
        if m:
            i = int(m.group(1))
            ttl = (fr.get('title') or '').strip()
            lab = _title_to_label(ttl)
            if lab: idx_to_label[i] = lab

    if idx_to_label:
        for i in sorted(idx_to_label):
            lab = idx_to_label[i]
            ta = soup.select_one(f"#contents_text_{i}")
            txt = clean(ta.get_text("\n", strip=True)) if ta else ""
            if txt: paras.append(f"{lab}: {txt}")
    else:
        # 기본 인덱스 추정
        default_map = {0: "출제경향", 1: "취득방법", 2: "출제기준"}
        for i, lab in default_map.items():
            ta = soup.select_one(f"#contents_text_{i}")
            if not ta: continue
            txt = clean(ta.get_text("\n", strip=True))
            if txt: paras.append(f"{lab}: {txt}")

    # 부족하면 헤딩 블록에서 보충
    have = {p.split(":", 1)[0] for p in paras if ":" in p}
    need = set(SEC_MAP.keys()) & {"출제경향", "공개문제", "취득방법", "출제기준"}
    if not need.issubset(have):
        for h in soup.select("b.contTit1"):
            title = clean(h.get_text()); label = _title_to_label(title)
            if not label or label in have: continue
            buf = []
            for sib in h.next_siblings:
                if getattr(sib, "name", None):
                    if "contTit1" in " ".join(sib.get("class", [])): break
                    t = clean(sib.get_text(" ", strip=True))
                    if t: buf.append(t)
            if buf:
                paras.append(f"{label}: " + " ".join(buf))

    links = collect_links(soup)
    return {"paragraphs": paras, "tables": tables, "tables_labeled": tables_labeled, "links": links}

# ──────────────────────────────────────────────────────────────────────────────
# 엔트리
# ──────────────────────────────────────────────────────────────────────────────
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--jmcd", required=True)
    ap.add_argument("--root", default="data/chansol_api")
    args = ap.parse_args()

    root = Path(args.root).resolve()
    jm_root = root / args.jmcd
    jm_root.mkdir(parents=True, exist_ok=True)

    files = {
        "basic_info": jm_root / "basic_info.html",
        "exam_info": jm_root / "exam_info.html",
        "preference": jm_root / "preference.html",
    }

    result = {"jmcd": args.jmcd, "tabs": {}}
    for tab, f in files.items():
        try:
            parsed = parse_exam_info_file(f) if tab == "exam_info" else parse_file(f)
        except FileNotFoundError:
            print(f"[skip] missing {f.name}(.gz)")
            continue

        out_json = jm_root / f"{tab}.json"
        out_json.write_text(json.dumps(parsed, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"[write] {out_json}")
        result["tabs"][tab] = parsed

    merged = jm_root / f"{args.jmcd}.json"
    merged.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"[write] merged -> {merged}")

if __name__ == "__main__":
    main()
