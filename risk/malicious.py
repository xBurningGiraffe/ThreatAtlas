# risk/malicious.py
from __future__ import annotations

import re
import unicodedata
from typing import Optional

import pandas as pd
import requests

SPAMHAUS_URL = "https://www.spamhaus.org/api/v1/stats/country/datasets/exploit"

# Occasional code quirks
ISO2_FIXUPS = {
    "UK": "GB",  # United Kingdom
    "EL": "GR",  # Greece
    "KO": "XK",  # Kosovo (not always present)
}


def _clean_name(name: str) -> str:
    if not isinstance(name, str):
        return ""
    s = re.sub(r"\(.*?\)", "", name)
    s = s.replace("\u200b", " ").strip()
    s = unicodedata.normalize("NFKD", s)
    s = "".join(c for c in s if not unicodedata.combining(c))
    s = re.sub(r"[’'`]", "", s)
    s = re.sub(r"[-,]", " ", s)
    s = re.sub(r"\s+", " ", s).strip()
    return s


def _norm_iso2(x: str | None) -> str | None:
    if not x:
        return None
    x = str(x).strip().upper()
    return ISO2_FIXUPS.get(x, x)


# ---------- Fetch (uses same headers as your working tester) ----------

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/127.0.0.0 Safari/537.36",
    "Accept": "application/json, text/javascript, */*; q=0.01",
    "Referer": "https://www.spamhaus.org/statistics/country/",
    "Origin": "https://www.spamhaus.org",
}


def fetch_spamhaus_exploits(session: requests.Session | None = None) -> pd.DataFrame:
    """
    Fetch Spamhaus 'exploited IPs' country rankings.

    Returns columns:
      ISO2 (upper), Exploit_Rank (int), Exploit_TotalToday (int),
      Exploit_Key (lower), Latest_Date (str)
    """
    sess = session or requests.Session()
    r = sess.get(SPAMHAUS_URL, headers=HEADERS, timeout=30)
    r.raise_for_status()
    data = r.json()

    rankings = (data.get("data") or {}).get("rankings") or []
    latest_date = (data.get("data") or {}).get("latest_date") or None

    rows = []
    for item in rankings:
        key = (item.get("key") or "").strip().lower()
        if not key or len(key) != 2:
            continue
        iso2 = _norm_iso2(key.upper())
        rank = item.get("rank")
        hits = item.get("hits") or {}
        total_today = hits.get("total_today")
        try:
            total_today = int(total_today) if total_today is not None else None
        except Exception:
            total_today = None
        if iso2 and rank is not None:
            rows.append(
                {
                    "ISO2": iso2,
                    "Exploit_Rank": int(rank),
                    "Exploit_TotalToday": total_today,
                    "Exploit_Key": key,
                    "Latest_Date": latest_date,
                }
            )

    df = pd.DataFrame(rows)
    if not df.empty:
        df["ISO2"] = df["ISO2"].astype(str).str.upper().str.strip().map(_norm_iso2)
        df["Exploit_Rank"] = pd.to_numeric(df["Exploit_Rank"], errors="coerce")
        df["Exploit_TotalToday"] = pd.to_numeric(
            df["Exploit_TotalToday"], errors="coerce"
        )
    return df


# ---------- Merge (ISO2-first, alias-aware fallback) ----------


def merge_exploits(
    base_df: pd.DataFrame,
    spamhaus_df: pd.DataFrame,
    *,
    alias_map: dict[str, str] | None = None,
) -> pd.DataFrame:
    """
    Merge Spamhaus Exploit_Rank/Exploit_TotalToday into base_df:
      1) ISO2 strict (preferred)
      2) Alias fallback: base country name -> ISO2 -> spamhaus
    """
    b = base_df.copy()
    s = spamhaus_df.copy()

    # Normalize ISO2
    b["ISO2"] = b["ISO2"].astype(str).str.upper().str.strip().map(_norm_iso2)
    s["ISO2"] = s["ISO2"].astype(str).str.upper().str.strip().map(_norm_iso2)

    # ISO2 strict join
    out = b.merge(
        s[["ISO2", "Exploit_Rank", "Exploit_TotalToday"]].drop_duplicates("ISO2"),
        on="ISO2",
        how="left",
        suffixes=("", "_exp"),
    )

    # Alias fallback (if provided)
    if alias_map:
        alias_norm = {
            str(k).strip().lower(): _norm_iso2(str(v).strip().upper())
            for k, v in alias_map.items()
        }
        need = out["Exploit_Rank"].isna()
        if need.any():
            base_names = (
                out.loc[need, "Country"].astype(str).map(_clean_name).str.lower()
            )
            alias_iso = base_names.map(alias_norm)
            spam_by_iso = s.set_index("ISO2")[["Exploit_Rank", "Exploit_TotalToday"]]
            out.loc[need, "Exploit_Rank"] = alias_iso.map(spam_by_iso["Exploit_Rank"])
            out.loc[need, "Exploit_TotalToday"] = alias_iso.map(
                spam_by_iso["Exploit_TotalToday"]
            )

    return out
