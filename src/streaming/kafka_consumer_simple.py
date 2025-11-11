import json
import logging
import os
import signal
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List

import joblib
import pandas as pd
from pymongo import MongoClient
from pymongo.errors import PyMongoError

try:
	from kafka import KafkaConsumer
	from kafka.errors import KafkaError
except ModuleNotFoundError as exc:
	if "kafka.vendor.six.moves" in str(exc):
		import six
		import sys
		import types

		vendor_module = types.ModuleType("kafka.vendor")
		vendor_module.__path__ = []
		vendor_module.six = six  # type: ignore[attr-defined]
		sys.modules.setdefault("kafka.vendor", vendor_module)
		sys.modules.setdefault("kafka.vendor.six", six)
		sys.modules.setdefault("kafka.vendor.six.moves", six.moves)
		from kafka import KafkaConsumer  # type: ignore[assignment]
		from kafka.errors import KafkaError  # type: ignore[assignment,misc]
	else:
		raise

try:
	from dotenv import load_dotenv
except ImportError:  # pragma: no cover
	load_dotenv = None

LOG_LEVEL = os.environ.get("LOG_LEVEL", "INFO").upper()
logging.basicConfig(
	level=getattr(logging, LOG_LEVEL, logging.INFO),
	format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
	stream=sys.stdout,
)
logger = logging.getLogger("consumer.simple")


def maybe_load_dotenv():
	if load_dotenv is None:
		return
	# load from .env if present; silently ignore missing file
	load_dotenv()


def load_artifacts() -> Dict[str, object]:
	root = Path(os.environ.get("ARTIFACT_DIR", "artifacts"))
	model_path = Path(os.environ.get("MODEL_PATH", root / "fraud_model.pkl"))
	scaler_path = Path(os.environ.get("SCALER_PATH", root / "scaler.pkl"))
	features_path = Path(os.environ.get("FEATURES_PATH", root / "feature_names.json"))
	threshold_path = Path(os.environ.get("THRESHOLD_PATH", root / "threshold.json"))
	default_threshold = float(os.environ.get("MODEL_THRESHOLD", "0.5"))

	missing = [
		str(path)
		for path in [model_path, scaler_path, features_path]
		if not Path(path).exists()
	]
	if missing:
		raise FileNotFoundError(
			"Artifacts missing. Train the model first so these exist: " + ", ".join(missing)
		)

	model = joblib.load(model_path)
	scaler = joblib.load(scaler_path)
	with open(features_path, "r", encoding="utf-8") as f:
		features: List[str] = json.load(f)

	if Path(threshold_path).exists():
		with open(threshold_path, "r", encoding="utf-8") as f:
			thr_obj = json.load(f) or {}
		threshold = float(thr_obj.get("threshold", default_threshold))
	else:
		threshold = default_threshold

	logger.info("Loaded artifacts (%s features, threshold=%.3f)", len(features), threshold)
	return {
		"model": model,
		"scaler": scaler,
		"features": features,
		"threshold": threshold,
	}


def make_kafka_consumer() -> KafkaConsumer:
	topic = os.environ.get("KAFKA_TOPIC", "creditcard_stream")
	bootstrap = os.environ.get("KAFKA_BOOTSTRAP_SERVERS", "localhost:9092")
	group_id = os.environ.get("KAFKA_GROUP_ID", "fraud-consumer")

	logger.info("Connecting to Kafka %s (topic=%s, group=%s)", bootstrap, topic, group_id)
	return KafkaConsumer(
		topic,
		bootstrap_servers=bootstrap,
		group_id=group_id,
		enable_auto_commit=True,
		auto_offset_reset=os.environ.get("KAFKA_AUTO_OFFSET_RESET", "earliest"),
		value_deserializer=lambda m: json.loads(m.decode("utf-8")),
		max_poll_interval_ms=int(os.environ.get("KAFKA_MAX_POLL_INTERVAL_MS", "300000")),
	)


def make_mongo_client() -> MongoClient:
	uri = os.environ.get("MONGO_URI", "mongodb://localhost:27017")
	logger.info("Connecting to MongoDB %s", uri)
	return MongoClient(uri, serverSelectionTimeoutMS=5000)


def transform_row(payload: Dict[str, object], artifacts: Dict[str, object]) -> Dict[str, object]:
	features: List[str] = artifacts["features"]
	model = artifacts["model"]
	scaler = artifacts["scaler"]
	threshold: float = artifacts["threshold"]

	df = pd.DataFrame([payload])

	# ensure all expected features exist
	for col in features:
		if col not in df.columns:
			df[col] = 0.0

	df = df[features].astype(float)

	# amount scaling (scaler trained on Amount column only)
	if "Amount" in df.columns:
		df["Amount"] = scaler.transform(df[["Amount"]])

	proba = model.predict_proba(df.values)[:, 1]
	pred = (proba >= threshold).astype(int)

	doc = dict(payload)
	doc["probability"] = float(proba[0])
	doc["prediction"] = int(pred[0])
	doc["ingest_ts"] = datetime.now(timezone.utc).isoformat()
	return doc


def main():
	maybe_load_dotenv()
	artifacts = load_artifacts()
	consumer = make_kafka_consumer()
	mongo_client = make_mongo_client()
	db = os.environ.get("MONGO_DB", "fraudDB")
	coll_name = os.environ.get("MONGO_COLLECTION", "transactions")
	collection = mongo_client[db][coll_name]

	running = True

	def _graceful_shutdown(signum, _frame):
		nonlocal running
		logger.info("Received signal %s, shutting down...", signum)
		running = False

	for sig in (signal.SIGINT, signal.SIGTERM):
		signal.signal(sig, _graceful_shutdown)

	logger.info("Consumer ready. Writing to MongoDB %s.%s", db, coll_name)

	try:
		while running:
			msg_pack = consumer.poll(timeout_ms=1000)
			if not msg_pack:
				continue

			for tp, records in msg_pack.items():
				for record in records:
					try:
						payload = record.value
						doc = transform_row(payload, artifacts)
						collection.insert_one(doc)
						logger.info(
							"offset=%s pred=%d prob=%.3f amount=%s",
							record.offset,
							doc["prediction"],
							doc["probability"],
							payload.get("Amount"),
						)
					except (KeyError, ValueError) as err:
						logger.warning("Payload parsing failed offset=%s err=%s", record.offset, err)
					except PyMongoError as err:
						logger.error("Mongo insert failed offset=%s err=%s", record.offset, err)
					except Exception as err:  # pragma: no cover
						logger.exception("Unexpected error for offset=%s: %s", record.offset, err)
	except KafkaError as err:
		logger.error("Kafka error: %s", err)
	finally:
		logger.info("Closing consumer...")
		consumer.close()
		mongo_client.close()


if __name__ == "__main__":
	main()

