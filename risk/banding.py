\
import numpy as np
import pandas as pd

DEFAULT_QUANTILES = [0.20, 0.50, 0.80, 0.95]
LEVELS = ["Low", "Medium", "High", "Very High", "Severe"]

def band(df: pd.DataFrame, quantiles=None) -> pd.DataFrame:
    d = df.copy()
    qs = DEFAULT_QUANTILES if quantiles is None else quantiles
    qs = sorted(qs)
    cut_points = [np.nanquantile(d["Risk_Score"], q) for q in qs]
    # Assign bands
    def label(x):
        if x <= cut_points[0]: return "Low"
        if x <= cut_points[1]: return "Medium"
        if x <= cut_points[2]: return "High"
        if x <= cut_points[3]: return "Very High"
        return "Severe"
    d["Risk_Level"] = d["Risk_Score"].apply(label)
    return d
