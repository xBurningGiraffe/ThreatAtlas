# cyber_risk/gui/view.py
from __future__ import annotations
from typing import List
import os

from PyQt6 import QtCore, QtWidgets
import pandas as pd

# project root = folder containing this 'gui' package's parent directory
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), os.pardir))

DEFAULT_BASE_CSV = os.path.join(PROJECT_ROOT, "country_risk.csv")
DEFAULT_ALIAS_TXT = os.path.join(PROJECT_ROOT, "alias.txt")

DEFAULT_PRINT_COLS = [
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


class DataFrameModel(QtCore.QAbstractTableModel):
    def __init__(self, df: pd.DataFrame = pd.DataFrame(), parent=None):
        super().__init__(parent)
        self._df = df.copy()

    def setDataFrame(self, df: pd.DataFrame):
        self.beginResetModel()
        self._df = df.copy()
        self.endResetModel()

    def rowCount(self, parent=QtCore.QModelIndex()) -> int:
        return 0 if parent.isValid() else len(self._df)

    def columnCount(self, parent=QtCore.QModelIndex()) -> int:
        return 0 if parent.isValid() else len(self._df.columns)

    def data(self, index, role=QtCore.Qt.ItemDataRole.DisplayRole):
        if not index.isValid():
            return None
        if role == QtCore.Qt.ItemDataRole.DisplayRole:
            val = self._df.iat[index.row(), index.column()]
            if pd.isna(val):
                return ""
            col = self._df.columns[index.column()]
            try:
                if col == "Risk_Score":
                    return f"{float(val):,.2f}"
                if col == "Spam_Magnitude":
                    return f"{float(val):.1f}"
                if col in ("GCI_Sum", "NCSI_Score"):
                    return f"{float(val):.2f}"
            except Exception:
                pass
            return str(val)
        return None

    def headerData(self, section, orientation, role=QtCore.Qt.ItemDataRole.DisplayRole):
        if role != QtCore.Qt.ItemDataRole.DisplayRole:
            return None
        return (
            str(self._df.columns[section])
            if orientation == QtCore.Qt.Orientation.Horizontal
            else str(section + 1)
        )


class MainWindow(QtWidgets.QMainWindow):
    runRequested = QtCore.pyqtSignal()
    exportRequested = QtCore.pyqtSignal()

    def __init__(self):
        super().__init__()
        self.setWindowTitle("Country Cyber Risk — Desktop")
        self.resize(1280, 800)

        central = QtWidgets.QWidget(self)
        self.setCentralWidget(central)
        self.model = DataFrameModel(pd.DataFrame(columns=DEFAULT_PRINT_COLS))
        self.table = QtWidgets.QTableView()
        self.table.setModel(self.model)
        self.table.setSortingEnabled(True)
        self.table.horizontalHeader().setStretchLastSection(True)

        # Left controls
        left = QtWidgets.QVBoxLayout()

        # Data Files
        self.base_edit = QtWidgets.QLineEdit(DEFAULT_BASE_CSV)
        self.alias_edit = QtWidgets.QLineEdit(DEFAULT_ALIAS_TXT)
        left.addWidget(
            self._group_form(
                "Data Files",
                [
                    (
                        "Base CSV:",
                        self._with_browse(self.base_edit, "CSV Files (*.csv)"),
                    ),
                    (
                        "Aliases:",
                        self._with_browse(
                            self.alias_edit, "Text Files (*.txt);;All Files (*)"
                        ),
                    ),
                ],
            )
        )

        # Weights
        self.w_apt = self._dspin(0.5)
        self.w_gci = self._dspin(0.2)
        self.w_ncsi = self._dspin(0.2)
        self.w_mal = self._dspin(0.1)
        self.w_spam = self._dspin(0.1)
        left.addWidget(
            self._group_form(
                "Weights",
                [
                    ("APT:", self.w_apt),
                    ("GCI:", self.w_gci),
                    ("NCSI:", self.w_ncsi),
                    ("Exploit rank (Spamhaus):", self.w_mal),
                    ("Spam magnitude (Talos):", self.w_spam),
                ],
            )
        )

        # Presence & Banding
        self.presence_mode = QtWidgets.QComboBox()
        self.presence_mode.addItems(["multiplicative", "percentile"])
        self.presence_cap = QtWidgets.QLineEdit("0:0.4,1-4:0.7,5-:1.0")
        self.quantiles = QtWidgets.QLineEdit("0.20,0.50,0.80,0.95")
        self.ncsi_missing = QtWidgets.QComboBox()
        self.ncsi_missing.addItems(["drop", "impute", "scale"])
        left.addWidget(
            self._group_form(
                "Presence & Banding",
                [
                    ("Presence mode:", self.presence_mode),
                    ("Presence cap:", self.presence_cap),
                    ("Quantiles:", self.quantiles),
                    ("NCSI missing:", self.ncsi_missing),
                ],
            )
        )

        # Exclusions
        self.excl_names = QtWidgets.QPlainTextEdit()
        self.excl_iso2 = QtWidgets.QLineEdit("")
        left.addWidget(
            self._group_form(
                "Exclusions",
                [
                    ("Exclude Countries (one per line):", self.excl_names),
                    ("Exclude ISO2 (comma):", self.excl_iso2),
                ],
            )
        )

        # Columns
        self.col_list = QtWidgets.QListWidget()
        self.col_list.setSelectionMode(
            QtWidgets.QAbstractItemView.SelectionMode.NoSelection
        )
        for c in DEFAULT_PRINT_COLS:
            it = QtWidgets.QListWidgetItem(c)
            it.setFlags(it.flags() | QtCore.Qt.ItemFlag.ItemIsUserCheckable)
            it.setCheckState(QtCore.Qt.CheckState.Checked)
            self.col_list.addItem(it)
        gb = QtWidgets.QGroupBox("Columns to Display")
        v = QtWidgets.QVBoxLayout(gb)
        v.addWidget(self.col_list)
        left.addWidget(gb)

        # Search / TopN
        self.search_edit = QtWidgets.QLineEdit()
        self.topn = QtWidgets.QSpinBox()
        self.topn.setRange(1, 9999)
        self.topn.setValue(10)
        left.addWidget(
            self._group_form(
                "Search & Output",
                [
                    ("Search (comma terms):", self.search_edit),
                    ("Top N:", self.topn),
                ],
            )
        )

        # Buttons
        self.run_btn = QtWidgets.QPushButton("Run Scoring")
        self.export_btn = QtWidgets.QPushButton("Export CSV")
        self.export_btn.setEnabled(False)
        hb = QtWidgets.QHBoxLayout()
        hb.addWidget(self.run_btn)
        hb.addWidget(self.export_btn)
        left.addLayout(hb)

        # Status label (NEW)
        self.status_lbl = QtWidgets.QLabel("Ready.")
        left.addWidget(self.status_lbl)

        # Split
        hl = QtWidgets.QHBoxLayout(central)
        left_scroll = QtWidgets.QScrollArea()
        left_scroll.setWidgetResizable(True)
        wrap = QtWidgets.QWidget()
        ll = QtWidgets.QVBoxLayout(wrap)
        ll.addLayout(left)
        ll.addStretch(1)
        left_scroll.setWidget(wrap)
        hl.addWidget(left_scroll, 0)
        hl.addWidget(self.table, 1)

        # Signals
        self.run_btn.clicked.connect(self.runRequested.emit)
        self.export_btn.clicked.connect(self.exportRequested.emit)

    # ---- helpers ----
    def _with_browse(self, line: QtWidgets.QLineEdit, filt: str):
        btn = QtWidgets.QPushButton("Browse…")
        btn.clicked.connect(lambda: self._pick(line, filt))
        hb = QtWidgets.QHBoxLayout()
        hb.addWidget(line)
        hb.addWidget(btn)
        w = QtWidgets.QWidget()
        w.setLayout(hb)
        return w

    def _pick(self, line: QtWidgets.QLineEdit, filt: str):
        path, _ = QtWidgets.QFileDialog.getOpenFileName(self, "Select file", "", filt)
        if path:
            line.setText(path)

    def _group_form(self, title: str, rows: list[tuple[str, QtWidgets.QWidget]]):
        gb = QtWidgets.QGroupBox(title)
        form = QtWidgets.QFormLayout()
        for label, widget in rows:
            form.addRow(label, widget)
        gb.setLayout(form)
        return gb

    def _dspin(self, default: float):
        sp = QtWidgets.QDoubleSpinBox()
        sp.setRange(0.0, 1.0)
        sp.setSingleStep(0.05)
        sp.setDecimals(3)
        sp.setValue(default)
        sp.setAlignment(QtCore.Qt.AlignmentFlag.AlignRight)
        return sp

    # ---- used by controller ----
    def selected_columns(self) -> List[str]:
        cols = []
        for i in range(self.col_list.count()):
            it = self.col_list.item(i)
            if it.checkState() == QtCore.Qt.CheckState.Checked:
                cols.append(it.text())
        return cols
