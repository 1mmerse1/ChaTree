"""允许 `python -m chaTree` 启动。"""

from .main import run

if __name__ == "__main__":
    raise SystemExit(run())
