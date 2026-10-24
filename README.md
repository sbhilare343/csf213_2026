# OOP TA C++ Grader — CS F213 Lab Midsem

A Python-based, resource-aware C++ autograder for the ride-sharing OOP assignment. It is built around the actual files provided in `Grader/`:

- `testcases.xlsx`: the authoritative per-testcase mark allocation.
- `grader-testcases.pdf`: the behavior specification for the 26 tests.
- `midterm-lab-attendance.xlsx`: the student roster, attendance, makeup, seat/zone, and Quanta submission indicator.

The C++ harness checks `Ride.calculateFare`, `RideService.requestRide`, and `RideService.completeRide`, covering all 26 IDs and the official total of 60 marks. The workbook has been inspected and reconciled against the PDF's list of test IDs. Marks are read from the workbook at runtime; the harness never assigns equal points to every case.

> **Important limitation of the supplied submission archive:** the provided Moodle export contained Java-oriented Git bundles and no C++ source/header submission files. This project does not claim to have graded students. Put the C++ submissions in `submissions/` using the layout below before a real grading run.

> **Instructor-only materials:** `Grader/midterm-lab-attendance.xlsx` contains student roster data, and `tests/fixtures/reference_solution/` is a trusted passing implementation used to test the grader. Keep this project ZIP in a staff-only location and do not distribute it to students.

## What the project does

- Validates the official rubric: 26 known testcase IDs, no duplicates, numeric/non-negative marks, and 60-mark total.
- Reads all students from the actual `LabMidterm Attendance` sheet (379 unique campus IDs in the provided file; four are marked absent and four have makeup granted).
- Matches submission folders by exact campus ID first and normalized full name second; fuzzy name matches are held for human confirmation.
- Runs each official testcase in its own process, resetting the static driver registry between tests.
- Builds production C++ sources into a per-submission executable, excluding the student's `main.cpp` and common test directories/files in header mode so they do not collide with the grader-owned harness; then runs 26 independent checks.
- Uses a bounded worker pool. By default, it reserves two logical CPU cores and further caps concurrency based on available memory and configured limits.
- Requires bubblewrap isolation by default (network namespace disabled, read-only source workspace at runtime, minimal environment) and uses `prlimit` for per-process CPU, memory, process count, file size, open-file, and core-dump limits.
- Distinguishes compile failures, failed assertions, runtime crashes, timeouts, output-limit breaches, missing submissions, C++-source absence, duplicate matches, identity ambiguity, and grader infrastructure failures.
- Produces `grades.xlsx`, `grades.csv`, `results.json`, `student_reconciliation.xlsx`, `run_summary.json`, `validation_report.json`, and per-student execution logs.
- Caches results by source, rubric, harness, adapter, and relevant settings fingerprint; use `--force` to regrade.

## 1. Project layout

```text
cpp_grader_project/
├── cpp_grader/
│   ├── attendance.py           # Reads and validates the roster
│   ├── rubric.py               # Loads testcase descriptions and marks
│   ├── submissions.py          # Discovers and matches C++ submissions
│   ├── archive_import.py       # Safely imports Moodle ZIPs, nested ZIPs, and Git bundles
│   ├── engine.py               # Compile/test/score pipeline
│   ├── process.py              # Bounded process output and timeout handling
│   ├── sandbox.py              # bubblewrap, prlimit, CPU/memory worker cap
│   ├── reports.py              # Excel and CSV reports
│   └── harness/ride_harness.cpp# The 26 independent unit tests
├── reference/java_grader/        # Supplied Java grader source (comparison only; no .git/student bundles)
├── config/
│   ├── settings.yaml
│   ├── ride_api_adapter.hpp
│   └── ride_api_adapter_monolithic.hpp
├── Grader/                     # Original PDF and workbooks
├── submissions/                # Put actual C++ student folders here
├── tests/fixtures/reference_solution/  # Trusted grader self-test fixture
├── tests/                      # Automated tests for the grader itself
└── docs/                       # Security, API, workflow, rubric reconciliation
```

The original rubric and attendance inputs are included for reproducibility. The supplied Java grader source is retained under `reference/java_grader/` for implementation comparison. Its `.git` metadata and the 54 MB Moodle submission archive are intentionally not copied into this code package: the archive contains student projects and the entries inspected are Java projects, not C++ solutions. Keep the original submission archive in a restricted location.

## 2. Requirements

- Linux (recommended/required for the default sandbox).
- Python 3.10 or later.
- `g++` with C++17 support.
- `bubblewrap` (`bwrap`) and `prlimit` (normally provided by `util-linux`).

Ubuntu/Debian setup:

```bash
sudo apt update
sudo apt install python3 python3-venv g++ bubblewrap util-linux
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -e '.[test]'
```

Check whether your account may create the namespaces bubblewrap requires:

```bash
bwrap --die-with-parent --unshare-all --ro-bind /usr /usr --proc /proc --dev /dev --tmpfs /tmp -- /usr/bin/true
```

If your OS or administrator disables unprivileged namespaces, ask for an approved sandbox configuration. **Do not disable isolation for untrusted student code.**

## 3. Prepare submissions

Create one directory per student, preferably named with the campus ID from the attendance sheet:

```text
submissions/
├── 2025A7CS0182G/
│   ├── User.h
│   ├── User.cpp
│   ├── Driver.h
│   ├── Driver.cpp
│   ├── Ride.h
│   ├── Ride.cpp
│   ├── RideService.h
│   └── RideService.cpp
└── 2025A7PS0683G/
    └── main.cpp
```

Do not put multiple students into one folder. The grader does not rewrite student code. It ignores `.git`, common build folders, editor metadata, and symlinks; source size/file-count bounds are configurable in `settings.yaml`.

### Import a Moodle submission-export ZIP

The archive importer handles Moodle's one-folder-per-student export layout, nested ZIP archives, and local Git bundles. For Git bundles, it shallow-clones only the bundle's default/HEAD branch to collect the submitted files, then copies project files into a normalized per-student `source/` directory. It writes an import manifest indicating `READY`, `NO_CPP_SOURCE`, `AMBIGUOUS_PROJECT_ROOT`, or `IMPORT_ERROR`. A Java-only or unsupported submission is held; it is never interpreted as a C++ grade. The import does **not** preserve Git history, and it does not score the separate Git-usage/commit-history criteria; retain the original bundle archive for that review.

```bash
python -m cpp_grader --config config/settings.yaml prepare-archive \
  "/path/to/Moodle-submission-export.zip"
```

Before importing over an existing `submissions/` directory, pick a fresh destination or deliberately pass `--replace-existing` after checking the directory. The importer has limits for entry counts, total expanded ZIP bytes, nested archive depth, bundle size, and copied project size. It rejects path traversal and symlinks in ZIPs. It never accesses a remote Git URL; only locally supplied bundle files are cloned.

After import, run `inspect` and `grade --dry-run`; check each `.cpp_grader_import.json` manifest and the reconciliation workbook before any live grading. The uploaded class export contains a mix of Java and C++ submissions, so expect Java-only submissions to be held as `NO_CPP_SOURCE`. Use the existing Java grader for Java submissions or resolve grading coverage separately; never treat `NO_CPP_SOURCE` as an automatic zero.

The default adapter follows the reference-based API found in multiple C++ bundles from the supplied export:

- `User(std::string)`
- `Driver(std::string, double)`, `isAvailable()`, `setAvailability(bool)`, `getRating()`
- `Ride(User&, int, Driver&)`, `calculateFare()`, `Driver& getDriver()`
- static `RideService::addDriver(Driver&)`, `requestRide(User&, int, double)`, `completeRide(Ride&)`

The wrapper exposes pointers internally to simplify the harness but dereferences them when calling the student's reference-based API. A one-file `.cpp` solution whose class definitions are in that file can be detected as monolithic. If a student's interface differs, adjust `config/ride_api_adapter.hpp` or `config/ride_api_adapter_monolithic.hpp` as explained in `docs/CPP_INTERFACE.md`. Verify the adapter against the official C++ starter or an instructor-approved reference solution before grading real submissions.

## 4. First-run sequence

Run commands from the project directory.

### Inspect the inputs and machine

```bash
python -m cpp_grader --config config/settings.yaml inspect
```

This reports the sheet names, rubric totals, PDF extraction, roster size, submission matching preview, sandbox readiness, and effective worker count. It also writes `output/rubric_catalog.json` and `output/validation_report.json`.

### Validate without running student code

```bash
python -m cpp_grader --config config/settings.yaml validate
```

Expected for the included inputs: 26 test cases, 60 marks, 379 unique roster records. The empty `submissions/` directory should produce a warning, not fabricated grades.

### Preview attendance/submission reconciliation

```bash
python -m cpp_grader --config config/settings.yaml grade --dry-run
```

Review `output/student_reconciliation.xlsx`. Resolve unmatched and duplicate directories before live grading.

### Pilot a single student with one worker

```bash
python -m cpp_grader --config config/settings.yaml grade --student-id 2025A7CS0182G --workers 1 --force
```

`--student-id` is for a pilot only and writes a partial result set; replace the example ID with one shown as `FOUND` in the reconciliation report. Do not distribute that gradebook as final. Confirm the compilation adapter, case results, marks, and execution logs. Alternatively, `--limit N` grades the first N attendance rows, which may include Java-only submissions.

### Grade the class

```bash
python -m cpp_grader --config config/settings.yaml grade
```

To rerun every matching C++ submission:

```bash
python -m cpp_grader --config config/settings.yaml grade --force
```

The default worker count is `max(1, logical_CPU_cores - worker_reserve_cores)`, capped by `execution.max_workers` and a simple memory budget. Use `--workers` to lower it for a pilot; it cannot raise the computed safety limit. The included default reserves two CPU cores.

## 5. Scoring and exceptions

- This program automates the **60 functional testcase marks** in the official testcase workbook. It does not automatically award the remaining Git-usage/commit-history (15), unit-test quality (15), or code-quality (10) marks described in the assignment README.
- Each testcase earns its exact configured marks only when its assertion passes; a failed assertion earns zero for that case.
- Compile failure defaults to zero, matching the documented policy of the reference Java grader; change `policies.compile_failure` to `hold` if the course policy requires review.
- Missing submissions, no C++ source, duplicate directories, uncertain identity matches, and infrastructure failures are **held**, not silently converted to zero.
- Attendance status is reported separately from correctness marks. The program does not apply attendance penalties.
- The submitted XLSX and CSV are generated after processing. Review `Exceptions` and `student_reconciliation.xlsx` before approving grades.
- Runtime failures, timeouts, and output-limit violations are zero for the relevant case. An infrastructure failure holds the student's total so a machine problem is not mistaken for student error.

## 6. CLI overview

```text
python -m cpp_grader [--config config/settings.yaml] inspect
python -m cpp_grader [--config config/settings.yaml] validate
python -m cpp_grader [--config config/settings.yaml] prepare-archive /path/to/moodle-export.zip [--destination DIR] [--replace-existing]
python -m cpp_grader [--config config/settings.yaml] grade [--dry-run] [--force] [--limit N | --student-id CAMPUS_ID] [--workers N]
```

The settings option comes before the subcommand. `cpp-grader` is also installed as a console command when the package is installed editable.

## 7. Test the grader, not students

```bash
pytest -q
```

Tests validate the actual PDF/XLSX inputs and run all 26 cases against the included trusted reference fixture. That fixture exists only to test the grader's correctness; it must not replace student submissions.

## 8. Instructor checklist

1. Verify `config/ride_api_adapter*.hpp` matches the actual C++ submission interface.
2. Confirm the sandbox readiness in `validate` and never run untrusted programs unsandboxed.
3. Resolve identity and duplicate-submission flags.
4. Pilot one known-correct and one known-incorrect C++ submission.
5. Compare `grades.xlsx` testcase marks with manual calculations.
6. Review all held students and exceptions.
7. Approve the final gradebook manually before sharing grades.

See `docs/GRADING_POLICY.md`, `docs/SECURITY.md`, `docs/CPP_INTERFACE.md`, and `docs/JAVA_GRADER_ANALYSIS.md`.
