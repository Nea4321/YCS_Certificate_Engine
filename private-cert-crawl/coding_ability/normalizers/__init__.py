from .schedule import normalize_schedule
from .content import normalize_content

__all__ = ["normalize_schedule", "normalize_content"]
#이제 여기서 normalize_schedule,normalize_content를 받아서 수출한다 run_once.py에서 import_callable 함수로
#이름을 편집해서 cert_map.yaml에서 편하게 normalize를 불러서 쓰게 만드는 용도이다.