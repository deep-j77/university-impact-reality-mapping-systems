"""
Automated Test Suite for Faculty Student Data Management System.
Tests Auth, CSV Persistence, Path Verification, Risk Engine Recalculation, and Role-Based Authorization.
"""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(__file__))

from app import create_app
from extensions import db
from models import User, Student
from csv_manager import CSV_PATH, BACKUP_PATH, read_students_csv, sync_db_to_csv


class TestFacultyStudentManagement(unittest.TestCase):
    def setUp(self):
        self.app = create_app()
        self.client = self.app.test_client()
        self.app_context = self.app.app_context()
        self.app_context.push()

        db.create_all()

        # Login as faculty
        faculty_res = self.client.post("/api/auth/login", json={
            "email": "faculty1@demo.import",
            "password": "faculty123"
        })
        if faculty_res.status_code == 200:
            self.faculty_token = faculty_res.json.get("token")
        else:
            from migrate_csv_to_mysql import seed_admin_and_faculty
            seed_admin_and_faculty()
            faculty_res = self.client.post("/api/auth/login", json={
                "email": "faculty1@demo.import",
                "password": "faculty123"
            })
            self.faculty_token = faculty_res.json.get("token")

        self.faculty_headers = {
            "Authorization": f"Bearer {self.faculty_token}",
            "Content-Type": "application/json"
        }

        # Login as student
        student_res = self.client.post("/api/auth/login", json={
            "email": "s001@legacy.import",
            "password": "student123"
        })
        if student_res.status_code == 200:
            self.student_token = student_res.json.get("token")
        else:
            self.student_token = None

        self.student_headers = {
            "Authorization": f"Bearer {self.student_token}",
            "Content-Type": "application/json"
        } if self.student_token else {}

    def tearDown(self):
        s = Student.query.filter_by(student_id="S999").first()
        if s:
            u = s.user
            db.session.delete(s)
            if u:
                db.session.delete(u)
            db.session.commit()
            sync_db_to_csv()
        self.app_context.pop()

    def test_01_verify_exact_csv_paths(self):
        expected_csv_path = os.path.abspath(
            os.path.join(os.path.dirname(__file__), "data", "students.csv")
        )
        expected_backup_path = os.path.abspath(
            os.path.join(os.path.dirname(__file__), "data", "students_backup.csv")
        )
        self.assertEqual(os.path.abspath(CSV_PATH), expected_csv_path)
        self.assertEqual(os.path.abspath(BACKUP_PATH), expected_backup_path)

    def test_02_get_faculty_students(self):
        res = self.client.get("/api/faculty/students", headers=self.faculty_headers)
        self.assertEqual(res.status_code, 200)
        data = res.json
        self.assertTrue(data.get("success"))
        self.assertIsInstance(data.get("students"), list)
        self.assertTrue(os.path.exists(CSV_PATH))

    def test_03_add_and_sync_csv(self):
        new_student = {
            "student_id": "S999",
            "name": "Test Student 999",
            "email": "s999@test.edu",
            "branch": "Computer Science",
            "year": 2,
            "semester": 4,
            "section": "B",
            "attendance_percentage": 88.5,
            "internal_marks": 25.0,
            "midterm_marks": 25.0,
            "assignment_marks": 15.0,
            "practical_marks": 15.0,
            "endterm_marks": 40.0,
            "cgpa": 8.8,
            "backlogs": 0
        }
        res = self.client.post("/api/faculty/students", json=new_student, headers=self.faculty_headers)
        self.assertEqual(res.status_code, 201)
        self.assertTrue(res.json.get("success"))

        # Verify CSV updated
        csv_rows = read_students_csv()
        s999_row = next((r for r in csv_rows if r["student_id"] == "S999"), None)
        self.assertIsNotNone(s999_row)
        self.assertEqual(s999_row["name"], "Test Student 999")
        self.assertEqual(float(s999_row["attendance_percentage"]), 88.5)

    def test_04_update_same_row_no_duplicates(self):
        self.test_03_add_and_sync_csv()
        initial_csv_rows = read_students_csv()
        initial_count = len(initial_csv_rows)

        update_payload = {
            "attendance_percentage": 45.0,
            "internal_marks": 10.0,
            "midterm_marks": 10.0,
            "cgpa": 5.2,
            "backlogs": 3
        }
        res = self.client.put("/api/faculty/students/S999", json=update_payload, headers=self.faculty_headers)
        self.assertEqual(res.status_code, 200)
        self.assertTrue(res.json.get("success"))

        updated_csv_rows = read_students_csv()
        self.assertEqual(len(updated_csv_rows), initial_count, "Editing student must not create duplicate rows")

        s999_row = next((r for r in updated_csv_rows if r["student_id"] == "S999"), None)
        self.assertIsNotNone(s999_row)
        self.assertEqual(float(s999_row["attendance_percentage"]), 45.0)
        self.assertEqual(s999_row["attendance_status"], "Critical")
        self.assertIn(s999_row["risk_status"], ["MEDIUM", "HIGH", "CRITICAL"])

    def test_05_delete_student_and_sync_csv(self):
        self.test_03_add_and_sync_csv()

        res = self.client.delete("/api/faculty/students/S999", headers=self.faculty_headers)
        self.assertEqual(res.status_code, 200)
        self.assertTrue(res.json.get("success"))

        csv_rows = read_students_csv()
        s999_row = next((r for r in csv_rows if r["student_id"] == "S999"), None)
        self.assertIsNone(s999_row)

    def test_06_persistence_across_app_restart(self):
        self.test_03_add_and_sync_csv()

        # Simulate Flask application restart by creating a new app context
        self.app_context.pop()
        new_app = create_app()
        new_client = new_app.test_client()
        new_context = new_app.app_context()
        new_context.push()

        # Check physical CSV file directly
        csv_rows = read_students_csv()
        s999_row = next((r for r in csv_rows if r["student_id"] == "S999"), None)
        self.assertIsNotNone(s999_row, "CSV data must persist after app restart")
        self.assertEqual(s999_row["name"], "Test Student 999")

        new_context.pop()
        # Re-attach original context for tearDown
        self.app_context = self.app.app_context()
        self.app_context.push()

    def test_07_student_role_forbidden_access(self):
        if not self.student_headers:
            self.skipTest("Student token unavailable")

        res = self.client.post("/api/faculty/students", json={"student_id": "S888"}, headers=self.student_headers)
        self.assertEqual(res.status_code, 403)

        res = self.client.delete("/api/faculty/students/S001", headers=self.student_headers)
        self.assertEqual(res.status_code, 403)


if __name__ == "__main__":
    unittest.main()
