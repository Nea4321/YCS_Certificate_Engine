# YCS Certificate **Engine** (Python)

자격증 공개/사설 정보를 크롤링·정규화해 **JSON 산출물**을 만드는 파이썬 엔진입니다.  
이 문서는 **`Crawling/Certificate/Engine` 루트**에서 사용하는 기준으로 작성되었습니다.

---

## 폴더 구성(요약)

```
Engine/
 ├─ public_cert_api/            # Q-Net(공개) 파이프라인: fetch/parse/normalize 러너
 ├─ private-cert-crawl/         # 사설(학교/민간) 크롤러 모음
 ├─ tools/
 │   └─ export_certs.py         # DB에서 certificate_id,jmcd,certificate_name,organization_id,inst → certs.csv 내보내기
 ├─ .gitignore / requirements.txt / README.md / run_once.py ...
```

---

## 1) 빠른 시작 (공개 Q-Net 정규화만 돌려보기)

### A. 필수 요건

- **Python 3.11+**
- **Chrome 최신 버전** (Selenium이 자동으로 ChromeDriver를 맞춰줍니다)
- (Windows) **PowerShell** 또는 (macOS/Linux) **bash**

**Windows에서 Python 설치(권장):**
```powershell
winget install Python.Python.3.11
```

### B. 가상환경 & 의존성

> 가상환경을 쓰면 의존성 격리/재현성이 좋아지고, 업그레이드/롤백이 안전하며, 실패 시 폴더만 지우면 깨끗하게 복원됩니다.

```bash
# venv 생성 (둘 중 하나 사용)
python -3.11 -m venv .venv
# 또는
py -3.11 -m venv .venv

# 위 명령이 막히면 버전 생략
python -m venv .venv
```

**활성화 & 설치**

- Windows (PowerShell):
```powershell
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```

- macOS/Linux (bash):
```bash
source ./.venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```

### B-2. 작업 루트(예: `chansol_api`) 만들기

> 엔진이 산출물을 쓰고 읽을 **루트 폴더**입니다. 경로는 사용자가 자유롭게 정해도 됩니다.

- Windows:
```powershell
New-Item -ItemType Directory -Force "C:\cert-data\chansol_api" | Out-Null
$BASE = "C:\cert-data"
$ROOT = Join-Path $BASE 'chansol_api'
```

- macOS/Linux:
```bash
mkdir -p ~/cert-data/chansol_api
BASE=~/cert-data
ROOT="$BASE/chansol_api"
```

---

## 2) 입력 데이터 & 실행

### C. 입력 데이터 준비

정규화 러너는 **탭별 HTML** 또는 **파싱된 JSON**이 있는 루트를 요구합니다. 예시:

```
C:\cert-data\chansol_api\1320\
  ├─ basic_info.html.gz
  ├─ exam_info.html.gz
  ├─ preference.html.gz
  └─ (정규화 결과는 같은 폴더에 생성)
```

> `--mode snapshot` : **fetch 단계를 건너뛰고**, 위 HTML/JSON 스냅샷을 바로 parse/normalize 합니다.  
> `--mode http` : Q-Net에서 직접 요청해 **fetch → parse → normalize** 순서로 수행합니다.

### C-2. certificate_id 매핑(선택)

정규화 산출물의 `_meta.certificate_id`를 채우고 싶다면 **`tools/export_certs.py`**로 CSV를 만듭니다.

---

### D. 한 종목 실행 (fetch → parse → normalize)

> HTML 스냅샷이 없으면 `--mode http`에서 **fetch**로 받아옵니다.

**PowerShell**
```powershell
$BASE  = Resolve-Path ..\..\..
$ROOT  = Join-Path $BASE 'chansol_api'
$CSV   = Join-Path $BASE 'certs.csv'      # 선택(있으면 _meta 보강)

python -m public_cert_api.run_public `
  --root "$ROOT" `
  --csv  "$CSV" `
  --jmcd 0080 `
  --mode http `
  --steps fetch,parse,normalize
```

> 기존 산출물을 **덮어써야** 하면 `--force`를 추가하세요.

---

### E. 여러 종목 일괄 실행

`r013.txt`(국가기관), `others.txt`(타기관) 등에 JMCD를 한 줄에 하나씩 넣어두세요. 예:

```
1320
0370
0752
```

**국가기관 (PowerShell)**
```powershell
python -m public_cert_api.run_public `
  --root "$ROOT" `
  --list ".\r013.txt" `
  --mode http `
  --steps fetch,parse,normalize
```

**타기관 (PowerShell)**  
스냅샷이 준비되어 있다면 `--mode snapshot` 으로 바로 파싱/정규화:
```powershell
python -m public_cert_api.run_public `
  --root "$ROOT" `
  --list ".\others.txt" `
  --mode snapshot `
  --steps parse,normalize
```

> 기존 결과를 덮어쓸 땐 `--force`를 더하세요.

---

### E-2. 쿠키 기반 안정화 옵션

**미리 서버에서 쿠키를 받아두고 요청하려면:**
```powershell
python -m public_cert_api.run_public `
  --root "$ROOT" `
  --csv  "$CSV" `
  --jmcd 0451 `
  --steps fetch,parse,normalize `
  --mode http `
  --force `
  --prewarm `
  --cookie_log
```
- `--cookie_log` : 쿠키 수집 로그 출력  
- `--prewarm` : 런타임에 쿠키를 먼저 받아서 사용

**쿠키 파일을 직접 지정해서 사용할 수도 있습니다:**
```powershell
python -m public_cert_api.run_public `
  --root "$ROOT" `
  --csv  "$CSV" `
  --jmcd 0451 `
  --steps fetch,parse,normalize `
  --mode http `
  --force `
  --cookies "C:\cert-data\chansol_api\cookies.txt" `
  --cookie_log
```
> 경로는 절대/상대 모두 가능. 저장소에 포함된 예시 위치를 기준으로 수정해 사용하세요.

---

### F. 산출물 확인 (최근 2시간 내 생성된 norm.json 개수)

**PowerShell**
```powershell
$all    = Get-ChildItem $ROOT -Recurse -Include *.norm.json -File
$since  = (Get-Date).AddHours(-2)  # 기준 창(2시간) 설정
$recent = $all | Where-Object { $_.LastWriteTime -ge $since }

"total=$($all.Count)  recent=$($recent.Count)  all_recent? " + ($recent.Count -eq $all.Count)
```
> 예) 전체 664개가 최신화되었는지(=최근 창 내 생성/수정) 빠르게 점검

---

## 3) 사설(민간/학교) 크롤러

`private-cert-crawl/` 이하의 크롤러는 **크롤링 → JSON 저장**까지 담당합니다.  
공유 저장소에서는 `.env`를 제공하지 않으므로, 팀 외부에서는 **DB 내보내기 기능은 비활성**로 간주하세요.

**공통 실행(예시)**
```bash
python run_once.py --cert linux_master --config private-cert-crawl/configs/cert_map.yaml
# 산출물은 기본적으로 Engine/data/ 아래 생성
```

Spring에서 소비하려면 결과 JSON을 **Spring 프로젝트의 `src/main/resources/json/`**로 복사하세요.

---

## 4) CSV 내보내기 & 정규화 결과에 주입(선택)

### A. .env 템플릿(팀 내부 DB 접속 가능 시)
> **중요**: `.env`는 절대 커밋하지 않습니다.

```
# .env.example (이 파일만 공개 저장소에 커밋)
DB_HOST=your-db-host.example.com
DB_PORT=your_port
DB_NAME=your_db_name
DB_USERNAME=your_db_user
DB_PASSWORD=your_secure_password
# DB_URL=jdbc:postgresql://HOST:PORT/DBNAME  # 한 줄 URL로 쓰고 싶다면
```

### B. CSV 내보내기
```bash
# Engine 루트에서
python tools/export_certs.py
# 기본 출력: Engine/out/certs.csv
# 환경변수 CERT_EXPORT_CSV 로 경로 변경 가능
```

### C. 정규화 결과에 주입
```powershell
$BASE = Resolve-Path ..\..\..
$ROOT = Join-Path $BASE 'chansol_api'
$CSV  = Join-Path $PWD  'out\certs.csv'   # Engine/out/certs.csv

python -m public_cert_api.run_public `
  --root "$ROOT" `
  --csv  "$CSV" `
  --jmcd 1320 `
  --mode snapshot `
  --steps normalize `
  --force
```
> CSV 없이도 실행은 됩니다. 이 기능은 **certificate_id/name을 `_meta`에 보강**하고 싶을 때만 사용하세요.

---

## 5) 커밋/배포 가이드

- **커밋 금지**: `.env`, `.venv/`, `__pycache__/`, 크롤링 캐시, 대용량 산출물(선택)
- 팀원 설치 절차:  
  1) 저장소 클론 → 2) 가상환경 생성/활성화 → 3) `pip install -r requirements.txt`
- Windows PowerShell은 **줄바꿈용 백틱(`)**, bash는 **` \`** 사용
- 항상 `python -m package.module` 형태로 실행(상대 import 오류 방지)

---

## 6) 자주 보는 오류 & 해결

- `ImportError: attempted relative import with no known parent package`  
  → 모듈 루트에서 **`python -m public_cert_api.run_public`** 같이 `-m` 사용.

- `ModuleNotFoundError: No module named 'psycopg2'`  
  → DB 내보내기 기능을 쓰는 경우에만 필요. `pip install -r requirements.txt` 재확인.

- 경로 인식 문제(Windows)  
  → PowerShell의 **따옴표**와 **백틱 줄바꿈**을 확인.  
  → 예: `--root "C:\cert-data\chansol_api"` 처럼 전체를 따옴표로 감쌈.

---

## 7) 라이선스

프로젝트 루트의 `LICENSE` 파일을 따릅니다.
