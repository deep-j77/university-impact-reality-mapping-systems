from flask import Blueprint, request, jsonify

from extensions import db
from models import User, Faculty
from auth import require_auth, require_role, hash_password
from risk_engine import load_thresholds, save_thresholds

admin_bp = Blueprint("admin", __name__)


@admin_bp.get("/thresholds")
@require_auth
@require_role("ADMIN")
def get_thresholds():
    return jsonify(load_thresholds())


@admin_bp.put("/thresholds")
@require_auth
@require_role("ADMIN")
def update_thresholds():
    data = request.get_json(silent=True) or {}
    return jsonify(save_thresholds(data))


@admin_bp.get("/users")
@require_auth
@require_role("ADMIN")
def list_users():
    role = request.args.get("role")
    q = User.query
    if role:
        q = q.filter_by(role=role.upper())
    return jsonify([u.to_dict() for u in q.order_by(User.id).all()])


@admin_bp.post("/users")
@require_auth
@require_role("ADMIN")
def create_staff_user():
    """Provision an ADMIN or FACULTY account."""
    data = request.get_json(silent=True) or {}
    required = ["name", "email", "password", "role"]
    missing = [f for f in required if not data.get(f)]
    if missing:
        return jsonify({"error": f"Missing fields: {', '.join(missing)}"}), 400

    role = data["role"].strip().upper()
    if role not in ("ADMIN", "FACULTY"):
        return jsonify({"error": "role must be ADMIN or FACULTY"}), 400
    if User.query.filter_by(email=data["email"].strip().lower()).first():
        return jsonify({"error": "Email already registered"}), 409

    user = User(name=data["name"].strip(), email=data["email"].strip().lower(),
                password_hash=hash_password(data["password"]), role=role)
    db.session.add(user)
    db.session.flush()

    if role == "FACULTY":
        if not data.get("employee_id") or not data.get("department"):
            return jsonify({"error": "employee_id and department are required for FACULTY"}), 400
        if Faculty.query.filter_by(employee_id=data["employee_id"]).first():
            return jsonify({"error": "employee_id already exists"}), 409
        db.session.add(Faculty(user_id=user.id, employee_id=data["employee_id"],
                                department=data["department"],
                                designation=data.get("designation", "")))

    db.session.commit()
    return jsonify(user.to_dict(include_role_profile=True)), 201


@admin_bp.delete("/users/<int:user_id>")
@require_auth
@require_role("ADMIN")
def delete_user(user_id):
    user = User.query.get(user_id)
    if not user:
        return jsonify({"error": "User not found"}), 404
    db.session.delete(user)
    db.session.commit()
    return jsonify({"deleted": user_id})
