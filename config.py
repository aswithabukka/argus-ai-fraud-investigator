"""Central configuration for Argus: model names, paths, and triage thresholds."""

import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

ROOT = Path(__file__).parent
DATA_DIR = ROOT / "data"
RESULTS_DIR = ROOT / "results"
AUDIT_DIR = RESULTS_DIR / "audit"
CASES_DIR = RESULTS_DIR / "cases"
PROMPTS_DIR = ROOT / "prompts"

EVAL_SET_PATH = DATA_DIR / "eval_set.csv"
TRANSACTIONS_PATH = DATA_DIR / "transactions.parquet"
PATTERN_STORE_PATH = ROOT / "memory" / "patterns.json"
METRICS_PATH = RESULTS_DIR / "metrics.csv"

# Gemini models. Gemini 2.5 Pro has a free-tier quota of ZERO, so on a free AI
# Studio key every agent must use Flash. The Critic is still a separate agent with
# a distinct verification role — on a paid tier, set CRITIC_MODEL to
# "gemini-2.5-pro" for stronger fact-checking. Override either via env var.
WORKHORSE_MODEL = os.getenv("ARGUS_WORKHORSE_MODEL", "gemini-2.5-flash")
CRITIC_MODEL = os.getenv("ARGUS_CRITIC_MODEL", "gemini-2.5-flash")
# Tiered routing: ambiguous / disagreeing / high-stakes cases are re-examined by
# the strong model (see agents/router.py). Needs a billed key — Pro has no free
# tier; on a free key set this to a flash variant.
STRONG_MODEL = os.getenv("ARGUS_STRONG_MODEL", "gemini-2.5-pro")

# Eval set construction (data/load_data.py)
EVAL_FRAUD_COUNT = 40
EVAL_LEGIT_COUNT = 40
RANDOM_SEED = 42

# Policy agent thresholds (PaySim amounts are in local currency units)
LARGE_TRANSFER_THRESHOLD = 200_000
BALANCE_DRAIN_RATIO = 0.95  # txn empties >=95% of the origin balance
VELOCITY_WINDOW_STEPS = 24  # PaySim step = 1 hour, so 24 steps = 1 day
VELOCITY_COUNT_THRESHOLD = 3

# Dispositions
ESCALATE = "ESCALATE"
CLEAR = "CLEAR"
