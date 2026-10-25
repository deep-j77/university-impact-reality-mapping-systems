from flask import Blueprint, request, jsonify, g

from extensions import db
from models import Student, User, Performance
from auth import require_auth, require_role, student_owns_or_staff, hash_password
from risk_engine import evaluate_triggers, load_thresholds, summary_counts

students_bp = Blueprint("students", __name__)


def _student_id_from_kwargs(**kwargs):
    return kwargs.get("student_id")


@students_bp.get("")
@require_auth
@require_role("ADMIN", "FACULTY")
def list_students():
    department = request.args.get("department")
    semester = request.args.get("semester")
    q = Student.query
    if department:
        q = q.filter(Student.department == department)
    if semester:
        q = q.filter(Student.semester == int(semester))
    students = q.order_by(Student.student_id).all()
    return jsonify([s.to_dict() for s in students])


@students_bp.get("/<student_id>")
@require_auth
@student_owns_or_staff(_student_id_from_kwargs)
def get_student(student_id):
    student = Student.query.filter_by(student_id=student_id).first()
    if not student:
        return jsonify({"error": "Student not found"}), 404
    data = student.to_dict()
    perf = (Performance.query.filter_by(student_id=student.id)
            .order_by(Performance.id.desc()).first())
    data["latest_performance"] = perf.to_dict() if perf else None
    return jsonify(data)


@students_bp.post("")
@require_auth
@require_role("ADMIN")
def create_student():
    data = request.get_json(silent=True) or {}
    required = ["name", "email", "password", "student_id", "department", "semester"]
    missing = [f for f in required if not data.get(f)]
    if missing:
        return jsonify({"error": f"Missing fields: {', '.join(missing)}"}), 400

    if User.query.filter_by(email=data["email"].strip().lower()).first():
        return jsonify({"error": "Email already registered"}), 409
    if Student.query.filter_by(student_id=data["student_id"].strip()).first():
        return jsonify({"error": "Student ID already exists"}), 409

    user = User(name=data["name"].strip(), email=data["email"].strip().lower(),
                password_hash=hash_password(data["password"]), role="STUDENT")
    db.session.add(user)
    db.session.flush()

    student = Student(
        user_id=user.id, student_id=data["student_id"].strip(),
        name=data["name"].strip(), department=data["department"].strip(),
        semester=int(data["semester"]), section=data.get("section"),
        enrollment_year=data.get("enrollment_year"), phone=data.get("phone"),
        email=user.email,
    )
    db.session.add(student)
    db.session.commit()
    return jsonify(student.to_dict()), 201


@students_bp.put("/<student_id>")
@require_auth
@require_role("ADMIN", "FACULTY")
def update_student(student_id):
    student = Student.query.filter_by(student_id=student_id).first()
    if not student:
        return jsonify({"error": "Student not found"}), 404
    data = request.get_json(silent=True) or {}
    for field in ("name", "department", "semester", "section", "enrollment_year", "phone", "email"):
        if field in data:
            setattr(student, field, data[field])
    db.session.commit()
    return jsonify(student.to_dict())


@students_bp.delete("/<student_id>")
@require_auth
@require_role("ADMIN")
def delete_student(student_id):
    student = Student.query.filter_by(student_id=student_id).first()
    if not student:
        return jsonify({"error": "Student not found"}), 404
    user = student.user
    db.session.delete(student)
    if user:
        db.session.delete(user)
    db.session.commit()
    return jsonify({"deleted": student_id})


# ---------------------------------------------------------------
# Legacy-equivalent endpoints (kept at familiar paths for continuity
# with the original minor project's frontend contract)
# ---------------------------------------------------------------
@students_bp.get("/triggers")
@require_auth
@require_role("ADMIN", "FACULTY")
def students_with_triggers():
    thresholds = load_thresholds()
    students = Student.query.order_by(Student.student_id).all()
    out = []
    for s in students:
        result = evaluate_triggers(s, thresholds)
        d = s.to_dict()
        d["triggers"] = result["triggers"]
        d["metrics"] = result["metrics"]
        out.append(d)
    return jsonify(out)


@students_bp.get("/summary")
@require_auth
@require_role("ADMIN", "FACULTY")
def summary():
    students = Student.query.all()
    return jsonify(summary_counts(students))
