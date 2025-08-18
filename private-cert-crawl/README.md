# Private Certificate Crawl

이 프로젝트는 **자격증 정보 크롤링**을 수행하여 JSON 데이터로 저장하는 Python 기반 엔진입니다.  
Spring Boot 프로젝트와 연동하여 `src/main/resources/json` 경로에 저장된 JSON을 활용합니다.

## 1. 설치 환경
- **Python 3.11+**
- **Google Chrome** (최신 버전)
- **ChromeDriver** (Selenium이 자동 관리)
- **Git (저장소 클론용)**

## 2. 설치 방법
### 2-1. 저장소 클론
```bash
git clone https://github.com/your-repo/YCS_Certificate_Engine.git
cd YCS_Certificate_Engine/private-cert-crawl
```

### 2-2. 가상환경 생성 및 활성화
```bash
python -m venv .venv

# Windows
.venv\Scripts\Activate.ps1

# Mac/Linux
source .venv/bin/activate
```

### 2-3. 의존성 설치(수동 설치) A
```bash
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```

### 2-4. 의존성 설치(bootstrap 자동 설치) B
```bash
python engine_bootstrap.py
```

## 3. 실행 방법
### 3-1. 기본 실행
JSON 출력 경로를 직접 지정:
```bash
python run_once.py --cert linux_master
```
--cert 뒤에는 자격증 디렉토리명(linux_master, office_master, digital_information 등)을 입력합니다.
실행하면 각 탭별 크롤러가 실행되고, JSON 파일이 생성됩니다.

### 3-2. 경로 미지정 시
경로를 지정하지 않으면 자동으로 프로젝트 내 `data/` 폴더에 저장됩니다.  
(단, Spring Boot에서 사용하려면 **반드시** `src/main/resources/json` 하위로 복사 필요)

## 4. JSON 저장 위치 (Spring 연동)
Spring Boot 프로젝트에서 JSON을 자동 인식하려면:
```
YCS_Certificate_Spring/src/main/resources/json/linux_master_full.json
```
위 폴더 안에 크롤링된 JSON을 넣으세요.

## 5. 팀 협업 규칙
  - 가상환경 공유하지 않는것으로 .venv/는 .gitignore에 추가. 팀원은 각자 생성.
  - 파이썬은 각자의 pc에 설치가 되어있어야 하고 .venv는 팀원과 서버가 같은 환경을 쉽게 맞추기    
    위해 존재함(각자의 버전이 다르면 실행이 안될수도 있기 때문)
  - requirements.txt 활용
    새 라이브러리 설치 시:
    pip freeze > requirements.txt
    팀원
    python -m pip freeze > requirements.txt-> 표준 파이썬 프로젝트에서 쓰는 의존성 목록 파일로 이걸 설치해야 사용가능
  - 모든 자격증 실행은 run_once.py를 통해 수행.
    개별 자격증마다 main.py는 더 이상 사용하지 않음. 


## 6. 주의 사항
- 크롬 버전이 너무 오래되면 Selenium이 정상 동작하지 않을 수 있습니다.
- pip 대신 반드시 python -m pip 사용을 권장합니다. (경로 꼬임 방지)

- 팀원은 private-cert-crawl/만 받아도 실행 가능하지만,
- Spring 연동을 하려면 Spring 프로젝트도 함께 필요합니다.