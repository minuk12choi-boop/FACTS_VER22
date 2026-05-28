from __future__ import annotations

from datetime import datetime
from pathlib import Path
import traceback


def save_feedback_log(prefix: str, content: str) -> str:
    ts = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
    root = Path(__file__).resolve().parent.parent
    log_dir = root / "feedback_log"
    log_dir.mkdir(parents=True, exist_ok=True)
    path = log_dir / f"{prefix}_{ts}.txt"
    path.write_text(content, encoding="utf-8")
    return str(path)


def try_save_feedback_log(prefix: str, content: str, tag: str) -> str | None:
    try:
        saved_path = save_feedback_log(prefix, content)
        print(f"[{tag}] log saved: {saved_path}")
        return saved_path
    except Exception:
        print(f"[{tag}] log save failed")
        print(traceback.format_exc())
        return None
