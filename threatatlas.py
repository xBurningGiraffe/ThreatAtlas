import argparse
import pandas as pd
import os, sys

# Make local package imports reliable when running as a script
sys.path.append(os.path.dirname(__file__))

from risk.io import load_base_csv, export_csv
from risk.alias import load_alias_map
from risk.ncsi import fetch_ncsi, merge_ncsi
from risk.malicious import fetch_spamhaus_exploits, merge_exploits
from risk.spam import fetch_spam_top_senders, merge_spam
from risk.scoring import topsis_score
from risk.presence import apply_presence
from risk.banding import band
from risk.query import fuzzy_country_lookup

# ---- single, robust GUI import (module-level; no re-imports in main()) ----
try:
    from gui import run_gui  # if gui/__init__.py exposes run_gui
except Exception:
    try:
        from gui.app import run_gui  # fallback to direct module
    except Exception:
        run_gui = None  # GUI not available; we'll guard when used

PRINT_COLS = [
    "Country",
    "ISO2",
    "NCSI_Score",
    "Spam_Magnitude",
    "GCI_Sum",
    "APT_Group_Count",
    "Exploit_Rank",
    "Exploit_TotalToday",
    "Risk_Score",
    "Risk_Level",
]


def print_table(df: pd.DataFrame, top: int | None = None):
    d = df.copy()
    if top is not None:
        d = d.head(top)
    with pd.option_context(
        "display.max_rows", None, "display.max_columns", None, "display.width", 180
    ):
        print(
            d.to_string(
                index=False,
                formatters={
                    "Risk_Score": lambda x: f"{x:,.2f}",
                    "Spam_Magnitude": lambda x: "" if pd.isna(x) else f"{x:.1f}",
                },
            )
        )


def main(argv=None):
    p = argparse.ArgumentParser(description="Country Cyber Risk Scorer (TOPSIS).")
    p.add_argument("--file", default="country_risk.csv", help="Base CSV input.")
    p.add_argument(
        "--aliases", default="alias.txt", help="Alias file (for CLI lookups)."
    )

    # NCSI
    p.add_argument(
        "--add-ncsi", default="fetch", help="Add NCSI: 'fetch' or path to CSV cache."
    )
    p.add_argument(
        "--ncsi-cache", default=None, help="Optional path to write/read NCSI cache CSV."
    )

    # Weights (all datasets active by default)
    p.add_argument("--w-apt", type=float, default=0.5)
    p.add_argument("--w-gci", type=float, default=0.2)
    p.add_argument("--w-ncsi", type=float, default=0.2)
    p.add_argument(
        "--w-mal",
        type=float,
        default=0.1,
        help="Weight for Spamhaus Exploit rank (cost).",
    )
    p.add_argument(
        "--w-spam",
        type=float,
        default=0.1,
        help="Weight for Talos Spam Magnitude (cost).",
    )

    # Presence / banding
    p.add_argument(
        "--presence-mode",
        choices=["multiplicative", "percentile"],
        default="multiplicative",
    )
    p.add_argument("--presence-cap", default="0:0.4,1-4:0.7,5-:1.0")
    p.add_argument("--quantiles", default="0.20,0.50,0.80,0.95")

    # Output control
    p.add_argument(
        "--top", type=int, default=10, help="Show top N (by highest Risk_Score)."
    )
    p.add_argument("--top5", action="store_true")
    p.add_argument("--top10", action="store_true")
    p.add_argument("--top20", action="store_true")
    p.add_argument("--export", default=None, help="Write full scored CSV to this path.")

    # Query / exclusions
    p.add_argument(
        "--country", default=None, help="Query a single country (name or ISO2)."
    )
    p.add_argument(
        "--assume-yes", action="store_true", help="Skip confirmation on fuzzy matches."
    )
    p.add_argument(
        "--exclude",
        action="append",
        default=[],
        help="Exclude by country name (repeatable).",
    )
    p.add_argument(
        "--exclude-iso2",
        action="append",
        default=[],
        help="Exclude by ISO2 code (repeatable).",
    )

    # Missing-data strategy
    p.add_argument(
        "--ncsi-missing",
        choices=["drop", "impute", "scale"],
        default="drop",
        help="How to handle missing NCSI_Score (default: drop per-row weight).",
    )

    # GUI
    p.add_argument(
        "--gui", action="store_true", help="Launch the desktop GUI and exit."
    )

    args = p.parse_args(argv)

    # ---- GUI path (early exit) ----
    if args.gui:
        if run_gui is None:
            print(
                "GUI is not available. Ensure 'gui/' is present and PyQt6 is installed."
            )
            return 1
        run_gui()
        return 0

    # ---- CLI pipeline ----
    base_df = load_base_csv(args.file)
    alias_map = load_alias_map(args.aliases)

    # NCSI local-first
    if "NCSI_Score" in base_df.columns and base_df["NCSI_Score"].notna().any():
        df = base_df
    else:
        if args.add_ncsi == "fetch":
            ncsi_df = fetch_ncsi(cache_csv=args.ncsi_cache)
        else:
            ncsi_df = pd.read_csv(args.add_ncsi)
        df = merge_ncsi(base_df, ncsi_df)
        if "NCSI_Score" not in df.columns:
            df["NCSI_Score"] = pd.NA

    # Talos spam (always merge)
    try:
        spam_df = fetch_spam_top_senders()
        df = merge_spam(df, spam_df, alias_map=alias_map)
    except Exception as e:
        print(f"[warn] Talos spam top-senders fetch failed: {e}")
        if "Spam_Magnitude" not in df.columns:
            df["Spam_Magnitude"] = pd.NA

    # Spamhaus exploits (always merge)
    try:
        exp_df = fetch_spamhaus_exploits()
        df = merge_exploits(df, exp_df, alias_map=alias_map)
    except Exception as e:
        print(f"[warn] Spamhaus exploits fetch failed: {e}")
        if "Exploit_Rank" not in df.columns:
            df["Exploit_Rank"] = pd.NA
        if "Exploit_TotalToday" not in df.columns:
            df["Exploit_TotalToday"] = pd.NA

    # Ensure columns exist even if sources failed
    for col in ["Spam_Magnitude", "Exploit_Rank", "Exploit_TotalToday"]:
        if col not in df.columns:
            df[col] = pd.NA

    # Score (TOPSIS)
    df = topsis_score(
        df,
        w_apt=args.w_apt,
        w_gci=args.w_gci,
        w_ncsi=args.w_ncsi,
        w_mal=args.w_mal,  # Spamhaus rank weight
        w_spam=args.w_spam,  # Talos magnitude weight
        ncsi_missing=args.ncsi_missing,
        spam_missing="drop",
    )

    # Presence caps
    df = apply_presence(df, mode=args.presence_mode, spec=args.presence_cap)

    # Banding
    q = [float(x) for x in args.quantiles.split(",") if x.strip()]
    df = band(df, quantiles=q)

    # Exclusions
    if args.exclude:
        df = df[~df["Country"].isin(args.exclude)]
    if args.exclude_iso2:
        df = df[~df["ISO2"].isin([x.upper() for x in args.exclude_iso2])]

    # Sort / Output
    df = df.sort_values("Risk_Score", ascending=False)

    out = df.copy()
    if "Exploit_TotalToday" not in out.columns:
        out["Exploit_TotalToday"] = pd.NA
    out = out[[c for c in PRINT_COLS if c in out.columns]]

    # Country query path
    if args.country:
        match_name, sub = fuzzy_country_lookup(out, args.country)
        if sub.empty:
            print(f"No match for '{args.country}'.")
            return 1
        if not args.assume_yes and match_name.lower() != args.country.strip().lower():
            try:
                resp = input(f"Did you mean '{match_name}'? [Y/n]: ").strip().lower()
            except EOFError:
                resp = "y"
            if resp not in ("", "y", "yes"):
                print("Cancelled.")
                return 0
        print_table(sub[PRINT_COLS])
        if args.export:
            export_csv(df, args.export)
            print(f"\nExported full results to {args.export}")
        return 0

    # TopN selection
    if args.top5:
        topN = 5
    elif args.top10:
        topN = 10
    elif args.top20:
        topN = 20
    else:
        topN = args.top

    print_table(out, top=topN)

    if args.export:
        export_csv(df, args.export)
        print(f"\nExported full results to {args.export}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
