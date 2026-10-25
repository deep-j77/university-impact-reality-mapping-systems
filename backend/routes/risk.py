import json

from flask import Blueprint, jsonify, g

from extensions import db
from models import Student, RiskAssessment
from config import Config
from auth import require_auth, require_role, student_owns_or_staff
from ml.risk_model import predict_risk, train_and_save

risk_bp = Blueprint("risk", __name__)


def _student_id_from_kwargs(**kwargs):
    return kwargs.get("student_id")


@risk_bp.post("/<student_id>/assess")
@require_auth
@require_role("ADMIN", "FACULTY")
def assess_student(student_id):
    student = Student.query.filter_by(student_id=student_id).first()
    if not student:
        return jsonify({"error": "Student not found"}), 404

    result = predict_risk(student, Config.ML_MODEL_PATH)

    row = RiskAssessment(
        student_id=student.id, risk_score=result["risk_score"],
        risk_level=result["risk_level"],
        reasons=json.dumps(result["reasons"]),
        recommendations=json.dumps(result["recommendations"]),
    )
    db.session.add(row)
    db.session.commit()

    out = row.to_dict()
    out["source"] = result.get("source")
    return jsonify(out), 201


@risk_bp.get("/<student_id>/latest")
@require_auth
@student_owns_or_staff(_student_id_from_kwargs)
def latest_assessment(student_id):
    student = Student.query.filter_by(student_id=student_id).first()
    if not student:
        return jsonify({"error": "Student not found"}), 404
    row = (RiskAssessment.query.filter_by(student_id=student.id)
           .order_by(RiskAssessment.created_at.desc()).first())
    if not row:
        return jsonify({"error": "No risk assessment yet. POST to /assess first."}), 404
    return jsonify(row.to_dict())


@risk_bp.get("/<student_id>/history")
@require_auth
@student_owns_or_staff(_student_id_from_kwargs)
def assessment_history(student_id):
    student = Student.query.filter_by(student_id=student_id).first()
    if not student:
        return jsonify({"error": "Student not found"}), 404
    rows = (RiskAssessment.query.filter_by(student_id=student.id)
            .order_by(RiskAssessment.created_at.desc()).all())
    return jsonify([r.to_dict() for r in rows])


@risk_bp.get("/at-risk")
@require_auth
@require_role("ADMIN", "FACULTY")
def all_at_risk():
    """Latest assessment per student, filtered to HIGH/CRITICAL."""
    students = Student.query.all()
    out = []
    for s in students:
        row = (RiskAssessment.query.filter_by(student_id=s.id)
               .order_by(RiskAssessment.created_at.desc()).first())
        if row and row.risk_level in ("HIGH", "CRITICAL"):
            d = row.to_dict()
            d["student_id"] = s.student_id
            d["name"] = s.name
            out.append(d)
    out.sort(key=lambda r: -r["risk_score"])
    return jsonify(out)


@risk_bp.post("/retrain")
@require_auth
@require_role("ADMIN")
def retrain():
    students = Student.query.all()
    try:
        result = train_and_save(students, Config.ML_MODEL_PATH)
    except ValueError as e:
        return jsonify({"error": str(e)}), 400
    return jsonify({
        "n_samples": result["n_samples"],
        "feature_importances": result["feature_importances"],
    })
