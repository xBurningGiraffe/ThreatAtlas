\
import difflib
import pandas as pd

def normalize(s: str) -> str:
    return " ".join(str(s).lower().replace("&", "and").split())

def fuzzy_country_lookup(df: pd.DataFrame, user_input: str) -> tuple[str, pd.DataFrame]:
    """Return (matched_name, filtered_df) using fuzzy match on Country or ISO2."""
    s = user_input.strip()
    # Try ISO2 exact
    iso = s.upper()
    if iso in set(df["ISO2"].unique()):
        sub = df[df["ISO2"] == iso]
        return sub.iloc[0]["Country"], sub
    # Country exact (case-insensitive)
    nrm_map = {normalize(c): c for c in df["Country"]}
    if normalize(s) in nrm_map:
        cname = nrm_map[normalize(s)]
        return cname, df[df["Country"] == cname]
    # Fuzzy
    candidates = list(df["Country"].unique())
    best = difflib.get_close_matches(s, candidates, n=1, cutoff=0.6)
    if best:
        cname = best[0]
        return cname, df[df["Country"] == cname]
    # Fallback to ISO2 fuzzy
    codes = list(df["ISO2"].unique())
    best2 = difflib.get_close_matches(iso, codes, n=1, cutoff=0.6)
    if best2:
        sub = df[df["ISO2"] == best2[0]]
        return sub.iloc[0]["Country"], sub
    return s, pd.DataFrame(columns=df.columns)
