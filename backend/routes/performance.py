from flask import Blueprint, request, jsonify, g

from extensions import db
from models import Performance, Student
from auth import require_auth, require_role

performance_bp = Blueprint("performance", __name__)


@performance_bp.get("/<student_id>")
@require_auth
def list_performance(student_id):
    student = Student.query.filter_by(student_id=student_id).first()
    if not student:
        return jsonify({"error": "Student not found"}), 404
    if g.role == "STUDENT" and (not g.current_user.student_profile
                                 or g.current_user.student_profile.student_id != student_id):
        return jsonify({"error": "Forbidden: not your record"}), 403

    rows = Performance.query.filter_by(student_id=student.id).order_by(Performance.semester).all()
    return jsonify([r.to_dict() for r in rows])


@performance_bp.post("/<student_id>")
@require_auth
@require_role("ADMIN", "FACULTY")
def record_performance(student_id):
    student = Student.query.filter_by(student_id=student_id).first()
    if not student:
        return jsonify({"error": "Student not found"}), 404
    data = request.get_json(silent=True) or {}
    required = ["semester", "sgpa", "cgpa", "academic_year"]
    missing = [f for f in required if data.get(f) is None]
    if missing:
        return jsonify({"error": f"Missing fields: {', '.join(missing)}"}), 400

    row = Performance(student_id=student.id, semester=int(data["semester"]),
                       sgpa=float(data["sgpa"]), cgpa=float(data["cgpa"]),
                       backlogs=int(data.get("backlogs", 0)),
                       academic_year=data["academic_year"])
    db.session.add(row)
    db.session.commit()
    return jsonify(row.to_dict()), 201
