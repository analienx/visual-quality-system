"""host_checks CLI: probe | record-calibration (operator-run only)."""
import argparse
import json
import sys


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="host_checks")
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("probe", help="Read-only tool/modeling probes")
    record = commands.add_parser("record-calibration",
                                 help="Judge measured canvas/PNG numbers")
    record.add_argument("--canvas-width", type=int, required=True)
    record.add_argument("--canvas-height", type=int, required=True)
    record.add_argument("--png-width", type=int, required=True)
    record.add_argument("--png-height", type=int, required=True)
    args = parser.parse_args(argv)
    if args.command == "probe":
        from host_checks.probes import probe_host

        print(json.dumps(probe_host(), indent=2))
        return 0
    from host_checks.calibration import judge_calibration

    try:
        verdict = judge_calibration(args.canvas_width, args.canvas_height,
                                    args.png_width, args.png_height)
    except ValueError as exc:
        print(json.dumps({"verdict": "invalid", "reason": str(exc)}))
        return 2
    print(json.dumps(verdict, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
