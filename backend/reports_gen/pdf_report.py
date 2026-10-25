"""
Phase 7 — Upgraded PDF reports.

Same ReportLab foundation as the original minor project's single PDF route,
but now pulls everything from the database (subjects, marks, attendance,
performance trend, ML risk assessment) instead of a flat CSV row, and adds
an AI-generated explanation section when available.
"""
import json
import os

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import cm
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle,
)

from models import Attendance, Marks, Performance, RiskAssessment, Subject
from config import Config


def _subj_lookup():
    return {s.id: s for s in Subject.query.all()}


def build_student_report(student, ai_explanation: str = None) -> str:
    os.makedirs(Config.REPORTS_DIR, exist_ok=True)
    path = os.path.join(Config.REPORTS_DIR, f"{student.student_id}_report.pdf")

    styles = getSampleStyleSheet()
    title_style = ParagraphStyle("TitleX", parent=styles["Title"], fontSize=18)
    h2 = styles["Heading2"]
    normal = styles["BodyText"]

    doc = SimpleDocTemplate(path, pagesize=A4, topMargin=1.5 * cm, bottomMargin=1.5 * cm)
    story = [
        Paragraph("University Impact &amp; Reality Mapping System", title_style),
        Paragraph("Student Academic Report", h2),
        Spacer(1, 0.3 * cm),
        Paragraph(f"<b>Student ID:</b> {student.student_id} &nbsp;&nbsp; "
                  f"<b>Name:</b> {student.name}", normal),
        Paragraph(f"<b>Department:</b> {student.department} &nbsp;&nbsp; "
                  f"<b>Semester:</b> {student.semester}", normal),
        Spacer(1, 0.5 * cm),
    ]

    # Performance trend
    perf_rows = (Performance.query.filter_by(student_id=student.id)
                 .order_by(Performance.semester).all())
    story.append(Paragraph("Academic Performance", h2))
    if perf_rows:
        data = [["Semester", "SGPA", "CGPA", "Backlogs", "Academic Year"]]
        for p in perf_rows:
            data.append([p.semester, p.sgpa, p.cgpa, p.backlogs, p.academic_year])
        t = Table(data, hAlign="LEFT")
        t.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#2c3e50")),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
            ("GRID", (0, 0), (-1, -1), 0.5, colors.grey),
            ("FONTSIZE", (0, 0), (-1, -1), 9),
        ]))
        story.append(t)
    else:
        story.append(Paragraph("No performance records on file.", normal))
    story.append(Spacer(1, 0.5 * cm))

    # Subject-level marks
    subjects = _subj_lookup()
    marks_rows = Marks.query.filter_by(student_id=student.id).all()
    story.append(Paragraph("Subject-wise Marks", h2))
    if marks_rows:
        data = [["Subject", "Internal", "Midterm", "Assignment", "Practical", "Final", "Total", "Grade"]]
        for m in marks_rows:
            subj_name = subjects.get(m.subject_id).subject_name if m.subject_id in subjects else "?"
            data.append([subj_name, m.internal_marks, m.midterm_marks, m.assignment_marks,
                         m.practical_marks, m.final_marks, m.total_marks, m.grade])
        t = Table(data, hAlign="LEFT")
        t.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#2c3e50")),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
            ("GRID", (0, 0), (-1, -1), 0.5, colors.grey),
            ("FONTSIZE", (0, 0), (-1, -1), 8),
        ]))
        story.append(t)
    else:
        story.append(Paragraph("No marks records on file.", normal))
    story.append(Spacer(1, 0.5 * cm))

    # Attendance
    att_rows = Attendance.query.filter_by(student_id=student.id).all()
    story.append(Paragraph("Subject-wise Attendance", h2))
    if att_rows:
        data = [["Subject", "Attended", "Total", "Percentage"]]
        for a in att_rows:
            subj_name = subjects.get(a.subject_id).subject_name if a.subject_id in subjects else "?"
            data.append([subj_name, a.attended_classes, a.total_classes, f"{a.attendance_percentage}%"])
        t = Table(data, hAlign="LEFT")
        t.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#2c3e50")),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
            ("GRID", (0, 0), (-1, -1), 0.5, colors.grey),
            ("FONTSIZE", (0, 0), (-1, -1), 9),
        ]))
        story.append(t)
    else:
        story.append(Paragraph("No attendance records on file.", normal))
    story.append(Spacer(1, 0.5 * cm))

    # Risk assessment
    risk = (RiskAssessment.query.filter_by(student_id=student.id)
            .order_by(RiskAssessment.created_at.desc()).first())
    story.append(Paragraph("Risk Assessment", h2))
    if risk:
        reasons = json.loads(risk.reasons) if risk.reasons else []
        recs = json.loads(risk.recommendations) if risk.recommendations else []
        story.append(Paragraph(f"<b>Risk level:</b> {risk.risk_level} "
                                f"(score {risk.risk_score:.2f})", normal))
        if reasons:
            story.append(Paragraph("<b>Contributing factors:</b> " + "; ".join(reasons), normal))
        if recs:
            story.append(Paragraph("<b>Recommendations:</b> " + "; ".join(recs), normal))
    else:
        story.append(Paragraph("No risk assessment on file yet.", normal))
    story.append(Spacer(1, 0.5 * cm))

    # AI explanation (Phase 5)
    if ai_explanation:
        story.append(Paragraph("AI-Generated Summary", h2))
        story.append(Paragraph(ai_explanation, normal))

    doc.build(story)
    return path
