"""
Baseline pipeline (lecture-scope only).

Lecture mapping
- Lecture 2 (Linear Regression / Regularization): StandardScaler, k-fold style 3-way split
- Lecture 3 (Logistic Regression): Logistic Regression baseline, ROC-AUC / F1 / Confusion Matrix
- Lecture 6 (Ensembles): Random Forest baseline, Feature Importance (MDI)
- Lecture 7 (SVM): SVM with RBF kernel

For full progression with AdaBoost / XGBoost / PCA visualization,
see `run_experiments.py`.
"""
import os
import json
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
from sklearn.model_selection import GroupShuffleSplit
from sklearn.ensemble import RandomForestClassifier
from sklearn.linear_model import LogisticRegression
from sklearn.svm import SVC
from sklearn.preprocessing import StandardScaler
from sklearn.metrics import (
    classification_report,
    accuracy_score,
    f1_score,
    roc_auc_score,
    confusion_matrix,
)

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
DATA_PATH = os.path.join(ROOT, "data", "processed", "features.csv")
FIGURES_DIR = os.path.join(ROOT, "figures")
RESULTS_DIR = os.path.join(ROOT, "results")

FEATURES = ["rg", "mean_dist", "std_dist", "clash_count", "density", "n_residues"]
RANDOM_STATE = 42


def load_data():
    df = pd.read_csv(DATA_PATH)
    df = df[df["label"] != -1].reset_index(drop=True)
    return df


def evaluate(name, y_true, y_pred, y_proba):
    return {
        "model": name,
        "accuracy": float(accuracy_score(y_true, y_pred)),
        "f1": float(f1_score(y_true, y_pred, zero_division=0)),
        "roc_auc": float(roc_auc_score(y_true, y_proba)),
        "confusion_matrix": confusion_matrix(y_true, y_pred).tolist(),
    }


def main():
    os.makedirs(FIGURES_DIR, exist_ok=True)
    os.makedirs(RESULTS_DIR, exist_ok=True)

    df = load_data()
    X = df[FEATURES]
    y = df["label"]
    groups = df["target"]
    print(f"Loaded {len(df)} samples across {groups.nunique()} target groups.")

    # Group-level 80/20 split (Lecture 2: k-fold CV extended to group level to prevent leakage)
    gss = GroupShuffleSplit(n_splits=1, test_size=0.25, random_state=RANDOM_STATE)
    train_idx, test_idx = next(gss.split(X, y, groups))
    X_train, X_test = X.iloc[train_idx], X.iloc[test_idx]
    y_train, y_test = y.iloc[train_idx], y.iloc[test_idx]
    print(f"Train targets: {sorted(df.iloc[train_idx]['target'].unique())}")
    print(f"Test  targets: {sorted(df.iloc[test_idx]['target'].unique())}")

    scaler = StandardScaler()
    X_train_s = scaler.fit_transform(X_train)
    X_test_s = scaler.transform(X_test)

    results = []

    # Lecture 3
    lr = LogisticRegression(max_iter=2000, class_weight="balanced", random_state=RANDOM_STATE)
    lr.fit(X_train_s, y_train)
    results.append(evaluate("LogReg", y_test, lr.predict(X_test_s), lr.predict_proba(X_test_s)[:, 1]))

    # Lecture 6
    rf = RandomForestClassifier(n_estimators=100, class_weight="balanced", random_state=RANDOM_STATE)
    rf.fit(X_train, y_train)
    results.append(evaluate("RandomForest", y_test, rf.predict(X_test), rf.predict_proba(X_test)[:, 1]))

    # Lecture 7
    svm = SVC(kernel="rbf", probability=True, class_weight="balanced", random_state=RANDOM_STATE)
    svm.fit(X_train_s, y_train)
    results.append(evaluate("SVM_RBF", y_test, svm.predict(X_test_s), svm.predict_proba(X_test_s)[:, 1]))

    for r in results:
        print(f"\n[{r['model']}]  ACC={r['accuracy']:.4f}  F1={r['f1']:.4f}  ROC-AUC={r['roc_auc']:.4f}")
        print(f"  CM = {r['confusion_matrix']}")

    # Feature Importance (Lecture 6 / RF MDI)
    importances = rf.feature_importances_
    order = np.argsort(importances)[::-1]
    plt.figure(figsize=(8, 5))
    plt.title("Random Forest Feature Importance (MDI)")
    plt.bar(range(len(FEATURES)), importances[order], color="#4C72B0")
    plt.xticks(range(len(FEATURES)), [FEATURES[i] for i in order], rotation=30)
    plt.ylabel("Importance")
    plt.tight_layout()
    plt.savefig(os.path.join(FIGURES_DIR, "feature_importance_rf.png"), dpi=150)
    plt.close()

    with open(os.path.join(RESULTS_DIR, "baseline_results.json"), "w", encoding="utf-8") as f:
        json.dump(results, f, indent=2, ensure_ascii=False)
    print(f"\nSaved baseline_results.json")


if __name__ == "__main__":
    main()
