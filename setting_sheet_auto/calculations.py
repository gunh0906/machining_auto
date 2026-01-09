# calculations.py
# 좌표·치수·Z 관련 모든 계산 전용 모듈

def parse_float(text: str):
    """문자열에서 공백/플러스 기호를 정리하고 실수로 변환. 실패 시 None."""
    try:
        t = text.strip()
        if t == "":
            return None
        # + 기호 허용
        return float(t.replace("+", ""))
    except Exception:
        return None


def format_signed(value: float) -> str:
    """± 기호 포함, 소수점 3자리 포맷."""
    return f"{value:+.3f}"


# ───────────────────────────────────────
# 1. 외곽(X-/X+) → 길이 L, 센터 C
# ───────────────────────────────────────
def calc_outer_to_center(x_minus, x_plus):
    """
    외곽 좌표(X-, X+)로부터 길이 L, 센터 C를 계산.
    x_minus, x_plus: float 또는 None
    return: (L, C) 또는 (None, None)
    """
    if x_minus is None or x_plus is None:
        return None, None
    L = x_plus - x_minus
    C = (x_plus + x_minus) / 2.0
    return L, C


# ───────────────────────────────────────
# 2. 센터 C + 길이 L → 외곽(X-/X+) 역산
# ───────────────────────────────────────
def calc_center_to_outer(center, length):
    """
    센터 좌표와 길이로부터 외곽(X-, X+)를 계산.
    center, length: float 또는 None
    return: (x_minus, x_plus) 또는 (None, None)
    """
    if center is None or length is None:
        return None, None
    x_minus = center - (length / 2.0)
    x_plus = center + (length / 2.0)
    return x_minus, x_plus


# ───────────────────────────────────────
# 3. Z 높이 계산
# ───────────────────────────────────────
def calc_z_height(z_bottom, z_top):
    """
    Z 바닥 / 상면 기준으로 Z 높이 계산.
    z_bottom, z_top: float 또는 None
    return: height 또는 None
    """
    if z_bottom is None or z_top is None:
        return None
    return z_top - z_bottom
