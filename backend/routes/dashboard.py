from flask import Blueprint, jsonify, g

from models import Student, Subject, Performance, RiskAssessment, Attendance, Marks
from auth import require_auth, require_role
from risk_engine import summary_counts, load_thresholds
from ml.risk_model import extract_features

dashboard_bp = Blueprint("dashboard", __name__)


def _latest_risk_map(students):
    out = {}
    for s in students:
        row = (RiskAssessment.query.filter_by(student_id=s.id)
               .order_by(RiskAssessment.created_at.desc()).first())
        if row:
            out[s.id] = row
    return out


@dashboard_bp.get("/admin")
@require_auth
@require_role("ADMIN")
def admin_dashboard():
    students = Student.query.all()
    risk_map = _latest_risk_map(students)

    by_dept = {}
    for s in students:
        by_dept.setdefault(s.department, {"count": 0, "cgpa_sum": 0.0, "cgpa_n": 0})
        by_dept[s.department]["count"] += 1
        perf = (Performance.query.filter_by(student_id=s.id)
                .order_by(Performance.id.desc()).first())
        if perf and perf.cgpa is not None:
            by_dept[s.department]["cgpa_sum"] += perf.cgpa
            by_dept[s.department]["cgpa_n"] += 1

    dept_stats = [{
        "department": d,
        "student_count": v["count"],
        "avg_cgpa": round(v["cgpa_sum"] / v["cgpa_n"], 2) if v["cgpa_n"] else None,
    } for d, v in by_dept.items()]

    risk_levels = {"LOW": 0, "MEDIUM": 0, "HIGH": 0, "CRITICAL": 0, "UNASSESSED": 0}
    for s in students:
        row = risk_map.get(s.id)
        risk_levels[row.risk_level if row else "UNASSESSED"] += 1

    return jsonify({
        "total_students": len(students),
        "total_subjects": Subject.query.count(),
        "trigger_counts": summary_counts(students),
        "risk_level_distribution": risk_levels,
        "department_stats": dept_stats,
        "thresholds": load_thresholds(),
    })


@dashboard_bp.get("/faculty")
@require_auth
@require_role("ADMIN", "FACULTY")
def faculty_dashboard():
    students = Student.query.all()
    risk_map = _latest_risk_map(students)

    at_risk = []
    for s in students:
        row = risk_map.get(s.id)
        if row and row.risk_level in ("HIGH", "CRITICAL"):
            at_risk.append({
                "student_id": s.student_id, "name": s.name, "department": s.department,
                "risk_level": row.risk_level, "risk_score": row.risk_score,
            })
    at_risk.sort(key=lambda r: -r["risk_score"])

    avg_marks_by_subject = {}
    for subj in Subject.query.all():
        rows = Marks.query.filter_by(subject_id=subj.id).all()
        if rows:
            avg_marks_by_subject[subj.subject_name] = round(
                sum(r.total_marks for r in rows) / len(rows), 1)

    return jsonify({
        "total_students": len(students),
        "at_risk_students": at_risk,
        "avg_marks_by_subject": avg_marks_by_subject,
    })


@dashboard_bp.get("/student")
@require_auth
@require_role("STUDENT")
def student_dashboard():
    student = g.current_user.student_profile
    if not student:
        return jsonify({"error": "No student profile linked to this account"}), 404

    feats = extract_features(student)
    perf_rows = (Performance.query.filter_by(student_id=student.id)
                 .order_by(Performance.semester).all())
    risk_row = (RiskAssessment.query.filter_by(student_id=student.id)
                .order_by(RiskAssessment.created_at.desc()).first())
    attendance_rows = Attendance.query.filter_by(student_id=student.id).all()
    marks_rows = Marks.query.filter_by(student_id=student.id).all()

    subj_by_id = {s.id: s.subject_name for s in Subject.query.all()}

    return jsonify({
        "student": student.to_dict(),
        "metrics": feats,
        "cgpa_trend": [{"semester": p.semester, "sgpa": p.sgpa, "cgpa": p.cgpa} for p in perf_rows],
        "latest_risk": risk_row.to_dict() if risk_row else None,
        "attendance_by_subject": [
            {"subject": subj_by_id.get(a.subject_id, "?"), "percentage": a.attendance_percentage}
            for a in attendance_rows
        ],
        "marks_by_subject": [
            {"subject": subj_by_id.get(m.subject_id, "?"), "total_marks": m.total_marks, "grade": m.grade}
            for m in marks_rows
        ],
    })
