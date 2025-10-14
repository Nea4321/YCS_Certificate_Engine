# YCS Certificate **Engine** (Python)

> 자격증 공개/사설 정보를 크롤링·정규화해서 **JSON 산출물**을 만드는 파이썬 엔진입니다.  
> 이 문서는 **`Crawling/Certificate/Engine` 루트**에서 사용하는 기준으로 작성되었습니다.

---

## 폴더 구성(요약)

```
Engine/
 ├─ public_cert_api/           # Q-Net(공개) 파이프라인: fetch/parse/normalize 러너
 ├─ private-cert-crawl/        # 사설(학교/민간) 크롤러 모음
 ├─ tools/
 │   └─ export_certs.py        # DB에서 certificate_id,jmcd,certificate_name,organization_id,inst → certs.csv 내보내기
 |
 ├─ .gitignore / requirements.txt / README.md / run_once.py ...
```

---

## 1) 빠른 시작 (공개 Q-Net 정규화만 돌려보기)

### A. 필수 요건
- **Python 3.11+**

- **Chrome 최신 버전** (Selenium이 자동으로 ChromeDriver를 맞춰줍니다)
- (Windows) PowerShell 또는 Git Bash

# Windows(파이썬 설치)
winget install Python.Python.3.11

### B. 가상환경 & 의존성
```bash
python -3.11 -m venv .venv or py -3.11 -m venv .venv 

안되면 python -m venv .venv


# Windows
.\.venv\Scripts\Activate.ps1
# macOS/Linux
source ./.venv/bin/activate

python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```
-> 이 가상환경을 쓰는 이유는 의존성 격리와 재현성을 이용해 쉽게 복원하고
   업그레이드/롤백을 안전하게 해서 실패하면 가상환경만 지우면 끝이고
   권한 이슈가 감소되서 로컬에서 설치가 가능해지기 때문입니다.

### B-2. 작업 루트(예: chansol_api) 만들기

# 예시: C:\cert-data\chansol_api 를 작업 루트로 사용

# Windows

New-Item -ItemType Directory -Force "C:\cert-data\chansol_api" | Out-Null
$BASE = "C:\cert-data"
$ROOT = Join-Path $BASE 'chansol_api'

# macOS/Linux

mkdir -p ~/cert-data/chansol_api
BASE=~/cert-data
ROOT="$BASE/chansol_api"

-> 비단 이것뿐 아니라 엔진의 산출물들을 만들 떄 필요한 폴더나 파이썬 
   파일들의 위치는 사용자 본인이 스스로 설정해도 상관없습니다.


### C. 입력 데이터 준비
정규화 러너는 **탭별 HTML 또는 파싱된 JSON**이 있는 루트를 요구합니다. 예시 구조:

```
C:\cert-data\chansol_api\1320\
  ├─ basic_info.html.gz
  ├─ exam_info.html.gz
  ├─ preference.html.gz
  └─ (정규화 결과는 같은 폴더에 생성)
```

> 스냅샷 모드(`--mode snapshot`)에서는 **fetch 단계를 건너뛰고** 위 파일들을 바로 parse/normalize 합니다.


### C-2. certificate_id 매핑(선택)
정규화 산출물의 `_meta.certificate_id`를 채우고 싶다면 **`tools/export_certs.py`**로 CSV를 만듭니다.


### D. 한 종목 일괄 실행(fetch,parse,normalize)
특정한 한 종목만 실행하고 싶을 땐 이렇게 씁니다.(우선 자격증의 html 산출물이 있어야 되는데 그게 없다면 큐넷에서 fetch하고, 그걸 json으로 parse한 후, 정규화 작업인 normalize를 한다.)
$BASE = Resolve-Path ..\..\..  
$ROOT = Join-Path $BASE 'chansol_api'  
$CSV  = Join-Path $BASE 'certs.csv'      
python -m public_cert_api.run_public`  
    --root "$ROOT" `   
    --csv  "$CSV"  `
    --jmcd 0080   `
    --mode http   `
    --steps fetch,parse,normalize

# 여기에 만약 잘못 만들거나 새롭게 만든 걸 기존에 있던 산출물에 추가하고 싶다면 --force를 써서 덮어씌우면 된다.     


### E. 여러 종목 일괄 실행
`r013.txt`에 JMCD를 한 줄에 하나씩 넣고 실행합니다.(r013은 국가기관만이 있는 것으로 타기관은 'others.txt' 파일로 돌린다 섞일 수도 있을 위험을 배제)
마찬가지로 여기에 있는 명령어들도 처음부터 만든다는 전제하에 이렇게 쓰는 거고 만약 덮어씌우고 싶으면 --force를 씀
```text
1320
0370
0752
```
```powershell

#국가
python -m public_cert_api.run_public `
  --root "$ROOT" `
  --list ".\r013.txt" `
  --mode http `
  --steps fetch,parse,normalize `

#타기관
python -m public_cert_api.run_public `
  --root "$ROOT" `
  --list ".\others.txt" `
  --mode shttp `
  --steps fetch,parse,normalize

### E-2. 쿠키를 받아서 안정적으로 확인하고 싶을 때
python -m public_cert_api.run_public `
  --root "$ROOT" `
  --csv  "$CSV" `
  --jmcd 0451 `
  --steps fetch,parse,normalize `
  --mode http `
  --force `
  --prewarm
  --cookie_log

-> --cookie_log를 이용해서 쿠키를 받아왔는지에 대한 로그를 볼 수 있고
   서버에서 쿠키를 받아서 직접 요청하고 싶다면 --prewarm을 쓴다.

python -m public_cert_api.run_public `
  --root "$ROOT" `
  --csv  "$CSV" `
  --jmcd 0451 `
  --steps fetch,parse,normalize `
  --mode http `
  --force `
  --cookies "C:\cert-data\chansol_api\cookies.txt" `
  --cookie_log

-> --prewarm으로 했는데도 제대로 못 받아서 문제가 생겼다면 cookies.txt 
   파일을 기준으로 제대로 받을 수 있게 한다.(절대경로는 후에 사용자가 상대경로로 고치면 되고 지금 올라가 있는 파일 기준으로는 찬솔api 폴더 안에 있음)        


### F. 산출물 확인(Powershell)
```
$all = Get-ChildItem $ROOT -Recurse -Include *.norm.json -File
$since = (Get-Date).AddHours(-2)      # 기준 창 설정
$recent = $all | Where-Object { $_.LastWriteTime -ge $since }
"total=$($all.Count)  recent=$($recent.Count)  all_recent? " + ($recent.Count -eq $all.Count)
=> 664개 전량이 잘 돌아갔는지 확인하는 명령어 즉 664개(r013 + others.txt)의 norm.json이 최신화됐는지 확인함
```


### E. 산출물
실행 후 각 종목 폴더 안에 다음이 생깁니다.

- `{jmcd}.json` : 파싱 중간 산출물
- `{jmcd}.norm.json` : **최종 정규화 결과**
- `norm_trace.json` : 정규화 **추적/근거(trace)** (검수용)
---



### A. .env 템플릿(팀 내부 DB 접속이 가능한 경우만 사용)
> **중요**: `.env`는 절대 커밋하지 않습니다.

```
# .env.example  (이 파일만 공개 저장소에 커밋)
DB_HOST=your-db-host.example.com
DB_PORT=your_port
DB_NAME=your_db_name
DB_USERNAME=your_db_user
DB_PASSWORD=your_secure_password

# (선택) 한 줄 URL로 쓰고 싶다면
# DB_URL=jdbc:postgresql://HOST:PORT/DBNAME

```

### B. CSV 내보내기
```bash
# Engine 루트에서
python tools/export_certs.py
```
- 기본 출력: `Engine/out/certs.csv`
- 환경변수 `CERT_EXPORT_CSV`로 경로를 바꿀 수 있습니다.

### C. 정규화 결과에 주입
`certs.csv`를 만들어 두면 러너가 `_meta.certificate_id`를 자동 패치합니다.

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

## 3) 사설(민간/학교) 크롤러

`private-cert-crawl/` 이하의 크롤러는 **크롤링 → JSON 저장**까지 담당합니다.  
공유 저장소에서는 `.env`를 제공하지 않으므로, 팀 외부에서는 **DB 내보내기 기능은 비활성**로 간주하세요.

### 공통 실행(예시)
```bash
python run_once.py --cert linux_master --config private-cert-crawl\configs\cert_map.yaml 
# 산출물은 기본적으로 Engine/data/ 아래 생성
```

Spring에서 소비하려면 결과 JSON을 **Spring 프로젝트의 `src/main/resources/json/`**로 복사하세요.

---

## 4) 커밋/배포 가이드

- **커밋 금지**: `.env`, `.venv/`, `__pycache__/`, 크롤링 캐시, 대용량 산출물(선택)  
- 팀원 설치 절차
  1) 저장소 클론 → 2) 가상환경 생성/활성화 → 3) `pip install -r requirements.txt`
- **윈도우 PowerShell**에서는 줄바꿈용 백틱(`)을, **bash**에서는 `\`을 사용하세요.
- `python -m package.module` 형태로 실행(상대 import 오류 방지)

---

## 5) 자주 보는 오류 & 해결

- `ImportError: attempted relative import with no known parent package`  
  → 모듈 루트에서 **`python -m public_cert_api.run_public`** 같이 `-m` 사용.

- `ModuleNotFoundError: No module named 'psycopg2'`  
  → DB 내보내기 기능을 쓰는 경우에만 필요합니다. `pip install -r requirements.txt` 확인.

- 경로 인식 문제(Windows)  
  → PowerShell의 **따옴표**와 **백틱 줄바꿈**을 확인.  
  → 예: `--root "C:\cert-data\chansol_api"` 처럼 전체를 따옴표로 감쌉니다.

---

## 6) 라이선스
프로젝트 루트의 `LICENSE` 파일을 따릅니다.
