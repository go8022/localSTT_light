import sys
import traceback
import tkinter as tk
from pathlib import Path
from tkinter import messagebox


def main():
    from localstt.app import LocalSTTApp

    root = tk.Tk()
    app = LocalSTTApp(root)
    root.mainloop()


def get_error_log_path():
    if getattr(sys, "frozen", False):
        app_dir = Path(sys.executable).resolve().parent
    else:
        app_dir = Path(__file__).resolve().parent

    try:
        app_dir.mkdir(parents=True, exist_ok=True)
        test_path = app_dir / ".write_test"
        test_path.write_text("", encoding="utf-8")
        test_path.unlink(missing_ok=True)
        return app_dir / "LocalSTT_error.log"
    except Exception:
        return Path.home() / "Documents" / "LocalSTT_error.log"


def report_startup_error(error):
    log_path = get_error_log_path()
    log_path.parent.mkdir(parents=True, exist_ok=True)
    log_path.write_text(
        "LocalSTT failed to start.\n\n"
        f"{error}\n\n"
        f"{traceback.format_exc()}",
        encoding="utf-8",
    )

    try:
        root = tk.Tk()
        root.withdraw()
        messagebox.showerror(
            "LocalSTT startup error",
            "LocalSTT could not start.\n\n"
            f"Error details were saved to:\n{log_path}",
        )
        root.destroy()
    except Exception:
        pass


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        report_startup_error(exc)
