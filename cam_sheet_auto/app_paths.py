# app_paths.py
from pathlib import Path

def project_root() -> Path:
    """
    현재 프로젝트(cam_sheet_auto)의 루트 경로를 반환합니다.
    실행 위치(CWD)와 무관하게 항상 동일한 경로를 제공합니다.
    """
    return Path(__file__).resolve().parent

def res_path(*parts: str) -> Path:
    """
    프로젝트 루트 기준 리소스 경로를 반환합니다.
    예: res_path("assets", "main-logo.png")
    """
    return project_root().joinpath(*parts)

