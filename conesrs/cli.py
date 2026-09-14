"""Command-line interface: `conesrs check <folder>` and `conesrs batch <folder>`.

No physics, no rendering logic — parse args, load config, dispatch to
engine.batch + report. Exit code 0 means the tool ran (Review/Action/Rejected are
clinical/scope outcomes, not failures); non-zero is a usage or run failure.
"""
from __future__ import annotations

import argparse
from pathlib import Path

from conesrs.config.machines import MachineConfig
from conesrs.dicomio.matching import match_folder
from conesrs.engine.batch import check_plan_set, run_batch
from conesrs.report.csv import status_label
from conesrs.report.pdf import write_pdf


def _config(path: str | None) -> MachineConfig:
    return MachineConfig.load(path) if path else MachineConfig.load_default()


def _cmd_check(args) -> int:
    sets = match_folder(args.folder)
    if len(sets) != 1:
        print(f"error: `check` needs exactly one plan set, found {len(sets)} "
              f"in {args.folder}", flush=True)
        return 2
    result = check_plan_set(sets[0], _config(args.config),
                            sphere_diameter_mm=args.sphere_diameter)
    print(f"{status_label(result)}  "
          f"calc={result.d_calc_cgy_per_fx}  tps={result.d_tps_cgy_per_fx}  "
          f"diff={result.percent_diff}")
    out_dir = Path(args.out) if args.out else Path(args.folder)
    out_dir.mkdir(parents=True, exist_ok=True)
    write_pdf(result, out_dir / "report.pdf", timestamp=args.timestamp or "")
    return 0


def _cmd_batch(args) -> int:
    summary = run_batch(args.folder, _config(args.config), args.out,
                        sphere_diameter_mm=args.sphere_diameter,
                        timestamp=args.timestamp or "")
    print("Batch complete:", dict(summary.counts))
    print("CSV:", summary.csv_path)
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="conesrs")
    sub = parser.add_subparsers(dest="command", required=True)

    pc = sub.add_parser("check", help="check exactly one plan set")
    pc.add_argument("folder")
    pc.add_argument("--out")
    pc.add_argument("--config")
    pc.add_argument("--sphere-diameter", type=float, default=2.0,
                    dest="sphere_diameter")
    pc.add_argument("--timestamp")
    pc.set_defaults(func=_cmd_check)

    pb = sub.add_parser("batch", help="check every plan set in a folder")
    pb.add_argument("folder")
    pb.add_argument("--out", required=True)
    pb.add_argument("--config")
    pb.add_argument("--sphere-diameter", type=float, default=2.0,
                    dest="sphere_diameter")
    pb.add_argument("--timestamp")
    pb.set_defaults(func=_cmd_batch)

    args = parser.parse_args(argv)
    return args.func(args)
