"""
score.py — reusable loader for the three Phase-7 base models.

Used by the online inference loop (Phase 9) to turn a window's feature vector
into the three anomaly scores [IF, PCA, AE] that feed the XGBoost meta-model.
"""
import os

import joblib
import numpy as np
import tensorflow as tf

MODELS = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "models"))


class BaseScorer:
    def __init__(self, models_dir: str = MODELS):
        b = joblib.load(os.path.join(models_dir, "base_models.joblib"))
        self.scaler = b["scaler"]
        self.iforest = b["iforest"]
        self.pca = b["pca"]
        self.pca_mu = b["pca_mu"]
        self.pca_sd = b["pca_sd"]
        self.features = b["features"]
        self.ae = tf.keras.models.load_model(os.path.join(models_dir, "autoencoder.keras"))

    def scores(self, x) -> np.ndarray:
        """x: feature vector(s) ordered as self.features. Returns (n, 3) = [IF, PCA, AE]."""
        X = np.atleast_2d(np.asarray(x, dtype=float))
        Xs = self.scaler.transform(X)
        s_if = -self.iforest.score_samples(Xs)
        recon = ((Xs - self.pca.inverse_transform(self.pca.transform(Xs))) ** 2).mean(axis=1)
        s_pca = (recon - self.pca_mu) / self.pca_sd
        s_ae = ((Xs - self.ae.predict(Xs, verbose=0)) ** 2).mean(axis=1)
        return np.column_stack([s_if, s_pca, s_ae])
