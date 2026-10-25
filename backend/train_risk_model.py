"""
Trains the Phase 4 ML risk model from whatever is currently in the DB and
saves it to backend/ml/risk_model.joblib (path from Config.ML_MODEL_PATH).

Run after migrate_csv_to_mysql.py (or whenever there's meaningfully new
academic data to retrain on):

    cd backend
    python train_risk_model.py
"""
import json

from app import create_app
from config import Config
from models import Student
from ml.risk_model import train_and_save


def main():
    app = create_app()
    with app.app_context():
        students = Student.query.all()
        print(f"Training on {len(students)} student records...")
        result = train_and_save(students, Config.ML_MODEL_PATH)
        print(f"\nTrained on {result['n_samples']} labeled rows.")
        print("Feature importances:")
        for k, v in sorted(result["feature_importances"].items(), key=lambda kv: -kv[1]):
            print(f"  {k:20s} {v:.3f}")
        print(f"\nModel saved to {Config.ML_MODEL_PATH}")
        print(json.dumps(result["report"], indent=2)[:800])


if __name__ == "__main__":
    main()
