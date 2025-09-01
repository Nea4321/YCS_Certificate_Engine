# schemas/v1.py
from pydantic import BaseModel
from typing import List, Optional, Literal
from datetime import datetime, timezone

class MetaV1(BaseModel):
    schema_version: Literal["v1"] = "v1"   # ← 이름 변경
    generated_at: str = datetime.now(timezone.utc).astimezone().isoformat()
    cert: str

class ExamItemV1(BaseModel):
    회차: str
    등급: Optional[str] = None
    원서접수표시: Optional[str] = None
    시험일자표시: Optional[str] = None
    발표표시: Optional[str] = None
    registerStart: Optional[str] = None
    registerEnd: Optional[str] = None
    examDate: Optional[str] = None
    resultDate: Optional[str] = None

class ExamScheduleV1(BaseModel):
    정기검정일정: List[ExamItemV1]

class ContentV1(BaseModel):
    syllabus: Optional[List[dict]] = None
    coverage: Optional[List[dict]] = None

class RootV1(BaseModel):
    _meta: MetaV1
    시험일정: Optional[ExamScheduleV1] = None
    시험내용: Optional[ContentV1] = None
