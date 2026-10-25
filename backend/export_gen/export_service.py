"""
Phase 9 — Data export (CSV / Excel).

Turns the same data that already powers the dashboards and PDF reports into
downloadable spreadsheets, so staff can pull data into Excel/Sheets for
further analysis, reporting to university administration, or record-keeping
outside the app.

Design notes:
  - Every export is built from a pandas DataFrame (or a dict of DataFrames
    for multi-sheet workbooks), then written out via `write_export`, which
    is the single place that knows how to serialize to .csv or .xlsx.
  - CSV exports always emit exactly one table/sheet, since CSV has no
    concept of multiple sheets. If a multi-sheet dict is passed in "csv"
    mode, only the first sheet is written (callers should prefer .xlsx for
    exports that are naturally multi-table).
  - Nothing here duplicates business logic: risk levels come from
    RiskAssessment rows (Phase 4), triggers come from `risk_engine`
    (the original rule engine, Phase 1/3), reasons/recommendations come
    from the same JSON columns the dashboards and PDF reports already read.
  - Output files are written under Config.EXPORTS_DIR, mirroring how
    reports_gen/pdf_report.py writes under Config.REPORTS_DIR.
"""
import json
import os

import pandas as pd

from config import Config
from models import Student, Subject, Performance, RiskAssessment, Attendance, Marks
from risk_engine import evaluate_triggers, load_thresholds


def _subject_lookup():
    return {s.id: s for s in Subject.query.all()}


def _latest_risk(student_id):
    return (RiskAssessment.query.filter_by(student_id=student_id)
            .order_by(RiskAssessment.created_at.desc()).first())


def _latest_performance(student_id):
    return (Performance.query.filter_by(student_id=student_id)
            .order_by(Performance.id.desc()).first())


# ------------------------------------------------------------------
# Sheet 1: full student roster with computed metrics + risk + triggers
# ------------------------------------------------------------------
def students_dataframe(students=None) -> pd.DataFrame:
    students = students if students is not None else Student.query.all()
    thresholds = load_thresholds()
    rows = []
    for s in students:
        result = evaluate_triggers(s, thresholds)
        metrics = result["metrics"]
        perf = _latest_performance(s.id)
        risk = _latest_risk(s.id)
        rows.append({
            "Student ID": s.student_id,
            "Name": s.name,
            "Department": s.department,
            "Semester": s.semester,
            "Section": s.section,
            "Avg Attendance %": round(metrics["avg_attendance"], 2) if metrics["avg_attendance"] is not None else None,
            "Avg Marks": round(metrics["avg_marks"], 2) if metrics["avg_marks"] is not None else None,
            "Late/Missed Ratio": round(metrics["late_missed_ratio"], 2),
            "CGPA": perf.cgpa if perf else None,
            "Backlogs": perf.backlogs if perf else None,
            "Triggers": ", ".join(result["triggers"]) if result["triggers"] else "None",
            "Risk Level (ML)": risk.risk_level if risk else "UNASSESSED",
            "Risk Score (ML)": round(risk.risk_score, 3) if risk else None,
        })
    return pd.DataFrame(rows)


# ------------------------------------------------------------------
# Sheet 2: HIGH / CRITICAL students only, with reasons + recommendations
# ------------------------------------------------------------------
def at_risk_dataframe(students=None) -> pd.DataFrame:
    students = students if students is not None else Student.query.all()
    rows = []
    for s in students:
        risk = _latest_risk(s.id)
        if not risk or risk.risk_level not in ("HIGH", "CRITICAL"):
            continue
        reasons = json.loads(risk.reasons) if risk.reasons else []
        recs = json.loads(risk.recommendations) if risk.recommendations else []
        rows.append({
            "Student ID": s.student_id,
            "Name": s.name,
            "Department": s.department,
            "Semester": s.semester,
            "Risk Level": risk.risk_level,
            "Risk Score": round(risk.risk_score, 3),
            "Reasons": "; ".join(reasons),
            "Recommendations": "; ".join(recs),
            "Assessed At": risk.created_at.isoformat() if risk.created_at else None,
        })
    df = pd.DataFrame(rows)
    if not df.empty:
        df = df.sort_values("Risk Score", ascending=False)
    return df


# ------------------------------------------------------------------
# Sheet 3: department-level rollup (same numbers as the admin dashboard)
# ------------------------------------------------------------------
def department_summary_dataframe(students=None) -> pd.DataFrame:
    students = students if students is not None else Student.query.all()
    by_dept = {}
    for s in students:
        d = by_dept.setdefault(s.department, {
            "count": 0, "cgpa_sum": 0.0, "cgpa_n": 0,
            "LOW": 0, "MEDIUM": 0, "HIGH": 0, "CRITICAL": 0, "UNASSESSED": 0,
        })
        d["count"] += 1
        perf = _latest_performance(s.id)
        if perf and perf.cgpa is not None:
            d["cgpa_sum"] += perf.cgpa
            d["cgpa_n"] += 1
        risk = _latest_risk(s.id)
        d[risk.risk_level if risk else "UNASSESSED"] += 1

    rows = [{
        "Department": dept,
        "Student Count": v["count"],
        "Avg CGPA": round(v["cgpa_sum"] / v["cgpa_n"], 2) if v["cgpa_n"] else None,
        "LOW Risk": v["LOW"], "MEDIUM Risk": v["MEDIUM"],
        "HIGH Risk": v["HIGH"], "CRITICAL Risk": v["CRITICAL"],
        "Unassessed": v["UNASSESSED"],
    } for dept, v in by_dept.items()]
    return pd.DataFrame(rows)


# ------------------------------------------------------------------
# Sheet 4: trigger summary (same numbers as /students/summary)
# ------------------------------------------------------------------
def trigger_summary_dataframe(students=None) -> pd.DataFrame:
    students = students if students is not None else Student.query.all()
    thresholds = load_thresholds()
    counts = {"BURNOUT_RISK": 0, "LEARNING_GAP": 0, "OUTCOME_MISMATCH": 0,
              "PLACEMENT_POLICY_MISMATCH": 0}
    for s in students:
        for trig in evaluate_triggers(s, thresholds)["triggers"]:
            counts[trig] += 1
    rows = [{"Trigger": k.replace("_", " ").title(), "Student Count": v} for k, v in counts.items()]
    return pd.DataFrame(rows)


# ------------------------------------------------------------------
# Single-student export: subject-wise marks / attendance / performance
# history / risk history, for a student's own record or a staff lookup
# ------------------------------------------------------------------
def student_record_dataframes(student) -> dict:
    subjects = _subject_lookup()

    perf_rows = (Performance.query.filter_by(student_id=student.id)
                 .order_by(Performance.semester).all())
    performance_df = pd.DataFrame([{
        "Semester": p.semester, "SGPA": p.sgpa, "CGPA": p.cgpa,
        "Backlogs": p.backlogs, "Academic Year": p.academic_year,
    } for p in perf_rows])

    marks_rows = Marks.query.filter_by(student_id=student.id).all()
    marks_df = pd.DataFrame([{
        "Subject": subjects.get(m.subject_id).subject_name if m.subject_id in subjects else "?",
        "Internal": m.internal_marks, "Midterm": m.midterm_marks,
        "Assignment": m.assignment_marks, "Practical": m.practical_marks,
        "Final": m.final_marks, "Total": m.total_marks, "Grade": m.grade,
    } for m in marks_rows])

    att_rows = Attendance.query.filter_by(student_id=student.id).all()
    attendance_df = pd.DataFrame([{
        "Subject": subjects.get(a.subject_id).subject_name if a.subject_id in subjects else "?",
        "Attended": a.attended_classes, "Total Classes": a.total_classes,
        "Attendance %": a.attendance_percentage, "Date": a.date.isoformat() if a.date else None,
    } for a in att_rows])

    risk_rows = (RiskAssessment.query.filter_by(student_id=student.id)
                 .order_by(RiskAssessment.created_at.desc()).all())
    risk_df = pd.DataFrame([{
        "Assessed At": r.created_at.isoformat() if r.created_at else None,
        "Risk Level": r.risk_level, "Risk Score": r.risk_score,
        "Reasons": "; ".join(json.loads(r.reasons)) if r.reasons else "",
        "Recommendations": "; ".join(json.loads(r.recommendations)) if r.recommendations else "",
    } for r in risk_rows])

    return {
        "Performance": performance_df,
        "Marks": marks_df,
        "Attendance": attendance_df,
        "Risk History": risk_df,
    }


# ------------------------------------------------------------------
# Serialization: write a DataFrame (csv/xlsx) or dict-of-DataFrames (xlsx)
# ------------------------------------------------------------------
def write_export(data, fmt: str, filename_base: str) -> tuple:
    """
    data: a single DataFrame, or a dict[str, DataFrame] for multi-sheet xlsx.
    fmt: "csv" or "xlsx".
    Returns (path, mimetype, download_name).
    """
    fmt = (fmt or "xlsx").lower()
    if fmt not in ("csv", "xlsx"):
        raise ValueError("format must be 'csv' or 'xlsx'")

    os.makedirs(Config.EXPORTS_DIR, exist_ok=True)

    if fmt == "csv":
        df = data if isinstance(data, pd.DataFrame) else next(iter(data.values()))
        path = os.path.join(Config.EXPORTS_DIR, f"{filename_base}.csv")
        df.to_csv(path, index=False)
        return path, "text/csv", f"{filename_base}.csv"

    # xlsx
    path = os.path.join(Config.EXPORTS_DIR, f"{filename_base}.xlsx")
    with pd.ExcelWriter(path, engine="openpyxl") as writer:
        if isinstance(data, pd.DataFrame):
            sheet_df = data if not data.empty else pd.DataFrame([{"Note": "No data available"}])
            sheet_df.to_excel(writer, sheet_name="Data", index=False)
        else:
            for sheet_name, df in data.items():
                safe_name = sheet_name[:31]  # Excel's sheet-name length limit
                sheet_df = df if not df.empty else pd.DataFrame([{"Note": "No data available"}])
                sheet_df.to_excel(writer, sheet_name=safe_name, index=False)
        _autosize_columns(writer)
    mimetype = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    return path, mimetype, f"{filename_base}.xlsx"


def _autosize_columns(writer):
    """Best-effort column width so exported sheets are readable without
    manual resizing in Excel. Not critical to correctness, so any failure
    here is swallowed rather than breaking the export."""
    try:
        for sheet in writer.sheets.values():
            for col_cells in sheet.columns:
                length = max((len(str(c.value)) if c.value is not None else 0) for c in col_cells)
                sheet.column_dimensions[col_cells[0].column_letter].width = min(max(length + 2, 10), 40)
    except Exception:
        pass
