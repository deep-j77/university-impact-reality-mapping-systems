from flask import Blueprint, request, jsonify, g

from extensions import db
from models import User, Student, Faculty
from auth import hash_password, verify_password, issue_token, require_auth

auth_bp = Blueprint("auth", __name__)


@auth_bp.post("/register")
def register():
    """
    Self-registration. Only STUDENT accounts can be created this way
    (mirrors the original signup.html flow). Admin/Faculty accounts are
    provisioned by an admin via /api/admin/users.
    """
    data = request.get_json(silent=True) or {}
    required = ["name", "email", "password", "student_id", "department", "semester"]
    missing = [f for f in required if not data.get(f)]
    if missing:
        return jsonify({"error": f"Missing fields: {', '.join(missing)}"}), 400

    if User.query.filter_by(email=data["email"].strip().lower()).first():
        return jsonify({"error": "Email already registered"}), 409
    if Student.query.filter_by(student_id=data["student_id"].strip()).first():
        return jsonify({"error": "Student ID already exists"}), 409

    user = User(
        name=data["name"].strip(),
        email=data["email"].strip().lower(),
        password_hash=hash_password(data["password"]),
        role="STUDENT",
    )
    db.session.add(user)
    db.session.flush()

    student = Student(
        user_id=user.id,
        student_id=data["student_id"].strip(),
        name=data["name"].strip(),
        department=data["department"].strip(),
        semester=int(data["semester"]),
        email=user.email,
    )
    db.session.add(student)
    db.session.commit()

    token = issue_token(user)
    return jsonify({"token": token, "user": user.to_dict(include_role_profile=True)}), 201


@auth_bp.post("/login")
def login():
    data = request.get_json(silent=True) or {}
    email = (data.get("email") or "").strip().lower()
    password = data.get("password") or ""

    if not email or not password:
        return jsonify({"error": "Email and password are required"}), 400

    user = User.query.filter_by(email=email).first()
    if not user or not verify_password(password, user.password_hash):
        return jsonify({"error": "Invalid credentials"}), 401

    token = issue_token(user)
    return jsonify({"token": token, "user": user.to_dict(include_role_profile=True)})


@auth_bp.get("/me")
@require_auth
def me():
    return jsonify(g.current_user.to_dict(include_role_profile=True))
