# cyber_risk/gui/controller.py
from __future__ import annotations
from typing import List
import re
import unicodedata

import pandas as pd
from PyQt6 import QtWidgets

from .model import RiskModel
from .view import MainWindow, DEFAULT_PRINT_COLS

from risk.alias import load_alias_map
from risk.query import fuzzy_country_lookup


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
    return s.lower()


class Controller:
    def __init__(self, window: MainWindow):
        self.w = window
        self.model = None
        self._last_full_df = pd.DataFrame()  # filtered set (for export)
        self._last_pipeline_df = pd.DataFrame()  # unfiltered set (for suggestions)

        self.w.runRequested.connect(self.on_run)
        self.w.exportRequested.connect(self.on_export)

    def _build_search_mask(self, df: pd.DataFrame, terms: List[str]) -> pd.Series:
        if not terms:
            return pd.Series(True, index=df.index)

        # Aliases to map query→ISO2
        try:
            alias_map = load_alias_map(self.w.alias_edit.text().strip())
        except Exception:
            alias_map = {}

        norm_country = df["Country"].astype(str).map(_clean_name)
        mask = pd.Series(False, index=df.index)

        for raw in terms:
            q = raw.strip()
            if not q:
                continue

            iso2_q = q.upper() if len(q) == 2 else None
            alias_iso = alias_map.get(_clean_name(q))
            if isinstance(alias_iso, str):
                alias_iso = alias_iso.upper()

            # literal contains on Country
            m_country = df["Country"].astype(str).str.contains(q, case=False, na=False)

            # ISO2 match (direct or via alias)
            m_iso = pd.Series(False, index=df.index)
            if iso2_q:
                m_iso |= df["ISO2"].astype(str).str.upper() == iso2_q
            if alias_iso:
                m_iso |= df["ISO2"].astype(str).str.upper() == alias_iso

            # token overlap
            q_tokens = set(_clean_name(q).split())

            def has_overlap(s: str) -> bool:
                if not q_tokens:
                    return True
                return len(set(s.split()) & q_tokens) > 0

            m_bag = norm_country.map(has_overlap)

            mask |= m_country | m_iso | m_bag

        return mask

    def _update_status(self, text: str):
        try:
            self.w.status_lbl.setText(text)
        except Exception:
            pass

    def _suggest_matches(self, df: pd.DataFrame, terms: List[str]) -> list[str]:
        """Return best fuzzy match names for each term (if any)."""
        suggestions = []
        for q in terms:
            q = q.strip()
            if not q:
                continue
            try:
                name, sub = fuzzy_country_lookup(df, q)
                if name:
                    suggestions.append(name)
            except Exception:
                continue
        # de-dup while preserving order
        seen = set()
        out = []
        for s in suggestions:
            if s not in seen:
                out.append(s)
                seen.add(s)
        return out

    def on_run(self):
        # 1) Run pipeline
        self._update_status("Running pipeline…")
        try:
            self.model = RiskModel(
                self.w.base_edit.text().strip(), self.w.alias_edit.text().strip()
            )
            df = self.model.run(
                w_apt=self.w.w_apt.value(),
                w_gci=self.w.w_gci.value(),
                w_ncsi=self.w.w_ncsi.value(),
                w_mal=self.w.w_mal.value(),
                w_spam=self.w.w_spam.value(),
                presence_mode=self.w.presence_mode.currentText(),
                presence_cap=self.w.presence_cap.text().strip(),
                quantiles=[
                    float(x.strip())
                    for x in self.w.quantiles.text().split(",")
                    if x.strip()
                ],
                exclude_names=[
                    x.strip()
                    for x in self.w.excl_names.toPlainText().splitlines()
                    if x.strip()
                ],
                exclude_iso2=[
                    x.strip().upper()
                    for x in self.w.excl_iso2.text().split(",")
                    if x.strip()
                ],
                ncsi_missing=self.w.ncsi_missing.currentText(),
            )
        except Exception as e:
            self._update_status("Run failed.")
            QtWidgets.QMessageBox.critical(self.w, "Run failed", str(e))
            return

        total_rows = len(df)
        self._last_pipeline_df = df.copy()
        self._update_status(f"Pipeline rows: {total_rows}")

        # 2) Search (alias- & fuzzy-aware)
        terms = [t.strip() for t in self.w.search_edit.text().split(",") if t.strip()]
        if terms:
            mask = self._build_search_mask(df, terms)
            df = df[mask]

        after_search = len(df)

        # 3) If nothing matched: suggest & show unfiltered top-N so user sees data
        if df.empty:
            suggestions = (
                self._suggest_matches(self._last_pipeline_df, terms) if terms else []
            )
            msg = "No rows matched your search."
            if suggestions:
                msg += "\n\nClosest matches:\n  - " + "\n  - ".join(suggestions)
            QtWidgets.QMessageBox.information(self.w, "No results", msg)

            # Show unfiltered pipeline head
            N = self.w.topn.value()
            view_df = (
                self._last_pipeline_df.head(N) if N > 0 else self._last_pipeline_df
            )

            # Column selection with safe fallback to "all"
            cols = [c for c in self.w.selected_columns() if c in view_df.columns]
            if not cols:
                cols = list(view_df.columns)
            view_df = view_df[cols]

            self.w.model.setDataFrame(view_df)
            self.w.table.resizeColumnsToContents()
            self._last_full_df = self._last_pipeline_df.copy()
            self.w.export_btn.setEnabled(True)
            self._update_status(
                f"Pipeline rows: {total_rows} | After search: 0 | Displayed (unfiltered): {len(view_df)}"
            )
            return

        # 4) Top-N on filtered set
        N = self.w.topn.value()
        view_df = df.head(N) if N > 0 else df
        displayed = len(view_df)

        # 5) Column selection with safe fallback to "all"
        cols = [c for c in self.w.selected_columns() if c in view_df.columns]
        if not cols:
            cols = list(view_df.columns)
        view_df = view_df[cols]

        # 6) Update table + controls + status
        self.w.model.setDataFrame(view_df)
        self.w.table.resizeColumnsToContents()
        self._last_full_df = df
        self.w.export_btn.setEnabled(True)
        self._update_status(
            f"Pipeline rows: {total_rows} | After search: {after_search} | Displayed: {displayed}"
        )

    def on_export(self):
        if self._last_full_df.empty:
            QtWidgets.QMessageBox.warning(self.w, "Export", "No data to export.")
            return
        path, _ = QtWidgets.QFileDialog.getSaveFileName(
            self.w, "Save CSV", "country_risk_scored.csv", "CSV Files (*.csv)"
        )
        if not path:
            return
        try:
            self._last_full_df.to_csv(path, index=False)
            QtWidgets.QMessageBox.information(self.w, "Export", f"Saved: {path}")
        except Exception as e:
            QtWidgets.QMessageBox.critical(self.w, "Export", f"Failed to save: {e}")
