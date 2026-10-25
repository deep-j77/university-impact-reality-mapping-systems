"""
Phase 5 — Generative AI layer using Google Gemini API.
"""
import os
import sys
from config import Config

_model = None
_init_failed = False


def _get_gemini_model():
    global _model, _init_failed
    if _model is not None or _init_failed:
        return _model

    api_key = getattr(Config, "GEMINI_API_KEY", None) or os.getenv("GEMINI_API_KEY")
    if not api_key:
        print("[AI ERROR] GEMINI_API_KEY is missing in Config/.env!", file=sys.stderr)
        _init_failed = True
        return None

    try:
        import google.generativeai as genai
        genai.configure(api_key=api_key)
        _model = genai.GenerativeModel("gemini-1.5-flash")
        print("[AI SUCCESS] Google Gemini client initialized successfully!", file=sys.stderr)
    except Exception as e:
        print(f"[AI ERROR] Failed to initialize Gemini: {e}", file=sys.stderr)
        _init_failed = True
        _model = None

    return _model


def explain_risk(student_name: str, risk_level: str, risk_score: float,
                 reasons: list, metrics: dict) -> dict:
    model = _get_gemini_model()
    if model:
        try:
            prompt = (
                f"You are an academic advisor assistant. Explain this student's risk assessment "
                f"in plain, encouraging language for faculty (concise, 3-4 sentences):\n"
                f"Student: {student_name}\n"
                f"Risk Level: {risk_level} (Score: {risk_score})\n"
                f"Contributing factors: {', '.join(reasons)}\n"
                f"Metrics: {metrics}"
            )
            resp = model.generate_content(prompt)
            if resp and resp.text:
                return {"explanation": resp.text.strip(), "used_llm": True}
        except Exception as e:
            print(f"[AI ERROR] Gemini explain_risk failed: {e}", file=sys.stderr)

    clean_reasons = "; ".join(r.rstrip(".") for r in reasons)
    fallback = (f"{student_name} is currently flagged as {risk_level} risk. "
                f"The main contributing factors are: {clean_reasons}.")
    return {"explanation": fallback, "used_llm": False}


def generate_recommendations(student_name: str, risk_level: str, reasons: list) -> dict:
    model = _get_gemini_model()
    if model:
        try:
            prompt = (
                f"You are an academic advisor. Suggest 3-4 concrete actionable next steps "
                f"for faculty to help this student. Return only a numbered list, no preamble:\n"
                f"Student: {student_name}\n"
                f"Risk Level: {risk_level}\n"
                f"Factors: {', '.join(reasons)}"
            )
            resp = model.generate_content(prompt)
            if resp and resp.text:
                return {"recommendations": resp.text.strip(), "used_llm": True}
        except Exception as e:
            print(f"[AI ERROR] Gemini recommendations failed: {e}", file=sys.stderr)

    return {
        "recommendations": "1. Schedule academic counseling.\n2. Review low attendance sessions.\n3. Offer remedial assignments.",
        "used_llm": False
    }


def chatbot_reply(student_name: str, context: dict, message: str, history=None) -> dict:
    model = _get_gemini_model()
    if model:
        try:
            system_context = (
                f"You are a friendly, concise academic advisor chatbot for {student_name}. "
                f"You help students understand their academic standings (attendance, marks, CGPA, risk status). "
                f"Keep answers short and clear (2 to 3 sentences maximum).\n"
                f"Student Context:\n"
                f"- Average Attendance: {context.get('avg_attendance')}%\n"
                f"- Average Marks: {context.get('avg_marks')}\n"
                f"- CGPA: {context.get('cgpa')}\n"
                f"- Risk Level: {context.get('risk_level')}\n"
            )

            history_text = ""
            for turn in (history or [])[-4:]:
                role = "Student" if turn.get("role") == "user" else "Advisor"
                history_text += f"{role}: {turn.get('content', '')}\n"

            prompt = f"{system_context}\n{history_text}Student: {message}\nAdvisor:"
            resp = model.generate_content(prompt)
            if resp and resp.text:
                return {"reply": resp.text.strip(), "used_llm": True}
        except Exception as e:
            print(f"[AI CHATBOT ERROR] Gemini failed: {e}", file=sys.stderr)

    attendance = context.get("avg_attendance")
    cgpa = context.get("cgpa")
    fallback = (
        f"Your current attendance is {attendance}% and CGPA is {cgpa}. "
        f"Reach out to your faculty advisor for detailed guidance."
    )
    return {"reply": fallback, "used_llm": False}