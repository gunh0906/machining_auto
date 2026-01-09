import os
import re
import pandas as pd
from datetime import datetime
from .encoding_utils import detect_encoding, read_file_with_encoding, safe_decode
# ===== 작업번호 추출 캐시(폴더 단위) =====
_JOBNO_CACHE = {}


def get_default_data():
    """작업자, 작업번호, 설비명, 날짜 기본 데이터 객체 생성"""
    return {
        "작업자": "",  # 사용자 입력값
        "작업번호": "N/A",  # 폴더 경로에서 추출 예정
        "설비명": "N/A",  # 문자열에서 추출 예정
        "날짜": datetime.now().strftime("%m-%d")  # 현재 날짜 자동 입력 (MM-DD 형식)
    }


def extract_job_number(folder_path, debug: bool = False):
    """경로 내에서 숫자가 6자리 이상 포함되고 '_'를 포함한 폴더명을 찾아 반환"""
    if not os.path.exists(folder_path):
        print(f"❌ 폴더 경로가 존재하지 않습니다: {folder_path}")
        return "N/A"

    # 경로를 '/' 또는 '\' 기준으로 분할하여 폴더별로 리스트화
    
    path_parts = os.path.normpath(folder_path).split(os.sep)
    if debug:
        print(f"🔍 경로 분할 결과: {path_parts}")

    matched_folders = []  # 매칭된 폴더명을 저장할 리스트
    number_pattern = re.compile(r'\d+')  # 숫자 찾기

    for folder in path_parts:
        has_underscore = "_" in folder  # _ 포함 여부
        numbers_found = number_pattern.findall(folder)  # 폴더 내 모든 숫자 찾기
        total_digit_count = sum(len(num) for num in numbers_found)  # 총 숫자 개수 계산

        # ✅ 숫자의 총 길이가 6자리 이상이고 '_'가 포함된 경우 매칭
        if has_underscore and total_digit_count >= 6:
            if debug:
                print(f"✅ 매칭된 폴더명 발견: {folder} (숫자 개수: {total_digit_count}, 숫자 목록: {numbers_found})")
            matched_folders.append(folder)
        else:
            missing_conditions = []
            if not has_underscore:
                missing_conditions.append("_ 없음")
            if total_digit_count < 6:
                missing_conditions.append(f"숫자 6자리 부족 (총 숫자 개수: {total_digit_count}, 숫자 목록: {numbers_found})")
            if debug:
                print(f"❌ 매칭되지 않은 폴더: {folder} (이유: {', '.join(missing_conditions)})")

    # 매칭된 폴더가 있다면 가장 적합한 폴더 반환
    if matched_folders:
        best_match = sorted(matched_folders, key=len, reverse=True)[0]  # 가장 긴 폴더명을 우선 반환
        if debug:
            print(f"✅ 최종 선택된 작업번호: {best_match}")
        return best_match

    # 특정 패턴을 찾지 못하면 "N/A" 반환
    if debug:
        print("🔍 6자리 이상 숫자가 포함되고 '_'가 있는 폴더를 찾지 못함. 'N/A' 반환")
    return "N/A"

def extract_tool_data(file_path, folder_path):
    """
    파일에서 TOOL CALL 및 TOOL D/B(TNAME:) 정보를 추출합니다.
    - 반환 구조:
      (tool_db, tool_number, allowance_value, pg_name, equip_name,
       job_number, date, coolant_code, detected_encoding)
    """
    try:
        detected_encoding = "utf-8"

        lines, detected_encoding = read_file_with_encoding(file_path)
        if not lines:
            return (
                "N/A", "N/A", "N/A", "N/A",
                "N/A", "N/A", "N/A",
                "OFF", detected_encoding
            )

        lines = [line.strip() for line in lines[:80]]

        tool_db = "N/A"
        tool_number = "N/A"
        allowance_value = "N/A"
        pg_name = "N/A"
        equip_name = "N/A"
        job_number = extract_job_number(folder_path)
        date = datetime.now().strftime("%m-%d")
        coolant_code = "OFF"

        equipment_patterns = [
            r"DINO_MAX#3", r"DINO_MAX#2",
            r"DINO_MAX#1", r"DINO", r"STINGER"
        ]

        coolant_map = {
            r"\bM08\b": "OIL",
            r"\bM8\b": "OIL",
            r"\bM17\b": "AIR",
            r"\bM28\b": "IN AIR",
            r"\bM18\b": "IN OIL",
        }

        for line in lines:
            line_upper = line.upper()

            match_tname = re.search(r"TNAME\s*:\s*(.+)", line, re.IGNORECASE)
            if match_tname:
                tool_db = match_tname.group(1).strip()

            match_tool_call = re.search(r"TOOL CALL\s+(\d+)\s+Z", line, re.IGNORECASE)
            if match_tool_call:
                tool_number = match_tool_call.group(1).strip()

            match_allowance = re.search(r"ALLOWANCE\s*:\s*([-\d\.]+)", line, re.IGNORECASE)
            if match_allowance:
                allowance_value = match_allowance.group(1).strip()

            match_pg = re.search(r"\[([^\]]+)\]", line)
            if match_pg:
                pg_name = match_pg.group(1).strip()

            if equip_name == "N/A":
                for pattern in equipment_patterns:
                    if re.search(pattern, line, re.IGNORECASE):
                        equip_name = pattern
                        break

            match_job = re.search(r"JOB NUMBER\s*:\s*(\S+)", line, re.IGNORECASE)
            if match_job:
                job_number = match_job.group(1).strip()

            if coolant_code == "OFF":
                for pattern, meaning in coolant_map.items():
                    if re.search(pattern, line_upper):
                        coolant_code = meaning
                        break

        return (
            tool_db, tool_number, allowance_value, pg_name,
            equip_name, job_number, date,
            coolant_code, detected_encoding
        )

    except Exception as e:
        print(f"❌ 파일 분석 오류: {e}")
        return (
            "N/A", "N/A", "N/A", "N/A",
            "N/A", "N/A", datetime.now().strftime("%m-%d"),
            "OFF", "utf-8"
        )



def export_to_excel(file_path, table):
    """QTableWidget 데이터를 Excel로 저장하는 함수"""
    data = []
    for row in range(table.rowCount()):
        row_data = []
        for col in range(table.columnCount()):
            item = table.item(row, col)
            row_data.append(item.text() if item else "")
        data.append(row_data)
    
    df = pd.DataFrame(data, columns=["FILE명", "TOOL D / B", "공구 번호", "여유량(XY)", "작업 내용", "설비명", "작업번호"])
    df.to_excel(file_path, index=False)
