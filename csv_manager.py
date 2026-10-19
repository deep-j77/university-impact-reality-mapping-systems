"""
CSV Data Manager for University Impact System.
Handles reading, writing, atomic updates, thread safety, and backups for:
D:\\university-impact-major-project-updated\\build\\backend\\data\\students.csv
and backup at:
D:\\university-impact-major-project-updated\\build\\backend\\data\\students_backup.csv
"""

import os
import csv
import shutil
import threading
from datetime import datetime

from config import Config, BASE_DIR
from extensions import db
from models import Student, User, Attendance, Marks, Performance, RiskAssessment
from risk_engine import evaluate_triggers, load_thresholds

_csv_lock = threading.Lock()

BACKEND_DATA_DIR = os.path.abspath(os.path.join(BASE_DIR, "data"))
ROOT_DATA_DIR = os.path.abspath(os.path.join(BASE_DIR, "..", "data"))

CSV_FILENAME = "students.csv"
BACKUP_FILENAME = "students_backup.csv"

CSV_PATH = os.path.abspath(os.path.join(BACKEND_DATA_DIR, CSV_FILENAME))
ROOT_CSV_PATH = os.path.abspath(os.path.join(ROOT_DATA_DIR, CSV_FILENAME))
BACKUP_PATH = os.path.abspath(os.path.join(BACKEND_DATA_DIR, BACKUP_FILENAME))

FIELDNAMES = [
    "student_id",
    "name",
    "email",
    "course",
    "branch",
    "year",
    "semester",
    "section",
    "attendance_percentage",
    "internal_marks",
    "midterm_marks",
    "assignment_marks",
    "practical_marks",
    "endterm_marks",
    "total_marks",
    "cgpa",
    "backlogs",
    "assignment_completion",
    "participation",
    "attendance_status",
    "academic_status",
    "risk_status",
    "risk_score",
    "last_updated",
]


def ensure_data_directories():
    os.makedirs(BACKEND_DATA_DIR, exist_ok=True)
    os.makedirs(ROOT_DATA_DIR, exist_ok=True)


def calculate_attendance_status(pct: float) -> str:
    if pct >= 75.0:
        return "Good"
    elif pct >= 60.0:
        return "Warning"
    else:
        return "Critical"


def calculate_academic_status(cgpa: float, backlogs: int) -> str:
    if backlogs > 0:
        return "Backlogs Pending"
    if cgpa >= 7.5:
        return "Good"
    elif cgpa >= 6.0:
        return "Average"
    else:
        return "Needs Attention"


def compute_student_csv_row(student: Student) -> dict:
    thresholds = load_thresholds()
    
    # 1. Attendance metrics
    att_rows = Attendance.query.filter_by(student_id=student.id).all()
    if att_rows:
        att_pct = round(sum(a.attendance_percentage for a in att_rows) / len(att_rows), 1)
    else:
        att_pct = 0.0

    # 2. Marks metrics
    marks_rows = Marks.query.filter_by(student_id=student.id).all()
    if marks_rows:
        n_m = len(marks_rows)
        internal = round(sum(m.internal_marks or 0 for m in marks_rows) / n_m, 1)
        midterm = round(sum(m.midterm_marks or 0 for m in marks_rows) / n_m, 1)
        assignment_m = round(sum(m.assignment_marks or 0 for m in marks_rows) / n_m, 1)
        practical = round(sum(m.practical_marks or 0 for m in marks_rows) / n_m, 1)
        endterm = round(sum(m.final_marks or 0 for m in marks_rows) / n_m, 1)
        total_m = round(sum(m.total_marks or 0 for m in marks_rows) / n_m, 1)
    else:
        internal = 0.0
        midterm = 0.0
        assignment_m = 0.0
        practical = 0.0
        endterm = 0.0
        total_m = 0.0

    # 3. Performance metrics
    perf = Performance.query.filter_by(student_id=student.id).order_by(Performance.id.desc()).first()
    cgpa = perf.cgpa if perf and perf.cgpa is not None else 0.0
    backlogs = perf.backlogs if perf and perf.backlogs is not None else 0

    # 4. Risk Assessment
    risk_row = RiskAssessment.query.filter_by(student_id=student.id).order_by(RiskAssessment.created_at.desc()).first()
    
    if risk_row:
        risk_status = risk_row.risk_level
        risk_score = round(risk_row.risk_score, 3)
    else:
        trig = evaluate_triggers(student, thresholds)
        n_trig = len(trig["triggers"])
        if n_trig == 0:
            risk_status = "LOW"
            risk_score = 0.2
        elif n_trig == 1:
            risk_status = "MEDIUM"
            risk_score = 0.45
        elif n_trig == 2:
            risk_status = "HIGH"
            risk_score = 0.7
        else:
            risk_status = "CRITICAL"
            risk_score = 0.9

    att_status = calculate_attendance_status(att_pct)
    acad_status = calculate_academic_status(cgpa, backlogs)

    branch = student.department or "Computer Science"
    course = "B.Tech"
    year_num = (student.semester + 1) // 2 if student.semester else 1

    return {
        "student_id": student.student_id,
        "name": student.name,
        "email": student.email or (student.user.email if student.user else ""),
        "course": course,
        "branch": branch,
        "year": year_num,
        "semester": student.semester,
        "section": student.section or "A",
        "attendance_percentage": att_pct,
        "internal_marks": internal,
        "midterm_marks": midterm,
        "assignment_marks": assignment_m,
        "practical_marks": practical,
        "endterm_marks": endterm,
        "total_marks": total_m,
        "cgpa": cgpa,
        "backlogs": backlogs,
        "assignment_completion": 85.0 if att_pct >= 75 else 60.0,
        "participation": "Good" if att_pct >= 75 else "Average",
        "attendance_status": att_status,
        "academic_status": acad_status,
        "risk_status": risk_status,
        "risk_score": risk_score,
        "last_updated": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    }


def sync_db_to_csv():
    """
    Reads all student records from DB, computes calculated metrics and risk scores,
    makes a backup, and updates backend/data/students.csv atomically and thread-safely.
    Logs: CSV SAVED: <absolute_path>
    """
    with _csv_lock:
        ensure_data_directories()
        
        # Create backup if file exists
        if os.path.exists(CSV_PATH):
            try:
                shutil.copy2(CSV_PATH, BACKUP_PATH)
            except OSError as err:
                print(f"[CSV BACKUP WARNING] Could not write backup: {err}")

        students = Student.query.order_by(Student.student_id).all()
        rows = [compute_student_csv_row(s) for s in students]

        # Write atomically using a temporary file
        temp_path = CSV_PATH + ".tmp"
        with open(temp_path, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=FIELDNAMES)
            writer.writeheader()
            writer.writerows(rows)

        os.replace(temp_path, CSV_PATH)

        # Copy to root data directory for compatibility
        try:
            shutil.copy2(CSV_PATH, ROOT_CSV_PATH)
        except OSError:
            pass

        print(f"CSV SAVED: {CSV_PATH}", flush=True)
        return rows


def read_students_csv() -> list:
    """Reads all rows from backend/data/students.csv in a thread-safe manner."""
    with _csv_lock:
        ensure_data_directories()
        if not os.path.exists(CSV_PATH):
            # Unlock temporarily or release lock when calling sync
            pass

    if not os.path.exists(CSV_PATH):
        sync_db_to_csv()

    with _csv_lock:
        rows = []
        with open(CSV_PATH, "r", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row in reader:
                rows.append(row)
        return rows
