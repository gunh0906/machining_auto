# cam_core.py
from __future__ import annotations

import os
import re
from typing import List

from .cam_models import CamRow
from .functions import extract_tool_data


def natural_sort_key(text: str):
    """
    파일명을 자연스럽게 정렬하기 위한 키를 생성합니다.
    예: T1, T2, ..., T10
    """
    return [int(c) if c.isdigit() else c for c in re.split(r"(\d+)", text)]


def scan_cam_rows(folder_path: str) -> List[CamRow]:
    """
    폴더 내 .h 파일을 스캔하여 CamRow 리스트로 반환합니다.
    - UI/출력/DB에서 공용으로 사용하기 위한 서비스 함수입니다.
    """
    if not os.path.isdir(folder_path):
        return []

    rows: List[CamRow] = []
    for file_name in os.listdir(folder_path):
        if not file_name.lower().endswith(".h"):
            continue

        file_path = os.path.join(folder_path, file_name)

        tool_db, tool_no, allowance, pg_name, equip_name, job_number, date, coolant, detected_encoding = extract_tool_data(
            file_path, folder_path
        )

        rows.append(
            CamRow(
                file_name=file_name,
                tool_db=tool_db,
                tool_no=tool_no,
                allowance_xy=allowance,
                pg_name=pg_name,
                coolant=coolant,
                equip_name=equip_name,
                job_number=job_number,
                date=date,
                detected_encoding=detected_encoding,
            )
        )

    rows.sort(key=lambda r: natural_sort_key(r.file_name))
    return rows

# cam_core.py (하단에 추가)

import re
from typing import Tuple

from .encoding_utils import read_file_with_encoding


def update_tool_call_in_file(file_path: str, new_tool_number: str) -> Tuple[bool, str]:
    """
    .h 파일 내 'TOOL CALL <번호> Z...' 구문에서 <번호>만 new_tool_number로 교체합니다.

    반환:
        (ok, message)
        - ok: True면 수정 성공(또는 변경 불필요), False면 실패
        - message: 로그/디버깅용 메시지
    """
    if not new_tool_number.isdigit():
        return (False, "new_tool_number가 숫자가 아닙니다.")

    try:
        lines, detected_encoding = read_file_with_encoding(file_path)
        if not lines:
            return (False, f"파일을 읽지 못했습니다: {file_path}")

        pattern = re.compile(r"(TOOL CALL\s+)(\d+)(\s+Z.*)", re.IGNORECASE)

        modified = False
        new_lines = []

        for line in lines:
            m = pattern.search(line)
            if m:
                prefix, old_no, suffix = m.group(1), m.group(2), m.group(3)
                if old_no != new_tool_number:
                    # 줄 끝 개행 유지
                    end = "\n" if line.endswith("\n") else ""
                    line = f"{prefix}{new_tool_number}{suffix}{end}"
                    modified = True
            new_lines.append(line)

        if not modified:
            return (True, "변경할 TOOL CALL이 없거나 이미 동일 번호입니다.")

        # 감지된 인코딩으로 저장(읽은 인코딩을 최대한 유지)
        with open(file_path, "w", encoding=detected_encoding, errors="ignore") as f:
            f.writelines(new_lines)

        return (True, f"TOOL CALL 수정 완료: {new_tool_number} (encoding={detected_encoding})")

    except Exception as e:
        return (False, f"TOOL CALL 수정 실패: {e}")


def update_tool_call_in_folder(folder_path: str, file_name: str, new_tool_number: str) -> Tuple[bool, str]:
    """
    folder_path + file_name으로 파일 경로를 구성하여 TOOL CALL을 수정합니다.
    """
    full_path = os.path.join(folder_path, file_name)
    return update_tool_call_in_file(full_path, new_tool_number)
