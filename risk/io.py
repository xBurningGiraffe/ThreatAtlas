\
import pandas as pd

EXPECTED_COLUMNS = ["Country", "ISO2", "GCI_Sum", "APT_Group_Count", "Tier"]

def load_base_csv(path: str) -> pd.DataFrame:
    df = pd.read_csv(path)
    # Keep legacy Tier column but ensure expected main columns exist
    # Coerce types and standardize headers
    # Ensure columns exist (some projects may not include Tier)
    for col in ["Country", "ISO2"]:
        if col not in df.columns:
            raise ValueError(f"Base CSV missing required column: {col}")
    if "GCI_Sum" not in df.columns:
        df["GCI_Sum"] = pd.NA
    if "APT_Group_Count" not in df.columns:
        df["APT_Group_Count"] = 0
    # Normalize ISO2 casing
    df["ISO2"] = df["ISO2"].astype(str).str.upper().str.strip()
    # Ensure numeric
    df["GCI_Sum"] = pd.to_numeric(df["GCI_Sum"], errors="coerce")
    df["APT_Group_Count"] = pd.to_numeric(df["APT_Group_Count"], errors="coerce").fillna(0).astype(int)
    return df

def export_csv(df: pd.DataFrame, path: str) -> None:
    df.to_csv(path, index=False)
