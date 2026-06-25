"""
train.py — Phase 7: three unsupervised base models, trained on NORMAL ONLY.

Each learns "healthy" from label==0 windows and flags deviation, so the system
can catch NOVEL anomalies it was never labelled for (the justification for not
just using a plain supervised model):
  - IsolationForest      -> outlier score      (-score_samples)
  - PCA reconstruction   -> z-scored recon MSE
  - TF Autoencoder       -> non-linear recon MSE

Produces three anomaly scores per window. Also writes the shared train/test
split + the three score columns into data/dataset_scored.parquet, which Phase 8
consumes (base models are fit ONLY on train-normal, so test scores are
out-of-sample -> no leakage into the meta-model).

Run:  python ai/base_models/train.py
"""
import json
import os
import random

import joblib
import numpy as np
import pandas as pd
import tensorflow as tf
from sklearn.decomposition import PCA
from sklearn.ensemble import IsolationForest
from sklearn.metrics import roc_auc_score
from sklearn.model_selection import train_test_split
from sklearn.preprocessing import StandardScaler

SEED = 42
random.seed(SEED); np.random.seed(SEED); tf.random.set_seed(SEED)

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
DATA = os.path.join(ROOT, "data")
MODELS = os.path.join(ROOT, "models")
os.makedirs(MODELS, exist_ok=True)


def build_autoencoder(d):
    m = tf.keras.Sequential([
        tf.keras.layers.Input((d,)),
        tf.keras.layers.Dense(16, activation="relu"),
        tf.keras.layers.Dense(8, activation="relu"),
        tf.keras.layers.Dense(16, activation="relu"),
        tf.keras.layers.Dense(d, activation="linear"),
    ])
    m.compile(optimizer="adam", loss="mse")
    return m


def main():
    df = pd.read_parquet(os.path.join(DATA, "features.parquet"))
    features = [c for c in df.columns if "__" in c]

    # shared stratified split (reused by Phase 8)
    idx_tr, idx_te = train_test_split(df.index, test_size=0.4, random_state=SEED,
                                      stratify=df["label"])
    df["split"] = "train"
    df.loc[idx_te, "split"] = "test"

    train_normal = df[(df.split == "train") & (df.label == 0)][features].values
    scaler = StandardScaler().fit(train_normal)
    Xn = scaler.transform(train_normal)

    # --- IsolationForest ---
    iforest = IsolationForest(n_estimators=200, random_state=SEED).fit(Xn)

    # --- PCA reconstruction ---
    # REGULARIZED: keep only a few dominant normal directions. A variance-ratio
    # target (0.95) on a SMALL normal set keeps ~n_samples-1 components, which
    # MEMORIZES the training-normal points and then explodes reconstruction error
    # on any benign drift at serve time (the false-positive baseline). A small
    # fixed rank captures the real normal structure (3 services x correlated RED
    # metrics) and GENERALIZES, while faults still project off-subspace -> high
    # recon. n_components is capped to a safe rank for the sample/feature size.
    n_comp = max(2, min(int(os.getenv("PCA_COMPONENTS", "5")), Xn.shape[0] - 1, Xn.shape[1]))
    pca = PCA(n_components=n_comp, random_state=SEED).fit(Xn)
    print(f"PCA rank = {n_comp} (from {Xn.shape[0]} train-normal windows)")

    def pca_recon(Xs):
        return ((Xs - pca.inverse_transform(pca.transform(Xs))) ** 2).mean(axis=1)
    rt = pca_recon(Xn)
    pca_mu, pca_sd = float(rt.mean()), float(rt.std() + 1e-9)

    # --- Autoencoder ---
    # Fewer epochs on a small normal set: 200 epochs memorizes the points (recon
    # ~0 on train-normal, high on benign serve drift). ~60 learns the manifold
    # and generalizes, keeping the fault/normal gap while taming false positives.
    ae = build_autoencoder(len(features))
    ae.fit(Xn, Xn, epochs=int(os.getenv("AE_EPOCHS", "60")), batch_size=8, verbose=0)

    # --- score every row ---
    Xall = scaler.transform(df[features].values)
    df["score_if"] = -iforest.score_samples(Xall)
    df["score_pca"] = (pca_recon(Xall) - pca_mu) / pca_sd
    df["score_ae"] = ((Xall - ae.predict(Xall, verbose=0)) ** 2).mean(axis=1)

    # --- evaluate on held-out test ---
    te = df[df.split == "test"]
    print(f"{'model':10} {'test AUC':>9} {'fault_mean':>11} {'normal_mean':>12}")
    report = {}
    for name in ["score_if", "score_pca", "score_ae"]:
        auc = roc_auc_score(te["label"], te[name])
        fm, nm = te[te.label == 1][name].mean(), te[te.label == 0][name].mean()
        report[name] = {"auc": float(auc), "fault_mean": float(fm), "normal_mean": float(nm)}
        print(f"{name:10} {auc:9.3f} {fm:11.3f} {nm:12.3f}")

    # --- persist ---
    joblib.dump({"scaler": scaler, "iforest": iforest, "pca": pca,
                 "pca_mu": pca_mu, "pca_sd": pca_sd, "features": features},
                os.path.join(MODELS, "base_models.joblib"))
    ae.save(os.path.join(MODELS, "autoencoder.keras"))
    df.to_parquet(os.path.join(DATA, "dataset_scored.parquet"), index=False)
    with open(os.path.join(MODELS, "base_report.json"), "w") as f:
        json.dump(report, f, indent=2)
    print(f"\nsaved base models -> {MODELS}; scored dataset -> {DATA}/dataset_scored.parquet")


if __name__ == "__main__":
    main()
