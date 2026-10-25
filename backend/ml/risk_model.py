"""
Phase 4 — ML risk model.

IMPORTANT / HONEST NOTE ON LABELS
----------------------------------
There is no historical ground-truth "did this student actually drop out /
fail / burn out" dataset anywhere in this project (neither the original CSV
nor the new DB tracks real outcomes). So this model is trained on WEAK
LABELS derived from the existing rule-based trigger engine (risk_engine.py):
number of triggers fired -> a LOW/MEDIUM/HIGH/CRITICAL bucket. That means
the classifier is, honestly, learning a smoothed / generalized version of
the same rules, but expressed as a probability instead of a hard if/else,
and able to pick up interactions between features the hand-written rules
don't capture. Document this in your report — don't claim it was trained on
real historical outcome data, because it wasn't. This is standard practice
for a capstone project without access to a real labeled dataset; the model
still adds value (feature-weighted probabilities instead of hard cutoffs)
without pretending to be something it isn't.

Swap `build_training_labels()` for a real outcomes table (e.g. actual
semester-end pass/fail/dropout records) if one ever becomes available, and
this pipeline keeps working unchanged.
"""
import json
import os

import joblib
import numpy as np
from sklearn.ensemble import RandomForestClassifier
from sklearn.model_selection import train_test_split
from sklearn.metrics import classification_report

from models import Attendance, Marks, AssignmentSubmission, Performance, Student
from risk_engine import evaluate_triggers, load_thresholds

FEATURE_NAMES = [
    "avg_attendance", "attendance_std", "avg_marks", "marks_std",
    "late_missed_ratio", "cgpa", "backlogs", "num_subjects",
]

LEVEL_ORDER = ["LOW", "MEDIUM", "HIGH", "CRITICAL"]


def extract_features(student: Student) -> dict:
    att_rows = Attendance.query.filter_by(student_id=student.id).all()
    marks_rows = Marks.query.filter_by(student_id=student.id).all()
    subs = AssignmentSubmission.query.filter_by(student_id=student.id).all()
    perf = (Performance.query.filter_by(student_id=student.id)
            .order_by(Performance.id.desc()).first())

    att_vals = [a.attendance_percentage for a in att_rows]
    marks_vals = [m.total_marks for m in marks_rows]
    late_missed = sum(1 for s in subs if s.status in ("LATE", "MISSED"))

    return {
        "avg_attendance": float(np.mean(att_vals)) if att_vals else 0.0,
        "attendance_std": float(np.std(att_vals)) if att_vals else 0.0,
        "avg_marks": float(np.mean(marks_vals)) if marks_vals else 0.0,
        "marks_std": float(np.std(marks_vals)) if marks_vals else 0.0,
        "late_missed_ratio": (late_missed / len(subs)) if subs else 0.0,
        "cgpa": float(perf.cgpa) if perf and perf.cgpa is not None else 0.0,
        "backlogs": float(perf.backlogs) if perf and perf.backlogs is not None else 0.0,
        "num_subjects": float(len(marks_rows)),
    }


def _level_from_trigger_count(n: int) -> str:
    if n == 0:
        return "LOW"
    if n == 1:
        return "MEDIUM"
    if n == 2:
        return "HIGH"
    return "CRITICAL"


def build_training_table(students):
    """Returns (X, y, feature_rows) for all students with any recorded data."""
    thresholds = load_thresholds()
    X, y, rows = [], [], []
    for s in students:
        feats = extract_features(s)
        if feats["num_subjects"] == 0 and feats["avg_attendance"] == 0:
            continue  # skip students with no academic records at all
        trig_result = evaluate_triggers(s, thresholds)
        label = _level_from_trigger_count(len(trig_result["triggers"]))
        X.append([feats[f] for f in FEATURE_NAMES])
        y.append(label)
        rows.append(feats)
    return np.array(X), np.array(y), rows


def train_and_save(students, model_path: str) -> dict:
    X, y, _ = build_training_table(students)
    if len(X) < 8 or len(set(y)) < 2:
        raise ValueError(
            f"Not enough varied data to train (have {len(X)} rows, "
            f"{len(set(y))} distinct risk levels). Seed/migrate more data first."
        )

    from collections import Counter
    class_counts = Counter(y)
    can_stratify = len(X) >= 12 and min(class_counts.values()) >= 2

    if len(X) >= 12:
        try:
            X_train, X_test, y_train, y_test = train_test_split(
                X, y, test_size=0.25, random_state=42, stratify=y if can_stratify else None)
        except ValueError:
            X_train, y_train = X, y
            X_test, y_test = X, y
    else:
        X_train, y_train = X, y
        X_test, y_test = X, y

    clf = RandomForestClassifier(n_estimators=200, max_depth=6, random_state=42, class_weight="balanced")
    clf.fit(X_train, y_train)

    report = classification_report(y_test, clf.predict(X_test), zero_division=0, output_dict=True)
    importances = dict(zip(FEATURE_NAMES, clf.feature_importances_.tolist()))

    os.makedirs(os.path.dirname(model_path), exist_ok=True)
    joblib.dump({"model": clf, "feature_names": FEATURE_NAMES, "classes": list(clf.classes_)}, model_path)

    meta_path = model_path.replace(".joblib", "_meta.json")
    with open(meta_path, "w") as f:
        json.dump({
            "n_samples": len(X), "report": report, "feature_importances": importances,
            "label_source": "weak labels from rule_engine trigger counts (see module docstring)",
        }, f, indent=2)

    return {"n_samples": len(X), "feature_importances": importances, "report": report}


_MODEL_CACHE = {}


def load_model(model_path: str):
    if model_path in _MODEL_CACHE:
        return _MODEL_CACHE[model_path]
    if not os.path.exists(model_path):
        return None
    bundle = joblib.load(model_path)
    _MODEL_CACHE[model_path] = bundle
    return bundle


def _top_reasons(feats: dict, importances: dict) -> list:
    """Simple explainability: flag features that look 'bad' weighted by
    how much the model relies on them, in plain language."""
    reasons = []
    if feats["avg_attendance"] < 75:
        reasons.append(f"Average attendance is low ({feats['avg_attendance']:.1f}%).")
    if feats["late_missed_ratio"] > 0.3:
        reasons.append(f"{feats['late_missed_ratio']*100:.0f}% of assignments were late or missed.")
    if feats["avg_marks"] < 50:
        reasons.append(f"Average marks are below passing threshold ({feats['avg_marks']:.1f}).")
    if feats["cgpa"] and feats["cgpa"] < 6.5:
        reasons.append(f"CGPA ({feats['cgpa']:.2f}) is below a healthy threshold.")
    if feats["backlogs"] > 0:
        reasons.append(f"{int(feats['backlogs'])} active backlog(s).")
    if not reasons:
        reasons.append("No major risk indicators detected — metrics are within healthy ranges.")
    # order by feature importance where possible
    reasons.sort(key=lambda r: -max(
        (v for k, v in importances.items() if k.split("_")[0] in r.lower()), default=0))
    return reasons[:5]


def _recommendations_for(level: str, feats: dict) -> list:
    recs = []
    if feats["avg_attendance"] < 75:
        recs.append("Schedule a check-in with the academic advisor about attendance.")
    if feats["late_missed_ratio"] > 0.3:
        recs.append("Set up a personal assignment tracker with earlier reminder deadlines.")
    if feats["avg_marks"] < 50:
        recs.append("Recommend peer tutoring or extra office hours for weaker subjects.")
    if feats["cgpa"] and feats["cgpa"] < 6.5:
        recs.append("Review course load and consider a study-skills workshop.")
    if level in ("HIGH", "CRITICAL") and not recs:
        recs.append("Flag for faculty review even though no single metric stands out.")
    if not recs:
        recs.append("Keep up the current routine — no intervention needed right now.")
    return recs


def predict_risk(student: Student, model_path: str) -> dict:
    bundle = load_model(model_path)
    feats = extract_features(student)

    if bundle is None:
        # Fallback: no trained model yet -> derive a score from the rule engine
        # so the endpoint still works, clearly marked as a fallback.
        trig_result = evaluate_triggers(student)
        level = _level_from_trigger_count(len(trig_result["triggers"]))
        score = {"LOW": 0.2, "MEDIUM": 0.45, "HIGH": 0.7, "CRITICAL": 0.9}[level]
        return {
            "risk_score": score, "risk_level": level,
            "reasons": _top_reasons(feats, {}),
            "recommendations": _recommendations_for(level, feats),
            "source": "rule_engine_fallback (ML model not trained yet — run train_risk_model.py)",
        }

    clf = bundle["model"]
    x = np.array([[feats[f] for f in FEATURE_NAMES]])
    proba = clf.predict_proba(x)[0]
    classes = bundle["classes"]
    level = classes[int(np.argmax(proba))]
    # risk_score: probability mass on HIGH+CRITICAL, weighted toward severity
    severity_weight = {"LOW": 0.0, "MEDIUM": 0.33, "HIGH": 0.66, "CRITICAL": 1.0}
    score = float(sum(p * severity_weight.get(c, 0.0) for c, p in zip(classes, proba)))

    importances = dict(zip(FEATURE_NAMES, getattr(clf, "feature_importances_", [0] * len(FEATURE_NAMES))))
    return {
        "risk_score": round(score, 3), "risk_level": level,
        "reasons": _top_reasons(feats, importances),
        "recommendations": _recommendations_for(level, feats),
        "source": "ml_model",
        "class_probabilities": dict(zip(classes, [round(float(p), 3) for p in proba])),
    }
