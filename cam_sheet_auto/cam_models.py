# cam_models.py
from __future__ import annotations
from dataclasses import dataclass


@dataclass(frozen=True)
class CamRow:
    """
    CAM 시트 1행의 표준 데이터 모델입니다.
    - DB/ML/PrintEngine 출력의 기준 스키마로 사용합니다.
    """
    file_name: str
    tool_db: str
    tool_no: str
    allowance_xy: str
    pg_name: str
    coolant: str
    equip_name: str
    job_number: str
    date: str  # "MM-DD"
    detected_encoding: str = "utf-8"
