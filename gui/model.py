# cyber_risk/gui/model.py
from __future__ import annotations
from typing import List, Tuple
import os

import pandas as pd

from risk.io import load_base_csv
from risk.alias import load_alias_map
from risk.ncsi import fetch_ncsi, merge_ncsi
from risk.spam import fetch_spam_top_senders, merge_spam
from risk.malicious import fetch_spamhaus_exploits, merge_exploits
from risk.scoring import topsis_score
from risk.presence import apply_presence
from risk.banding import band

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), os.pardir))


def _resolve_path(path: str, default_name: str | None = None) -> str:
    """
    Resolve a file path robustly:
      - absolute path as-is if it exists
      - relative to CWD if exists
      - relative to PROJECT_ROOT if exists
      - if default_name given, try PROJECT_ROOT/default_name
    Raise FileNotFoundError otherwise.
    """
    if not path:
        path = default_name or ""
    candidates = []
    if os.path.isabs(path):
        candidates.append(path)
    else:
        candidates.append(os.path.abspath(path))
        candidates.append(os.path.join(PROJECT_ROOT, path))
    if default_name:
        candidates.append(os.path.join(PROJECT_ROOT, default_name))
    for c in candidates:
        if c and os.path.isfile(c):
            return c
    raise FileNotFoundError(
        f"File not found: {path!r} (checked: {', '.join(candidates)})"
    )


class RiskModel:
    def __init__(
        self, base_path: str = "country_risk.csv", alias_path: str = "alias.txt"
    ):
        self.base_path = base_path
        self.alias_path = alias_path

    def run(
        self,
        w_apt: float,
        w_gci: float,
        w_ncsi: float,
        w_mal: float,
        w_spam: float,
        presence_mode: str,
        presence_cap: str,
        quantiles: List[float],
        exclude_names: List[str],
        exclude_iso2: List[str],
        ncsi_missing: str,
    ) -> pd.DataFrame:

        base_file = _resolve_path(self.base_path, "country_risk.csv")
        alias_file = _resolve_path(self.alias_path, "alias.txt")

        base_df = load_base_csv(base_file)
        if base_df is None or base_df.empty:
            raise RuntimeError(f"Loaded 0 rows from base CSV: {base_file}")

        alias_map = load_alias_map(alias_file)

        # NCSI local-first
        if "NCSI_Score" in base_df.columns and base_df["NCSI_Score"].notna().any():
            df = base_df
        else:
            ncsi_df = fetch_ncsi(
                cache_csv=os.path.join(PROJECT_ROOT, "risk", "data", "ncsi_scores.csv")
            )
            df = merge_ncsi(base_df, ncsi_df)
            if "NCSI_Score" not in df.columns:
                df["NCSI_Score"] = pd.NA

        # Talos spam (always merge)
        try:
            spam_df = fetch_spam_top_senders()
            df = merge_spam(df, spam_df, alias_map=alias_map)
        except Exception:
            if "Spam_Magnitude" not in df.columns:
                df["Spam_Magnitude"] = pd.NA

        # Spamhaus exploits (always merge)
        try:
            exp_df = fetch_spamhaus_exploits()
            df = merge_exploits(df, exp_df, alias_map=alias_map)
        except Exception:
            if "Exploit_Rank" not in df.columns:
                df["Exploit_Rank"] = pd.NA
            if "Exploit_TotalToday" not in df.columns:
                df["Exploit_TotalToday"] = pd.NA

        # Ensure columns exist even if sources failed
        for col in ("Spam_Magnitude", "Exploit_Rank", "Exploit_TotalToday"):
            if col not in df.columns:
                df[col] = pd.NA

        # Score
        df = topsis_score(
            df,
            w_apt=w_apt,
            w_gci=w_gci,
            w_ncsi=w_ncsi,
            w_mal=w_mal,
            w_spam=w_spam,
            ncsi_missing=ncsi_missing,
            spam_missing="drop",
        )

        # Presence & Banding
        df = apply_presence(df, mode=presence_mode, spec=presence_cap)
        df = band(df, quantiles=quantiles)

        # Exclusions
        if exclude_names:
            df = df[~df["Country"].isin(exclude_names)]
        if exclude_iso2:
            df = df[~df["ISO2"].isin([x.upper() for x in exclude_iso2])]

        if df.empty:
            # Fail loud so the UI can report and we can diagnose
            raise RuntimeError(
                "Pipeline produced 0 rows after processing. Check exclusions and inputs."
            )

        return df.sort_values("Risk_Score", ascending=False).reset_index(drop=True)
