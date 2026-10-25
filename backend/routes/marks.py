from flask import Blueprint, request, jsonify, g

from extensions import db
from models import Marks, Student
from auth import require_auth, require_role

marks_bp = Blueprint("marks", __name__)


def _grade_for(total):
    return ("A" if total >= 85 else "B" if total >= 70 else
            "C" if total >= 55 else "D" if total >= 40 else "F")


@marks_bp.get("/<student_id>")
@require_auth
def list_marks(student_id):
    student = Student.query.filter_by(student_id=student_id).first()
    if not student:
        return jsonify({"error": "Student not found"}), 404
    if g.role == "STUDENT" and (not g.current_user.student_profile
                                 or g.current_user.student_profile.student_id != student_id):
        return jsonify({"error": "Forbidden: not your record"}), 403

    rows = Marks.query.filter_by(student_id=student.id).all()
    return jsonify([r.to_dict() for r in rows])


@marks_bp.post("/<student_id>")
@require_auth
@require_role("ADMIN", "FACULTY")
def record_marks(student_id):
    student = Student.query.filter_by(student_id=student_id).first()
    if not student:
        return jsonify({"error": "Student not found"}), 404
    data = request.get_json(silent=True) or {}
    if not data.get("subject_id"):
        return jsonify({"error": "subject_id is required"}), 400

    components = ["internal_marks", "midterm_marks", "assignment_marks",
                  "practical_marks", "final_marks"]
    values = {c: float(data.get(c, 0)) for c in components}
    total = round(sum(values.values()), 1)

    row = Marks(student_id=student.id, subject_id=int(data["subject_id"]),
                total_marks=total, grade=_grade_for(total), **values)
    db.session.add(row)
    db.session.commit()
    return jsonify(row.to_dict()), 201


@marks_bp.put("/record/<int:record_id>")
@require_auth
@require_role("ADMIN", "FACULTY")
def update_marks(record_id):
    row = Marks.query.get(record_id)
    if not row:
        return jsonify({"error": "Marks record not found"}), 404
    data = request.get_json(silent=True) or {}
    for c in ("internal_marks", "midterm_marks", "assignment_marks",
              "practical_marks", "final_marks"):
        if c in data:
            setattr(row, c, float(data[c]))
    row.total_marks = round(
        row.internal_marks + row.midterm_marks + row.assignment_marks
        + row.practical_marks + row.final_marks, 1)
    row.grade = _grade_for(row.total_marks)
    db.session.commit()
    return jsonify(row.to_dict())
