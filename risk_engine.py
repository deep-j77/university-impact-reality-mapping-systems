"""
Rule-based trigger engine — the one part of the original minor project that
was explicitly worth preserving conceptually (explainable, no black box).

Reworked to read from the new relational schema (Attendance/Marks/
AssignmentSubmission/Performance) instead of the old flat CSV columns, but
the four trigger categories and their spirit are the same:
    BURNOUT_RISK, LEARNING_GAP, OUTCOME_MISMATCH, PLACEMENT_POLICY_MISMATCH

This still runs independently of the Phase 4 ML model — the ML model
augments this, it doesn't replace it, so results stay explainable.
"""
import json
import os

from models import Attendance, Marks, AssignmentSubmission, Performance

THRESHOLDS_FILE = os.path.join(os.path.dirname(__file__), "thresholds.json")

DEFAULT_THRESHOLDS = {
    "attendance_burnout_pct": 75.0,       # below this -> burnout candidate
    "late_missed_ratio_burnout": 0.35,    # share of late/missed submissions
    "marks_learning_gap": 50.0,           # avg total_marks below this despite ok attendance
    "attendance_ok_for_gap": 70.0,
    "cgpa_outcome_mismatch": 6.5,         # cgpa below this while attendance/skills look fine
    "attendance_good_for_mismatch": 85.0,
    "cgpa_placement_policy": 6.0,         # typical placement eligibility cutoff
}


def load_thresholds() -> dict:
    if os.path.exists(THRESHOLDS_FILE):
        try:
            with open(THRESHOLDS_FILE) as f:
                data = json.load(f)
            merged = DEFAULT_THRESHOLDS.copy()
            merged.update(data)
            return merged
        except (json.JSONDecodeError, OSError):
            pass
    return DEFAULT_THRESHOLDS.copy()


def save_thresholds(new_values: dict) -> dict:
    current = load_thresholds()
    for k, v in new_values.items():
        if k in DEFAULT_THRESHOLDS:
            current[k] = float(v)
    with open(THRESHOLDS_FILE, "w") as f:
        json.dump(current, f, indent=2)
    return current


def _student_metrics(student):
    att_rows = Attendance.query.filter_by(student_id=student.id).all()
    marks_rows = Marks.query.filter_by(student_id=student.id).all()
    subs = AssignmentSubmission.query.filter_by(student_id=student.id).all()
    perf = (Performance.query.filter_by(student_id=student.id)
            .order_by(Performance.id.desc()).first())

    avg_attendance = (sum(a.attendance_percentage for a in att_rows) / len(att_rows)
                       if att_rows else None)
    avg_marks = (sum(m.total_marks for m in marks_rows) / len(marks_rows)
                 if marks_rows else None)
    late_missed = sum(1 for s in subs if s.status in ("LATE", "MISSED"))
    late_missed_ratio = (late_missed / len(subs)) if subs else 0.0
    cgpa = perf.cgpa if perf else None

    return {
        "avg_attendance": avg_attendance,
        "avg_marks": avg_marks,
        "late_missed_ratio": late_missed_ratio,
        "cgpa": cgpa,
    }


def evaluate_triggers(student, thresholds=None) -> dict:
    """Returns {"triggers": [...], "metrics": {...}} for one Student row."""
    t = thresholds or load_thresholds()
    m = _student_metrics(student)
    triggers = []

    if m["avg_attendance"] is not None and (
        m["avg_attendance"] < t["attendance_burnout_pct"]
        or m["late_missed_ratio"] > t["late_missed_ratio_burnout"]
    ):
        triggers.append("BURNOUT_RISK")

    if (m["avg_marks"] is not None and m["avg_attendance"] is not None
            and m["avg_marks"] < t["marks_learning_gap"]
            and m["avg_attendance"] >= t["attendance_ok_for_gap"]):
        triggers.append("LEARNING_GAP")

    if (m["cgpa"] is not None and m["avg_attendance"] is not None
            and m["cgpa"] < t["cgpa_outcome_mismatch"]
            and m["avg_attendance"] >= t["attendance_good_for_mismatch"]):
        triggers.append("OUTCOME_MISMATCH")

    if m["cgpa"] is not None and m["cgpa"] < t["cgpa_placement_policy"]:
        triggers.append("PLACEMENT_POLICY_MISMATCH")

    return {"triggers": triggers, "metrics": m}


def summary_counts(students, thresholds=None) -> dict:
    t = thresholds or load_thresholds()
    counts = {"BURNOUT_RISK": 0, "LEARNING_GAP": 0, "OUTCOME_MISMATCH": 0,
              "PLACEMENT_POLICY_MISMATCH": 0}
    for s in students:
        result = evaluate_triggers(s, t)
        for trig in result["triggers"]:
            counts[trig] += 1
    return counts
