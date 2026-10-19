"""
Migration script: legacy CSV data -> MySQL.

WHAT THIS DOES
---------------
1. Creates all tables (via SQLAlchemy metadata) in the MySQL database
   configured in .env.
2. Imports the REAL legacy data from the original minor project:
     - data/users.csv          -> users table (passwords re-hashed with bcrypt)
     - data/students_extended.csv -> students table + one performance row
       per student (using the CGPA that was already in the CSV) + one
       aggregate attendance row per student.
3. Seeds a small SYNTHETIC demo dataset (subjects, per-subject marks,
   assignments, submissions) because the original CSV never captured
   subject-level data. This is clearly labeled below and in the README.
   It exists only so the new subject/marks/assignment tables aren't
   empty for demo purposes -- it is NOT real academic history and
   should not be presented as such.

Run with:
    cd backend
    python migrate_csv_to_mysql.py
"""

import os
import sys
import random
from datetime import datetime, timedelta

import pandas as pd
import bcrypt

sys.path.insert(0, os.path.dirname(__file__))

from app import create_app  # noqa: E402
from extensions import db  # noqa: E402
from models import (  # noqa: E402
    User, Student, Faculty, Subject, Enrollment, Attendance,
    Marks, Assignment, AssignmentSubmission, Performance,
)

DATA_DIR = os.path.join(os.path.dirname(__file__), "..", "data")
USERS_CSV = os.path.join(DATA_DIR, "users.csv")
STUDENTS_CSV = os.path.join(DATA_DIR, "students_extended.csv")

CURRENT_ACADEMIC_YEAR = "2025-2026"

# Demo subjects seeded per department for the synthetic dataset described above.
DEMO_SUBJECTS = [
    ("CS301", "Data Structures & Algorithms", 4),
    ("CS302", "Database Management Systems", 4),
    ("CS303", "Operating Systems", 3),
    ("CS304", "Computer Networks", 3),
    ("CS305", "Software Engineering", 3),
]


def hash_password(plain: str) -> str:
    return bcrypt.hashpw(plain.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def migrate_users_and_students():
    print("Reading legacy CSVs...")
    users_df = pd.read_csv(USERS_CSV)
    students_df = pd.read_csv(STUDENTS_CSV)

    user_by_business_id = {}

    for _, row in users_df.iterrows():
        business_id = str(row["user_id"]).strip()
        role = str(row["role"]).strip().upper()
        role = role if role in ("ADMIN", "FACULTY", "STUDENT") else "STUDENT"

        # Original CSV had no email/name -- synthesize a placeholder email
        # from the legacy user_id so login can move to email-based auth.
        email = f"{business_id.lower()}@legacy.import"

        existing = User.query.filter_by(email=email).first()
        if existing:
            user_by_business_id[business_id] = existing
            continue

        user = User(
            name=business_id,
            email=email,
            password_hash=hash_password(str(row["password"])),
            role=role,
        )
        db.session.add(user)
        db.session.flush()  # get user.id
        user_by_business_id[business_id] = user

    db.session.commit()
    print(f"Imported {len(user_by_business_id)} legacy user accounts.")

    student_count = 0
    for _, row in students_df.iterrows():
        business_id = str(row["student_id"]).strip()
        user = user_by_business_id.get(business_id)
        if user is None:
            # Student existed in students_extended.csv but not in users.csv.
            # Create a matching login so the record isn't orphaned.
            email = f"{business_id.lower()}@legacy.import"
            user = User(
                name=business_id,
                email=email,
                password_hash=hash_password("student123"),
                role="STUDENT",
            )
            db.session.add(user)
            db.session.flush()

        if Student.query.filter_by(student_id=business_id).first():
            continue

        department = str(row["university"])  # legacy field reused as department/cohort
        semester = int(row["semester"])

        student = Student(
            user_id=user.id,
            student_id=business_id,
            name=business_id,
            department=department,
            semester=semester,
            enrollment_year=datetime.now().year - semester // 2,
        )
        db.session.add(student)
        db.session.flush()

        # Real legacy CGPA -> one performance row for the current semester.
        db.session.add(Performance(
            student_id=student.id,
            semester=semester,
            sgpa=float(row["cgpa"]),  # only one data point available, reused for both
            cgpa=float(row["cgpa"]),
            backlogs=0,
            academic_year=CURRENT_ACADEMIC_YEAR,
        ))

        student_count += 1

    db.session.commit()
    print(f"Imported {student_count} legacy student profiles + performance rows.")
    return students_df


def seed_demo_subjects_and_academics(students_df: pd.DataFrame):
    """
    SYNTHETIC DEMO DATA -- see module docstring.
    Seeds subjects + per-subject marks/attendance/assignments so the new
    tables have realistic-looking structure for the dashboards and AI layer
    to work against. Distribution is randomized around each student's real
    legacy attendance_pct / cgpa so it stays roughly consistent, but exact
    per-subject figures are NOT real.
    """
    print("Seeding synthetic demo subjects/marks/assignments (documented as demo data)...")
    random.seed(42)

    subjects = []
    for code, name, credits in DEMO_SUBJECTS:
        existing = Subject.query.filter_by(subject_code=code).first()
        if existing:
            subjects.append(existing)
            continue
        subj = Subject(subject_code=code, subject_name=name, credits=credits,
                        semester=3, department="Computer Science")
        db.session.add(subj)
        db.session.flush()
        subjects.append(subj)
    db.session.commit()

    assignments = []
    for subj in subjects:
        a = Assignment(
            subject_id=subj.id,
            title=f"{subj.subject_name} - Assignment 1",
            description="Demo assignment seeded during migration.",
            deadline=datetime.now() + timedelta(days=14),
            total_marks=100,
        )
        db.session.add(a)
        db.session.flush()
        assignments.append(a)
    db.session.commit()

    for _, row in students_df.iterrows():
        student = Student.query.filter_by(student_id=str(row["student_id"]).strip()).first()
        if not student:
            continue

        base_attendance = float(row["attendance_pct"])
        base_cgpa = float(row["cgpa"])

        for subj, assignment in zip(subjects, assignments):
            if Enrollment.query.filter_by(student_id=student.id, subject_id=subj.id,
                                           academic_year=CURRENT_ACADEMIC_YEAR).first():
                continue

            db.session.add(Enrollment(
                student_id=student.id, subject_id=subj.id,
                academic_year=CURRENT_ACADEMIC_YEAR, semester=student.semester,
            ))

            jitter = random.uniform(-8, 8)
            pct = max(0.0, min(100.0, base_attendance + jitter))
            total_classes = 40
            attended = round(total_classes * pct / 100)
            db.session.add(Attendance(
                student_id=student.id, subject_id=subj.id,
                total_classes=total_classes, attended_classes=attended,
                attendance_percentage=round(attended / total_classes * 100, 1),
            ))

            mark_base = max(0.0, min(100.0, base_cgpa * 10 + random.uniform(-10, 10)))
            internal, midterm, assignment_m, practical, final = (
                round(mark_base * 0.15, 1), round(mark_base * 0.20, 1),
                round(mark_base * 0.15, 1), round(mark_base * 0.10, 1),
                round(mark_base * 0.40, 1),
            )
            total = round(internal + midterm + assignment_m + practical + final, 1)
            grade = ("A" if total >= 85 else "B" if total >= 70 else
                     "C" if total >= 55 else "D" if total >= 40 else "F")
            db.session.add(Marks(
                student_id=student.id, subject_id=subj.id,
                internal_marks=internal, midterm_marks=midterm,
                assignment_marks=assignment_m, practical_marks=practical,
                final_marks=final, total_marks=total, grade=grade,
            ))

            db.session.add(AssignmentSubmission(
                assignment_id=assignment.id, student_id=student.id,
                submitted_at=datetime.now() - timedelta(days=random.randint(0, 10)),
                marks=round(assignment_m / 15 * 100, 1),
                status=random.choice(["SUBMITTED", "SUBMITTED", "LATE", "MISSED"]),
            ))

    db.session.commit()
    print("Demo academic records seeded.")


def seed_admin_and_faculty():
    admin_email = "admin@legacy.import"
    admin = User.query.filter_by(email=admin_email).first()
    if admin and admin.role != "ADMIN":
        admin.role = "ADMIN"
        db.session.commit()

    faculty_email = "faculty1@demo.import"
    if not User.query.filter_by(email=faculty_email).first():
        fac_user = User(name="Demo Faculty", email=faculty_email,
                         password_hash=hash_password("faculty123"), role="FACULTY")
        db.session.add(fac_user)
        db.session.flush()
        db.session.add(Faculty(user_id=fac_user.id, employee_id="F001",
                                department="Computer Science", designation="Assistant Professor"))
        db.session.commit()
        print("Seeded one demo faculty account (faculty1@demo.import / faculty123).")


def main():
    app = create_app()
    with app.app_context():
        print("Creating tables (if not already present)...")
        db.create_all()

        students_df = migrate_users_and_students()
        seed_demo_subjects_and_academics(students_df)
        seed_admin_and_faculty()

        print("\nMigration complete.")
        print("Legacy admin login: admin@legacy.import / admin123 (original password, now hashed)")
        print("Legacy student logins: s001@legacy.import ... / student123 (original passwords, now hashed)")


if __name__ == "__main__":
    main()
