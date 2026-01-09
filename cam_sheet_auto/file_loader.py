import os
import re
from functions import extract_tool_data

def natural_sort_key(text):
    """파일명을 자연스럽게 정렬하기 위한 함수 (T1, T2, ..., T10 순서 유지)"""
    return [int(c) if c.isdigit() else c.lower() for c in re.split(r'(\d+)', text)]

def load_h_files(folder_path):
    files_data = []
    found_h_files = False
    try:
        file_list = os.listdir(folder_path)
        for file_name in file_list:
            if file_name.lower().endswith(".h"):
                found_h_files = True
                file_path = os.path.join(folder_path, file_name)

                try:
                    tool_db, tool_number, allowance, pg_name, equip_name, job_number, date, coolant, detected_encoding = extract_tool_data(
                        file_path, folder_path
                    )

                    print(f"파일: {file_name}, 설비명: {equip_name}")

                    if not equip_name:
                        equip_name = "N/A"

                    files_data.append(
                        (file_name, tool_db, tool_number, allowance, pg_name, equip_name, job_number, date, coolant)
                    )

                except Exception as e:
                    print(f"❌ 파일 처리 오류 ({file_name}): {e}")
    except Exception as e:
        print(f"❌ 폴더를 읽을 수 없음: {e}")

    if not found_h_files:
        print("⚠ 선택한 폴더에 .H 파일이 없습니다!")

    files_data.sort(key=lambda x: natural_sort_key(x[0]))
    return files_data
