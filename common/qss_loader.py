import os
from typing import Iterable

def load_qss_files(*paths: str) -> str:
    """
    여러 QSS 파일을 순서대로 읽어 하나의 문자열로 합친다.
    - 존재하지 않는 파일은 건너뛴다.
    """
    chunks = []
    for p in paths:
        if not p:
            continue
        if os.path.exists(p) and os.path.isfile(p):
            with open(p, "r", encoding="utf-8") as f:
                chunks.append(f.read())
    return "\n\n".join(chunks)
