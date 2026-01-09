import chardet

def detect_encoding(file_path, num_bytes=2048):
    """파일의 인코딩을 자동 감지하고 신뢰도 높은 인코딩을 반환"""
    with open(file_path, 'rb') as f:
        raw_data = f.read(num_bytes)
    result = chardet.detect(raw_data)
    encoding = result['encoding']

    if encoding is None:
        return 'utf-8'  # 기본값 설정
    elif encoding.lower() in ['ascii', 'iso-8859-1']:
        return 'cp949'  # 한국어 파일일 가능성이 크므로 cp949 설정
    return encoding
    
def read_file_with_encoding(file_path):
    """📌 감지된 인코딩으로 파일을 읽고, 한글이 깨지면 다른 인코딩으로 재시도"""
    detected_encoding = detect_encoding(file_path)
    encodings = [detected_encoding, 'utf-8-sig', 'utf-8', 'cp949', 'euc-kr', 'latin1']

    for enc in encodings:
        try:
            with open(file_path, 'r', encoding=enc, errors='ignore') as file:
                lines = file.readlines()
                print(f"✅ 성공적으로 읽음 (사용된 인코딩: {enc})")
                return lines, enc
        except UnicodeDecodeError:
            print(f"⚠ {enc} 인코딩으로 읽기 실패, 다른 인코딩 시도 중...")

    print("❌ 모든 인코딩 시도 실패. 기본값 utf-8 사용")
    return [], 'utf-8'

def safe_decode(text):
    """ISO-8859-1로 감지된 한글을 복구하기 위한 디코딩 함수"""
    try:
        # 🚨 ISO-8859-1로 저장된 깨진 한글을 복구하기 위해 여러 인코딩 변환 시도
        encoding_attempts = ["cp949", "euc-kr", "utf-8"]

        # 한글이 깨진 경우 추가 변환
        for enc in encoding_attempts:
            try:
                decoded_text = text.encode("iso-8859-1", errors="ignore").decode(enc, errors="ignore")
                
                # ✅ 한글 포함 여부 확인
                if any("\uac00" <= ch <= "\ud7a3" for ch in decoded_text):
                    return decoded_text  # 한글이 포함되면 정상 변환된 것으로 간주하고 반환
            except (UnicodeDecodeError, LookupError):
                continue

        return text  # 변환 실패 시 원본 유지

    except Exception as e:
        print(f"❌ safe_decode() 변환 오류: {e}")
        return text  # 오류 발생 시 원본 그대로 반환
