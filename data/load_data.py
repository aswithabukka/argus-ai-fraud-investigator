"""Download PaySim, cache it locally, and build the balanced eval set.

PaySim is a synthetic mobile-money dataset (~6.3M transactions) with an
`isFraud` ground-truth label. Fraud in PaySim only occurs in TRANSFER and
CASH_OUT transactions, so the "legit" half of the eval set is sampled from
large TRANSFER/CASH_OUT rows — plausible false-positive alerts, not random
low-risk payments. That makes the eval a genuine alert-triage task.

Run directly for the Phase 0 smoke test:
    python -m data.load_data
"""

import sys
from pathlib import Path

import kagglehub
import pandas as pd

sys.path.insert(0, str(Path(__file__).parent.parent))

import config

PAYSIM_DATASET = "ealaxi/paysim1"

COLUMNS = [
    "step", "type", "amount", "nameOrig", "oldbalanceOrg", "newbalanceOrig",
    "nameDest", "oldbalanceDest", "newbalanceDest", "isFraud",
]


def load_transactions(force_download: bool = False) -> pd.DataFrame:
    """Return the full PaySim dataframe with a stable txn_id column."""
    if config.TRANSACTIONS_PATH.exists() and not force_download:
        return pd.read_parquet(config.TRANSACTIONS_PATH)

    dataset_dir = Path(kagglehub.dataset_download(PAYSIM_DATASET))
    csv_path = next(dataset_dir.glob("*.csv"))
    df = pd.read_csv(csv_path, usecols=COLUMNS)
    # Row order is stable, so the index doubles as a transaction id.
    df.insert(0, "txn_id", df.index)

    config.TRANSACTIONS_PATH.parent.mkdir(parents=True, exist_ok=True)
    df.to_parquet(config.TRANSACTIONS_PATH, index=False)
    return df


def build_eval_set(df: pd.DataFrame) -> pd.DataFrame:
    """Sample a balanced, alert-like eval set and save it to CSV."""
    fraud = df[df["isFraud"] == 1].sample(
        n=config.EVAL_FRAUD_COUNT, random_state=config.RANDOM_SEED
    )

    alertlike = df[(df["isFraud"] == 0) & (df["type"].isin(["TRANSFER", "CASH_OUT"]))]
    amount_cutoff = alertlike["amount"].quantile(0.90)
    legit = alertlike[alertlike["amount"] >= amount_cutoff].sample(
        n=config.EVAL_LEGIT_COUNT, random_state=config.RANDOM_SEED
    )

    eval_set = (
        pd.concat([fraud, legit])
        .sample(frac=1, random_state=config.RANDOM_SEED)  # shuffle
        .reset_index(drop=True)
    )
    eval_set.to_csv(config.EVAL_SET_PATH, index=False)
    return eval_set


if __name__ == "__main__":
    df = load_transactions()
    print(f"transactions: {df.shape[0]:,} rows, {df.shape[1]} cols")
    print(f"fraud rate: {df['isFraud'].mean():.4%}")

    eval_set = build_eval_set(df)
    print(f"\neval set: {len(eval_set)} rows -> {config.EVAL_SET_PATH}")
    print(eval_set["isFraud"].value_counts().rename("count").to_string())
    print(eval_set["type"].value_counts().rename("count").to_string())
