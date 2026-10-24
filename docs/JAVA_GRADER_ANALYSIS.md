# Java Grader Analysis and C++ Porting Decisions

The supplied Java Bundle Grader source is preserved under `reference/java_grader/Java-Bundle-Grader-CSF213/` for comparison. It is a per-student Gradle/JUnit pipeline. It unpacks or reads student projects, replaces the ordinary test directory with the grader-owned tests, applies a controlled Java toolchain, runs tests, records test-level marks, and builds a roster-aware CSV report. Its documented policy assigns zero when a student project does not build. Its testcase configuration defines the same 26 IDs and a 60-mark total.

The C++ grader preserves the important behavior while using the native compilation model:

| Java reference pattern | C++ implementation |
|---|---|
| Per-student isolated project copy | Per-student temporary source/build workspace |
| Gradle + injected JUnit tests | `g++` + injected standalone C++ assertion harness |
| One JUnit class/test per operation | One harness process per official testcase ID |
| Gradle build/test output | Compile logs and bounded testcase stdout/stderr |
| Test marks keyed by F1..E2 | Marks loaded from `testcases.xlsx` and attached by ID |
| Attendance roster report | Same concept, with explicit identity reconciliation and exceptions |
| Parallel student builds | Bounded concurrent student workers; two logical cores reserved by default |

## Important differences

The uploaded class export contains a mix of Java and C++ Git bundles. Multiple C++ bundles share the reference-based API used by the default C++ adapter, but it must still be checked against the official course starter/reference solution. The importer copies only the checkout on each bundle's default/HEAD branch and deliberately drops `.git` metadata; retain the original archive for Git-history evaluation. Java-only submissions receive a `NO_CPP_SOURCE` hold status in the C++ run and must be handled by the Java grader, not silently scored as zero.

The root `main.cpp` in the archive is an earlier attempted grader, not a suitable testing harness. It tries to parse `.xlsx` workbooks as XML text, constructs shell command strings, assumes every testcase has plain stdin/stdout, uses equal per-test points, and incorrectly populates the student's name using the ID. The C++ grader replaces these assumptions with workbook-aware parsing, the official stateful unit-test cases, subprocess argument lists, bounded execution, and roster-based reports.
