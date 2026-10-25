# University Impact & Reality Mapping System

## 📌 Overview
This project is a rule-based analytical system designed to identify academic burnout,
learning gaps, and policy mismatches in universities using student behavioral and academic data.

The system focuses on **explainability and transparency**, avoiding black-box models
while remaining fully extendable to Machine Learning in the future.

---

## 🎯 Key Features
- Burnout risk detection
- Learning gap identification
- Outcome mismatch analysis
- Placement policy mismatch detection
- Student-wise PDF report generation
- Semester-wise analytical insights
- Interactive frontend dashboard

---

## 🏗️ System Architecture
CSV Data
↓
Flask Backend (Trigger Engine)
↓
REST APIs
↓
Frontend Dashboard
↓
PDF Reports

---

## 🛠️ Technology Stack
- **Backend:** Python, Flask
- **Frontend:** HTML, CSS, JavaScript
- **Data Source:** CSV
- **Reporting:** ReportLab (PDF generation)

---

## 🚀 How to Run the Project

### 1️⃣ Install Dependencies
```bash
pip install flask pandas reportlab flask-cors

2️⃣ Start Backend Server
cd backend
python app.py


Server runs on:
http://127.0.0.1:5000

3️⃣ Run Frontend

Open the file:

frontend/index.html

using any modern browser or VS Code Live Server.

🔗 Important API Endpoints

/students
/students/triggers
/summary
/student/report/<student_id>
/reports/semester/<semester>


📄 PDF Reports

Automatically generated per student
Downloadable directly from frontend
Stored safely in backend/reports/


📈 Academic Relevance

This project demonstrates:

System design thinking
Rule-based intelligence
Ethical analytics
Full-stack integration
Practical debugging and optimization



🔮 Future Enhancements

Database integration
Machine learning-based predictions
Admin threshold tuning
University-wide analytics


👤 Author

