# Operational Runbook

1. Install Python package dependencies and system tools as in the main README.
2. Put C++ submissions in `submissions/<campus_id>/`, or import a Moodle export ZIP with `python -m cpp_grader --config config/settings.yaml prepare-archive /path/to/export.zip`. Bundle import shallow-clones the default branch for file extraction; keep the original submission archive for Git-history grading.
3. Run `inspect`, then `validate`.
4. Run `grade --dry-run` and manually inspect the reconciliation workbook.
5. Check the `config/ride_api_adapter*.hpp` against a trusted solution.
6. Grade a tiny pilot with `grade --student-id CAMPUS_ID --workers 1 --force` (replace with a known C++ campus ID from the reconciliation report) and review `output/work/<normalized-campus-id>/compile.log` and `output/work/<normalized-campus-id>/tests/*.log`.
7. Run a full grade with the default safety-limited worker count.
8. Review `output/grades.xlsx`, especially `Exceptions`, and `output/student_reconciliation.xlsx` before release.

A result cached in `output/work/<normalized-campus-id>/result.json` is reused only when the source, marks, harness, adapter, and relevant settings fingerprint remain unchanged. Use `--force` after any intentional regrade.

A `--limit` run produces a partial gradebook by design; never send it out as the final class result.
