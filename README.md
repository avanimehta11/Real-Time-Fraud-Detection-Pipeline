# Real-Time Credit Card Fraud Detection

This project demonstrates a **real-time machine learning pipeline** for detecting fraudulent credit card transactions using **Kafka**, **scikit-learn**, **MongoDB**, and a **Streamlit dashboard**.  

It continuously streams transactions from the **Kaggle Credit Card Fraud dataset**, classifies each record using a trained ML model, stores results in MongoDB, and visualizes live fraud statistics in real time.

---

## Overview  

**Architecture summary:**
- **Data Ingestion** → Transaction data streamed from Kaggle dataset via **Kafka Producer**
- **Processing** → A **Python Kafka Consumer** runs a trained **scikit-learn model** to score transactions
- **Storage** → Predictions stored in **MongoDB**
- **Visualization** → A **Streamlit dashboard** connects to MongoDB and displays live metrics

---


## 📂 Project Structure
```  
.
├── app/
│   └── streamlit_app.py           # Live fraud analytics dashboard
├── data/
│   └── raw/creditcard.csv         # Source dataset (Kaggle)
├── src/
│   ├── ingestion/kafka_producer.py # Kafka producer for streaming data
│   └── models/train_model.py       # Model training script
├── artifacts/
│   ├── fraud_model.pkl             # Trained scikit-learn model
│   ├── scaler.pkl                  # Feature scaler
│   └── feature_names.json          # Feature list used in training
├── scripts/
│   └── create_topic.ps1            # Helper script to create Kafka topic
├── docker-compose.yml
├── requirements.txt
└── README.md
```

---

## ⚙️ Prerequisites
- **Python 3.12** on Windows Powershell.
- **Docker Desktop** (for MongoDB and the consumer container)
- **Kafka + Zookeeper** (installed locally or launched via Docker Compose)
- **Kaggle Credit Card Fraud Dataset** (`creditcard.csv`)

---

## Paths

| Description | Path |
|--------------|------|
| Raw dataset | `data/raw/creditcard.csv` |
| Model artifacts | `artifacts/fraud_model.pkl`, `artifacts/scaler.pkl`, `artifacts/feature_names.json` |

---

## Why MongoDB?
- Fast JSON/document sink for streaming results, easy to query and power Streamlit.
 - Enables fast queries for real-time analytics.

---  

## 🚀 Setup

> Configure runtime variables using `.env` (copy `.env.example` and update the values before starting the services).

1. **Create a Virtual environment**
   ```
   python -m venv .venv
   . .venv\Scripts\Activate.ps1
   pip install -r requirements.txt
   ```

2. **Add dataset**

   Copy your downloaded Kaggle dataset to: 
   ```
   data/raw/creditcard.csv
   ```


3. **Train Model & Generate Artifacts**
   ```
   python src/models/train_model.py
   ```

4. **Start Infrastructure with Docker**
   ```
   docker compose up -d --build mongo kafka zookeeper consumer
   ```
    - MongoDB → localhost:27018 (inside Docker: mongo:27017)
    - Kafka → localhost:9092 (inside Docker: kafka:9093)

5. **Create Kafka Topic**
   ```
   ./scripts/create_topic.ps1
   ```

6. **Stream data into Kafka**
   ```
   python src/ingestion/kafka_producer.py
   ```

7. **Launch Streamlit Dashboard**
   ```
   streamlit run app/streamlit_app.py
   ```
   Dashboard connects to MongoDB and visualizes live fraud predictions.

---
## Model Overview  

- **Algorithm:** Logistic Regression 
- **Input Features:** Standardized features from `creditcard.csv`  
- **Output:** Binary fraud classification (`0` = legitimate, `1` = fraud)  

Artifacts are serialized to the `artifacts/` directory for consistent inference.  

---

## 📊 Dashboard Features  

The Streamlit app displays:  
- Real-time fraud detection metrics  
- Transaction stream visualizations  
- Fraud vs. non-fraud trend charts  
- Live database insights from MongoDB  
