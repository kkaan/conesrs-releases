"""Portable GUI entry point with an explicit local beam-data configuration."""
import argparse
import json
from pathlib import Path
import sys

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication

from conesrs.config.machines import MachineConfig
from conesrs.gui.app import MainWindow


def main():
    parser = argparse.ArgumentParser(description="ConeSRS desktop")
    parser.add_argument("--config", type=Path, help="Local machines.json path")
    parser.add_argument("--self-test", type=Path, help=argparse.SUPPRESS)
    args = parser.parse_args()
    app = QApplication.instance() or QApplication([sys.argv[0]])
    config = MachineConfig.load(args.config) if args.config else MachineConfig.load_default()
    window = MainWindow(config=config)
    window.show()
    if args.self_test:
        def check():
            from conesrs.engine.result import PlanCheckResult
            from conesrs.report.pdf import write_pdf
            # Exercise packaged Qt, report fonts, and matplotlib resources.
            exit_code = 0
            try:
                pdf = args.self_test.with_suffix(".pdf")
                write_pdf(PlanCheckResult(status="ACCEPTED", model_id="synthetic",
                          tolerance_flag="PASS", d_calc_cgy_per_fx=100,
                          d_tps_cgy_per_fx=100, percent_diff=0,
                          depth_profile=((0, 40), (90, 50))), pdf, timestamp="Synthetic smoke test")
                args.self_test.write_text(json.dumps({"ok": pdf.is_file(),
                    "machines": config.machines, "models": config.models}), encoding="utf-8")
            except Exception as exc:
                exit_code = 1
                args.self_test.write_text(json.dumps({"ok": False, "error": str(exc)}), encoding="utf-8")
            finally:
                app.exit(exit_code)
        QTimer.singleShot(0, check)
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
