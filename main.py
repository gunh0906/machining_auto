# machining_auto/main.py
"""
machining_auto 통합 런처.

- 실행 예:
  python -m machining_auto setting
  python -m machining_auto cam

주의:
- 아래 import 경로는 전하의 실제 엔트리 파일명에 맞게 1줄만 수정하면 된다.
"""

from __future__ import annotations

import sys


def run_setting() -> None:
    """
    Setting Sheet UI 실행 진입점.
    전하의 실제 엔트리 모듈로 import 경로를 맞춰야 한다.
    """
    # TODO: 전하 프로젝트의 실제 엔트리 모듈로 바꾸시오.
    # 예시) from machining_auto.setting_sheet_auto.main_window import main
    # 예시) from machining_auto.setting_sheet_auto.ui import main
    raise RuntimeError("Setting 엔트리 모듈 경로를 아직 지정하지 않았습니다.")


def run_cam() -> None:
    """
    CAM Sheet UI 실행 진입점.
    전하의 실제 엔트리 모듈로 import 경로를 맞춰야 한다.
    """
    # TODO: 전하 프로젝트의 실제 엔트리 모듈로 바꾸시오.
    raise RuntimeError("CAM 엔트리 모듈 경로를 아직 지정하지 않았습니다.")


def main(argv: list[str]) -> int:
    mode = "setting"
    if len(argv) >= 2:
        mode = str(argv[1]).strip().lower()

    if mode in ("setting", "set", "s"):
        run_setting()
        return 0

    if mode in ("cam", "c"):
        run_cam()
        return 0

    print("사용법: python -m machining_auto [setting|cam]")
    return 2


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
