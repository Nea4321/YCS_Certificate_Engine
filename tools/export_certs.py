from dotenv import load_dotenv
from pathlib import Path
import os, re, csv

load_dotenv(dotenv_path=Path(__file__).resolve().parents[1] / ".env")

def build_url_from_parts():
    h, p, n = os.getenv("DB_HOST"), os.getenv("DB_PORT"), os.getenv("DB_NAME")
    if h and p and n:
        return f"jdbc:postgresql://{h}:{p}/{n}"
    return None

JDBC = os.getenv("DB_URL") or build_url_from_parts()
USER = os.getenv("DB_USERNAME") or os.getenv("DB_USER")
PASS = os.getenv("DB_PASSWORD")
DEFAULT_INST = os.getenv("DEFAULT_INST", "R013")  # 매핑 없을 때 기본값

if not JDBC or not USER:
    raise SystemExit("DB_URL / DB_USERNAME(.env) 확인 필요")

def to_native_conn_params(url: str):
    m = re.match(r"jdbc:(mysql|postgresql)://([^/:]+)(?::(\d+))?/([^?]+)", url)
    if not m: raise SystemExit(f"지원하지 않는 JDBC URL: {url}")
    kind, host, port, db = m.groups()
    port = int(port) if port else (3306 if kind=="mysql" else 5432)
    return kind, host, port, db

kind, host, port, db = to_native_conn_params(JDBC)

ROOT = Path(__file__).resolve().parents[1]         # Engine/
TOOLS = ROOT / "tools"
OUTDIR = ROOT / "out"
OUTDIR.mkdir(parents=True, exist_ok=True)

OUT_CSV = Path(os.getenv("CERT_EXPORT_CSV", OUTDIR / "certs.csv"))
ORG_MAP_CSV = Path(os.getenv("ORG_MAP_CSV", TOOLS / "org_map.csv"))

# --- DB에서 certificate + organization_id까지 가져오기 ---
SQL = """
SELECT c.certificate_id, c.jmcd, c.certificate_name, c.organization_id
FROM certificate c
WHERE c.jmcd IS NOT NULL
ORDER BY c.certificate_id
"""

rows = []
if kind == "postgresql":
    import psycopg2, psycopg2.extras
    conn = psycopg2.connect(host=host, port=port, user=USER, password=PASS, dbname=db)
    with conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(SQL)
            rows = cur.fetchall()
else:
    raise SystemExit(f"미지원 DB: {kind}")

# --- org_map.csv 로드(없으면 뼈대 생성) ---
def load_org_map(path: Path) -> dict[int, str]:
    if not path.exists():
        # DB에서 고유 organization_id 추출해 뼈대 파일 생성
        uniq = []
        seen = set()
        for r in rows:
            oid = r.get("organization_id")
            if oid is None: 
                continue
            if oid not in seen:
                seen.add(oid)
                uniq.append(oid)
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("w", newline="", encoding="utf-8") as f:
            w = csv.writer(f)
            w.writerow(["organization_id","inst"])
            for oid in uniq:
                w.writerow([oid, ""])  # inst 비워둠(사용자가 채움)
        print(f"[init] org_map skeleton -> {path}  (inst 칸을 채우고 다시 실행하세요)")
        return {}
    # 파일이 이미 있으면 로드
    mapping: dict[int, str] = {}
    with path.open("r", encoding="utf-8") as f:
        rd = csv.DictReader(f)
        for row in rd:
            try:
                oid = int(row["organization_id"])
            except Exception:
                continue
            inst = (row.get("inst") or "").strip()
            if inst:
                mapping[oid] = inst
    return mapping

org_map = load_org_map(ORG_MAP_CSV)

# --- certs.csv 쓰기(최종) ---
with OUT_CSV.open("w", newline="", encoding="utf-8") as f:
    w = csv.writer(f)
    w.writerow(["certificate_id","jmcd","certificate_name","organization_id","inst"])
    for r in rows:
        jmcd = str(r["jmcd"])  # 앞자리 0 보존
        name = r["certificate_name"]
        oid = r.get("organization_id")
        inst = org_map.get(oid, DEFAULT_INST) if oid is not None else DEFAULT_INST
        w.writerow([r["certificate_id"], jmcd, name, oid if oid is not None else "", inst])

print(f"[ok] exported {len(rows)} rows -> {OUT_CSV}")
print(f"[info] org_map size={len(org_map)} default_inst={DEFAULT_INST}")
