# settings_manager.py
# 전역 설정(설비 목록, 설비별 작업자명)과 파일명 생성 규칙 관리 모듈

from __future__ import annotations
import json
import re
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Tuple

# 전역 설정 파일 경로 (main.py와 같은 디렉토리에 두도록 함)
BASE_DIR = Path(__file__).resolve().parent
GLOBAL_SETTINGS_PATH = BASE_DIR / "global_settings.json"


def sanitize_for_filename(text: str) -> str:
    """
    파일명에 쓰기 어려운 문자를 간단히 정리.
    - 공백 → '_'
    - 한글/영문/숫자/_/- 만 허용
    """
    t = (text or "").strip()
    t = t.replace(" ", "_")
    t = re.sub(r"[^0-9A-Za-z가-힣_\-]", "", t)
    return t or "NONAME"


def generate_default_filename(project: str, machine: str) -> str:
    """
    기본 저장 파일명 규칙:
      프로젝트명_설비명_YYYYMMDD.json
    """
    project_s = sanitize_for_filename(project)
    machine_s = sanitize_for_filename(machine)
    today = datetime.now().strftime("%Y%m%d")
    return f"{project_s}_{machine_s}_{today}.json"


# ─────────────────────────────────────
# 전역 설정: 설비 목록 / 설비별 작업자명
# ─────────────────────────────────────

def load_global_settings() -> Tuple[List[str], Dict[str, str]]:
    """
    전역 설정 파일(global_settings.json)에서
    설비 목록과 설비별 작업자명을 읽어온다.

    반환:
      (machine_list, operator_map)

    - machine_list : ["DINO 5AX", "STINGER", ...]
    - operator_map : {"DINO 5AX": "홍길동", ...}

    파일이 없거나 오류가 나면 ([], {}) 반환.
    """
    if not GLOBAL_SETTINGS_PATH.exists():
        return [], {}

    try:
        with GLOBAL_SETTINGS_PATH.open("r", encoding="utf-8") as f:
            data = json.load(f)
    except Exception:
        return [], {}

    machines = data.get("machine_list", [])
    operator_map = data.get("operator_map", {})

    # 구버전 호환: operator_name 이 단일 문자열로 있는 경우,
    # 모든 설비에 동일 작업자를 매핑해 준다.
    if not operator_map and isinstance(data.get("operator_name"), str):
        old_name = data.get("operator_name")
        operator_map = {m: old_name for m in machines}

    # 타입 방어
    if not isinstance(machines, list):
        machines = []
    machines = [str(m) for m in machines]

    if not isinstance(operator_map, dict):
        operator_map = {}

    # operator_map 키/값을 문자열로 정리
    clean_map: Dict[str, str] = {}
    for k, v in operator_map.items():
        clean_map[str(k)] = "" if v is None else str(v)

    return machines, clean_map


def save_global_settings(machine_list: List[str], operator_map: Dict[str, str]) -> None:
    """
    현재 설비 목록과 설비별 작업자명을 전역 설정 파일(global_settings.json)에 저장.
    """
    # 존재하지 않는 설비 키는 제거
    mset = set(machine_list or [])
    filtered_map = {m: (operator_map.get(m) or "") for m in mset}

    data = {
        "machine_list": list(machine_list or []),
        "operator_map": filtered_map,
        "updated_at": datetime.now().isoformat(timespec="seconds"),
    }

    try:
        with GLOBAL_SETTINGS_PATH.open("w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    except Exception as e:
        # UI가 아니므로 단순 출력만
        print(f"[settings_manager] 전역 설정 저장 중 오류: {e}")


def get_operator_for_machine(machine: str, operator_map: Dict[str, str]) -> str:
    """
    주어진 설비명에 대응하는 작업자명을 반환.
    없으면 빈 문자열.
    """
    if not machine:
        return ""
    return operator_map.get(machine, "") or ""
