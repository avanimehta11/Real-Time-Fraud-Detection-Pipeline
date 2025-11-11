import os
import json
import joblib
import pandas as pd
from pathlib import Path
from sklearn.model_selection import train_test_split
from sklearn.preprocessing import StandardScaler
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import classification_report, roc_auc_score

RAW_CSV = Path("data/raw/creditcard.csv")
ARTIFACT_DIR = Path("artifacts")
MODEL_PATH = ARTIFACT_DIR / "fraud_model.pkl"
SCALER_PATH = ARTIFACT_DIR / "scaler.pkl"
FEATURES_PATH = ARTIFACT_DIR / "feature_names.json"


def ensure_dirs():
	ARTIFACT_DIR.mkdir(parents=True, exist_ok=True)


def load_data() -> pd.DataFrame:
	if not RAW_CSV.exists():
		raise FileNotFoundError(f"Dataset not found at {RAW_CSV}. Place creditcard.csv there.")
	return pd.read_csv(RAW_CSV)


def preprocess(df: pd.DataFrame):
	# Features V1..V28 + Amount (+ optionally Time)
	feature_cols = [f"V{i}" for i in range(1, 29)] + ["Amount"]
	# Normalize Amount only (PCA components already scaled); Time is often dropped
	scaler = StandardScaler()
	df_feat = df[feature_cols].copy()
	df_feat[["Amount"]] = scaler.fit_transform(df_feat[["Amount"]])
	X = df_feat.values
	y = df["Class"].values
	return X, y, scaler, feature_cols


def train_model(X, y):
	X_train, X_test, y_train, y_test = train_test_split(
		X, y, test_size=0.2, random_state=42, stratify=y
	)
	model = LogisticRegression(max_iter=200, class_weight="balanced", n_jobs=-1)
	model.fit(X_train, y_train)
	proba = model.predict_proba(X_test)[:, 1]
	preds = (proba >= 0.5).astype(int)
	print("AUC:", roc_auc_score(y_test, proba))
	print(classification_report(y_test, preds, digits=4))
	return model


def save_artifacts(model, scaler, feature_cols):
	joblib.dump(model, MODEL_PATH)
	joblib.dump(scaler, SCALER_PATH)
	with open(FEATURES_PATH, "w", encoding="utf-8") as f:
		json.dump(feature_cols, f)
	print(f"Saved model -> {MODEL_PATH}")
	print(f"Saved scaler -> {SCALER_PATH}")
	print(f"Saved features -> {FEATURES_PATH}")


def main():
	ensure_dirs()
	df = load_data()
	X, y, scaler, feature_cols = preprocess(df)
	model = train_model(X, y)
	save_artifacts(model, scaler, feature_cols)


if __name__ == "__main__":
	main()


