# risk/spam.py
from __future__ import annotations

import re
import unicodedata
from typing import Optional

import pandas as pd
import requests

TALOS_URL = "https://www.talosintelligence.com/cloud_intel/top_senders_list"

# Common ISO2 fixups seen in the wild
ISO2_FIXUPS = {
    "UK": "GB",  # United Kingdom
    "EL": "GR",  # Greece (sometimes EL in EU contexts)
    "KO": "XK",  # Kosovo (Talos may not list it; included for completeness)
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


def fetch_spam_top_senders(session: requests.Session | None = None) -> pd.DataFrame:
    """
    Pull Talos 'top_senders_list' JSON and return:
      ISO2 (str), Country (str), Spam_Magnitude (float), Spam_GlobalPct (float)
    """
    sess = session or requests.Session()
    r = sess.get(TALOS_URL, timeout=30)
    r.raise_for_status()
    try:
        data = r.json()
    except Exception:
        import json

        data = json.loads(r.text)

    block = data.get("spam_country") or data.get("data", {}).get("spam_country") or []
    rows = []
    for item in block:
        cinfo = item.get("country_info", {}) or {}
        iso2 = _norm_iso2(cinfo.get("code"))
        name = _clean_name(cinfo.get("name") or "")
        mag_x10 = item.get("day_magnitude_x10")
        if mag_x10 is None:
            continue
        try:
            mag = float(mag_x10) / 10.0
        except Exception:
            continue
        pct = 100.0 * (10.0 ** (mag - 10.0))
        rows.append(
            {
                "ISO2": iso2,
                "Country": name,
                "Spam_Magnitude": mag,
                "Spam_GlobalPct": pct,
            }
        )

    df = pd.DataFrame(rows)
    if not df.empty:
        df["ISO2"] = df["ISO2"].astype(str).str.upper().str.strip()
        df["Country"] = df["Country"].astype(str)
        df["Spam_Magnitude"] = pd.to_numeric(df["Spam_Magnitude"], errors="coerce")
        df["Spam_GlobalPct"] = pd.to_numeric(df["Spam_GlobalPct"], errors="coerce")
    return df


def merge_spam(
    base_df: pd.DataFrame,
    spam_df: pd.DataFrame,
    *,
    alias_map: dict[str, str] | None = None,
) -> pd.DataFrame:
    """
    Merge Spam_Magnitude into base_df using:
      1) ISO2 (normalized + fixups), strict;
      2) If no hit, try alias_map and cleaned Country names → ISO2;
      3) Last resort: cleaned Country-name match (left join).

    alias_map: mapping like {"united states of america": "US", "ivory coast": "CI", ...}
               Keys should be case-insensitive (we’ll .lower() them).
    """
    b = base_df.copy()
    s = spam_df.copy()

    # Normalize base ISO2 and Country
    b["ISO2"] = b["ISO2"].astype(str).str.upper().str.strip()
    b["ISO2"] = b["ISO2"].map(lambda x: _norm_iso2(x) or x)
    b["_name_clean"] = b["Country"].astype(str).map(_clean_name).str.lower()

    # Normalize spam ISO2 and Country
    if "ISO2" not in s.columns:
        s["ISO2"] = pd.NA
    s["ISO2"] = s["ISO2"].astype(str).str.upper().str.strip()
    s["ISO2"] = s["ISO2"].map(lambda x: _norm_iso2(x) or x)
    s["_name_clean"] = s["Country"].astype(str).map(_clean_name).str.lower()

    # 1) ISO2 strict merge first
    out = b.merge(
        s[["ISO2", "Spam_Magnitude"]].dropna(subset=["ISO2"]).drop_duplicates("ISO2"),
        on="ISO2",
        how="left",
        suffixes=("", "_spam_iso2"),
    )

    # 2) For rows still missing, try alias_map → ISO2 mapping from base names
    if alias_map:
        # lower-case keys for robust lookups
        alias_norm = {
            str(k).strip().lower(): str(v).strip().upper() for k, v in alias_map.items()
        }
        # Also apply fixups to mapped ISO2
        for k, v in list(alias_norm.items()):
            alias_norm[k] = _norm_iso2(v) or v

        need = out["Spam_Magnitude"].isna()
        if need.any():
            # get ISO2 via alias for base row's cleaned name
            alias_iso2 = out.loc[need, "_name_clean"].map(alias_norm)
            if alias_iso2.notna().any():
                alias_iso2 = alias_iso2.astype(str).str.upper().str.strip()
                # join spam on alias ISO2
                spam_iso_map = s.set_index("ISO2")["Spam_Magnitude"]
                out.loc[need, "Spam_Magnitude"] = alias_iso2.map(spam_iso_map)

    # 3) Last resort: name-to-name join for still-missing rows
    need = out["Spam_Magnitude"].isna()
    if need.any():
        spam_name_map = s.set_index("_name_clean")["Spam_Magnitude"]
        out.loc[need, "Spam_Magnitude"] = out.loc[need, "_name_clean"].map(
            spam_name_map
        )

    # Clean temp columns
    out = out.drop(columns=["_name_clean"], errors="ignore")
    return out
