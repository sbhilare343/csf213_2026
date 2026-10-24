from __future__ import annotations
from collections import Counter
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
import hashlib
import json
import os
import re
import shutil
import tempfile
import time
from typing import Any

from .attendance import load_roster
from .case_catalog import SUPPORTED_TEST_IDS
from .config import AppConfig
from .errors import InputValidationError, SandboxUnavailableError
from .models import CaseResult, Student, StudentResult, Submission, TestCase
from .process import run_bounded
from .sandbox import effective_workers, sandbox_mode, sandbox_probe
from .submissions import match_submissions
from .utils import json_write, norm, sha256_file

PASS_MARKER = "__CPP_GRADER_RESULT__:PASS:"
FAIL_MARKER = "__CPP_GRADER_RESULT__:FAIL:"


def _max_marks(cases: list[TestCase]) -> float:
    return round(sum(c.marks for c in cases), 4)


def _report_path(config: AppConfig, output_dir: Path, key: str, default: str) -> Path:
    """Resolve a report name under output_dir; disallow paths escaping that directory."""
    value = str(config.section("reports").get(key, default)).strip()
    candidate = Path(value)
    if not value or candidate.is_absolute() or ".." in candidate.parts:
        raise InputValidationError(f"reports.{key} must be a non-empty relative path that stays inside output_dir.")
    return output_dir / candidate


def _source_fingerprint(folder: Path, submission: Submission, cases: list[TestCase], config: AppConfig) -> str:
    h = hashlib.sha256()
    h.update(str(folder.resolve()).encode("utf-8")); h.update(b"\0")
    h.update(norm(submission.student_id).encode("utf-8")); h.update(b"\0")
    for rel in sorted((*submission.source_files, *submission.header_files)):
        p = folder / rel
        h.update(rel.encode()); h.update(b"\0")
        h.update(sha256_file(p).encode()); h.update(b"\0")
    for c in cases:
        h.update(f"{c.id}:{c.marks}:{c.expected}\n".encode("utf-8"))
    harness = Path(__file__).parent / "harness" / "ride_harness.cpp"
    h.update(sha256_file(harness).encode())
    harness_cfg = config.section("harness")
    for key in ("adapter_header", "monolithic_adapter_header", "source_mode", "headers"):
        h.update(json.dumps(harness_cfg.get(key), sort_keys=True).encode())
    for section in ("compiler", "execution"):
        h.update(json.dumps(config.section(section), sort_keys=True).encode())
    for adapter_key in ("adapter_header", "monolithic_adapter_header"):
        adapter = config.path_value("harness", adapter_key)
        if adapter and adapter.is_file(): h.update(sha256_file(adapter).encode())
    return h.hexdigest()


def _all_include_dirs(source_root: Path, relative_files: tuple[str, ...]) -> list[str]:
    dirs = {"student_src"}
    for rel in relative_files:
        parent = Path(rel).parent
        while str(parent) not in {".", ""}:
            dirs.add((Path("student_src") / parent).as_posix())
            parent = parent.parent
    return sorted(dirs, key=lambda x: (x.count("/"), x))


def _select_source_mode(config: AppConfig, source_root: Path, submission: Submission) -> tuple[str, str | None]:
    desired = str(config.section("harness").get("source_mode", "auto"))
    if desired == "headers": return "headers", None
    if desired == "monolithic":
        if len(submission.source_files) != 1:
            raise InputValidationError("harness.source_mode=monolithic requires exactly one C++ source file per submission.")
        return "monolithic", submission.source_files[0]
    configured = config.section("harness").get("headers", {})
    needed = [str(configured.get(k, default)).casefold() for k, default in (
        ("user", "User.h"), ("driver", "Driver.h"), ("ride", "Ride.h"), ("ride_service", "RideService.h"))]
    present = {Path(rel).name.casefold() for rel in submission.header_files}
    if all(name in present for name in needed):
        return "headers", None
    if len(submission.source_files) == 1:
        return "monolithic", submission.source_files[0]
    return "headers", None


def _write_harness_workspace(workspace: Path, config: AppConfig, submission: Submission,
                             source_files: tuple[str, ...]) -> tuple[str, str | None]:
    source_root = workspace / "student_src"
    grader_dir = workspace / "grader"
    build_dir = workspace / "build"
    source_root.mkdir(parents=True, exist_ok=True); grader_dir.mkdir(parents=True, exist_ok=True); build_dir.mkdir(parents=True, exist_ok=True)
    total_bytes = 0
    for rel in (*submission.source_files, *submission.header_files):
        rel_path = Path(rel)
        if rel_path.is_absolute() or ".." in rel_path.parts or "" in rel_path.parts:
            raise InputValidationError(f"Unsafe student file path: {rel!r}")
        source = Path(submission.folder) / rel_path
        if source.is_symlink() or not source.is_file():
            raise InputValidationError(f"Submission file is missing or is a symlink: {source}")
        size = source.stat().st_size
        max_single = int(config.section("submissions").get("max_single_file_bytes", 10_485_760))
        total_bytes += size
        if size > max_single:
            raise InputValidationError(f"Submission file {rel} exceeds the configured file-size limit.")
        target = source_root / rel_path
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, target)
    max_total = int(config.section("submissions").get("max_total_bytes", 52_428_800))
    if total_bytes > max_total:
        raise InputValidationError("Submission exceeds the configured total source-size limit.")

    mode, mono_source = _select_source_mode(config, source_root, submission)
    adapter_setting = "adapter_header" if mode == "headers" else "monolithic_adapter_header"
    adapter_path = config.path_value("harness", adapter_setting)
    if not adapter_path or not adapter_path.is_file():
        raise InputValidationError(f"Required API adapter file missing: {adapter_path}")
    adapter_text = adapter_path.read_text(encoding="utf-8")
    if mode == "headers":
        header_cfg = config.section("harness").get("headers", {})
        default_names = {"user": "User.h", "driver": "Driver.h", "ride": "Ride.h", "ride_service": "RideService.h"}
        for field, default_name in default_names.items():
            configured_name = str(header_cfg.get(field, default_name))
            adapter_text = adapter_text.replace(f'#include "{default_name}"', f'#include "{configured_name}"')
    (grader_dir / "grader_api_adapter.hpp").write_text(adapter_text, encoding="utf-8")

    harness_src = (Path(__file__).parent / "harness" / "ride_harness.cpp").read_text(encoding="utf-8")
    injection = ""
    if mode == "monolithic":
        assert mono_source is not None
        include_path = (Path("../student_src") / Path(mono_source)).as_posix()
        injection = f"#define main __cpp_grader_original_main\n#include \"{include_path}\"\n#undef main\n"
    harness_src = harness_src.replace("/*__STUDENT_SOURCE_INJECTION__*/", injection)
    (grader_dir / "ride_harness.cpp").write_text(harness_src, encoding="utf-8")
    return mode, mono_source


def _compiler_base(config: AppConfig, include_dirs: list[str]) -> list[str]:
    ccfg = config.section("compiler")
    compiler = str(ccfg.get("executable", "g++"))
    cmd = [compiler, f"-std={ccfg.get('standard', 'c++17')}"]
    cmd.extend(str(x) for x in ccfg.get("flags", ["-O2", "-pipe", "-Wall", "-Wextra"]))
    cmd.append("-Igrader")
    for directory in include_dirs:
        cmd.extend(["-I", directory])
    return cmd


def _is_test_or_entrypoint_source(relative_path: str) -> bool:
    """Avoid linking the student's own main/gtest tests into the grader harness."""
    path = Path(relative_path)
    parent_parts = {part.casefold() for part in path.parts[:-1]}
    test_dirs = {
        "test", "tests", "testing", "unit_test", "unit_tests",
        "unittest", "unittests", "gtest", "googletest",
    }
    if parent_parts & test_dirs:
        return True
    filename = path.name.casefold()
    if filename in {"main.cpp", "main.cc", "main.cxx", "main.c++"}:
        return True
    stem = path.stem.casefold()
    return (
        stem in {"test", "tests", "test_main", "testrunner"}
        or stem.startswith("test_")
        or stem.endswith("_test")
        or stem.endswith("test")
    )


def _compile_student(workspace: Path, config: AppConfig, submission: Submission, mode: str,
                     mono_source: str | None) -> tuple[bool, str, str]:
    # Header-mode submissions contain their own main.cpp and unit tests (often
    # GoogleTest). They must not be linked with the grader-owned main/test harness.
    # Monolithic mode deliberately retains its single source file for source injection.
    if mode == "headers":
        source_rel = tuple(rel for rel in submission.source_files if not _is_test_or_entrypoint_source(rel))
        excluded = tuple(rel for rel in submission.source_files if _is_test_or_entrypoint_source(rel))
    else:
        source_rel = tuple(submission.source_files)
        excluded = ()
    header_rel = tuple(submission.header_files)
    include_dirs = _all_include_dirs(workspace / "student_src", (*source_rel, *header_rel))
    base = _compiler_base(config, include_dirs)
    outputs: list[str] = []
    if excluded:
        outputs.append("Excluded student entrypoint/test sources from grader build: " + ", ".join(excluded) + "\n")
    if mode == "headers":
        objects: list[str] = []
        for index, rel in enumerate(source_rel):
            obj = f"build/student_{index:03d}.o"
            cmd = base + ["-Dmain=__cpp_grader_original_main", "-c", (Path("student_src") / rel).as_posix(), "-o", obj]
            outcome = run_bounded(cmd, workspace, config, phase="compile", readonly=False)
            outputs.append(f"$ {' '.join(cmd)}\n[{outcome.status}, rc={outcome.return_code}]\n{outcome.stdout}{outcome.stderr}{outcome.message}\n")
            if outcome.status != "OK":
                prefix = "INFRASTRUCTURE_ERROR: " if outcome.status == "INFRASTRUCTURE_ERROR" else ""
                return False, "".join(outputs), prefix + f"Could not compile {rel}: {outcome.status}; {outcome.message or outcome.stderr[-1000:]}"
            objects.append(obj)
        harness_obj = "build/ride_harness.o"
        cmd = base + ["-c", "grader/ride_harness.cpp", "-o", harness_obj]
        outcome = run_bounded(cmd, workspace, config, phase="compile", readonly=False)
        outputs.append(f"$ {' '.join(cmd)}\n[{outcome.status}, rc={outcome.return_code}]\n{outcome.stdout}{outcome.stderr}{outcome.message}\n")
        if outcome.status != "OK":
            prefix = "INFRASTRUCTURE_ERROR: " if outcome.status == "INFRASTRUCTURE_ERROR" else ""
            return False, "".join(outputs), prefix + f"Could not compile grading harness: {outcome.status}; {outcome.message or outcome.stderr[-1200:]}"
        objects.append(harness_obj)
        cmd = [str(config.section("compiler").get("executable", "g++")), *[str(x) for x in config.section("compiler").get("flags", ["-O2", "-pipe", "-Wall", "-Wextra"])], *objects, "-o", "build/ride_grader"]
        outcome = run_bounded(cmd, workspace, config, phase="compile", readonly=False)
        outputs.append(f"$ {' '.join(cmd)}\n[{outcome.status}, rc={outcome.return_code}]\n{outcome.stdout}{outcome.stderr}{outcome.message}\n")
        if outcome.status != "OK":
            prefix = "INFRASTRUCTURE_ERROR: " if outcome.status == "INFRASTRUCTURE_ERROR" else ""
            return False, "".join(outputs), prefix + f"Link failed: {outcome.status}; {outcome.message or outcome.stderr[-1200:]}"
    else:
        cmd = base + ["-c", "grader/ride_harness.cpp", "-o", "build/ride_grader.o"]
        outcome = run_bounded(cmd, workspace, config, phase="compile", readonly=False)
        outputs.append(f"$ {' '.join(cmd)}\n[{outcome.status}, rc={outcome.return_code}]\n{outcome.stdout}{outcome.stderr}{outcome.message}\n")
        if outcome.status != "OK":
            prefix = "INFRASTRUCTURE_ERROR: " if outcome.status == "INFRASTRUCTURE_ERROR" else ""
            return False, "".join(outputs), prefix + f"Could not compile monolithic harness: {outcome.status}; {outcome.message or outcome.stderr[-1200:]}"
        cmd = [str(config.section("compiler").get("executable", "g++")), *[str(x) for x in config.section("compiler").get("flags", ["-O2", "-pipe", "-Wall", "-Wextra"])], "build/ride_grader.o", "-o", "build/ride_grader"]
        outcome = run_bounded(cmd, workspace, config, phase="compile", readonly=False)
        outputs.append(f"$ {' '.join(cmd)}\n[{outcome.status}, rc={outcome.return_code}]\n{outcome.stdout}{outcome.stderr}{outcome.message}\n")
        if outcome.status != "OK":
            prefix = "INFRASTRUCTURE_ERROR: " if outcome.status == "INFRASTRUCTURE_ERROR" else ""
            return False, "".join(outputs), prefix + f"Link failed: {outcome.status}; {outcome.message or outcome.stderr[-1200:]}"
    binary = workspace / "build" / "ride_grader"
    if not binary.is_file():
        return False, "".join(outputs), "Compiler returned success but did not create the grading executable."
    max_binary = int(config.section("compiler").get("max_binary_bytes", 52_428_800))
    if binary.stat().st_size > max_binary:
        return False, "".join(outputs), f"Grading executable exceeds configured limit of {max_binary} bytes."
    return True, "".join(outputs), "Compilation succeeded."


def _case_run(workspace: Path, config: AppConfig, student_id: str, case: TestCase) -> CaseResult:
    started = time.monotonic()
    outcome = run_bounded(["./build/ride_grader", case.id], workspace, config, phase="run", readonly=True)
    marker_pass = f"{PASS_MARKER}{case.id}" in outcome.stdout
    marker_fail = f"{FAIL_MARKER}{case.id}" in outcome.stdout
    if outcome.status == "INFRASTRUCTURE_ERROR":
        status, earned, message = "INFRASTRUCTURE_ERROR", 0.0, outcome.message
    elif outcome.status == "TIMEOUT":
        status, earned, message = "TIMEOUT", 0.0, outcome.message
    elif outcome.status == "OUTPUT_LIMIT":
        status, earned, message = "OUTPUT_LIMIT", 0.0, outcome.message
    elif outcome.status == "OK" and marker_pass:
        status, earned, message = "PASS", case.marks, "Passed."
    elif marker_fail:
        status, earned, message = "FAIL", 0.0, (outcome.stderr.strip() or "Grading assertion failed.")[-2000:]
    elif outcome.status == "NONZERO_EXIT":
        status, earned, message = "RUNTIME_ERROR", 0.0, f"Process exited with code {outcome.return_code}; " + (outcome.stderr.strip()[-1200:] or "no diagnostic")
    else:
        status, earned, message = "HARNESS_ERROR", 0.0, "Expected result marker was not found; inspect process output."
    return CaseResult(student_id, case.id, case.scenario, case.marks, earned, status, message,
                      outcome.return_code, outcome.duration_seconds, outcome.stdout[-2000:], outcome.stderr[-2000:])


def _grade_one(student: Student, submission: Submission, cases: list[TestCase], config: AppConfig,
               output_dir: Path, fingerprint: str, force: bool) -> dict[str, Any]:
    work_dir = output_dir / "work" / norm(student.student_id)
    work_dir.mkdir(parents=True, exist_ok=True)
    cache_file = work_dir / "result.json"
    if not force and cache_file.is_file():
        try:
            cached = json.loads(cache_file.read_text(encoding="utf-8"))
            case_statuses = {c.get("status") for c in cached.get("case_results", [])}
            retryable_infra = (
                cached.get("compilation_status") in {"INFRASTRUCTURE_ERROR", "BLOCKED"}
                or bool(case_statuses & {"INFRASTRUCTURE_ERROR", "NOT_RUN_INFRASTRUCTURE", "HARNESS_ERROR"})
            )
            if cached.get("fingerprint") == fingerprint and not retryable_infra:
                cached["cache_hit"] = True
                return cached
        except (OSError, json.JSONDecodeError):
            pass

    result = StudentResult(student, submission.status, submission.folder, submission.matched_by,
                           len(submission.source_files), max_marks=_max_marks(cases), fingerprint=fingerprint)
    if submission.status != "FOUND":
        result.compilation_status = "NOT_RUN"
        result.review_flag = submission.issue or submission.status
        result.earned_marks = None
        payload = result.to_dict(); payload["cache_hit"] = False
        json_write(cache_file, payload)
        return payload

    try:
        with tempfile.TemporaryDirectory(prefix=f"cppgrader-{norm(student.student_id)}-") as temp:
            workspace = Path(temp)
            mode, mono_source = _write_harness_workspace(workspace, config, submission, submission.source_files)
            ok, compile_log, compile_message = _compile_student(workspace, config, submission, mode, mono_source)
            (work_dir / "compile.log").write_text(compile_log, encoding="utf-8")
            infrastructure_compile_error = (not ok and compile_message.startswith("INFRASTRUCTURE_ERROR:"))
            result.compilation_status = "SUCCESS" if ok else ("INFRASTRUCTURE_ERROR" if infrastructure_compile_error else "FAILED")
            result.compile_message = compile_message
            if not ok:
                if infrastructure_compile_error:
                    result.earned_marks = None
                    result.review_flag = "Compiler/sandbox infrastructure failure; grade held and must be rerun."
                    result.case_results = [CaseResult(student.student_id, c.id, c.scenario, c.marks, 0.0,
                        "NOT_RUN_INFRASTRUCTURE", compile_message, None, None, "", "") for c in cases]
                elif config.section("policies").get("compile_failure", "zero") == "zero":
                    result.earned_marks = 0.0
                    result.review_flag = "Compilation failed; zero applied according to configured policy."
                    result.case_results = [CaseResult(student.student_id, c.id, c.scenario, c.marks, 0.0,
                        "COMPILE_ERROR", compile_message, None, None, "", "") for c in cases]
                else:
                    result.earned_marks = None
                    result.review_flag = "Compilation failed; grade held for review by configured policy."
                    result.case_results = [CaseResult(student.student_id, c.id, c.scenario, c.marks, 0.0,
                        "COMPILE_ERROR_HELD", compile_message, None, None, "", "") for c in cases]
            else:
                (work_dir / "tests").mkdir(parents=True, exist_ok=True)
                for case in cases:
                    cr = _case_run(workspace, config, student.student_id, case)
                    result.case_results.append(cr)
                    (work_dir / "tests" / f"{case.id}.log").write_text(
                        f"STATUS: {cr.status}\nMESSAGE: {cr.message}\n--- STDOUT ---\n{cr.stdout}\n--- STDERR ---\n{cr.stderr}\n", encoding="utf-8")
                    if cr.status == "INFRASTRUCTURE_ERROR":
                        for remaining in cases[len(result.case_results):]:
                            result.case_results.append(CaseResult(student.student_id, remaining.id, remaining.scenario,
                                remaining.marks, 0.0, "NOT_RUN_INFRASTRUCTURE", "Stopped after an infrastructure error."))
                        break
                statuses = {r.status for r in result.case_results}
                if any(s in statuses for s in {"INFRASTRUCTURE_ERROR", "NOT_RUN_INFRASTRUCTURE", "HARNESS_ERROR"}):
                    result.earned_marks = None
                    result.review_flag = "At least one case could not be evaluated reliably; total held for review."
                else:
                    result.earned_marks = round(sum(r.earned_marks for r in result.case_results), 4)
                    failed = [r.testcase_id for r in result.case_results if r.status != "PASS"]
                    result.review_flag = "" if not failed else "Review failures: " + ", ".join(failed)
            if result.earned_marks is not None and result.max_marks > 0:
                result.percentage = round(100 * result.earned_marks / result.max_marks, 2)
            result.submission_status = submission.status
            result.fingerprint = fingerprint
            payload = result.to_dict(); payload["cache_hit"] = False; payload["harness_mode"] = mode
            json_write(cache_file, payload)
            return payload
    except SandboxUnavailableError as exc:
        result.compilation_status = "BLOCKED"
        result.earned_marks = None
        result.review_flag = str(exc)
        payload = result.to_dict(); payload["cache_hit"] = False
        json_write(cache_file, payload)
        return payload
    except Exception as exc:
        result.compilation_status = "INFRASTRUCTURE_ERROR"
        result.earned_marks = None
        result.review_flag = f"Grader infrastructure error: {type(exc).__name__}: {exc}"
        payload = result.to_dict(); payload["cache_hit"] = False
        json_write(cache_file, payload)
        return payload


def prepare_run(config: AppConfig) -> dict[str, Any]:
    from .rubric import load_rubric, inspect_pdf, validate_pdf_reconciliation
    errors: list[str] = []
    cases = load_rubric(config)
    pdf = config.path_value("paths", "rubric_pdf")
    if not pdf or not pdf.is_file():
        raise InputValidationError(f"Official testcase PDF is missing: {pdf}")
    pdf_info = inspect_pdf(pdf)
    warnings = validate_pdf_reconciliation(pdf)
    # Store the extractable PDF text as an audit aid. The original PDF remains unchanged.
    try:
        import fitz
        with fitz.open(pdf) as doc:
            pdf_text = "\n\n".join(f"--- PAGE {i + 1} ---\n" + page.get_text("text") for i, page in enumerate(doc))
        pdf_audit_dir = (config.path_value("paths", "output_dir") or (config.root / "output")) / "input_audit"
        pdf_audit_dir.mkdir(parents=True, exist_ok=True)
        (pdf_audit_dir / "grader-testcases-extracted.txt").write_text(pdf_text, encoding="utf-8")
    except Exception as exc:
        warnings.append(f"Could not save extracted PDF text for audit: {type(exc).__name__}: {exc}")
    roster = load_roster(config)
    sub_map, unmatched, sub_warnings = match_submissions(config, roster)
    warnings.extend(sub_warnings)
    output = config.path_value("paths", "output_dir") or (config.root / "output")
    output.mkdir(parents=True, exist_ok=True)
    from .utils import json_write
    sandbox_status = sandbox_probe()
    compiler_name = str(config.section("compiler").get("executable", "g++"))
    compiler_path = shutil.which(compiler_name)
    sandbox_ready = sandbox_status.get("ready", False) if sandbox_mode(config) == "required" else bool(sandbox_status.get("prlimit"))
    execution_ready = bool(compiler_path and sandbox_ready)
    if not compiler_path:
        warnings.append(f"Configured C++ compiler was not found on PATH: {compiler_name}")
    summary = {
        "valid": not errors,
        "input_valid": not errors,
        "execution_ready": execution_ready,
        "compiler_path": compiler_path,
        "assignment": "CS F213 OOP Lab Midsem C++",
        "testcase_count": len(cases), "maximum_marks_per_student": _max_marks(cases),
        "rubric_source": str(config.path_value("paths", "rubric_xlsx")),
        "pdf": {k: v for k, v in pdf_info.items() if k != "text_excerpt"},
        "roster_count": len(roster), "roster_unique_ids": len({norm(s.student_id) for s in roster}),
        "attendance_status_counts": dict(sorted(Counter(s.attendance for s in roster).items())),
        "submission_directories": sum(len(v) for v in sub_map.values()) + len(unmatched),
        "matched_student_ids": sum(1 for v in sub_map.values() if len(v) == 1),
        "unmatched_submission_directories": len(unmatched), "warnings": warnings,
        "sandbox": sandbox_status, "effective_workers": effective_workers(config),
        "errors": errors,
    }
    json_write(output / "validation_report.json", summary)
    json_write(output / "rubric_catalog.json", {
        "assignment": summary["assignment"], "maximum_marks_per_student": summary["maximum_marks_per_student"],
        "testcases": [c.__dict__ for c in cases], "pdf_audit": summary["pdf"],
    })
    return {"cases": cases, "roster": roster, "submissions": sub_map, "unmatched": unmatched,
            "warnings": warnings, "summary": summary, "output_dir": output}


def dry_run(config: AppConfig) -> dict[str, Any]:
    prepared = prepare_run(config)
    from .reports import write_reconciliation
    recon_path = _report_path(config, prepared["output_dir"], "reconciliation_xlsx", "student_reconciliation.xlsx")
    write_reconciliation(recon_path, prepared["roster"], prepared["submissions"], prepared["unmatched"])
    summary = prepared["summary"] | {"dry_run": True, "grades_computed": False}
    summary_path = _report_path(config, prepared["output_dir"], "run_summary", "run_summary.json")
    json_write(summary_path, summary)
    return {"run_summary": summary, "paths": {"reconciliation": recon_path, "run_summary": summary_path}}


def run_grading(
    config: AppConfig,
    *,
    force: bool = False,
    limit: int | None = None,
    workers: int | None = None,
    student_ids: list[str] | None = None,
) -> dict[str, Any]:
    prepared = prepare_run(config)
    if sandbox_mode(config) == "required":
        probe = sandbox_probe()
        if not probe.get("ready"):
            raise SandboxUnavailableError(probe.get("message") or "Required secure sandbox is not available.")
    cases: list[TestCase] = prepared["cases"]
    if not any(sub.status == "FOUND" for matches in prepared["submissions"].values() for sub in matches):
        raise InputValidationError(
            "No gradeable C++ submissions were discovered. Run `grade --dry-run`, place each student's "
            "C++ source/header files in a separate folder under submissions/, and resolve the reconciliation report. "
            "No gradebook was produced."
        )
    roster: list[Student] = prepared["roster"]
    sub_map: dict[str, list[Submission]] = prepared["submissions"]
    output_dir: Path = prepared["output_dir"]
    if student_ids:
        requested = {norm(item) for item in student_ids if norm(item)}
        roster_ids = {norm(student.student_id) for student in roster}
        unknown = sorted(requested - roster_ids)
        if not requested:
            raise InputValidationError("--student-id requires at least one non-empty campus ID.")
        if unknown:
            raise InputValidationError("Campus ID(s) not found in attendance roster: " + ", ".join(unknown))
        roster_to_grade = [student for student in roster if norm(student.student_id) in requested]
    else:
        roster_to_grade = roster[:limit] if limit is not None else roster
    jobs = workers if workers is not None else effective_workers(config)
    if jobs < 1: raise InputValidationError("workers must be at least 1.")
    # The CLI may lower concurrency but may not override machine-safety config upward.
    jobs = min(jobs, effective_workers(config))
    results: list[dict[str, Any] | None] = [None] * len(roster_to_grade)
    task_specs = []
    for i, student in enumerate(roster_to_grade):
        matches = sub_map.get(norm(student.student_id), [])
        if not matches:
            r = StudentResult(student, "NO_SUBMISSION", max_marks=_max_marks(cases),
                              review_flag="No matching C++ submission directory; grade held.")
            results[i] = r.to_dict()
        elif len(matches) > 1 or matches[0].status == "DUPLICATE_SUBMISSIONS":
            r = StudentResult(student, "DUPLICATE_SUBMISSIONS", max_marks=_max_marks(cases),
                              review_flag="Multiple submission folders matched this student; grade held.")
            results[i] = r.to_dict()
        else:
            submission = matches[0]
            if submission.status != "FOUND":
                r = StudentResult(student, submission.status, submission.folder, submission.matched_by,
                                  len(submission.source_files), max_marks=_max_marks(cases),
                                  review_flag=submission.issue or submission.status)
                results[i] = r.to_dict()
            else:
                folder = Path(submission.folder)
                fingerprint = _source_fingerprint(folder, submission, cases, config)
                task_specs.append((i, student, submission, fingerprint))
    if task_specs:
        with ThreadPoolExecutor(max_workers=jobs, thread_name_prefix="cpp-grade") as pool:
            future_map = {
                pool.submit(_grade_one, student, sub, cases, config, output_dir, fingerprint, force): i
                for i, student, sub, fingerprint in task_specs
            }
            for future in as_completed(future_map):
                idx = future_map[future]
                try:
                    results[idx] = future.result()
                except Exception as exc:
                    student = roster_to_grade[idx]
                    r = StudentResult(student, "INFRASTRUCTURE_ERROR", max_marks=_max_marks(cases),
                                      review_flag=f"Worker exception: {type(exc).__name__}: {exc}")
                    results[idx] = r.to_dict()
    clean_results = [r for r in results if r is not None]
    # Reconciliation includes all roster entries, even on a limited pilot run.
    from .reports import write_grade_reports, write_reconciliation
    counts = Counter(str(r.get("submission_status", "UNKNOWN")) for r in clean_results)
    case_counts = Counter(c["status"] for r in clean_results for c in r.get("case_results", []))
    summary = prepared["summary"] | {
        "run_timestamp": time.strftime("%Y-%m-%dT%H:%M:%S%z"), "dry_run": False,
        "students_in_this_run": len(clean_results), "workers_used": jobs, "force": force,
        "status_counts": dict(sorted(counts.items())), "case_status_counts": dict(sorted(case_counts.items())),
        "scored_students": sum(r.get("earned_marks") is not None for r in clean_results),
        "held_students": sum(r.get("earned_marks") is None for r in clean_results),
        "grades_computed": True,
        "safety_note": "Scores are provisional until the instructor reviews Exceptions and validates API adapter compatibility.",
    }
    grade_paths = write_grade_reports(
        output_dir, clean_results, cases, prepared["unmatched"], summary,
        xlsx_name=_report_path(config, output_dir, "xlsx", "grades.xlsx").relative_to(output_dir).as_posix(),
        csv_name=_report_path(config, output_dir, "csv", "grades.csv").relative_to(output_dir).as_posix(),
    )
    recon_path = _report_path(config, output_dir, "reconciliation_xlsx", "student_reconciliation.xlsx")
    write_reconciliation(recon_path, roster, sub_map, prepared["unmatched"])
    summary_path = _report_path(config, output_dir, "run_summary", "run_summary.json")
    results_path = _report_path(config, output_dir, "json", "results.json")
    json_write(summary_path, summary)
    # results.json contains the full per-case evidence; reports are rebuilt from this file.
    json_write(results_path, {"summary": summary, "students": clean_results, "unmatched_submissions": [s.__dict__ for s in prepared["unmatched"]]})
    paths = {"xlsx": grade_paths["xlsx"], "csv": grade_paths["csv"], "json": results_path,
             "reconciliation_xlsx": recon_path, "run_summary": summary_path}
    return {"run_summary": summary, "paths": paths}
