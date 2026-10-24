# Security Model

Student code is untrusted native code. A correct-case result is meaningful only if compilation and execution were bounded and isolated.

## Default mode

`execution.sandbox: required` requires `bubblewrap` and `prlimit`. The runner disables network namespace access, mounts system directories read-only, exposes a size-limited temporary filesystem (`execution.tmpfs_mb`), binds each per-student workspace at `/work`, passes a minimal environment, and remounts `/work` read-only while executing a testcase. `prlimit` applies CPU seconds, virtual memory, file size, process count, open-file, and core-dump limits. Wall-clock timeout and bounded pipe capture are enforced by the Python controller.

The grader does not run student programs as root. Do not run the overall grader with elevated privileges. Keep the attendance workbook and output directory private to grading staff.

## Compilation is also constrained

Student sources are copied to a temporary workspace. Each source translation unit is compiled separately so the student's `main()` can be renamed without renaming the grader harness's `main()`. Compilation is subject to time, CPU, address-space, file-size, and process limits. A source-size and file-count limit is enforced before compilation.

## Sandbox readiness

Run `python -m cpp_grader --config config/settings.yaml validate` and inspect the `sandbox` object. If bubblewrap is absent or namespace setup fails, installation needs administrator attention. Do not solve that by silently switching to unsafe mode.

## Unsafe mode

`execution.sandbox: unsafe` is intentionally an explicit opt-in for trusted local test fixtures only. It retains `prlimit`, wall timeout, process-group termination, and output cap but does not isolate filesystem or network access. Never use it for a class set of untrusted submissions.

## Operational safeguards

- Original student files are read-only from the grader's perspective; the grader copies inputs into temporary workspaces.
- Symlinks and common metadata/build folders are ignored.
- Submission filenames are passed as subprocess argument lists, never interpolated into shell strings.
- Ambiguous names, duplicate folders, missing sources, and infrastructure errors are held rather than silently scored.
- Review logs and delete them according to your course's data-retention policy.
