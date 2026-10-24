from __future__ import annotations
import argparse
import json
import sys
from pathlib import Path
from typing import Sequence
from .config import load_config, validate_settings
from .engine import dry_run, prepare_run, run_grading
from .archive_import import prepare_moodle_archive
from .errors import GraderError, InputValidationError
from .sandbox import sandbox_mode, sandbox_probe


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="cpp-grader",
        description="Grade the CS F213 ride-sharing OOP assignment in C++ using the official 26-case, 60-mark rubric.",
    )
    parser.add_argument("--config", default="config/settings.yaml", help="Settings YAML (default: config/settings.yaml)")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("inspect", help="Inspect official rubric, PDF, attendance, and submission folders without running code.")
    sub.add_parser("validate", help="Validate inputs, IDs, testcase count/marks, roster, and machine sandbox readiness.")
    grade = sub.add_parser("grade", help="Grade C++ submissions and generate reports.")
    grade.add_argument("--dry-run", action="store_true", help="Create roster/submission reconciliation without compiling or grading.")
    grade.add_argument("--force", action="store_true", help="Ignore cached results and regrade matched submissions.")
    grade.add_argument("--limit", type=int, help="Grade only the first N roster entries (pilot only).")
    grade.add_argument("--student-id", action="append", help="Grade only this roster campus ID (pilot only; may be repeated).")
    grade.add_argument("--workers", type=int, help="Lower concurrency; cannot exceed the safety-derived worker limit.")
    imp = sub.add_parser("prepare-archive", help="Safely import a Moodle ZIP export, including ZIPs and local Git bundles.")
    imp.add_argument("archive", help="Path to the Moodle export ZIP (not the grader repository ZIP).")
    imp.add_argument("--destination", help="Destination submissions directory; defaults to paths.submissions_dir.")
    imp.add_argument("--replace-existing", action="store_true", help="Replace existing non-hidden submission entries; use only after reviewing the destination.")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        cfg = load_config(args.config)
        settings_errors = validate_settings(cfg)
        if settings_errors:
            raise InputValidationError("Settings validation failed:\n- " + "\n- ".join(settings_errors))
        if args.command == "inspect":
            prepared = prepare_run(cfg)
            summary = prepared["summary"]
            summary["submission_dirs_preview"] = [
                {"student_id": (subs[0].student_id if subs else None), "folder": (subs[0].folder_name if subs else ""),
                 "status": (subs[0].status if subs else ""), "source_files": len(subs[0].source_files) if subs else 0}
                for subs in list(prepared["submissions"].values())[:20]
            ]
            print(json.dumps(summary, indent=2, ensure_ascii=False))
            return 0
        if args.command == "validate":
            prepared = prepare_run(cfg)
            summary = prepared["summary"]
            probe = summary.get("sandbox", {})
            if sandbox_mode(cfg) == "required" and not probe.get("ready"):
                summary.setdefault("warnings", []).append(probe.get("message", "Required sandbox is not ready."))
            # Missing C++ submissions are a warning, not a rubric-validation failure.
            print(json.dumps(summary, indent=2, ensure_ascii=False))
            return 0 if summary.get("valid") and summary.get("execution_ready") else 1
        if args.command == "prepare-archive":
            destination = Path(args.destination).expanduser() if args.destination else cfg.path_value("paths", "submissions_dir")
            if destination is None:
                raise InputValidationError("Set paths.submissions_dir or pass --destination.")
            if not destination.is_absolute():
                destination = (cfg.root / destination).resolve()
            summary = prepare_moodle_archive(cfg, Path(args.archive), destination, replace_existing=args.replace_existing)
            print(json.dumps(summary, indent=2, ensure_ascii=False))
            return 0
        if args.command == "grade":
            if args.limit is not None and args.limit < 1:
                raise InputValidationError("--limit must be at least 1.")
            if args.student_id and args.limit is not None:
                raise InputValidationError("Use either --student-id or --limit, not both.")
            if args.workers is not None and args.workers < 1:
                raise InputValidationError("--workers must be at least 1.")
            result = dry_run(cfg) if args.dry_run else run_grading(
                cfg, force=args.force, limit=args.limit, workers=args.workers, student_ids=args.student_id
            )
            print(json.dumps({"run_summary": result["run_summary"],
                              "generated_files": {k: str(v) for k, v in result["paths"].items()}}, indent=2, ensure_ascii=False))
            return 0
        return 2
    except GraderError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2
    except KeyboardInterrupt:
        print("Interrupted. Inputs remain unchanged; inspect output/work before resuming.", file=sys.stderr)
        return 130

if __name__ == "__main__":
    raise SystemExit(main())
