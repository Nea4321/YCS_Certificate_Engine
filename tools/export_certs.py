from dotenv import load_dotenv
from pathlib import Path
import os, re, csv
import pymysql

load_dotenv(dotenv_path=Path(__file__).resolve().parents[1] / ".env")

def build_url_from_parts():
    h, p, n = os.getenv("DB_HOST"), os.getenv("DB_PORT"), os.getenv("DB_NAME")
    if h and p and n:
        return f"jdbc:postgresql://{h}:{p}/{n}"
    return None

JDBC = os.getenv("DB_URL") or build_url_from_parts()
USER = os.getenv("DB_USERNAME") or os.getenv("DB_USER")
PASS = os.getenv("DB_PASSWORD")

if not JDBC or not USER:
    raise SystemExit("DB_URL / DB_USERNAME(.env) 확인 필요")

def to_native_conn_params(url: str):
    m = re.match(r"jdbc:(mysql|postgresql)://([^/:]+)(?::(\d+))?/([^?]+)", url)
    if not m: raise SystemExit(f"지원하지 않는 JDBC URL: {url}")
    kind, host, port, db = m.groups()
    port = int(port) if port else (3306 if kind=="mysql" else 5432)
    return kind, host, port, db

kind, host, port, db = to_native_conn_params(JDBC)

ROOT = Path(__file__).resolve().parents[1]   # Engine/
OUT  = Path(os.getenv("CERT_EXPORT_CSV", ROOT / "out" / "certs.csv"))
OUT.parent.mkdir(parents=True, exist_ok=True)


SQL = """
SELECT certificate_id, jmcd, certificate_name
FROM certificate
WHERE jmcd IS NOT NULL
ORDER BY certificate_id
"""

rows = []
if kind == "mysql":
    conn = pymysql.connect(host=host, port=port, user=USER, password=PASS,
                           database=db, charset="utf8mb4", cursorclass=pymysql.cursors.DictCursor)
    with conn:
        with conn.cursor() as cur:
            cur.execute(SQL)
            rows = cur.fetchall()
elif kind == "postgresql":
    import psycopg2, psycopg2.extras
    conn = psycopg2.connect(host=host, port=port, user=USER, password=PASS, dbname=db)
    with conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(SQL)
            rows = cur.fetchall()
else:
    raise SystemExit(f"미지원 DB: {kind}")

# CSV 쓰기 (jmcd는 반드시 문자열로!)
OUT.parent.mkdir(parents=True, exist_ok=True)
with OUT.open("w", newline="", encoding="utf-8") as f:
    w = csv.writer(f)
    w.writerow(["certificate_id","jmcd","certificate_name"])
    for r in rows:
        jmcd = str(r["jmcd"])  # 앞자리 0 보존
        w.writerow([r["certificate_id"], jmcd, r["certificate_name"]])

print(f"[ok] exported {len(rows)} rows -> {OUT}")
