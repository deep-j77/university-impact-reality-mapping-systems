"""
Phase 9 — Data export routes.

Adds CSV / Excel download endpoints on top of the existing data (students,
risk assessments, triggers, department stats, and a single student's own
academic record). This is additive: no existing route, model, or behavior
is changed. It reuses the same rule engine, ML risk data, and DB models
that already back the dashboards and PDF reports (Phases 3/4/6/7), so
exported numbers always match what's shown on screen.

Endpoints (all under /api/export, JWT required):
  GET /students          ?format=csv|xlsx   ADMIN/FACULTY  full roster + metrics
  GET /at-risk           ?format=csv|xlsx   ADMIN/FACULTY  HIGH/CRITICAL only
  GET /analytics         ?format=xlsx       ADMIN          multi-sheet workbook
                                                            (roster, at-risk,
                                                             departments, triggers)
  GET /student/<id>      ?format=csv|xlsx   owner or staff  one student's own
                                                             marks/attendance/
                                                             performance/risk
                                                             history
"""
from flask import Blueprint, jsonify, request, send_file

from models import Student
from auth import require_auth, require_role, student_owns_or_staff
from export_gen import export_service as ex

export_bp = Blueprint("export", __name__)


def _fmt():
    fmt = request.args.get("format", "xlsx").lower()
    if fmt not in ("csv", "xlsx"):
        fmt = "xlsx"
    return fmt


def _send(path, mimetype, download_name):
    return send_file(path, as_attachment=True, download_name=download_name, mimetype=mimetype)


@export_bp.get("/students")
@require_auth
@require_role("ADMIN", "FACULTY")
def export_students():
    """Full student roster: department, semester, computed attendance/marks
    metrics, CGPA, backlogs, rule-engine triggers, and the latest ML risk
    assessment — one row per student."""
    df = ex.students_dataframe()
    path, mimetype, name = ex.write_export(df, _fmt(), "students_export")
    return _send(path, mimetype, name)


@export_bp.get("/at-risk")
@require_auth
@require_role("ADMIN", "FACULTY")
def export_at_risk():
    """HIGH/CRITICAL students only, with the ML risk score, contributing
    reasons, and recommendations, sorted highest-risk first — ready to hand
    to counseling/advising staff."""
    df = ex.at_risk_dataframe()
    path, mimetype, name = ex.write_export(df, _fmt(), "at_risk_students_export")
    return _send(path, mimetype, name)


@export_bp.get("/analytics")
@require_auth
@require_role("ADMIN")
def export_analytics():
    """Full multi-sheet analytics workbook (Excel only, since CSV can't
    hold multiple sheets): student roster, at-risk list, department rollup,
    and trigger summary — the same numbers shown across the admin dashboard,
    bundled into one file for reporting to university administration."""
    students = Student.query.all()
    sheets = {
        "All Students": ex.students_dataframe(students),
        "At-Risk (High-Critical)": ex.at_risk_dataframe(students),
        "By Department": ex.department_summary_dataframe(students),
        "Trigger Summary": ex.trigger_summary_dataframe(students),
    }
    path, mimetype, name = ex.write_export(sheets, "xlsx", "analytics_export")
    return _send(path, mimetype, name)


def _student_id_from_kwargs(**kwargs):
    return kwargs.get("student_id")


@export_bp.get("/student/<student_id>")
@require_auth
@student_owns_or_staff(_student_id_from_kwargs)
def export_student_record(student_id):
    """One student's own academic record — performance history, subject-wise
    marks, subject-wise attendance, and risk assessment history — as a
    multi-sheet workbook (or a single CSV of the marks sheet if format=csv
    is requested, since CSV has no concept of multiple sheets)."""
    student = Student.query.filter_by(student_id=student_id).first()
    if not student:
        return jsonify({"error": "Student not found"}), 404

    sheets = ex.student_record_dataframes(student)
    path, mimetype, name = ex.write_export(sheets, _fmt(), f"{student.student_id}_data_export")
    return _send(path, mimetype, name)
