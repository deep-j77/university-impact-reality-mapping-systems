from flask import Flask, jsonify, send_file, request
from flask_cors import CORS
import pandas as pd
import os

from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas

app = Flask(__name__)
CORS(app)

# =========================
# Load Data
# =========================
DATA_PATH = "../data/students_extended.csv"
df = pd.read_csv(DATA_PATH)

USERS_PATH = "../data/users.csv"
users_df = pd.read_csv(USERS_PATH)

# =========================
# University Placement Policies
# =========================
PLACEMENT_POLICIES = {
    3: 7.0,
    5: 7.5,
    7: 8.0
}

# =========================
# Trigger Engine
# =========================
def evaluate_triggers(student):
    triggers = []

    if student["night_study_ratio"] > 0.6 and student["avg_submission_delay_days"] > 2.5:
        triggers.append("BURNOUT_RISK")

    if student["attendance_pct"] > 85 and student["skills_acquired"] <= 2:
        triggers.append("LEARNING_GAP")

    if student["skills_acquired"] >= 4 and student["cgpa"] < 7.0:
        triggers.append("OUTCOME_MISMATCH")

    cutoff = PLACEMENT_POLICIES.get(student["semester"])
    if cutoff and student["skills_acquired"] >= 4 and student["cgpa"] < cutoff:
        triggers.append("PLACEMENT_POLICY_MISMATCH")

    return triggers

# =========================
# AUTH ROUTE
# =========================
@app.route("/login", methods=["POST"])
def login():
    data = request.json
    user_id = data.get("user_id")
    password = data.get("password")

    user = users_df[
        (users_df["user_id"] == user_id) &
        (users_df["password"] == password)
    ]

    if user.empty:
        return {"error": "Invalid credentials"}, 401

    return {
        "message": "Login successful",
        "user_id": user_id,
        "role": user.iloc[0]["role"]
    }



@app.route("/signup", methods=["POST"])
def signup():
    data = request.json
    new_user = {
        "user_id": data["user_id"],
        "password": data["password"],
        "role": data["role"]
    }

    global users_df
    users_df = pd.concat([users_df, pd.DataFrame([new_user])])
    users_df.to_csv(USERS_PATH, index=False)

    return {"message": "Signup successful (demo only)"}





# =========================
# HELPER: AUTH CHECK
# =========================
def get_auth():
    user_id = request.headers.get("X-User-ID")
    role = request.headers.get("X-Role")
    return user_id, role

# =========================
# CORE ROUTES
# =========================
@app.route("/")
def home():
    return {"message": "Backend running"}

@app.route("/summary")
def summary():
    user_id, role = get_auth()
    if not user_id:
        return {"error": "Unauthorized"}, 401

    data = df if role == "admin" else df[df["student_id"] == user_id]

    summary = {
        "BURNOUT_RISK": 0,
        "LEARNING_GAP": 0,
        "OUTCOME_MISMATCH": 0,
        "PLACEMENT_POLICY_MISMATCH": 0
    }

    for _, row in data.iterrows():
        for t in evaluate_triggers(row.to_dict()):
            summary[t] += 1

    return jsonify(summary)

@app.route("/students/triggers")
def students_triggers():
    user_id, role = get_auth()
    if not user_id:
        return {"error": "Unauthorized"}, 401

    data = df if role == "admin" else df[df["student_id"] == user_id]

    results = []
    for _, row in data.iterrows():
        student = row.to_dict()
        student["triggers"] = evaluate_triggers(student)
        results.append(student)

    return jsonify(results)

# =========================
# PDF REPORT
# =========================
@app.route("/student/report/<student_id>")
def student_report(student_id):
    user_id = request.args.get("uid")
    role = request.args.get("role")

    if not user_id:
        return {"error": "Unauthorized"}, 401

    if role == "student" and user_id != student_id:
        return {"error": "Access denied"}, 403

    student_row = df[df["student_id"] == student_id]
    if student_row.empty:
        return {"error": "Student not found"}, 404

    student = student_row.iloc[0].to_dict()
    triggers = evaluate_triggers(student)

    reports_dir = os.path.join(os.getcwd(), "reports")
    os.makedirs(reports_dir, exist_ok=True)

    file_path = os.path.join(reports_dir, f"{student_id}_report.pdf")
    c = canvas.Canvas(file_path, pagesize=A4)

    c.setFont("Helvetica-Bold", 18)
    c.drawCentredString(300, 800, "University Impact Report")
    c.line(40, 740, 560, 740)

    c.setFont("Helvetica", 11)
    c.drawString(50, 760, f"Student ID: {student_id}")
    c.drawString(300, 760, f"University: {student['university']}")

    y = 720
    c.setFont("Helvetica-Bold", 13)
    c.drawString(50, y, "Academic Metrics")
    y -= 25

    for k in ["semester", "attendance_pct", "avg_submission_delay_days",
              "night_study_ratio", "skills_acquired", "cgpa"]:
        c.setFont("Helvetica", 11)
        c.drawString(70, y, f"{k}: {student[k]}")
        y -= 18

    y -= 20
    c.setFont("Helvetica-Bold", 13)
    c.drawString(50, y, "Triggered Insights")
    y -= 20

    if triggers:
        for t in triggers:
            c.drawString(70, y, f"- {t.replace('_',' ')}")
            y -= 18
    else:
        c.drawString(70, y, "No risks detected")

    c.save()
    return send_file(file_path, as_attachment=True)



@app.route("/admin/thresholds")
def admin_thresholds():
    user_id = request.headers.get("X-User-ID")
    role = request.headers.get("X-Role")

    if role != "admin":
        return {"error": "Admin access only"}, 403

    return {
        "burnout_rule": "Night study + submission delay",
        "learning_gap_rule": "High attendance + low skills",
        "policy_cutoff": PLACEMENT_POLICIES
    }



# =========================
# RUN
# =========================
if __name__ == "__main__":
    app.run(debug=True)
