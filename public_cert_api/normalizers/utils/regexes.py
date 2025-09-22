import re, datetime as dt
DATE = re.compile(r"(?P<y>\d{2,4})[.\-\/](?P<m>\d{1,2})[.\-\/](?P<d>\d{1,2})")
LAW  = re.compile(r"(대통령령)\s*제?\s*(\d+)\s*호")
HHMM_RANGE = re.compile(r"(?P<s>\d{1,2}:\d{2}).{0,10}~.{0,10}(?P<e>\d{1,2}:\d{2})")
URL = re.compile(r"https?://[^\s]+")

def now_iso():
    return dt.datetime.now().astimezone().isoformat(timespec="seconds")

def norm_date(s: str) -> str | None:
    m = DATE.search(s or "")
    if not m: return None
    y = int(m.group("y"))
    if y < 100: y = 1900 + y if y >= 50 else 2000 + y
    return f"{y:04d}-{int(m.group('m')):02d}-{int(m.group('d')):02d}"
