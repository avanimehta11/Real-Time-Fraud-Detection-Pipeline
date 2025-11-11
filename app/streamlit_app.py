import os
import time
import pymongo
import pandas as pd
import streamlit as st
from pymongo.errors import PyMongoError

try:
	from dotenv import load_dotenv
except ImportError:
	load_dotenv = None

if load_dotenv is not None:
	load_dotenv()

MONGO_URI = os.environ.get("MONGO_URI", "mongodb://localhost:27017")
DB = os.environ.get("MONGO_DB", "fraudDB")
COLL = os.environ.get("MONGO_COLLECTION", "transactions")
DEFAULT_REFRESH_SEC = float(os.environ.get("DASHBOARD_REFRESH_SEC", "2"))
DEFAULT_LIMIT = int(os.environ.get("DASHBOARD_LIMIT", "10000"))
DEFAULT_THEME = os.environ.get("DASHBOARD_THEME", "Dark").strip().capitalize()
if DEFAULT_THEME not in {"Light", "Dark"}:
	DEFAULT_THEME = "Dark"

st.set_page_config(page_title="Fraud Monitor", layout="wide")
st.title("Real-Time Fraud Detection Dashboard")

if "theme" not in st.session_state:
	st.session_state["theme"] = DEFAULT_THEME
if "refresh_sec" not in st.session_state:
	st.session_state["refresh_sec"] = DEFAULT_REFRESH_SEC
if "row_limit" not in st.session_state:
	st.session_state["row_limit"] = DEFAULT_LIMIT
if "table_filter" not in st.session_state:
	st.session_state["table_filter"] = "All transactions"


def apply_theme(theme: str) -> None:
	if theme == "Dark":
		css = """
		body, .stApp { background-color: #0E1117; color: #E0E0E0; }
		[data-testid="metric-container"] { background: #1B1F24; border-radius: 12px; padding: 16px; }
		[data-testid="stMetricValue"] { color: #F2F2F2; }
		[data-testid="stMetricDelta"] { color: #A0C1FF; }
		.stTabs [role="tablist"] { border-bottom: 1px solid #262B33; }
		.stTabs [role="tab"] { color: #E0E0E0; }
		"""
	else:
		css = """
		body, .stApp { background-color: #F5F7FA; color: #222; }
		[data-testid="metric-container"] { background: #FFFFFF; border-radius: 12px; padding: 16px; box-shadow: 0 2px 6px rgba(15, 23, 42, 0.08); }
		[data-testid="metric-container"] label, [data-testid="stMetricLabel"] { color: #1F2A37 !important; font-weight: 600; }
		[data-testid="stMetricValue"] { color: #101B33; }
		[data-testid="stMetricDelta"] { color: #1F4B99; }
		.stTabs [role="tablist"] { border-bottom: 1px solid #D7DFE9; }
		.stTabs [role="tab"] { color: #1F2A37; }
		h1, h2, h3, h4, h5, h6, .stMarkdown p strong { color: #1F2A37; }
		"""
	st.markdown(f"<style>{css}</style>", unsafe_allow_html=True)


def theme_sidebar():
	with st.sidebar:
		st.header("Dashboard Controls")
		theme_choice = st.radio(
			"Theme",
			("Dark", "Light"),
			index=0 if st.session_state["theme"] == "Dark" else 1,
		)
		st.session_state["theme"] = theme_choice

		refresh_choice = st.slider(
			"Refresh interval (seconds)",
			min_value=0.5,
			max_value=10.0,
			value=float(st.session_state["refresh_sec"]),
			step=0.5,
		)
		st.session_state["refresh_sec"] = refresh_choice

		row_limit_choice = st.number_input(
			"Rows to fetch from MongoDB",
			min_value=100,
			max_value=20000,
			value=int(st.session_state["row_limit"]),
			step=100,
		)
		st.session_state["row_limit"] = row_limit_choice

		filter_choice = st.selectbox(
			"Transactions shown in table",
			("All transactions", "Flagged only"),
			index=0 if st.session_state["table_filter"] == "All transactions" else 1,
		)
		st.session_state["table_filter"] = filter_choice

		st.caption(f"MongoDB URI: {MONGO_URI}")


apply_theme(st.session_state["theme"])
theme_sidebar()
apply_theme(st.session_state["theme"])

@st.cache_resource
def get_client():
	return pymongo.MongoClient(MONGO_URI, serverSelectionTimeoutMS=5000)

def load_latest(limit=10000):
	"""
	pull back a rolling window of documents plus aggregate stats so the header
	metrics stay accurate even when we have more than `limit` rows live.
	"""
	client = get_client()
	coll = client[DB][COLL]

	total_docs = coll.estimated_document_count()
	fraud_docs = coll.count_documents({"prediction": 1})

	cutoff_dt = pd.Timestamp.now(tz="UTC") - pd.Timedelta(seconds=60)
	rows_last_min = coll.count_documents({"ingest_ts": {"$gte": cutoff_dt.isoformat()}})

	cur = coll.find({}, {"_id": 0}).sort("ingest_ts", -1).limit(limit)
	docs = list(cur)
	df = pd.DataFrame(docs)

	if df.empty:
		stats = {
			"total": total_docs,
			"frauds": fraud_docs,
			"rows_last_min": rows_last_min,
			"last_ingest": None,
		}
		return df, stats

	if "ingest_ts" in df.columns:
		df = df.copy()
		df["ingest_ts"] = pd.to_datetime(df["ingest_ts"], utc=True, errors="coerce")
		last_ingest = df["ingest_ts"].max()
	else:
		last_ingest = None

	stats = {
		"total": total_docs,
		"frauds": fraud_docs,
		"rows_last_min": rows_last_min,
		"last_ingest": last_ingest,
	}
	return df, stats

placeholder = st.empty()

while True:
	try:
		limit = int(st.session_state.get("row_limit", DEFAULT_LIMIT))
		df, stats = load_latest(limit=limit)
		error = None
	except PyMongoError as e:
		df = pd.DataFrame()
		stats = {"total": 0, "frauds": 0, "rows_last_min": 0, "last_ingest": None}
		error = str(e)
	except Exception as e:
		df = pd.DataFrame()
		stats = {"total": 0, "frauds": 0, "rows_last_min": 0, "last_ingest": None}
		error = str(e)

	with placeholder.container():
		if error:
			st.error(f"Could not load data from MongoDB: {error}")
			st.caption(f"Mongo URI: {MONGO_URI} | DB: {DB} | Coll: {COLL}")
			if st.button("Retry now", key="retry_mongo"):
				st.experimental_rerun()
			time.sleep(float(st.session_state.get("refresh_sec", DEFAULT_REFRESH_SEC)))
			continue

		col1, col2, col3, col4 = st.columns(4)

		total = int(stats["total"])
		frauds = int(stats["frauds"])
		rate = (frauds / total * 100) if total else 0.0

		last_ts = stats.get("last_ingest")
		if last_ts is not None and pd.isna(last_ts):
			last_ts = None

		if last_ts is not None:
			now_utc = pd.Timestamp.now(tz="UTC")
			age_sec = (now_utc - last_ts).total_seconds()
		else:
			age_sec = None

		rows_last_min = int(stats["rows_last_min"])
		throughput = rows_last_min / 60.0 if rows_last_min else 0.0

		col1.metric("Total Rows", f"{total}")
		col2.metric("Fraudulent", f"{frauds}")
		col3.metric("Fraud Rate", f"{rate:.2f}%")
		col4.metric("Throughput (rows/s)", f"{throughput:.2f}")

		if total and age_sec is not None:
			status = "🟢 Live" if age_sec < 10 else "🟡 Idle" if age_sec < 60 else "🔴 Stale"
			st.markdown(f"**Status**: {status} | Last event: {last_ts} (age {age_sec:.1f}s)")
		else:
			st.markdown("**Status**: No data yet")

		if not df.empty:
			charts_tab, table_tab = st.tabs(["Charts & Insights", "Recent Transactions"])

			with charts_tab:
				if "prediction" in df.columns:
					counts = (
						df["prediction"]
						.value_counts()
						.rename(index={0: "Legit", 1: "Fraud"})
						.sort_index()
					)
					st.subheader("Predictions Breakdown")
					st.bar_chart(counts)

				if {"prediction", "probability", "ingest_ts"}.issubset(df.columns):
					chart_df = (
						df[["ingest_ts", "probability", "prediction"]]
						.sort_values("ingest_ts")
						.tail(200)
						.copy()
					)
					if not chart_df.empty:
						if isinstance(chart_df["ingest_ts"].dtype, pd.DatetimeTZDtype):
							chart_df["ingest_ts"] = chart_df["ingest_ts"].dt.tz_convert(None)
						chart_df = chart_df.set_index("ingest_ts")
						st.subheader("Probability Trend (latest 200 rows)")
						st.line_chart(chart_df["probability"])

				if {"prediction", "Class"}.issubset(df.columns):
					st.subheader("Prediction vs Ground Truth (if available)")
					ct = pd.crosstab(
						df["Class"],
						df["prediction"],
						rownames=["Class"],
						colnames=["Pred"],
						dropna=False,
					)
					st.dataframe(ct)

				if "probability" in df.columns:
					st.subheader("Top Suspicious Transactions")
					cols_to_show = [
						col
						for col in ["ingest_ts", "probability", "prediction", "Amount", "Class"]
						if col in df.columns
					]
					topk = df.sort_values("probability", ascending=False)[cols_to_show].head(20)
					st.dataframe(topk)

			with table_tab:
				table_df = df.copy()
				if (
					st.session_state.get("table_filter") == "Flagged only"
					and "prediction" in table_df.columns
				):
					table_df = table_df[table_df["prediction"] == 1]

				table_preview = table_df.head(500)
				if not table_preview.empty:
					dl_name = f"fraud_transactions_{pd.Timestamp.utcnow().strftime('%Y%m%dT%H%M%SZ')}.csv"
					st.download_button(
						"Download visible rows",
						table_preview.to_csv(index=False).encode("utf-8"),
						file_name=dl_name,
						mime="text/csv",
					)
				st.dataframe(table_preview)

	time.sleep(float(st.session_state.get("refresh_sec", DEFAULT_REFRESH_SEC)))
