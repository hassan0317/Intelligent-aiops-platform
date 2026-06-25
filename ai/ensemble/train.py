"""
train.py — Phase 8: XGBoost meta-model + per-incident SHAP RCA (Fix #2 & #4).

Stack:  X = 24 service-prefixed features  +  [IF, PCA, AE] base scores  -> XGBoost.
Labels come from the chaos ground truth (Fix #2). Imbalance handled with
scale_pos_weight; PR-AUC is the headline metric (accuracy is misleading here).

RCA (Fix #4): per-INCIDENT SHAP (not global importance). The top SHAP feature
for THIS window, mapped through its service-prefixed name, names the ORIGIN
service -- e.g. payments_service__lat_p99 -> payments-service -- even though the
errors surface at frontend-api.

Validated quantitatively against fault_service (the Phase-5 ground truth):
"RCA named the correct origin in N% of injected incidents."

Run:  python ai/ensemble/train.py   (also: make train)
"""
import json
import os

import numpy as np
import pandas as pd
import shap
import xgboost as xgb
from sklearn.metrics import (average_precision_score, classification_report,
                             confusion_matrix, roc_auc_score)
from sklearn.model_selection import StratifiedKFold, cross_val_score

from rca import localize_origin  # shared topology-aware localizer

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
DATA = os.path.join(ROOT, "data")
MODELS = os.path.join(ROOT, "models")
SCORE_COLS = ["score_if", "score_pca", "score_ae"]


def rank_by_abs_shap(sv, names):
    return [(names[i], float(sv[i])) for i in np.argsort(-np.abs(sv))]


def main():
    df = pd.read_parquet(os.path.join(DATA, "dataset_scored.parquet"))
    feat_cols = [c for c in df.columns if "__" in c]
    FEATURES = feat_cols + SCORE_COLS

    tr, te = df[df.split == "train"], df[df.split == "test"]
    Xtr, ytr = tr[FEATURES].values, tr["label"].values
    Xte, yte = te[FEATURES].values, te["label"].values
    neg, pos = int((ytr == 0).sum()), int((ytr == 1).sum())
    spw = neg / max(pos, 1)
    print(f"train: {len(tr)} ({pos} pos / {neg} neg)  test: {len(te)}  scale_pos_weight={spw:.2f}")

    # regularised to avoid razor-thin splits on the (bimodal) base scores, which
    # otherwise flip benign operating-point shifts to "incident" on small data.
    clf = xgb.XGBClassifier(scale_pos_weight=spw, eval_metric="aucpr",
                            n_estimators=300, max_depth=4, learning_rate=0.1,
                            subsample=0.9, colsample_bytree=0.9, random_state=42)

    # cross-validated PR-AUC on train (imbalance-aware)
    cv = StratifiedKFold(n_splits=3, shuffle=True, random_state=42)
    cv_pr = cross_val_score(clf, Xtr, ytr, scoring="average_precision", cv=cv)
    print(f"CV PR-AUC (train, 3-fold): {cv_pr.mean():.3f} +/- {cv_pr.std():.3f}")

    clf.fit(Xtr, ytr)

    # --- headline metrics on held-out test ---
    p_te = clf.predict_proba(Xte)[:, 1]
    pred = (p_te >= 0.5).astype(int)
    pr_auc = average_precision_score(yte, p_te)
    roc = roc_auc_score(yte, p_te)
    cm = confusion_matrix(yte, pred)
    print(f"\nTEST PR-AUC={pr_auc:.3f}  ROC-AUC={roc:.3f}")
    print("confusion matrix [ [TN FP] [FN TP] ]:\n", cm)
    print(classification_report(yte, pred, target_names=["normal", "incident"], zero_division=0))

    # --- per-incident RCA: topology-aware localizer (shared with live path) ---
    norm = tr[tr.label == 0][feat_cols]
    nmu, nsd = norm.mean(), norm.std() + 1e-9
    nmu_d, nsd_d = nmu.to_dict(), nsd.to_dict()
    explainer = shap.TreeExplainer(clf)
    sv_te = explainer.shap_values(Xte)              # (n, n_features), positive-class margin
    inc_idx = np.where(yte == 1)[0]
    hits, rows = 0, []
    for i in inc_idx:
        raw = te.iloc[i][feat_cols].to_dict()
        origin = localize_origin(raw, nmu_d, nsd_d, sv=sv_te[i], names=FEATURES)
        truth = te.iloc[i]["fault_service"]
        hits += int(origin == truth)
        rows.append((te.iloc[i]["fault_type"], truth, origin, float(p_te[i])))
    rca = hits / max(len(inc_idx), 1)
    print(f"RCA hit-rate on test incidents: {hits}/{len(inc_idx)} = {rca:.1%}")

    # demonstrate a payments-injected incident: confirmed + origin named correctly
    print("\nsample test incidents (fault_type | true_origin | SHAP_origin | p_incident):")
    for ft, truth, origin, p in rows:
        flag = "OK" if origin == truth else "X"
        print(f"  [{flag}] {ft:8} | {truth:16} | {origin or '-':16} | {p:.3f}")

    # --- persist ---
    os.makedirs(MODELS, exist_ok=True)
    clf.save_model(os.path.join(MODELS, "xgb_meta.json"))
    meta = {"features": FEATURES, "threshold": 0.5,
            "scale_pos_weight": spw, "test_pr_auc": float(pr_auc),
            "test_roc_auc": float(roc), "cv_pr_auc": float(cv_pr.mean()),
            "rca_hit_rate": float(rca),
            "confusion_matrix": cm.tolist(),
            "norm_mean": nmu.to_dict(), "norm_std": nsd.to_dict()}  # for z-filtered RCA at inference
    with open(os.path.join(MODELS, "ensemble_report.json"), "w") as f:
        json.dump(meta, f, indent=2)
    print(f"\nsaved meta-model -> {MODELS}/xgb_meta.json ; report -> {MODELS}/ensemble_report.json")


if __name__ == "__main__":
    main()
