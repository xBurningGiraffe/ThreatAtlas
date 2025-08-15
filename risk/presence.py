\
import numpy as np
import pandas as pd

def apply_presence(df: pd.DataFrame, mode: str, spec: str) -> pd.DataFrame:
    d = df.copy()
    if mode == "percentile":
        # spec like "0:q50,1-4:q75,5-:q100"
        caps = {}
        for part in spec.split(","):
            rng, q = part.split(":")
            qv = float(q.replace("q", ""))
            caps[rng.strip()] = np.nanpercentile(d["Risk_Score"], qv)
        def cap_for(apt):
            if apt == 0 and "0" in caps:
                return caps["0"]
            if 1 <= apt <= 4 and "1-4" in caps:
                return caps["1-4"]
            if apt >= 5 and "5-" in caps:
                return caps["5-"]
            return None
        d["Risk_Score"] = [
            min(rs, cap_for(apt)) if cap_for(apt) is not None else rs
            for rs, apt in zip(d["Risk_Score"], d["APT_Group_Count"])
        ]
        return d

    # multiplicative: "0:0.4,1-4:0.7,5-:1.0"
    factors = {"0": 0.4, "1-4": 0.7, "5-": 1.0}
    try:
        for part in spec.split(","):
            rng, val = part.split(":")
            factors[rng.strip()] = float(val)
    except Exception:
        pass
    mults = []
    for apt in d["APT_Group_Count"]:
        if apt == 0:
            mults.append(factors.get("0", 0.4))
        elif 1 <= apt <= 4:
            mults.append(factors.get("1-4", 0.7))
        else:
            mults.append(factors.get("5-", 1.0))
    d["Risk_Score"] = d["Risk_Score"] * pd.Series(mults, index=d.index)
    return d
