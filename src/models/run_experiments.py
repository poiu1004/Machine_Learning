"""
Lecture-scope experiment pipeline for the term project.

Lecture mapping
---------------
- Lecture 2 (Linear Regression / Regularization)
    : StandardScaler, train/val/test 3-way split, k-fold style group split,
      L1/L2 regularization for Logistic Regression.
- Lecture 3 (Logistic Regression)
    : Logistic Regression baseline, ROC curve / ROC-AUC, F1 / Precision / Recall,
      Confusion Matrix, class imbalance handling via `class_weight='balanced'`.
- Lecture 6 (Ensembles)
    : Random Forest, AdaBoost, Gradient Boosting / XGBoost.
- Lecture 7 (SVM)
    : SVM with RBF (Gaussian) kernel; C / gamma tuning.
- Lecture 10 (K-Means & PCA)
    : PCA 2D embedding for visualization.

Outside lecture scope (NOT used): PointNet, t-SNE, deep learning.

Two scenarios
-------------
- Scenario A: Random 3-way split (60/20/20) ignoring target groups.
- Scenario B: Group-level 3-way split (train/val/test split by protein target),
  to measure true generalization to unseen folds.
"""
import os
import json
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt

from sklearn.model_selection import train_test_split, GroupShuffleSplit
from sklearn.preprocessing import StandardScaler
from sklearn.decomposition import PCA
from sklearn.linear_model import LogisticRegression
from sklearn.ensemble import (
    RandomForestClassifier,
    AdaBoostClassifier,
    GradientBoostingClassifier,
)
from sklearn.svm import SVC
from sklearn.metrics import (
    roc_auc_score,
    f1_score,
    accuracy_score,
    confusion_matrix,
    roc_curve,
    classification_report,
)

import warnings
warnings.filterwarnings("ignore", category=FutureWarning, module="sklearn")
warnings.filterwarnings("ignore", category=UserWarning, module="sklearn")

try:
    from xgboost import XGBClassifier
    HAS_XGB = True
except ImportError:
    HAS_XGB = False


ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
DATA_PATH = os.path.join(ROOT, "data", "processed", "features.csv")
FIGURES_DIR = os.path.join(ROOT, "figures")
RESULTS_DIR = os.path.join(ROOT, "results")

FEATURES = ["rg", "mean_dist", "std_dist", "clash_count", "density", "n_residues"]
RANDOM_STATE = 42


# ---------------------------------------------------------------------------
# Data loading
# ---------------------------------------------------------------------------
def load_data():
    df = pd.read_csv(DATA_PATH)
    df = df[df["label"] != -1].reset_index(drop=True)
    return df


# ---------------------------------------------------------------------------
# Split builders
# ---------------------------------------------------------------------------
def random_3way_split(df, seed=RANDOM_STATE):
    """Scenario A: 60/20/20 random split, ignoring target groups."""
    idx = np.arange(len(df))
    train, temp = train_test_split(idx, test_size=0.4, random_state=seed)
    val, test = train_test_split(temp, test_size=0.5, random_state=seed)
    return train, val, test


def group_3way_split(df):
    """
    Scenario B: target-level 3-way split.

    Train : 2cro, 4icb (largest two groups, ~60%)
    Val   : 1fc2       (~21%)
    Test  : 1hdd-C     (~17%)
    """
    train_targets = ["2cro", "4icb"]
    val_targets = ["1fc2"]
    test_targets = ["1hdd-C"]
    train_idx = df.index[df["target"].isin(train_targets)].to_numpy()
    val_idx = df.index[df["target"].isin(val_targets)].to_numpy()
    test_idx = df.index[df["target"].isin(test_targets)].to_numpy()
    return train_idx, val_idx, test_idx


# ---------------------------------------------------------------------------
# Tuning loops
# ---------------------------------------------------------------------------
def _auc(model, X_val, y_val):
    return roc_auc_score(y_val, model.predict_proba(X_val)[:, 1])


def tune_logreg(X_tr, y_tr, X_val, y_val):
    """Lecture 3 + Lecture 2: try L1 vs L2 with a small C grid."""
    best, best_auc, best_cfg = None, -1.0, None
    grid = [("l2", 0.1), ("l2", 1.0), ("l2", 10.0), ("l1", 1.0)]
    for penalty, C in grid:
        clf = LogisticRegression(
            penalty=penalty,
            C=C,
            solver="liblinear",
            class_weight="balanced",
            max_iter=2000,
            random_state=RANDOM_STATE,
        )
        clf.fit(X_tr, y_tr)
        auc = _auc(clf, X_val, y_val)
        if auc > best_auc:
            best, best_auc, best_cfg = clf, auc, {"penalty": penalty, "C": C}
    return best, best_cfg, best_auc


def tune_rf(X_tr, y_tr, X_val, y_val):
    best, best_auc, best_cfg = None, -1.0, None
    for n in [50, 100, 200]:
        for max_depth in [None, 6]:
            clf = RandomForestClassifier(
                n_estimators=n,
                max_depth=max_depth,
                class_weight="balanced",
                random_state=RANDOM_STATE,
            )
            clf.fit(X_tr, y_tr)
            auc = _auc(clf, X_val, y_val)
            if auc > best_auc:
                best, best_auc, best_cfg = clf, auc, {"n_estimators": n, "max_depth": max_depth}
    return best, best_cfg, best_auc


def tune_adaboost(X_tr, y_tr, X_val, y_val):
    best, best_auc, best_cfg = None, -1.0, None
    for n in [50, 100, 200]:
        for lr in [0.5, 1.0]:
            clf = AdaBoostClassifier(
                n_estimators=n,
                learning_rate=lr,
                random_state=RANDOM_STATE,
            )
            clf.fit(X_tr, y_tr)
            auc = _auc(clf, X_val, y_val)
            if auc > best_auc:
                best, best_auc, best_cfg = clf, auc, {"n_estimators": n, "learning_rate": lr}
    return best, best_cfg, best_auc


def tune_xgboost(X_tr, y_tr, X_val, y_val, scale_pos_weight):
    """Lecture 6: XGBoost. Fallback to sklearn GradientBoosting if xgboost absent."""
    best, best_auc, best_cfg = None, -1.0, None
    if HAS_XGB:
        for n in [100, 200]:
            for depth in [3, 5]:
                for lr in [0.05, 0.1]:
                    clf = XGBClassifier(
                        n_estimators=n,
                        max_depth=depth,
                        learning_rate=lr,
                        scale_pos_weight=scale_pos_weight,
                        eval_metric="logloss",
                        random_state=RANDOM_STATE,
                        n_jobs=2,
                        verbosity=0,
                    )
                    clf.fit(X_tr, y_tr)
                    auc = _auc(clf, X_val, y_val)
                    if auc > best_auc:
                        best, best_auc, best_cfg = clf, auc, {
                            "engine": "xgboost",
                            "n_estimators": n,
                            "max_depth": depth,
                            "learning_rate": lr,
                            "scale_pos_weight": scale_pos_weight,
                        }
    else:
        for n in [100, 200]:
            for depth in [3, 5]:
                for lr in [0.05, 0.1]:
                    clf = GradientBoostingClassifier(
                        n_estimators=n,
                        max_depth=depth,
                        learning_rate=lr,
                        random_state=RANDOM_STATE,
                    )
                    clf.fit(X_tr, y_tr)
                    auc = _auc(clf, X_val, y_val)
                    if auc > best_auc:
                        best, best_auc, best_cfg = clf, auc, {
                            "engine": "sklearn-gbm",
                            "n_estimators": n,
                            "max_depth": depth,
                            "learning_rate": lr,
                        }
    return best, best_cfg, best_auc


def tune_svm(X_tr, y_tr, X_val, y_val):
    best, best_auc, best_cfg = None, -1.0, None
    for C in [0.1, 1.0, 10.0]:
        for gamma in ["scale", 0.1, 1.0]:
            clf = SVC(
                kernel="rbf",
                C=C,
                gamma=gamma,
                probability=True,
                class_weight="balanced",
                random_state=RANDOM_STATE,
            )
            clf.fit(X_tr, y_tr)
            auc = _auc(clf, X_val, y_val)
            if auc > best_auc:
                best, best_auc, best_cfg = clf, auc, {"C": C, "gamma": gamma}
    return best, best_cfg, best_auc


# ---------------------------------------------------------------------------
# Evaluation helper
# ---------------------------------------------------------------------------
def evaluate(model, X_test, y_test):
    proba = model.predict_proba(X_test)[:, 1]
    pred = model.predict(X_test)
    return {
        "accuracy": float(accuracy_score(y_test, pred)),
        "f1": float(f1_score(y_test, pred, zero_division=0)),
        "roc_auc": float(roc_auc_score(y_test, proba)),
        "confusion_matrix": confusion_matrix(y_test, pred).tolist(),
        "report": classification_report(y_test, pred, zero_division=0),
        "_proba": proba,
        "_pred": pred,
    }


# ---------------------------------------------------------------------------
# Per-scenario runner
# ---------------------------------------------------------------------------
def run_scenario(name, df, train_idx, val_idx, test_idx):
    X = df[FEATURES].to_numpy()
    y = df["label"].to_numpy()

    X_tr, X_val, X_te = X[train_idx], X[val_idx], X[test_idx]
    y_tr, y_val, y_te = y[train_idx], y[val_idx], y[test_idx]

    scaler = StandardScaler().fit(X_tr)
    X_tr_s = scaler.transform(X_tr)
    X_val_s = scaler.transform(X_val)
    X_te_s = scaler.transform(X_te)

    pos = max(int((y_tr == 1).sum()), 1)
    neg = max(int((y_tr == 0).sum()), 1)
    scale_pos_weight = neg / pos

    print(f"\n========== Scenario {name} ==========")
    print(f"sizes: train={len(y_tr)}  val={len(y_val)}  test={len(y_te)}")
    print(f"train class balance: 0={neg}  1={pos}  -> scale_pos_weight={scale_pos_weight:.3f}")

    runners = [
        ("LogReg", tune_logreg, True),
        ("RandomForest", tune_rf, False),
        ("AdaBoost", tune_adaboost, False),
        ("XGBoost", tune_xgboost, False),
        ("SVM_RBF", tune_svm, True),
    ]

    results = {}
    for model_name, tuner, needs_scaling in runners:
        Xa, Xb, Xc = (X_tr_s, X_val_s, X_te_s) if needs_scaling else (X_tr, X_val, X_te)
        if model_name == "XGBoost":
            best, cfg, val_auc = tuner(Xa, y_tr, Xb, y_val, scale_pos_weight)
        else:
            best, cfg, val_auc = tuner(Xa, y_tr, Xb, y_val)
        test_result = evaluate(best, Xc, y_te)
        results[model_name] = {
            "best_config": cfg,
            "val_roc_auc": float(val_auc),
            "test_accuracy": test_result["accuracy"],
            "test_f1": test_result["f1"],
            "test_roc_auc": test_result["roc_auc"],
            "test_confusion_matrix": test_result["confusion_matrix"],
            "test_classification_report": test_result["report"],
            "_test_proba": test_result["_proba"],
            "_test_pred": test_result["_pred"],
        }
        print(
            f"\n[{model_name}] best_cfg={cfg}\n"
            f"  val ROC-AUC={val_auc:.4f}\n"
            f"  test ROC-AUC={test_result['roc_auc']:.4f}  "
            f"F1={test_result['f1']:.4f}  ACC={test_result['accuracy']:.4f}\n"
            f"  test CM={test_result['confusion_matrix']}"
        )

    return {
        "y_test": y_te,
        "X_test_raw": X_te,
        "X_test_scaled": X_te_s,
        "results": results,
    }


# ---------------------------------------------------------------------------
# Plots
# ---------------------------------------------------------------------------
def plot_roc(scenario_name, y_true, model_results, out_path):
    plt.figure(figsize=(7, 6))
    for model_name, r in model_results.items():
        proba = r["_test_proba"]
        fpr, tpr, _ = roc_curve(y_true, proba)
        plt.plot(fpr, tpr, label=f"{model_name} (AUC={r['test_roc_auc']:.3f})")
    plt.plot([0, 1], [0, 1], "k--", alpha=0.5)
    plt.xlabel("False Positive Rate")
    plt.ylabel("True Positive Rate")
    plt.title(f"ROC Curves - {scenario_name}")
    plt.legend(loc="lower right", fontsize=9)
    plt.tight_layout()
    plt.savefig(out_path, dpi=150)
    plt.close()


def plot_confusion_matrices(scenario_name, model_results, out_path):
    n = len(model_results)
    cols = min(n, 3)
    rows = int(np.ceil(n / cols))
    fig, axes = plt.subplots(rows, cols, figsize=(4 * cols, 4 * rows))
    axes = np.array(axes).reshape(-1)
    for ax, (name, r) in zip(axes, model_results.items()):
        cm = np.array(r["test_confusion_matrix"])
        im = ax.imshow(cm, cmap="Blues")
        ax.set_title(f"{name}\nF1={r['test_f1']:.3f}, AUC={r['test_roc_auc']:.3f}")
        ax.set_xticks([0, 1]); ax.set_yticks([0, 1])
        ax.set_xticklabels(["Stable", "Defective"])
        ax.set_yticklabels(["Stable", "Defective"])
        ax.set_xlabel("Predicted")
        ax.set_ylabel("True")
        for i in range(cm.shape[0]):
            for j in range(cm.shape[1]):
                ax.text(j, i, str(cm[i, j]), ha="center", va="center",
                        color="white" if cm[i, j] > cm.max() / 2 else "black")
        fig.colorbar(im, ax=ax, fraction=0.046, pad=0.04)
    for ax in axes[len(model_results):]:
        ax.set_visible(False)
    fig.suptitle(f"Confusion Matrices - {scenario_name}", y=1.02, fontsize=13)
    plt.tight_layout()
    plt.savefig(out_path, dpi=150, bbox_inches="tight")
    plt.close()


def plot_pca(df, out_path):
    X = StandardScaler().fit_transform(df[FEATURES])
    y = df["label"].to_numpy()
    pca = PCA(n_components=2, random_state=RANDOM_STATE)
    Z = pca.fit_transform(X)
    plt.figure(figsize=(7, 6))
    for cls, color, lab in [(0, "#1f77b4", "Stable"), (1, "#d62728", "Defective")]:
        m = y == cls
        plt.scatter(Z[m, 0], Z[m, 1], c=color, s=14, alpha=0.55, label=lab)
    var = pca.explained_variance_ratio_
    plt.xlabel(f"PC1 ({var[0]*100:.1f}%)")
    plt.ylabel(f"PC2 ({var[1]*100:.1f}%)")
    plt.title("PCA 2D Embedding of Geometric Features")
    plt.legend()
    plt.tight_layout()
    plt.savefig(out_path, dpi=150)
    plt.close()
    return var


def plot_feature_importance(model, out_path):
    importances = model.feature_importances_
    order = np.argsort(importances)[::-1]
    plt.figure(figsize=(8, 5))
    plt.title("Random Forest Feature Importance (MDI)")
    plt.bar(range(len(FEATURES)), importances[order], color="#4C72B0")
    plt.xticks(range(len(FEATURES)), [FEATURES[i] for i in order], rotation=30)
    plt.ylabel("Importance")
    plt.tight_layout()
    plt.savefig(out_path, dpi=150)
    plt.close()


# ---------------------------------------------------------------------------
# Serialization
# ---------------------------------------------------------------------------
def strip_arrays(scenario_payload):
    """Drop numpy arrays before JSON dump."""
    out = {}
    for k, v in scenario_payload["results"].items():
        out[k] = {kk: vv for kk, vv in v.items() if not kk.startswith("_")}
    return out


def main():
    os.makedirs(FIGURES_DIR, exist_ok=True)
    os.makedirs(RESULTS_DIR, exist_ok=True)

    df = load_data()
    print(f"Loaded {len(df)} samples across targets: {sorted(df['target'].unique())}")
    print(df["target"].value_counts())

    # PCA (visualization only, Lecture 10)
    var = plot_pca(df, os.path.join(FIGURES_DIR, "pca_analysis.png"))
    print(f"PCA explained variance: PC1={var[0]:.3f} PC2={var[1]:.3f}")

    # Scenario A
    tr_A, val_A, te_A = random_3way_split(df)
    payload_A = run_scenario("A (Random 3-way split)", df, tr_A, val_A, te_A)

    # Scenario B
    tr_B, val_B, te_B = group_3way_split(df)
    payload_B = run_scenario("B (Target-level 3-way split)", df, tr_B, val_B, te_B)

    # Plots
    plot_roc("Scenario A", payload_A["y_test"], payload_A["results"],
             os.path.join(FIGURES_DIR, "roc_scenario_A.png"))
    plot_roc("Scenario B", payload_B["y_test"], payload_B["results"],
             os.path.join(FIGURES_DIR, "roc_scenario_B.png"))
    plot_confusion_matrices("Scenario A", payload_A["results"],
                            os.path.join(FIGURES_DIR, "confusion_matrix_A.png"))
    plot_confusion_matrices("Scenario B", payload_B["results"],
                            os.path.join(FIGURES_DIR, "confusion_matrix_B.png"))

    # Feature importance from Scenario B RF (more realistic generalization view)
    rf_B = None
    # rebuild a quick RF on scenario B train set using the chosen config
    cfg = payload_B["results"]["RandomForest"]["best_config"]
    rf_B = RandomForestClassifier(
        n_estimators=cfg["n_estimators"],
        max_depth=cfg["max_depth"],
        class_weight="balanced",
        random_state=RANDOM_STATE,
    )
    X = df[FEATURES].to_numpy()
    y = df["label"].to_numpy()
    rf_B.fit(X[tr_B], y[tr_B])
    plot_feature_importance(rf_B, os.path.join(FIGURES_DIR, "feature_importance_rf.png"))

    # Serialize
    out = {
        "scenario_A": strip_arrays(payload_A),
        "scenario_B": strip_arrays(payload_B),
        "pca_explained_variance": [float(v) for v in var],
        "features": FEATURES,
        "n_samples": int(len(df)),
        "targets": sorted(df["target"].unique().tolist()),
        "xgboost_engine": "xgboost" if HAS_XGB else "sklearn-gbm-fallback",
    }
    with open(os.path.join(RESULTS_DIR, "experiment_results.json"), "w", encoding="utf-8") as f:
        json.dump(out, f, indent=2, ensure_ascii=False)
    print(f"\nSaved experiment_results.json")
    print(f"Figures saved under: {FIGURES_DIR}")


if __name__ == "__main__":
    main()
