import os
import time
import json
import pandas as pd
from pathlib import Path
from kafka import KafkaProducer
from kafka.errors import KafkaError

CSV_PATH = Path("data/raw/creditcard.csv")
KAFKA_BOOTSTRAP = os.environ.get("KAFKA_BOOTSTRAP_SERVERS", "localhost:9092")
TOPIC = os.environ.get("KAFKA_TOPIC", "creditcard_stream")
SLEEP_SEC = float(os.environ.get("PRODUCER_SLEEP_SEC", "0.5"))


def main():
    if not CSV_PATH.exists():
        raise FileNotFoundError(f"Dataset not found at {CSV_PATH}")

    print(f"Reading source CSV: {CSV_PATH}")
    print(f"Streaming to Kafka topic '{TOPIC}' at {KAFKA_BOOTSTRAP}")

    producer = KafkaProducer(
        bootstrap_servers=KAFKA_BOOTSTRAP,
        value_serializer=lambda v: json.dumps(v).encode("utf-8"),
    )

    df = pd.read_csv(CSV_PATH)
    for index, row in df.iterrows():
        try:
            producer.send(TOPIC, row.to_dict()).get(timeout=10)
            print(f"Sent record {index + 1}/{len(df)}")
        except KafkaError as e:
            print(f"Kafka send failed: {e}")
        time.sleep(SLEEP_SEC)

    producer.flush()
    producer.close()
    print("Streaming complete")


if __name__ == "__main__":
    main()
