"""Transaction data tools — the functions Argus agents call to gather evidence.

These are plain Python functions over the PaySim dataframe; the MCP server in
`tools/mcp_server.py` exposes the same functions over MCP. Two rules apply to
every tool:

  1. Never return the `isFraud` label — that's the eval ground truth, and
     leaking it would let agents "investigate" by reading the answer.
  2. Return JSON-serializable dicts, since outputs go straight into prompts.

Run directly for the Phase 1 smoke test:
    python -m tools.data_tools
"""

import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).parent.parent))

import config

_df: pd.DataFrame | None = None


def _data() -> pd.DataFrame:
    global _df
    if _df is None:
        if not config.TRANSACTIONS_PATH.exists():
            raise FileNotFoundError(
                "transactions.parquet missing — run `python -m data.load_data` first"
            )
        _df = pd.read_parquet(config.TRANSACTIONS_PATH)
    return _df


def _clean(rows: pd.DataFrame) -> list[dict]:
    """Drop the ground-truth label and convert to plain dicts."""
    return rows.drop(columns=["isFraud"]).to_dict(orient="records")


def get_transaction(txn_id: int) -> dict:
    """Return the alerted transaction by id, or an error dict if not found."""
    rows = _data()[_data()["txn_id"] == txn_id]
    if rows.empty:
        return {"error": f"transaction {txn_id} not found"}
    return _clean(rows)[0]


def get_customer_history(account_id: str, n: int = 10) -> dict:
    """Recent transactions where the account is sender or receiver."""
    df = _data()
    mask = (df["nameOrig"] == account_id) | (df["nameDest"] == account_id)
    rows = df[mask].sort_values("step", ascending=False).head(n)
    records = _clean(rows)
    for r in records:
        r["role"] = "sender" if r["nameOrig"] == account_id else "receiver"
    return {"account_id": account_id, "n_found": len(records), "transactions": records}


def get_customer_baseline(account_id: str) -> dict:
    """Typical behavior of the account as a sender: volume, amounts, types."""
    df = _data()
    sent = df[df["nameOrig"] == account_id]
    if sent.empty:
        return {"account_id": account_id, "n_sent": 0,
                "note": "no outgoing history — single-transaction account"}
    return {
        "account_id": account_id,
        "n_sent": int(len(sent)),
        "mean_amount": round(float(sent["amount"].mean()), 2),
        "median_amount": round(float(sent["amount"].median()), 2),
        "max_amount": round(float(sent["amount"].max()), 2),
        "type_counts": sent["type"].value_counts().to_dict(),
        "first_step": int(sent["step"].min()),
        "last_step": int(sent["step"].max()),
    }


def get_counterparty_risk(account_id: str) -> dict:
    """Activity profile of the destination account (who is receiving the money)."""
    df = _data()
    received = df[df["nameDest"] == account_id]
    if received.empty:
        return {"account_id": account_id, "n_received": 0,
                "note": "destination has never received funds in the dataset"}
    # A destination whose recorded balance stays at zero while receiving funds
    # is a classic mule/pass-through indicator in PaySim.
    zero_balance_rate = float((received["oldbalanceDest"] == 0).mean())
    return {
        "account_id": account_id,
        "is_merchant": account_id.startswith("M"),
        "n_received": int(len(received)),
        "total_received": round(float(received["amount"].sum()), 2),
        "distinct_senders": int(received["nameOrig"].nunique()),
        "zero_balance_rate": round(zero_balance_rate, 3),
        "type_counts": received["type"].value_counts().to_dict(),
    }


def compute_velocity_signals(account_id: str, as_of_step: int,
                             window: int = config.VELOCITY_WINDOW_STEPS) -> dict:
    """Count/sum of the account's outgoing transfers in the window before as_of_step."""
    df = _data()
    recent = df[
        (df["nameOrig"] == account_id)
        & (df["step"] <= as_of_step)
        & (df["step"] > as_of_step - window)
    ]
    return {
        "account_id": account_id,
        "window_steps": window,
        "as_of_step": as_of_step,
        "txn_count": int(len(recent)),
        "total_amount": round(float(recent["amount"].sum()), 2),
        "types": recent["type"].value_counts().to_dict(),
    }


ALL_TOOLS = [
    get_transaction,
    get_customer_history,
    get_customer_baseline,
    get_counterparty_risk,
    compute_velocity_signals,
]


if __name__ == "__main__":
    eval_set = pd.read_csv(config.EVAL_SET_PATH)
    sample = eval_set.iloc[0]
    txn_id = int(sample["txn_id"])

    txn = get_transaction(txn_id)
    assert txn["txn_id"] == txn_id and "isFraud" not in txn
    print(f"transaction {txn_id}: {txn['type']} amount={txn['amount']:,}")

    hist = get_customer_history(txn["nameOrig"])
    baseline = get_customer_baseline(txn["nameOrig"])
    risk = get_counterparty_risk(txn["nameDest"])
    velocity = compute_velocity_signals(txn["nameOrig"], as_of_step=txn["step"])

    assert all("isFraud" not in t for t in hist["transactions"])
    print(f"history: {hist['n_found']} txns | baseline n_sent={baseline['n_sent']}")
    print(f"counterparty: received {risk.get('n_received', 0)} txns, "
          f"zero_balance_rate={risk.get('zero_balance_rate', 'n/a')}")
    print(f"velocity: {velocity['txn_count']} txns in last {velocity['window_steps']} steps")
    print("\nPhase 1 smoke test OK — no label leakage, all tools return dicts.")
