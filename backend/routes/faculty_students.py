"""
Phase: Faculty Student Data Management Blueprint.
Provides REST API endpoints for Faculty/Admin to manage student academic records,
attendance, marks, backlogs, and trigger automatic CSV persistence and Risk Engine updates.
"""
from datetime import datetime
from flask import Blueprint, request, jsonify, g

from extensions import db
from models import Student, User, Attendance, Marks, Performance, Subject, Enrollment, RiskAssessment
from auth import require_auth, require_role, hash_password
from config import Config
from risk_engine import evaluate_triggers
from ml.risk_model import predict_risk
from csv_manager import sync_db_to_csv, compute_student_csv_row, CSV_PATH

faculty_students_bp = Blueprint("faculty_students", __name__)


def _validate_student_payload(data: dict, is_update=False):
    errors = []
    if not is_update:
        if not data.get("student_id") or not str(data["student_id"]).strip():
            errors.append("Student ID is required.")
        if not data.get("name") or not str(data["name"]).strip():
            errors.append("Name is required.")
        if not data.get("email") or not str(data["email"]).strip():
            errors.append("Email is required.")

    if "email" in data and "@" not in str(data.get("email", "")):
        errors.append("Invalid email format.")

    if "attendance_percentage" in data:
        try:
            att = float(data["attendance_percentage"])
            if not (0 <= att <= 100):
                errors.append("Attendance percentage must be between 0 and 100.")
        except (ValueError, TypeError):
            errors.append("Attendance percentage must be a valid number.")

    if "cgpa" in data:
        try:
            cgpa = float(data["cgpa"])
            if not (0 <= cgpa <= 10.0):
                errors.append("CGPA must be between 0.0 and 10.0.")
        except (ValueError, TypeError):
            errors.append("CGPA must be a valid number.")

    if "backlogs" in data:
        try:
            backlogs = int(data["backlogs"])
            if backlogs < 0:
                errors.append("Backlogs cannot be negative.")
        except (ValueError, TypeError):
            errors.append("Backlogs must be an integer.")

    mark_fields = ["internal_marks", "midterm_marks", "assignment_marks", "practical_marks", "endterm_marks"]
    for mf in mark_fields:
        if mf in data and data[mf] is not None:
            try:
                val = float(data[mf])
                if val < 0:
                    errors.append(f"{mf.replace('_', ' ').title()} cannot be negative.")
            except (ValueError, TypeError):
                errors.append(f"{mf.replace('_', ' ').title()} must be a valid number.")

    return errors


def _update_or_create_academics(student: Student, data: dict):
    """Updates Attendance, Marks, Performance, and Risk Assessment for a student."""
    subj = Subject.query.first()
    if not subj:
        subj = Subject(
            subject_code="CORE101",
            subject_name="Core Academic Module",
            credits=4,
            semester=student.semester or 1,
            department=student.department or "Computer Science",
        )
        db.session.add(subj)
        db.session.flush()

    # Attendance
    att_row = Attendance.query.filter_by(student_id=student.id).first()
    att_pct = float(data.get("attendance_percentage", att_row.attendance_percentage if att_row else 80.0))
    total_classes = 40
    attended_classes = int(round(total_classes * att_pct / 100.0))
    if att_row:
        att_row.total_classes = total_classes
        att_row.attended_classes = attended_classes
        att_row.attendance_percentage = att_pct
    else:
        db.session.add(Attendance(
            student_id=student.id,
            subject_id=subj.id,
            total_classes=total_classes,
            attended_classes=attended_classes,
            attendance_percentage=att_pct,
        ))

    # Marks
    marks_row = Marks.query.filter_by(student_id=student.id).first()
    internal = float(data.get("internal_marks", marks_row.internal_marks if marks_row else 15.0))
    midterm = float(data.get("midterm_marks", marks_row.midterm_marks if marks_row else 20.0))
    assignment_m = float(data.get("assignment_marks", marks_row.assignment_marks if marks_row else 15.0))
    practical = float(data.get("practical_marks", marks_row.practical_marks if marks_row else 10.0))
    endterm = float(data.get("endterm_marks", marks_row.final_marks if marks_row else 35.0))
    total = round(internal + midterm + assignment_m + practical + endterm, 1)

    grade = "A" if total >= 85 else "B" if total >= 70 else "C" if total >= 55 else "D" if total >= 40 else "F"

    if marks_row:
        marks_row.internal_marks = internal
        marks_row.midterm_marks = midterm
        marks_row.assignment_marks = assignment_m
        marks_row.practical_marks = practical
        marks_row.final_marks = endterm
        marks_row.total_marks = total
        marks_row.grade = grade
    else:
        db.session.add(Marks(
            student_id=student.id,
            subject_id=subj.id,
            internal_marks=internal,
            midterm_marks=midterm,
            assignment_marks=assignment_m,
            practical_marks=practical,
            final_marks=endterm,
            total_marks=total,
            grade=grade,
        ))

    # Performance
    perf_row = Performance.query.filter_by(student_id=student.id).order_by(Performance.id.desc()).first()
    cgpa = float(data.get("cgpa", perf_row.cgpa if perf_row else 7.5))
    backlogs = int(data.get("backlogs", perf_row.backlogs if perf_row else 0))

    if perf_row:
        perf_row.cgpa = cgpa
        perf_row.sgpa = cgpa
        perf_row.backlogs = backlogs
    else:
        db.session.add(Performance(
            student_id=student.id,
            semester=student.semester or 1,
            sgpa=cgpa,
            cgpa=cgpa,
            backlogs=backlogs,
            academic_year="2025-2026",
        ))

    db.session.flush()

    # Risk Assessment calculation
    risk_result = predict_risk(student, Config.ML_MODEL_PATH)
    import json
    new_risk = RiskAssessment(
        student_id=student.id,
        risk_score=risk_result["risk_score"],
        risk_level=risk_result["risk_level"],
        reasons=json.dumps(risk_result["reasons"]),
        recommendations=json.dumps(risk_result["recommendations"]),
    )
    db.session.add(new_risk)
    db.session.commit()


@faculty_students_bp.get("")
@require_auth
@require_role("FACULTY", "ADMIN")
def get_all_faculty_students():
    """Return all students enriched with CSV metrics & risk statuses."""
    try:
        sync_db_to_csv()
    except Exception as e:
        return jsonify({"success": False, "message": f"CSV sync failed: {str(e)}"}), 500

    students = Student.query.order_by(Student.student_id).all()
    rows = [compute_student_csv_row(s) for s in students]
    return jsonify({"success": True, "students": rows, "csv_path": CSV_PATH})


@faculty_students_bp.get("/<student_id>")
@require_auth
@require_role("FACULTY", "ADMIN")
def get_single_faculty_student(student_id):
    student = Student.query.filter_by(student_id=student_id.strip()).first()
    if not student:
        return jsonify({"success": False, "message": "Student not found"}), 404
    
    row = compute_student_csv_row(student)
    return jsonify({"success": True, "student": row, "csv_path": CSV_PATH})


@faculty_students_bp.post("")
@require_auth
@require_role("FACULTY", "ADMIN")
def add_faculty_student():
    data = request.get_json(silent=True) or {}
    errors = _validate_student_payload(data, is_update=False)
    if errors:
        return jsonify({"success": False, "message": " / ".join(errors)}), 400

    std_id = data["student_id"].strip().upper()
    email = data["email"].strip().lower()

    if Student.query.filter_by(student_id=std_id).first():
        return jsonify({"success": False, "message": "Student ID already exists"}), 409
    if User.query.filter_by(email=email).first():
        return jsonify({"success": False, "message": "Email already registered"}), 409

    try:
        # Create User account
        password = data.get("password") or "student123"
        user = User(
            name=data["name"].strip(),
            email=email,
            password_hash=hash_password(password),
            role="STUDENT",
        )
        db.session.add(user)
        db.session.flush()

        dept = data.get("branch") or data.get("department") or "Computer Science"
        sem = int(data.get("semester") or 1)
        sec = data.get("section") or "A"
        enroll_year = datetime.now().year - (sem // 2)

        student = Student(
            user_id=user.id,
            student_id=std_id,
            name=data["name"].strip(),
            department=dept,
            semester=sem,
            section=sec,
            enrollment_year=enroll_year,
            email=email,
        )
        db.session.add(student)
        db.session.flush()

        _update_or_create_academics(student, data)

        # Auto update CSV file
        sync_db_to_csv()
        updated_row = compute_student_csv_row(student)

        return jsonify({
            "success": True,
            "message": "Student added successfully.",
            "student": updated_row,
            "csv_path": CSV_PATH,
        }), 201
    except Exception as e:
        db.session.rollback()
        return jsonify({"success": False, "message": f"Failed to add student / save CSV: {str(e)}"}), 500


@faculty_students_bp.put("/<student_id>")
@require_auth
@require_role("FACULTY", "ADMIN")
def update_faculty_student(student_id):
    student = Student.query.filter_by(student_id=student_id.strip()).first()
    if not student:
        return jsonify({"success": False, "message": "Student not found"}), 404

    data = request.get_json(silent=True) or {}
    errors = _validate_student_payload(data, is_update=True)
    if errors:
        return jsonify({"success": False, "message": " / ".join(errors)}), 400

    try:
        if "name" in data:
            student.name = data["name"].strip()
            if student.user:
                student.user.name = data["name"].strip()

        if "email" in data:
            new_email = data["email"].strip().lower()
            existing_user = User.query.filter(User.email == new_email, User.id != student.user_id).first()
            if existing_user:
                return jsonify({"success": False, "message": "Email address already in use by another user"}), 409
            student.email = new_email
            if student.user:
                student.user.email = new_email

        if "branch" in data or "department" in data:
            student.department = (data.get("branch") or data.get("department")).strip()

        if "semester" in data:
            student.semester = int(data["semester"])

        if "section" in data:
            student.section = str(data["section"]).strip()

        _update_or_create_academics(student, data)

        # Save to database and auto sync CSV
        sync_db_to_csv()
        updated_row = compute_student_csv_row(student)

        return jsonify({
            "success": True,
            "message": "Student data updated successfully.",
            "student": updated_row,
            "csv_path": CSV_PATH,
        })
    except Exception as e:
        db.session.rollback()
        return jsonify({"success": False, "message": f"Failed to update student / save CSV: {str(e)}"}), 500


@faculty_students_bp.delete("/<student_id>")
@require_auth
@require_role("FACULTY", "ADMIN")
def delete_faculty_student(student_id):
    student = Student.query.filter_by(student_id=student_id.strip()).first()
    if not student:
        return jsonify({"success": False, "message": "Student not found"}), 404

    try:
        user = student.user
        db.session.delete(student)
        if user:
            db.session.delete(user)
        db.session.commit()

        # Sync CSV after removal
        sync_db_to_csv()

        return jsonify({
            "success": True,
            "message": "Student deleted successfully.",
            "deleted_student_id": student_id,
            "csv_path": CSV_PATH,
        })
    except Exception as e:
        db.session.rollback()
        return jsonify({"success": False, "message": f"Failed to delete student / sync CSV: {str(e)}"}), 500
