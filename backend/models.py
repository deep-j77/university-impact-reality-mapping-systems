from datetime import datetime, date
from extensions import db


# ============================================================
# USERS / AUTH
# ============================================================
class User(db.Model):
    __tablename__ = "users"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(120), nullable=False)
    email = db.Column(db.String(150), unique=True, nullable=False, index=True)
    password_hash = db.Column(db.String(255), nullable=False)
    role = db.Column(db.Enum("ADMIN", "FACULTY", "STUDENT", name="user_role"), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    student_profile = db.relationship("Student", backref="user", uselist=False, cascade="all, delete-orphan")
    faculty_profile = db.relationship("Faculty", backref="user", uselist=False, cascade="all, delete-orphan")

    def to_dict(self, include_role_profile=False):
        data = {
            "id": self.id,
            "name": self.name,
            "email": self.email,
            "role": self.role,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }
        if include_role_profile:
            if self.role == "STUDENT" and self.student_profile:
                data["profile"] = self.student_profile.to_dict()
            elif self.role == "FACULTY" and self.faculty_profile:
                data["profile"] = self.faculty_profile.to_dict()
        return data


# ============================================================
# STUDENTS
# ============================================================
class Student(db.Model):
    __tablename__ = "students"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id", ondelete="CASCADE"), nullable=False, unique=True)
    student_id = db.Column(db.String(20), unique=True, nullable=False, index=True)  # business key e.g. S001
    name = db.Column(db.String(120), nullable=False)
    department = db.Column(db.String(100), nullable=False, index=True)
    semester = db.Column(db.Integer, nullable=False)
    section = db.Column(db.String(10))
    enrollment_year = db.Column(db.Integer)
    phone = db.Column(db.String(20))
    email = db.Column(db.String(150))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    enrollments = db.relationship("Enrollment", backref="student", cascade="all, delete-orphan")
    attendance_records = db.relationship("Attendance", backref="student", cascade="all, delete-orphan")
    marks_records = db.relationship("Marks", backref="student", cascade="all, delete-orphan")
    submissions = db.relationship("AssignmentSubmission", backref="student", cascade="all, delete-orphan")
    performance_records = db.relationship("Performance", backref="student", cascade="all, delete-orphan")
    risk_assessments = db.relationship("RiskAssessment", backref="student", cascade="all, delete-orphan")
    ai_predictions = db.relationship("AIPrediction", backref="student", cascade="all, delete-orphan")
    reports = db.relationship("Report", backref="student", cascade="all, delete-orphan")

    def to_dict(self):
        return {
            "id": self.id,
            "student_id": self.student_id,
            "name": self.name,
            "department": self.department,
            "semester": self.semester,
            "section": self.section,
            "enrollment_year": self.enrollment_year,
            "phone": self.phone,
            "email": self.email,
        }


# ============================================================
# FACULTY
# ============================================================
class Faculty(db.Model):
    __tablename__ = "faculty"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id", ondelete="CASCADE"), nullable=False, unique=True)
    employee_id = db.Column(db.String(20), unique=True, nullable=False, index=True)
    department = db.Column(db.String(100), nullable=False, index=True)
    designation = db.Column(db.String(100))

    def to_dict(self):
        return {
            "id": self.id,
            "employee_id": self.employee_id,
            "department": self.department,
            "designation": self.designation,
        }


# ============================================================
# SUBJECTS
# ============================================================
class Subject(db.Model):
    __tablename__ = "subjects"

    id = db.Column(db.Integer, primary_key=True)
    subject_code = db.Column(db.String(20), unique=True, nullable=False, index=True)
    subject_name = db.Column(db.String(150), nullable=False)
    credits = db.Column(db.Integer, nullable=False, default=3)
    semester = db.Column(db.Integer, nullable=False)
    department = db.Column(db.String(100), nullable=False, index=True)

    enrollments = db.relationship("Enrollment", backref="subject", cascade="all, delete-orphan")
    attendance_records = db.relationship("Attendance", backref="subject", cascade="all, delete-orphan")
    marks_records = db.relationship("Marks", backref="subject", cascade="all, delete-orphan")
    assignments = db.relationship("Assignment", backref="subject", cascade="all, delete-orphan")

    def to_dict(self):
        return {
            "id": self.id,
            "subject_code": self.subject_code,
            "subject_name": self.subject_name,
            "credits": self.credits,
            "semester": self.semester,
            "department": self.department,
        }


# ============================================================
# ENROLLMENTS
# ============================================================
class Enrollment(db.Model):
    __tablename__ = "enrollments"
    __table_args__ = (
        db.UniqueConstraint("student_id", "subject_id", "academic_year", "semester", name="uq_enrollment"),
    )

    id = db.Column(db.Integer, primary_key=True)
    student_id = db.Column(db.Integer, db.ForeignKey("students.id", ondelete="CASCADE"), nullable=False)
    subject_id = db.Column(db.Integer, db.ForeignKey("subjects.id", ondelete="CASCADE"), nullable=False)
    academic_year = db.Column(db.String(9), nullable=False)  # e.g. "2025-2026"
    semester = db.Column(db.Integer, nullable=False)


# ============================================================
# ATTENDANCE
# ============================================================
class Attendance(db.Model):
    __tablename__ = "attendance"
    __table_args__ = (
        db.CheckConstraint("attended_classes <= total_classes", name="chk_attended_le_total"),
    )

    id = db.Column(db.Integer, primary_key=True)
    student_id = db.Column(db.Integer, db.ForeignKey("students.id", ondelete="CASCADE"), nullable=False, index=True)
    subject_id = db.Column(db.Integer, db.ForeignKey("subjects.id", ondelete="CASCADE"), nullable=False, index=True)
    total_classes = db.Column(db.Integer, nullable=False, default=0)
    attended_classes = db.Column(db.Integer, nullable=False, default=0)
    attendance_percentage = db.Column(db.Float, nullable=False, default=0.0)
    date = db.Column(db.Date, default=date.today)

    def to_dict(self):
        return {
            "id": self.id,
            "subject_id": self.subject_id,
            "total_classes": self.total_classes,
            "attended_classes": self.attended_classes,
            "attendance_percentage": self.attendance_percentage,
            "date": self.date.isoformat() if self.date else None,
        }


# ============================================================
# MARKS
# ============================================================
class Marks(db.Model):
    __tablename__ = "marks"

    id = db.Column(db.Integer, primary_key=True)
    student_id = db.Column(db.Integer, db.ForeignKey("students.id", ondelete="CASCADE"), nullable=False, index=True)
    subject_id = db.Column(db.Integer, db.ForeignKey("subjects.id", ondelete="CASCADE"), nullable=False, index=True)
    internal_marks = db.Column(db.Float, default=0)
    midterm_marks = db.Column(db.Float, default=0)
    assignment_marks = db.Column(db.Float, default=0)
    practical_marks = db.Column(db.Float, default=0)
    final_marks = db.Column(db.Float, default=0)
    total_marks = db.Column(db.Float, default=0)
    grade = db.Column(db.String(2))

    def to_dict(self):
        return {
            "id": self.id,
            "subject_id": self.subject_id,
            "internal_marks": self.internal_marks,
            "midterm_marks": self.midterm_marks,
            "assignment_marks": self.assignment_marks,
            "practical_marks": self.practical_marks,
            "final_marks": self.final_marks,
            "total_marks": self.total_marks,
            "grade": self.grade,
        }


# ============================================================
# ASSIGNMENTS
# ============================================================
class Assignment(db.Model):
    __tablename__ = "assignments"

    id = db.Column(db.Integer, primary_key=True)
    subject_id = db.Column(db.Integer, db.ForeignKey("subjects.id", ondelete="CASCADE"), nullable=False, index=True)
    title = db.Column(db.String(200), nullable=False)
    description = db.Column(db.Text)
    deadline = db.Column(db.DateTime)
    total_marks = db.Column(db.Float, default=100)

    submissions = db.relationship("AssignmentSubmission", backref="assignment", cascade="all, delete-orphan")


# ============================================================
# ASSIGNMENT SUBMISSIONS
# ============================================================
class AssignmentSubmission(db.Model):
    __tablename__ = "assignment_submissions"
    __table_args__ = (
        db.UniqueConstraint("assignment_id", "student_id", name="uq_submission"),
    )

    id = db.Column(db.Integer, primary_key=True)
    assignment_id = db.Column(db.Integer, db.ForeignKey("assignments.id", ondelete="CASCADE"), nullable=False)
    student_id = db.Column(db.Integer, db.ForeignKey("students.id", ondelete="CASCADE"), nullable=False, index=True)
    submitted_at = db.Column(db.DateTime)
    marks = db.Column(db.Float)
    status = db.Column(db.Enum("PENDING", "SUBMITTED", "LATE", "MISSED", name="submission_status"),
                        default="PENDING")


# ============================================================
# PERFORMANCE
# ============================================================
class Performance(db.Model):
    __tablename__ = "performance"
    __table_args__ = (
        db.UniqueConstraint("student_id", "semester", "academic_year", name="uq_performance"),
    )

    id = db.Column(db.Integer, primary_key=True)
    student_id = db.Column(db.Integer, db.ForeignKey("students.id", ondelete="CASCADE"), nullable=False, index=True)
    semester = db.Column(db.Integer, nullable=False)
    sgpa = db.Column(db.Float)
    cgpa = db.Column(db.Float)
    backlogs = db.Column(db.Integer, default=0)
    academic_year = db.Column(db.String(9))

    def to_dict(self):
        return {
            "id": self.id,
            "semester": self.semester,
            "sgpa": self.sgpa,
            "cgpa": self.cgpa,
            "backlogs": self.backlogs,
            "academic_year": self.academic_year,
        }


# ============================================================
# RISK ASSESSMENTS (ML output)
# ============================================================
class RiskAssessment(db.Model):
    __tablename__ = "risk_assessments"

    id = db.Column(db.Integer, primary_key=True)
    student_id = db.Column(db.Integer, db.ForeignKey("students.id", ondelete="CASCADE"), nullable=False, index=True)
    risk_score = db.Column(db.Float, nullable=False)
    risk_level = db.Column(db.Enum("LOW", "MEDIUM", "HIGH", "CRITICAL", name="risk_level"), nullable=False)
    reasons = db.Column(db.Text)  # JSON-encoded list of reason strings
    recommendations = db.Column(db.Text)  # JSON-encoded list of recommendation strings
    created_at = db.Column(db.DateTime, default=datetime.utcnow, index=True)

    def to_dict(self):
        import json
        return {
            "id": self.id,
            "risk_score": self.risk_score,
            "risk_level": self.risk_level,
            "reasons": json.loads(self.reasons) if self.reasons else [],
            "recommendations": json.loads(self.recommendations) if self.recommendations else [],
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }


# ============================================================
# AI PREDICTIONS (generative AI output: explanations, chatbot, study plans)
# ============================================================
class AIPrediction(db.Model):
    __tablename__ = "ai_predictions"

    id = db.Column(db.Integer, primary_key=True)
    student_id = db.Column(db.Integer, db.ForeignKey("students.id", ondelete="CASCADE"), nullable=False, index=True)
    prediction_type = db.Column(db.String(50), nullable=False)  # e.g. CGPA_FORECAST, DROPOUT_WARNING, CHATBOT_REPLY
    prediction = db.Column(db.Text)
    confidence = db.Column(db.Float)
    explanation = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, index=True)


# ============================================================
# REPORTS
# ============================================================
class Report(db.Model):
    __tablename__ = "reports"

    id = db.Column(db.Integer, primary_key=True)
    student_id = db.Column(db.Integer, db.ForeignKey("students.id", ondelete="CASCADE"), nullable=False, index=True)
    report_type = db.Column(db.String(50), default="FULL")
    file_path = db.Column(db.String(255))
    generated_at = db.Column(db.DateTime, default=datetime.utcnow)
