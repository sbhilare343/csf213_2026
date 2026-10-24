from __future__ import annotations
from dataclasses import dataclass, asdict, field
from typing import Any

@dataclass(frozen=True)
class TestCase:
    id: str
    method: str
    section: str
    category: str
    scenario: str
    drivers_added: str
    steps: str
    expected: str
    catches: str
    marks: float
    source_row: int

@dataclass(frozen=True)
class Student:
    student_id: str
    name: str
    email: str = ""
    groups: str = ""
    zone: str = ""
    seat: str = ""
    attendance: str = "Unknown"
    absent: bool | None = None
    makeup: str = ""
    valid_submission: bool | None = None
    roster_row: int | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

@dataclass(frozen=True)
class Submission:
    folder: str
    folder_name: str
    student_id: str | None
    status: str
    source_files: tuple[str, ...] = ()
    header_files: tuple[str, ...] = ()
    matched_by: str = ""
    issue: str = ""

@dataclass
class CaseResult:
    student_id: str
    testcase_id: str
    testcase_name: str
    max_marks: float
    earned_marks: float
    status: str
    message: str = ""
    return_code: int | None = None
    duration_seconds: float | None = None
    stdout: str = ""
    stderr: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

@dataclass
class StudentResult:
    student: Student
    submission_status: str
    submission_path: str = ""
    matched_by: str = ""
    source_count: int = 0
    compilation_status: str = "NOT_RUN"
    compile_message: str = ""
    earned_marks: float | None = None
    max_marks: float = 0.0
    percentage: float | None = None
    review_flag: str = ""
    fingerprint: str = ""
    case_results: list[CaseResult] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        # Email is not needed for grading or score audits; avoid copying it into JSON logs.
        student_fields = self.student.to_dict()
        student_fields.pop("email", None)
        return {
            **student_fields, "submission_status": self.submission_status,
            "submission_path": self.submission_path, "matched_by": self.matched_by,
            "source_count": self.source_count, "compilation_status": self.compilation_status,
            "compile_message": self.compile_message, "earned_marks": self.earned_marks,
            "max_marks": self.max_marks, "percentage": self.percentage,
            "review_flag": self.review_flag, "fingerprint": self.fingerprint,
            "case_results": [c.to_dict() for c in self.case_results],
        }
