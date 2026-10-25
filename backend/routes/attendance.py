from flask import Blueprint, request, jsonify, g

from extensions import db
from models import Attendance, Student
from auth import require_auth, require_role

attendance_bp = Blueprint("attendance", __name__)


def _resolve_student(student_id):
    return Student.query.filter_by(student_id=student_id).first()


@attendance_bp.get("/<student_id>")
@require_auth
def list_attendance(student_id):
    student = _resolve_student(student_id)
    if not student:
        return jsonify({"error": "Student not found"}), 404
    if g.role == "STUDENT" and (not g.current_user.student_profile
                                 or g.current_user.student_profile.student_id != student_id):
        return jsonify({"error": "Forbidden: not your record"}), 403

    subject_id = request.args.get("subject_id")
    q = Attendance.query.filter_by(student_id=student.id)
    if subject_id:
        q = q.filter_by(subject_id=int(subject_id))
    rows = q.order_by(Attendance.date.desc()).all()
    return jsonify([r.to_dict() for r in rows])


@attendance_bp.post("/<student_id>")
@require_auth
@require_role("ADMIN", "FACULTY")
def record_attendance(student_id):
    student = _resolve_student(student_id)
    if not student:
        return jsonify({"error": "Student not found"}), 404
    data = request.get_json(silent=True) or {}
    required = ["subject_id", "total_classes", "attended_classes"]
    missing = [f for f in required if data.get(f) is None]
    if missing:
        return jsonify({"error": f"Missing fields: {', '.join(missing)}"}), 400

    total = int(data["total_classes"])
    attended = int(data["attended_classes"])
    if attended > total:
        return jsonify({"error": "attended_classes cannot exceed total_classes"}), 400

    row = Attendance(
        student_id=student.id, subject_id=int(data["subject_id"]),
        total_classes=total, attended_classes=attended,
        attendance_percentage=round(attended / total * 100, 1) if total else 0.0,
    )
    db.session.add(row)
    db.session.commit()
    return jsonify(row.to_dict()), 201


@attendance_bp.put("/record/<int:record_id>")
@require_auth
@require_role("ADMIN", "FACULTY")
def update_attendance(record_id):
    row = Attendance.query.get(record_id)
    if not row:
        return jsonify({"error": "Attendance record not found"}), 404
    data = request.get_json(silent=True) or {}
    total = data.get("total_classes", row.total_classes)
    attended = data.get("attended_classes", row.attended_classes)
    if attended > total:
        return jsonify({"error": "attended_classes cannot exceed total_classes"}), 400
    row.total_classes = total
    row.attended_classes = attended
    row.attendance_percentage = round(attended / total * 100, 1) if total else 0.0
    db.session.commit()
    return jsonify(row.to_dict())
