from datetime import datetime

from flask import Blueprint, request, jsonify, g

from extensions import db
from models import Assignment, AssignmentSubmission, Student, Subject
from auth import require_auth, require_role

assignments_bp = Blueprint("assignments", __name__)


@assignments_bp.get("")
@require_auth
def list_assignments():
    subject_id = request.args.get("subject_id")
    q = Assignment.query
    if subject_id:
        q = q.filter_by(subject_id=int(subject_id))
    rows = q.order_by(Assignment.deadline).all()
    return jsonify([{
        "id": a.id, "subject_id": a.subject_id, "title": a.title,
        "description": a.description,
        "deadline": a.deadline.isoformat() if a.deadline else None,
        "total_marks": a.total_marks,
    } for a in rows])


@assignments_bp.post("")
@require_auth
@require_role("ADMIN", "FACULTY")
def create_assignment():
    data = request.get_json(silent=True) or {}
    if not data.get("subject_id") or not data.get("title"):
        return jsonify({"error": "subject_id and title are required"}), 400
    if not Subject.query.get(int(data["subject_id"])):
        return jsonify({"error": "Subject not found"}), 404

    deadline = None
    if data.get("deadline"):
        deadline = datetime.fromisoformat(data["deadline"])

    a = Assignment(subject_id=int(data["subject_id"]), title=data["title"],
                    description=data.get("description", ""), deadline=deadline,
                    total_marks=data.get("total_marks", 100))
    db.session.add(a)
    db.session.commit()
    return jsonify({"id": a.id, "title": a.title}), 201


@assignments_bp.get("/<int:assignment_id>/submissions")
@require_auth
@require_role("ADMIN", "FACULTY")
def list_submissions(assignment_id):
    rows = AssignmentSubmission.query.filter_by(assignment_id=assignment_id).all()
    out = []
    for s in rows:
        out.append({
            "id": s.id, "student_id": s.student.student_id,
            "submitted_at": s.submitted_at.isoformat() if s.submitted_at else None,
            "marks": s.marks, "status": s.status,
        })
    return jsonify(out)


@assignments_bp.post("/<int:assignment_id>/submit/<student_id>")
@require_auth
def submit_assignment(assignment_id, student_id):
    student = Student.query.filter_by(student_id=student_id).first()
    if not student:
        return jsonify({"error": "Student not found"}), 404
    if g.role == "STUDENT" and (not g.current_user.student_profile
                                 or g.current_user.student_profile.student_id != student_id):
        return jsonify({"error": "Forbidden: not your record"}), 403

    assignment = Assignment.query.get(assignment_id)
    if not assignment:
        return jsonify({"error": "Assignment not found"}), 404

    now = datetime.now()
    status = "SUBMITTED"
    if assignment.deadline and now > assignment.deadline:
        status = "LATE"

    existing = AssignmentSubmission.query.filter_by(
        assignment_id=assignment_id, student_id=student.id).first()
    if existing:
        existing.submitted_at = now
        existing.status = status
    else:
        existing = AssignmentSubmission(assignment_id=assignment_id, student_id=student.id,
                                         submitted_at=now, status=status)
        db.session.add(existing)
    db.session.commit()
    return jsonify({"status": existing.status, "submitted_at": existing.submitted_at.isoformat()})


@assignments_bp.put("/submission/<int:submission_id>/grade")
@require_auth
@require_role("ADMIN", "FACULTY")
def grade_submission(submission_id):
    sub = AssignmentSubmission.query.get(submission_id)
    if not sub:
        return jsonify({"error": "Submission not found"}), 404
    data = request.get_json(silent=True) or {}
    if "marks" not in data:
        return jsonify({"error": "marks is required"}), 400
    sub.marks = float(data["marks"])
    db.session.commit()
    return jsonify({"id": sub.id, "marks": sub.marks})
