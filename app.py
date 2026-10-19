from flask import Flask, jsonify
from flask_cors import CORS

from config import Config
from extensions import db


def create_app():
    app = Flask(__name__)
    app.config.from_object(Config)
    CORS(app)

    db.init_app(app)

    # Import models so SQLAlchemy metadata knows about every table
    # before db.create_all() / migrations run.
    import models  # noqa: F401

    @app.route("/")
    def home():
        return jsonify({
            "message": "University Impact & Reality Mapping System API",
            "status": "running",
            "phase": "9 of 9 - all phases complete (Phase 9: CSV/Excel data export)",
        })

    @app.route("/health/db")
    def health_db():
        try:
            db.session.execute(db.text("SELECT 1"))
            return jsonify({"database": "connected"})
        except Exception as e:
            return jsonify({"database": "error", "detail": str(e)}), 500

    from routes.auth import auth_bp
    from routes.students import students_bp
    from routes.subjects import subjects_bp
    from routes.attendance import attendance_bp
    from routes.marks import marks_bp
    from routes.assignments import assignments_bp
    from routes.performance import performance_bp
    from routes.admin import admin_bp
    from routes.risk import risk_bp
    from routes.ai import ai_bp
    from routes.dashboard import dashboard_bp
    from routes.reports import reports_bp
    from routes.export import export_bp
    from routes.faculty_students import faculty_students_bp

    app.register_blueprint(auth_bp, url_prefix="/api/auth")
    app.register_blueprint(students_bp, url_prefix="/api/students")
    app.register_blueprint(faculty_students_bp, url_prefix="/api/faculty/students")
    app.register_blueprint(subjects_bp, url_prefix="/api/subjects")
    app.register_blueprint(attendance_bp, url_prefix="/api/attendance")
    app.register_blueprint(marks_bp, url_prefix="/api/marks")
    app.register_blueprint(assignments_bp, url_prefix="/api/assignments")
    app.register_blueprint(performance_bp, url_prefix="/api/performance")
    app.register_blueprint(admin_bp, url_prefix="/api/admin")
    app.register_blueprint(risk_bp, url_prefix="/api/risk")
    app.register_blueprint(ai_bp, url_prefix="/api/ai")
    app.register_blueprint(dashboard_bp, url_prefix="/api/dashboard")
    app.register_blueprint(reports_bp, url_prefix="/api/reports")
    app.register_blueprint(export_bp, url_prefix="/api/export")

    @app.errorhandler(404)
    def not_found(e):
        return jsonify({"error": "Not found"}), 404

    @app.errorhandler(500)
    def server_error(e):
        return jsonify({"error": "Internal server error"}), 500

    return app


if __name__ == "__main__":
    application = create_app()
    application.run(debug=Config.DEBUG)
