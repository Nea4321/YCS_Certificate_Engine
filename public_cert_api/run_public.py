# public_cert_api/run_public.py
from __future__ import annotations
from typing import Optional, Dict  # 파일 상단에 있으면 더 좋음
import argparse, sys, subprocess, time, shutil, gzip
from pathlib import Path
import json
from .normalizers.v1_core.build_trace import build_norm_with_trace
# run_public.py 상단
import csv
import os
import re

def _clean_jmcd(s: str) -> str | None:
    # 앞뒤 공백, 따옴표, BOM 제거
    s = (s or "").strip().lstrip("\ufeff").strip("'\"")
    # 숫자만 남기기
    s = re.sub(r"\D+", "", s)
    # 4자리만 유효
    return s if len(s) == 4 else None
#BOM을 제거 하기 위해 이 함수를 쓰며 BOM이란 텍스트 파일 맨 앞에 붙는 특수한 표시로 UTF-8에서는 바이트 3개 EF BB BF (10진수 239, 187, 191), 파이썬에선 문자 '\ufeff'.이다
#리스트의 첫 줄앞에 BOM이 있으면 그 줄이 이상하게 읽혀서 경로를 못 찾는 상황이 발생하므로 
#반드시 지워야 한다. 어쩌다가 생긴진 모르겠는데 내가 무의식적으로 새로운 걸 추가했다 지우고 새로 저장해서 생겼을 가능성도 있음
#그래서 사전에 아예 지워버리고 시작한다

def load_idmap(csv_path: str) -> dict[str, dict]:
    if not csv_path:
        return {}
    mp: dict[str, dict] = {}
    # CSV도 BOM 가능 → utf-8-sig
    with open(csv_path, newline="", encoding="utf-8-sig") as f:
        for r in csv.DictReader(f):
            jmcd = _clean_jmcd(r.get("jmcd") or "")
            if not jmcd:
                continue
            mp[jmcd] = {
                "certificate_id": (r.get("certificate_id") or "").strip(),
                "certificate_name": (r.get("certificate_name") or "").strip(),
            }
    return mp



def run(cmd: list[str]) -> None:
    print("[cmd]", " ".join(cmd))
    p = subprocess.run(cmd)
    if p.returncode != 0:
        raise SystemExit(p.returncode)

def has(path: Path) -> bool:
    return path.exists()

def exists_htmls(jm_root: Path) -> bool:
    # .html 또는 .html.gz 둘 다 인정
    def any_ext(stem: str) -> bool:
        return has(jm_root / f"{stem}.html") or has(jm_root / f"{stem}.html.gz")
    return all(any_ext(stem) for stem in ("basic_info","exam_info","preference"))

def exists_parsed(jm_root: Path) -> bool:
    # 9694.json 또는 9694 (무확장) 둘 다 인정
    base = jm_root / jm_root.name
    return has(base.with_suffix(".json")) or has(base)

def exists_norm(jm_root: Path) -> bool:
    # 9694.norm.json 또는 9694.norm 둘 다 인정
    base = jm_root / f"{jm_root.name}.norm"
    return has(base.with_suffix(".json")) or has(base)

def compress_or_remove_htmls(jm_root: Path, policy: str) -> None:
    files = [jm_root/"basic_info.html", jm_root/"exam_info.html", jm_root/"preference.html"]
    for f in files:
        if not f.exists():  # 이미 .gz일 수도 있음
            gz = Path(str(f) + ".gz")
            if gz.exists():
                continue
            else:
                continue
        if policy == "keep":
            continue
        if policy == "gz":
            gz_path = f.with_suffix(f.suffix + ".gz")
            with f.open("rb") as src, gzip.open(gz_path, "wb") as dst:
                dst.write(src.read())
            f.unlink(missing_ok=True)
        if policy == "rm":
            f.unlink(missing_ok=True)

def ensure_free_space(root: Path, min_free_gb: float) -> None:
    free_gb = shutil.disk_usage(root).free / (1024**3)
    print(f"[disk] free={free_gb:.1f} GB (min={min_free_gb} GB)")
    if free_gb < min_free_gb:
        raise SystemExit(f"ENOSPC: free={free_gb:.1f}GB < {min_free_gb}GB")

def iter_jmcds(arg_jmcd: str | None, list_file: str | None, root: Path):
    if arg_jmcd:
        cj = _clean_jmcd(arg_jmcd)
        if cj:
            yield cj
        return

    if list_file:
        # 리스트 파일은 무조건 utf-8-sig 로 읽어 BOM 자동 제거
        with open(list_file, encoding="utf-8-sig") as f:
            for line in f:
                cj = _clean_jmcd(line)
                if cj:
                    yield cj
        return

    # 리스트를 안 주면 디렉터리명에서 추출
    for d in sorted(p.name for p in root.iterdir() if p.is_dir()):
        cj = _clean_jmcd(d)
        if cj:
            yield cj


def run_normalize_with_trace(root: Path, jmcd: str, cert_meta: Optional[Dict] = None):
    jm_dir = root / jmcd

    def read_json_variants(stem: str):
        for fname in [stem, f"{stem}.json"]:
            p = jm_dir / fname
            if p.exists():
                return json.loads(p.read_text(encoding="utf-8"))
        return None

    raw_p = jm_dir / "raw.json"
    if raw_p.exists():
        raw = json.loads(raw_p.read_text(encoding="utf-8"))
    else:
        bi = read_json_variants("basic_info") or {}
        ex = read_json_variants("exam_info") or {}
        pr = read_json_variants("preference") or {}
        if not (bi or ex or pr):
            raise FileNotFoundError(f"[{jmcd}] no raw.json and no basic_info/exam_info/preference files in {jm_dir}")
        raw = {"tabs": {"basic_info": bi, "exam_info": ex, "preference": pr}}

    # build_norm_with_trace: (norm, trace, issues)
    _, trace, issues = build_norm_with_trace(raw, jmcd, name=None, type_str=None, issued_by=None)

    # ← 여기서 certificate_id/이름을 trace 메타에 주입
    if cert_meta:
       trace.setdefault("_meta", {}).update({
        "certificate_id": cert_meta.get("certificate_id"),
        "certificate_name_from_db": cert_meta.get("certificate_name"),
       })
       # trace의 표시 이름도 없으면 CSV 이름으로 채움
       nm = (cert_meta.get("certificate_name") or "").strip()
       if nm and trace["_meta"].get("name") in (None, "", jmcd):
          trace["_meta"]["name"] = nm

    # trace만 저장 (norm.json은 생성하지 않음)
    (jm_dir / "norm_trace.json").write_text(
        json.dumps(trace, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    # issues.jsonl에도 certificate_id 함께 남김(있을 때만)
    with (root / "issues.jsonl").open("a", encoding="utf-8") as f:
        f.write(json.dumps({
            "jmcd": jmcd,
            "certificate_id": (cert_meta.get("certificate_id") if cert_meta else None),
            "issues": issues
        }, ensure_ascii=False) + "\n")

    


def main():
    ap = argparse.ArgumentParser(description="Fetch→Parse→Normalize 파이프라인")
    ap.add_argument("--root", help=r'예: C:\cert-data\chansol_api')
    ap.add_argument("--snapshot-root", help="스냅샷 루트 별칭(없으면 --root 사용)")
    ap.add_argument("--jmcd", help="단일 자격코드")
    ap.add_argument("--list", help="여러 jmcd가 들어있는 txt 파일")
    ap.add_argument("--steps", default="fetch,parse,normalize", help="콤마로 선택: fetch,parse,normalize")
    ap.add_argument("--mode", choices=["http","snapshot"], default="http",
                    help="snapshot: fetch 스킵하고 오프라인 파싱만")
    ap.add_argument("--resume", action="store_true", help="이미 있는 산출물은 건너뜀")
    ap.add_argument("--force", action="store_true", help="기존 산출물 무시하고 재실행")
    ap.add_argument("--out", help=r'정규화 결과 저장 루트(예: C:\cert_norm_out)')
    ap.add_argument("--sleep", type=float, default=0.6, help="jmcd 간 대기(초)")
    ap.add_argument("--min-free-gb", type=float, default=5.0, help="최소 여유 용량(GB)")
    ap.add_argument("--keep-html", choices=["keep","gz","rm"], default="gz",
                    help="parse 이후 HTML 보존 정책: keep=그대로, gz=gzip 압축, rm=삭제")
    ap.add_argument("--name", default="seed", help="태그/로그용 이름(선택)")
    ap.add_argument("--display-name", help="한글 표시명(파일 _meta.name 패치용)")
    ap.add_argument("--csv", help="certificate_id/jmcd 매핑 CSV 경로")
    ap.add_argument("--frame-mode", choices=["off", "selenium"], default="off",
                help="fetch 단계에서 iframe 본문 저장 방식")
    ap.add_argument("--prewarm", action="store_true",
                help="fetch 전에 세션 예열 1회")
    ap.add_argument("--cookies", help="Netscape 포맷 cookies.txt 경로")
    # 선택: 쿠키 로그 on/off (환경변수 대신 플래그로)
    ap.add_argument("--cookie_log", action="store_true",
                help="쿠키 적재/전송 정보 로그 출력")
    args = ap.parse_args()


    idmap = load_idmap(args.csv)

    root_arg = args.snapshot_root or args.root
    if not root_arg:
        raise SystemExit("--root 또는 --snapshot-root 중 하나는 필요합니다.")
    root = Path(root_arg).resolve()
    ensure_free_space(root, args.min_free_gb)

    # steps 정리: snapshot 모드면 fetch 강제 제외
    steps = set(s.strip() for s in args.steps.split(",") if s.strip())
    if args.mode == "snapshot" and "fetch" in steps:
        steps.remove("fetch")

    # 출력 루트
    out_root = Path(args.out).resolve() if args.out else None
    if out_root:
        out_root.mkdir(parents=True, exist_ok=True)

    for jmcd in iter_jmcds(args.jmcd, args.list, root):
        jm_root = root / jmcd
        jm_root.mkdir(parents=True, exist_ok=True)
        print(f"\n===== [{jmcd}] ({args.name}) =====")

        # 존재 체크 플래그
        have_htmls = exists_htmls(jm_root)
        have_parsed = exists_parsed(jm_root)
        have_norm = exists_norm(jm_root)

        # 스킵/포스 정책
        def should(step_exists: bool) -> bool:
            if args.force:  # 항상 실행
                return True
            if args.resume and step_exists:  # 있으면 건너뛰기
                return False
            return True

        # 1) Fetch
        if "fetch" in steps:
            if args.mode == "snapshot":
                print("[skip] fetch (snapshot mode)")
            elif not should(have_htmls):
                print("[skip] fetch (resume)")
            else:
                cmd = [sys.executable, "-m", "public_cert_api.fetch_qnet_tabs_min",
               "--jmcd", jmcd, "--out", str(root), "--frame-mode", args.frame_mode]
                if args.prewarm:
                   cmd += ["--prewarm"]
                if args.cookies:
                   cmd += ["--cookies", args.cookies]
                if args.cookie_log:
                   os.environ["FETCH_COOKIE_LOG"] = "1"

                run(cmd)
                have_htmls = exists_htmls(jm_root)
                #run(cmd)는 public_cert_api.fetch_qnet_tabs로 자식 파이썬 프로세스를 띄우고
                #자식 프로세스는 시작 시점에 부모(run_public)의 환경변수를 가져가므로 쿠키 로깅(쿠키 발급과정을 보여줌)을 켜려면
                #run(cmd)를 호출 직전에 os.environ["FETCH_COOKIE_LOG"] = "1" -> 이걸로 설정해야 됨
                #따라서 cookie.log안에 run(cmd)를 쓸 경우 이미 호출한 상태에서 쿠키 로깅을 키는 것이므로
                #의미가 없다 그래서 반드시 호출전에 찍어야 된다.  
        else:
            print("[skip] fetch (steps)")

        # 2) Parse
        if "parse" in steps:
            if not should(have_parsed):
                print("[skip] parse (resume)")
            else:
                run([sys.executable, "-m", "public_cert_api.parse_tabs_min",  "--jmcd", jmcd, "--root", str(root)])
                compress_or_remove_htmls(jm_root, args.keep_html)
                have_parsed = exists_parsed(jm_root)
        else:
            print("[skip] parse (steps)")

        # 3) Normalize
        if "normalize" in steps:
            if not should(have_norm):
                print("[skip] normalize (resume)")
            else:
                cmd = [sys.executable, "-m", "public_cert_api.normalizer_min_v1",
                       "--jmcd", jmcd, "--root", str(root)]
                if out_root:
                    cmd += ["--out", str(out_root)]
                run(cmd)
                have_norm = exists_norm(jm_root) or (out_root and any((out_root/ jmcd).parent.exists() for _ in [0]))
        else:
            print("[skip] normalize (steps)")

        if args.csv:
            cert = idmap.get(jmcd)
            if cert:
                # out_root가 있으면 out 쪽, 아니면 jm_root 쪽에서 찾음
                target_root = out_root or jm_root
                legacy = target_root / f"{jmcd}.norm.json"
                if legacy.exists():
                    obj = json.loads(legacy.read_text(encoding="utf-8"))
                    meta = obj.setdefault("_meta", {})
                    cid = cert.get("certificate_id")
                    if cid:
                        meta["certificate_id"] = str(cid)
                    csv_name = (cert.get("certificate_name") or "").strip()
                    if csv_name and (meta.get("name") in (None, "", jmcd)):
                        meta["name"] = csv_name
                    legacy.write_text(json.dumps(obj, ensure_ascii=False, indent=2), encoding="utf-8")
                    print(f"[patch] add certificate_id -> {legacy}")
                else:
                    print(f"[patch][skip] legacy norm not found: {legacy}")    

        ensure_free_space(root, args.min_free_gb)
        time.sleep(args.sleep)

        try:
            run_normalize_with_trace(root, jmcd, cert_meta=idmap.get(jmcd))
            print(f"[trace] norm_trace.json + issues.jsonl written for {jmcd}")
        except Exception as e:
            print(f"[trace][warn] failed to build trace for {jmcd}: {e}")

        if args.display_name:
            # out_root가 있으면 out 경로의 norm.json, 아니면 jm_root의 norm.json을 패치
            target_root = out_root or jm_root
            norm_path = target_root / f"{jmcd}.norm.json"
            if norm_path.exists():
                obj = json.loads(norm_path.read_text(encoding="utf-8"))
                meta = obj.setdefault("_meta", {})
                meta["name"] = args.display_name
                norm_path.write_text(json.dumps(obj, ensure_ascii=False, indent=2), encoding="utf-8")
                print(f"[patch] set _meta.name='{args.display_name}' -> {norm_path}")
            else:
                print(f"[warn] norm file not found for display-name: {norm_path}")

    print("\n[ALL DONE]")

if __name__ == "__main__":
    main()
