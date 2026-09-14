"""Build from this public tree only: python build_windows.py."""
from pathlib import Path
import subprocess
import sys

root = Path(__file__).resolve().parent
subprocess.run([sys.executable, "-m", "PyInstaller", "--noconfirm", "--clean",
    "--onedir", "--windowed", "--name", "ConeSRS", "--noupx",
    "--add-data", f"{root / 'conesrs/config/machines.default.json'};conesrs/config",
    "--collect-data", "reportlab", "--collect-data", "matplotlib",
    "--exclude-module", "PyQt5", "--exclude-module", "PyQt6",
    str(root / "launch_gui.py")], cwd=root, check=True)
