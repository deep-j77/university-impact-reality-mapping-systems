from flask import Blueprint, request, jsonify

from extensions import db
from models import Subject
from auth import require_auth, require_role

subjects_bp = Blueprint("subjects", __name__)


@subjects_bp.get("")
@require_auth
def list_subjects():
    department = request.args.get("department")
    semester = request.args.get("semester")
    q = Subject.query
    if department:
        q = q.filter(Subject.department == department)
    if semester:
        q = q.filter(Subject.semester == int(semester))
    return jsonify([s.to_dict() for s in q.order_by(Subject.subject_code).all()])


@subjects_bp.get("/<int:subject_id>")
@require_auth
def get_subject(subject_id):
    subj = Subject.query.get(subject_id)
    if not subj:
        return jsonify({"error": "Subject not found"}), 404
    return jsonify(subj.to_dict())


@subjects_bp.post("")
@require_auth
@require_role("ADMIN", "FACULTY")
def create_subject():
    data = request.get_json(silent=True) or {}
    required = ["subject_code", "subject_name", "semester", "department"]
    missing = [f for f in required if not data.get(f)]
    if missing:
        return jsonify({"error": f"Missing fields: {', '.join(missing)}"}), 400
    if Subject.query.filter_by(subject_code=data["subject_code"]).first():
        return jsonify({"error": "Subject code already exists"}), 409

    subj = Subject(
        subject_code=data["subject_code"], subject_name=data["subject_name"],
        credits=data.get("credits", 3), semester=int(data["semester"]),
        department=data["department"],
    )
    db.session.add(subj)
    db.session.commit()
    return jsonify(subj.to_dict()), 201


@subjects_bp.put("/<int:subject_id>")
@require_auth
@require_role("ADMIN", "FACULTY")
def update_subject(subject_id):
    subj = Subject.query.get(subject_id)
    if not subj:
        return jsonify({"error": "Subject not found"}), 404
    data = request.get_json(silent=True) or {}
    for field in ("subject_name", "credits", "semester", "department"):
        if field in data:
            setattr(subj, field, data[field])
    db.session.commit()
    return jsonify(subj.to_dict())


@subjects_bp.delete("/<int:subject_id>")
@require_auth
@require_role("ADMIN")
def delete_subject(subject_id):
    subj = Subject.query.get(subject_id)
    if not subj:
        return jsonify({"error": "Subject not found"}), 404
    db.session.delete(subj)
    db.session.commit()
    return jsonify({"deleted": subject_id})
