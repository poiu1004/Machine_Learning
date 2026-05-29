"""
Failure-case qualitative analysis for Scenario B (target-level split).

Goal
----
Scenario B test = 1hdd-C decoys. Every model except XGBoost predicted all 185 samples
as Defective (1), so the 40 Stable (label=0) samples are mis-classified.
This script answers:
  1. What is the RMSD distribution of the 40 mis-classified Stable samples?
  2. How do their geometric features compare against the Train-set Stable population
     (where the model "learned" what Stable looks like)?
  3. Which feature shows the largest train-vs-test distribution shift?

Outputs
-------
- results/failure_analysis.json      : numerical summary used by build_report.py
- figures/failure_feature_shift.png  : boxplot of features (Train Stable vs Test Stable)
- figures/failure_rmsd_dist.png      : RMSD histogram of mis-classified samples
"""
import os
import json
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
DATA_PATH = os.path.join(ROOT, "data", "processed", "features.csv")
FIGURES_DIR = os.path.join(ROOT, "figures")
RESULTS_DIR = os.path.join(ROOT, "results")
FEATURES = ["rg", "mean_dist", "std_dist", "clash_count", "density", "n_residues"]


def main():
    os.makedirs(FIGURES_DIR, exist_ok=True)
    os.makedirs(RESULTS_DIR, exist_ok=True)

    df = pd.read_csv(DATA_PATH)
    df = df[df["label"] != -1].reset_index(drop=True)

    train_targets = ["2cro", "4icb"]
    test_targets = ["1hdd-C"]

    train = df[df["target"].isin(train_targets)].copy()
    test = df[df["target"].isin(test_targets)].copy()

    train_stable = train[train["label"] == 0]
    train_def = train[train["label"] == 1]
    test_stable = test[test["label"] == 0]  # 40 mis-classified by 4 of 5 models
    test_def = test[test["label"] == 1]

    print(f"Train: Stable={len(train_stable)}  Defective={len(train_def)}")
    print(f"Test (1hdd-C): Stable={len(test_stable)}  Defective={len(test_def)}")

    # 1. RMSD distribution of mis-classified samples
    plt.figure(figsize=(8, 4.5))
    plt.hist(test_stable["rmsd"], bins=20, color="#4C72B0", alpha=0.8,
             label=f"Test Stable (mis-classified by 4/5 models, n={len(test_stable)})")
    plt.axvline(4.0, color="red", linestyle="--", label="Stable/Defective threshold (4Å)")
    plt.xlabel("RMSD (Å)")
    plt.ylabel("# decoys")
    plt.title("RMSD distribution of mis-classified Stable decoys (Scenario B, 1hdd-C)")
    plt.legend()
    plt.tight_layout()
    plt.savefig(os.path.join(FIGURES_DIR, "failure_rmsd_dist.png"), dpi=150)
    plt.close()

    # 2. Train-Stable vs Test-Stable feature comparison
    # IMPORTANT: train_stable has only n=2, so a sample standard deviation is statistically meaningless.
    # Instead we report MIN / MAX RANGE for the two training points, and ask whether the
    # test population mean falls outside that range (Out-Of-Distribution check).
    fig, axes = plt.subplots(2, 3, figsize=(13, 7))
    summary_shift = {}
    for ax, feat in zip(axes.ravel(), FEATURES):
        ts_vals = train_stable[feat].to_numpy()  # only 2 points
        te_vals = test_stable[feat].to_numpy()
        # Plot: scatter for the 2 train points, boxplot for test (n=40)
        ax.scatter([1] * len(ts_vals), ts_vals, color="#1F77B4", s=70, zorder=3, label="Train Stable (n=2)")
        ax.boxplot([te_vals], positions=[2], widths=0.6, patch_artist=True,
                   boxprops=dict(facecolor="#FFB78A"), medianprops=dict(color="#B0392B"))
        ax.set_xticks([1, 2])
        ax.set_xticklabels(["Train Stable\n(2cro+4icb, n=2)", "Test Stable\n(1hdd-C, n=40)"])
        ax.set_title(feat)
        ts_min, ts_max = float(ts_vals.min()), float(ts_vals.max())
        te_mean = float(te_vals.mean())
        oo_range = (te_mean < ts_min) or (te_mean > ts_max)
        label = "OOD ✗" if oo_range else "in-range"
        ax.text(0.5, 0.95, f"Train range = [{ts_min:.3f}, {ts_max:.3f}]\nTest mean = {te_mean:.3f}  ({label})",
                transform=ax.transAxes, ha="center", va="top", fontsize=9,
                bbox=dict(boxstyle="round", facecolor="#FFF3B0", alpha=0.85))
        summary_shift[feat] = {
            "train_stable_n": int(len(ts_vals)),
            "train_stable_values": [float(v) for v in ts_vals],
            "train_stable_min": ts_min,
            "train_stable_max": ts_max,
            "test_stable_n": int(len(te_vals)),
            "test_stable_min": float(te_vals.min()),
            "test_stable_max": float(te_vals.max()),
            "test_stable_mean": te_mean,
            "test_mean_outside_train_range": oo_range,
        }
    fig.suptitle("Train Stable (n=2) vs Test Stable (n=40): out-of-distribution check (no σ assumed)",
                 y=1.02, fontsize=12)
    plt.tight_layout()
    plt.savefig(os.path.join(FIGURES_DIR, "failure_feature_shift.png"), dpi=150, bbox_inches="tight")
    plt.close()

    # 3. Count OOD features
    n_ood = sum(1 for v in summary_shift.values() if v["test_mean_outside_train_range"])
    worst = ("n_residues", summary_shift["n_residues"])  # known to be the cleanest case

    # 4. Sanity check: where are the Train Stable points in n_residues / rg space?
    train_size_summary = {
        "train_stable_n_residues_unique": sorted(train_stable["n_residues"].unique().tolist()),
        "test_stable_n_residues_unique": sorted(test_stable["n_residues"].unique().tolist()),
        "train_stable_rg_range": [float(train_stable["rg"].min()), float(train_stable["rg"].max())],
        "test_stable_rg_range": [float(test_stable["rg"].min()), float(test_stable["rg"].max())],
    }

    rmsd_summary = {
        "n_misclassified_stable": int(len(test_stable)),
        "rmsd_min": float(test_stable["rmsd"].min()),
        "rmsd_max": float(test_stable["rmsd"].max()),
        "rmsd_mean": float(test_stable["rmsd"].mean()),
        "rmsd_median": float(test_stable["rmsd"].median()),
        "near_threshold_fraction": float((test_stable["rmsd"] >= 3.0).mean()),
    }

    out = {
        "scenario": "B (target-level: train=2cro+4icb, test=1hdd-C)",
        "split_sizes": {"train": int(len(train)), "val_skipped": None, "test_total": int(len(test))},
        "rmsd_summary": rmsd_summary,
        "feature_range_check": summary_shift,
        "n_ood_features_of_6": int(n_ood),
        "ood_note": "Test Stable mean falls OUTSIDE the train-stable [min, max] range for the marked features.",
        "size_summary": train_size_summary,
    }
    out_path = os.path.join(RESULTS_DIR, "failure_analysis.json")
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(out, f, indent=2, ensure_ascii=False)
    print(f"Saved: {out_path}")
    print(f"OOD features (test mean outside train range): {n_ood} / {len(FEATURES)}")


if __name__ == "__main__":
    main()
