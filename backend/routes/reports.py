import json

from flask import Blueprint, jsonify, send_file, request

from extensions import db
from models import Student, Report, RiskAssessment, AIPrediction
from auth import require_auth, student_owns_or_staff
from reports_gen.pdf_report import build_student_report

reports_bp = Blueprint("reports", __name__)


def _student_id_from_kwargs(**kwargs):
    return kwargs.get("student_id")


@reports_bp.get("/<student_id>")
@require_auth
@student_owns_or_staff(_student_id_from_kwargs)
def download_report(student_id):
    student = Student.query.filter_by(student_id=student_id).first()
    if not student:
        return jsonify({"error": "Student not found"}), 404

    ai_explanation = None
    if request.args.get("include_ai") == "1":
        latest_pred = (AIPrediction.query
                       .filter_by(student_id=student.id, prediction_type="RISK_EXPLANATION")
                       .order_by(AIPrediction.created_at.desc()).first())
        if latest_pred:
            ai_explanation = latest_pred.prediction

    path = build_student_report(student, ai_explanation=ai_explanation)

    record = Report(student_id=student.id, report_type="FULL", file_path=path)
    db.session.add(record)
    db.session.commit()

    return send_file(path, as_attachment=True,
                      download_name=f"{student.student_id}_report.pdf",
                      mimetype="application/pdf")
