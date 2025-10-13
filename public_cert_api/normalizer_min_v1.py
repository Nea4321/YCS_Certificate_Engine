# normalizer_min_v1.py (PATCH)
from pathlib import Path
import argparse, json
from .paths import RAW_DIR, DATA_DIR
from .normalizers.v1_core.build import build_norm

ap = argparse.ArgumentParser()
ap.add_argument("--jmcd", required=True)
ap.add_argument("--root", default=None, help="override data root (e.g. E:\\cert-data\\chansol_api)")
ap.add_argument("--name", default=None)
ap.add_argument("--type", dest="type_str", default=None)
ap.add_argument("--issued-by", dest="issued_by", default=None)
ap.add_argument("--out", default=None, help="output root for *.norm.json")   # <<<<<< 추가
args = ap.parse_args()

# base root 결정
base = Path(args.root) if args.root else RAW_DIR
if not base.is_absolute():
    base = DATA_DIR / base

# 폴더/파일 두 구조 모두 지원
jm_root = (base / str(args.jmcd)).resolve()
cand1 = jm_root / f"{args.jmcd}.json"   # .../9745/9745.json
cand2 = base / f"{args.jmcd}.json"      # .../9745.json
raw_path = cand1 if cand1.exists() else cand2 if cand2.exists() else None
if raw_path is None:
    raise FileNotFoundError(f"not found: {cand1} or {cand2}")

raw = json.loads(raw_path.read_text(encoding="utf-8"))

# 출력 경로 결정
if args.out:
    out_root = Path(args.out).resolve()
    out_root.mkdir(parents=True, exist_ok=True)
    out_path = out_root / f"{args.jmcd}.norm.json"
else:
    jm_root.mkdir(parents=True, exist_ok=True)
    out_path = jm_root / f"{args.jmcd}.norm.json"

norm = build_norm(raw, args.jmcd, args.name, args.type_str, args.issued_by)

out_path.write_text(json.dumps(norm, ensure_ascii=False, indent=2), encoding="utf-8")
print(f"[in ] {raw_path}")
print(f"[out] {out_path}")
