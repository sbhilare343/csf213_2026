# Grading Policy and Rubric Reconciliation

## Official sources inspected

- `Grader/testcases.xlsx`, sheet `TestCases`: 26 rows with testcase IDs and per-case marks; total 60.
- `Grader/grader-testcases.pdf`: 12 pages; lists the behavior of 26 tests across fare calculation, ride assignment, availability, completion, and end-to-end sequences.
- `Grader/midterm-lab-attendance.xlsx`, sheet `LabMidterm Attendance`: 379 unique campus IDs. Four rows are marked absent and four rows have makeup granted (these are separate flags in the sheet); attendance is presented separately from correctness marks.

The Python loader reads marks live from `testcases.xlsx`, verifies the complete expected test-ID set, prevents duplicate IDs, and validates the total marks configured in `settings.yaml`. The PDF is parsed for selectable text and every test ID is checked for presence. The PDF does not itself provide the mark for every row as a machine-readable table, so the XLSX remains the source of mark weights.

## Test ID coverage

- `F1`-`F4`: fare formula, 4 marks total.
- `Q1`-`Q6`: rating eligibility and boundary cases.
- `O1`-`O3`: first eligible driver in insertion order.
- `S1`-`S6`: availability and multi-request behavior.
- `C1`: requested distance is stored in the returned ride.
- `M1`-`M4`: completing rides restores only the relevant driver.
- `E1`-`E2`: full sequences involving request, completion, and retry.

The exact mark weights are in the included `testcases.xlsx` and are used from that workbook at grading time. They are not recomputed from test count.

## Grade handling

| Condition | Default handling |
|---|---|
| Test assertion passes | Full marks for that testcase as assigned in the workbook |
| Test assertion fails | Zero for that testcase |
| Runtime crash, timeout, or output over limit | Zero for that testcase; reason logged |
| C++ compilation fails | Zero overall, matching the reference Java grader's documented rule; configurable to hold |
| No submission folder | Hold for instructor review |
| No C++ source in matched folder | Hold for instructor review; not presumed to be an incorrect solution |
| Duplicate or ambiguous student identity | Hold for manual resolution |
| Grader infrastructure or sandbox error | Hold the student's total; do not interpret as a student failure |
| Attendance absent/makeup value | Report separately; no automatic mark deduction |

## Before grades are released

The instructor must confirm the default C++ adapter against a known-correct C++ reference solution. The supplied Moodle archive inspected for this project contains Java Git bundles, not `.cpp`/`.hpp` student submissions, so it was not used as a grading set. The self-test fixture only validates the grading infrastructure.
