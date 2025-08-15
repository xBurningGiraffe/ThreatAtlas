# risk/ncsi.py
import re
import unicodedata
from typing import Optional, List, Dict

import pandas as pd
import requests
from bs4 import BeautifulSoup

NCSI_URL = "https://ncsi.ega.ee/ncsi-index/?order=rank&type=c"

# ----------------- helpers -----------------


def _clean_name(name: str) -> str:
    """Light normalization: strip () notes, diacritics, punctuation, collapse spaces."""
    if not isinstance(name, str):
        return ""
    name = re.sub(r"\(.*?\)", "", name)
    name = name.replace("\u200b", " ").strip()
    name = unicodedata.normalize("NFKD", name)
    name = "".join([c for c in name if not unicodedata.combining(c)])
    name = re.sub(r"[’'`]", "", name)
    name = re.sub(r"[-,]", " ", name)
    name = re.sub(r"\s+", " ", name).strip()
    return name


def _bag(s: str) -> set:
    return set(_clean_name(s).lower().split())


def _num(text: str) -> Optional[float]:
    """Extract a 0–100 float from a text fragment with possible % and comma/period decimals."""
    if not text:
        return None
    m = re.search(r"(\d{1,3}(?:[.,]\d+)?)(?:\s*%?)", text)
    if not m:
        return None
    x = m.group(1)
    if x.count(",") == 1 and x.count(".") == 0:
        x = x.replace(",", ".")
    else:
        x = x.replace(",", "")
    try:
        val = float(x)
        if 0 <= val <= 100:
            return val
    except Exception:
        pass
    return None


def _closest_score_in_row(tr) -> Optional[float]:
    """Within a <tr>, find the most likely element containing the score (0–100)."""
    preferred_sel = [
        "td.blue-frame strong",
        "td .value-size",
        "td .c-blue-light",
        "td strong",
        "td span",
    ]
    seen = set()
    for sel in preferred_sel:
        for el in tr.select(sel):
            if el in seen:
                continue
            seen.add(el)
            v = _num(el.get_text(strip=True))
            if v is not None:
                return v
    return _num(tr.get_text(" ", strip=True))


# ----------------- scraping & parsing -----------------


def _fetch_html(from_file: Optional[str] = None) -> str:
    if from_file:
        with open(from_file, "r", encoding="utf-8", errors="ignore") as f:
            return f.read()
    headers = {
        "User-Agent": "Mozilla/5.0 (compatible; NCSI-Scrape/1.0)",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    }
    r = requests.get(NCSI_URL, timeout=30, headers=headers)
    r.raise_for_status()
    return r.text


def _parse_ncsi(html: str) -> List[Dict]:
    """
    Returns list of dicts: [{"Country": str, "NCSI_Score": float, "NCSI_Rank": int|None}, ...]
    """
    soup = BeautifulSoup(html, "html.parser")

    table = soup.find("table", {"id": "full-countries-table"}) or soup.find(
        "table", {"class": "full-countries-table"}
    )
    rows = table.find_all("tr") if table else soup.find_all("tr")

    out = []
    for tr in rows:
        anchors = [
            a for a in tr.find_all("a", href=True) if a["href"].startswith("/country/")
        ]
        if not anchors:
            continue
        # choose anchor that has visible country text (not the flag icon)
        country_a = None
        for a in anchors:
            text = a.get_text(strip=True)
            if text and "flag-icon" not in (a.get("class") or []):
                country_a = a
                break
        if country_a is None:
            country_a = anchors[-1]
        country = _clean_name(country_a.get_text(strip=True))
        if not country:
            continue

        # optional rank (e.g., "1." in first cell)
        tds = tr.find_all("td")
        rank = None
        if tds:
            m = re.search(r"\d+", tds[0].get_text(strip=True))
            if m:
                try:
                    rank = int(m.group(0))
                except Exception:
                    rank = None

        score = _closest_score_in_row(tr)
        if score is None:
            continue

        out.append({"Country": country, "NCSI_Score": score, "NCSI_Rank": rank})

    if not out:
        raise RuntimeError(
            "Parsed zero rows from NCSI page; site structure may have changed."
        )

    # Deduplicate by normalized name; prefer smaller (better) rank when present
    dedup = {}
    for r in out:
        key = _clean_name(r["Country"]).lower()
        if key not in dedup:
            dedup[key] = r
        else:
            a, b = dedup[key], r

            def rank_key(x):
                rk = x.get("NCSI_Rank")
                return (rk is None, rk if rk is not None else 10**9)

            dedup[key] = min([a, b], key=rank_key)
    return list(dedup.values())


def fetch_ncsi(
    cache_csv: Optional[str] = None, from_file: Optional[str] = None
) -> pd.DataFrame:
    """
    Fetch the NCSI “countries” list and return a DataFrame with columns:
      Country (str), NCSI_Score (float), NCSI_Rank (optional, int)
    If cache_csv exists and is valid, load from it; otherwise scrape and (if given) write it.
    """
    if cache_csv:
        try:
            df = pd.read_csv(cache_csv)
            if {"Country", "NCSI_Score"}.issubset(df.columns) and len(df) > 0:
                return df
        except FileNotFoundError:
            pass
        except Exception:
            pass

    html = _fetch_html(from_file=from_file)
    rows = _parse_ncsi(html)
    df = pd.DataFrame(rows, columns=["Country", "NCSI_Score", "NCSI_Rank"])
    df["NCSI_Score"] = pd.to_numeric(df["NCSI_Score"], errors="coerce")
    if "NCSI_Rank" in df.columns:
        df["NCSI_Rank"] = pd.to_numeric(df["NCSI_Rank"], errors="coerce")
    df = df.dropna(subset=["Country", "NCSI_Score"]).reset_index(drop=True)

    if cache_csv:
        try:
            df.to_csv(cache_csv, index=False)
        except Exception:
            pass
    return df


# ----------------- merging -----------------


def merge_ncsi(base_df: pd.DataFrame, ncsi_df: pd.DataFrame) -> pd.DataFrame:
    """
    Merge NCSI_Score into base_df by normalized country name with a word-bag fallback.
    - If base already has NCSI_Score, we KEEP it and only fill missing from ncsi_df.
    - Guarantees the result has a single 'NCSI_Score' column.
    """
    b = base_df.copy()

    # If ncsi_df is empty or lacks NCSI_Score, just ensure the column exists and return
    if ncsi_df is None or ncsi_df.empty or ("NCSI_Score" not in ncsi_df.columns):
        if "NCSI_Score" not in b.columns:
            b["NCSI_Score"] = pd.NA
        return b

    n = ncsi_df.copy()

    b["_norm"] = b["Country"].astype(str).map(_clean_name).str.lower()
    n["_norm"] = n["Country"].astype(str).map(_clean_name).str.lower()

    # First pass merge; use suffix to avoid KeyError when base already has NCSI_Score
    merged = b.merge(
        n[["_norm", "NCSI_Score"]].drop_duplicates("_norm"),
        on="_norm",
        how="left",
        suffixes=("", "_n"),
    )

    # Consolidate into a single NCSI_Score:
    # Prefer existing base value; fill missing from the new "_n" column.
    if "NCSI_Score_n" in merged.columns:
        if "NCSI_Score" not in merged.columns:
            merged.rename(columns={"NCSI_Score_n": "NCSI_Score"}, inplace=True)
        else:
            merged["NCSI_Score"] = merged["NCSI_Score"].combine_first(
                merged["NCSI_Score_n"]
            )
            merged.drop(columns=["NCSI_Score_n"], inplace=True)

    # Second pass: bag-of-words fallback for remaining misses (fill into NCSI_Score)
    missing = merged["NCSI_Score"].isna()
    if missing.any():
        n_bags = {row["_norm"]: _bag(row["_norm"]) for _, row in n.iterrows()}
        for idx in merged[missing].index:
            bag = _bag(merged.at[idx, "_norm"])
            best_key = None
            best_overlap = 0
            for key, nbag in n_bags.items():
                ov = len(bag & nbag)
                if ov > best_overlap:
                    best_overlap = ov
                    best_key = key
            if best_key and best_overlap > 0:
                row = n.loc[n["_norm"] == best_key].iloc[0]
                merged.at[idx, "NCSI_Score"] = row["NCSI_Score"]

    merged.drop(columns=["_norm"], inplace=True)
    return merged
