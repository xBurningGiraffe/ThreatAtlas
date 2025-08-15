# risk/scoring.py
from __future__ import annotations

import numpy as np
import pandas as pd

# Defaults (you can ignore these if your CLI passes weights)
DEFAULT_WEIGHTS = {
    "APT_Group_Count": 0.5,
    "GCI_Sum": 0.2,  # used as (100 - GCI_Sum) cost
    "NCSI_Score": 0.2,  # used as (100 - NCSI_Score) cost
    "Exploit_Rank": 0.1,  # Spamhaus rank (transformed to cost via Exploit_Score)
    "Spam_Magnitude": 0.1,  # Talos email spam magnitude (log10 scale; higher=worse)
}


def _to_float_series(df: pd.DataFrame, col: str) -> pd.Series:
    """Coerce a column to float64; create if missing."""
    if col not in df.columns:
        return pd.Series(np.nan, index=df.index, dtype="float64")
    return pd.to_numeric(df[col], errors="coerce").astype("float64")


def _vector_norm(x: np.ndarray) -> float:
    """L2 norm ignoring NaNs; returns 1.0 if degenerate to avoid division-by-zero."""
    # replace nan with 0 for norm computation
    x = np.where(np.isnan(x), 0.0, x)
    denom = float(np.sqrt(np.sum(np.square(x))))
    return denom if denom > 0.0 else 1.0


def _row_normalize_weights(W: np.ndarray) -> np.ndarray:
    s = W.sum(axis=1, keepdims=True)
    s[s == 0.0] = 1.0
    return W / s


def topsis_score(
    df: pd.DataFrame,
    w_apt: float = 0.5,
    w_gci: float = 0.2,
    w_ncsi: float = 0.2,
    w_mal: float = 0.1,  # applied to Spamhaus Exploit rank (via Exploit_Score)
    w_spam: float = 0.1,  # applied to Talos spam magnitude
    *,
    ncsi_missing: str = "drop",  # "drop" | "impute" | "scale" (scale is treated as drop here)
    spam_missing: str = "drop",  # "drop" | "impute"
) -> pd.DataFrame:
    """
    Compute TOPSIS with cost-type criteria:
      - c_APT  = APT_Group_Count
      - c_GCI  = 100 - GCI_Sum
      - c_NCSI = 100 - NCSI_Score
      - c_EXP  = Exploit_Score  (from Spamhaus rank)
      - c_SPAM = Spam_Magnitude (Talos)

    Returns a copy of df with added 'Risk_Score' (0..100, higher = riskier).
    """
    d = df.copy()

    # --- Coerce inputs to float64 (safe) ---
    apt = _to_float_series(d, "APT_Group_Count")
    gci = _to_float_series(d, "GCI_Sum")
    ncsi = _to_float_series(d, "NCSI_Score")
    exp_rank = _to_float_series(d, "Exploit_Rank")
    spam = _to_float_series(d, "Spam_Magnitude")

    # --- Missingness masks ---
    has_ncsi = ~ncsi.isna()
    has_spam = ~spam.isna()
    has_exp = ~exp_rank.isna()

    # --- Optional imputations (kept minimal) ---
    if ncsi_missing == "impute":
        if has_ncsi.any():
            ncsi = ncsi.fillna(float(ncsi[has_ncsi].median()))
        else:
            ncsi = ncsi.fillna(50.0)
    if spam_missing == "impute":
        if has_spam.any():
            spam = spam.fillna(float(spam[has_spam].median()))
        else:
            spam = spam.fillna(0.0)

    # --- Exploit rank -> Exploit_Score (higher=worse) ---
    if has_exp.any():
        max_rank = int(np.nanmax(exp_rank.values))
        if max_rank > 0:
            exp_score = (max_rank - exp_rank + 1.0).astype("float64")
        else:
            exp_score = pd.Series(np.nan, index=d.index, dtype="float64")
    else:
        exp_score = pd.Series(np.nan, index=d.index, dtype="float64")

    # --- Build cost-criteria matrix (NaNs allowed) ---
    c_APT = apt.fillna(0.0).values.astype("float64")
    c_GCI = (100.0 - gci.fillna(0.0)).values.astype("float64")
    c_NCSI = (100.0 - ncsi.fillna(0.0)).values.astype("float64")
    c_EXP = exp_score.fillna(0.0).values.astype("float64")
    c_SPAM = spam.values.astype("float64")
    # Replace remaining NaNs with 0 for computation
    c_SPAM = np.where(np.isnan(c_SPAM), 0.0, c_SPAM)

    crit = np.column_stack([c_APT, c_GCI, c_NCSI, c_EXP, c_SPAM])  # shape (n,5)

    # --- Vector normalization (column-wise) ---
    for j in range(crit.shape[1]):
        denom = _vector_norm(crit[:, j])
        crit[:, j] = crit[:, j] / denom

    # --- Base weights and per-row drop for missing data ---
    base_w = np.array([w_apt, w_gci, w_ncsi, w_mal, w_spam], dtype="float64")
    if base_w.sum() <= 0.0:
        base_w = np.array([0.5, 0.2, 0.2, 0.1, 0.1], dtype="float64")
    base_w = base_w / base_w.sum()

    # Start with same weights for all rows
    W = np.tile(base_w, (len(d), 1))

    # Drop weights where data is missing for that row (per-row normalization later)
    # Indices: 0 APT (assumed always present), 1 GCI, 2 NCSI, 3 EXP, 4 SPAM
    if ncsi_missing in ("drop", "scale"):
        W[~has_ncsi.values, 2] = 0.0
    if not has_exp.any():
        W[:, 3] = W[:, 3] * 0.0
    else:
        W[~has_exp.values, 3] = 0.0
    if spam_missing == "drop":
        W[~has_spam.values, 4] = 0.0

    # Row-wise renormalization
    W = _row_normalize_weights(W)

    # --- Weighted normalized decision matrix ---
    Xw = crit * W  # (n,5)

    # --- Ideal best/worst for cost criteria (best=min, worst=max) ---
    # Guard against all-zero columns: min==max==0 → distances will be 0 for that dim
    ideal_best = np.nanmin(Xw, axis=0)
    ideal_worst = np.nanmax(Xw, axis=0)

    # Replace NaNs (which can only happen if column entirely NaN before) with zeros
    ideal_best = np.where(np.isnan(ideal_best), 0.0, ideal_best)
    ideal_worst = np.where(np.isnan(ideal_worst), 0.0, ideal_worst)

    # --- Distances & closeness ---
    d_best = np.sqrt(np.sum((Xw - ideal_best) ** 2, axis=1))
    d_worst = np.sqrt(np.sum((Xw - ideal_worst) ** 2, axis=1))
    denom = d_best + d_worst
    denom[denom == 0.0] = 1.0  # avoid division by zero

    c_star = d_worst / denom  # higher = safer
    risk_score = (1.0 - c_star) * 100.0

    d["Risk_Score"] = pd.Series(risk_score, index=d.index, dtype="float64")
    return d
