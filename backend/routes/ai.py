from flask import Blueprint, request, jsonify, g

from extensions import db
from models import Student, RiskAssessment, AIPrediction
from auth import require_auth, require_role, student_owns_or_staff
from ml.risk_model import extract_features
from ai_layer.ai_service import explain_risk, generate_recommendations, chatbot_reply

ai_bp = Blueprint("ai", __name__)


def _student_id_from_kwargs(**kwargs):
    return kwargs.get("student_id")


def _latest_risk_or_400(student):
    row = (RiskAssessment.query.filter_by(student_id=student.id)
           .order_by(RiskAssessment.created_at.desc()).first())
    return row


@ai_bp.post("/<student_id>/explain")
@require_auth
@require_role("ADMIN", "FACULTY")
def explain(student_id):
    student = Student.query.filter_by(student_id=student_id).first()
    if not student:
        return jsonify({"error": "Student not found"}), 404
    risk = _latest_risk_or_400(student)
    if not risk:
        return jsonify({"error": "No risk assessment yet. POST /api/risk/<id>/assess first."}), 400

    import json
    reasons = json.loads(risk.reasons) if risk.reasons else []
    metrics = extract_features(student)
    result = explain_risk(student.name, risk.risk_level, risk.risk_score, reasons, metrics)

    pred = AIPrediction(student_id=student.id, prediction_type="RISK_EXPLANATION",
                         prediction=result["explanation"], confidence=risk.risk_score,
                         explanation="used_llm=" + str(result["used_llm"]))
    db.session.add(pred)
    db.session.commit()
    return jsonify(result)


@ai_bp.post("/<student_id>/recommendations")
@require_auth
@require_role("ADMIN", "FACULTY")
def recommendations(student_id):
    student = Student.query.filter_by(student_id=student_id).first()
    if not student:
        return jsonify({"error": "Student not found"}), 404
    risk = _latest_risk_or_400(student)
    if not risk:
        return jsonify({"error": "No risk assessment yet. POST /api/risk/<id>/assess first."}), 400

    import json
    reasons = json.loads(risk.reasons) if risk.reasons else []
    result = generate_recommendations(student.name, risk.risk_level, reasons)

    pred = AIPrediction(student_id=student.id, prediction_type="RECOMMENDATION",
                         prediction=result["recommendations"],
                         explanation="used_llm=" + str(result["used_llm"]))
    db.session.add(pred)
    db.session.commit()
    return jsonify(result)


@ai_bp.post("/<student_id>/chat")
@require_auth
@student_owns_or_staff(_student_id_from_kwargs)
def chat(student_id):
    student = Student.query.filter_by(student_id=student_id).first()
    if not student:
        return jsonify({"error": "Student not found"}), 404
    data = request.get_json(silent=True) or {}
    message = (data.get("message") or "").strip()
    if not message:
        return jsonify({"error": "message is required"}), 400
    history = data.get("history", [])

    context = extract_features(student)
    result = chatbot_reply(student.name, context, message, history)

    pred = AIPrediction(student_id=student.id, prediction_type="CHATBOT_REPLY",
                         prediction=result["reply"],
                         explanation="used_llm=" + str(result["used_llm"]))
    db.session.add(pred)
    db.session.commit()
    return jsonify(result)
