"""Dark variant of the GenesisCare Physics design system for the Qt GUI.

The design system (colors_and_type.css) is white-paper-first; the desktop app is
dark. The rules carry over unchanged - one brand green, fine 1 px rules that carry
elevation instead of shadows, 8 px corners on rectangles, 999 px capsules reserved
for status, uppercase only for eyebrows / metric labels / status chips - and the
neutrals are inverted onto a near-black ground.
"""
from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QFrame, QHBoxLayout, QLabel, QPushButton, QVBoxLayout, QWidget

# ---- tokens -------------------------------------------------------------------
GROUND = "#141518"        # page ground (dock background)
CARD = "#1c1d21"          # cards, primary surface
BAND = "#26282d"          # table header / tile bg
LINE = "#33363c"          # borders, dividers
INK_STRONG = "#f3f3f4"    # headings, primary text
INK = "#d6d7db"           # body text
MUTED = "#9b9da5"         # captions, labels

GREEN = "#00a869"         # brand - buttons, eyebrow, highlight
GREEN_TEXT = "#3fd193"    # brand green lifted for legibility on dark

# (background, border, text) - pills and notices share these pairings
PASS = ("#0f2f22", "#1e6a4a", "#4fd39a")
NEAR = ("#33280f", "#7a5f1f", "#f0cf8a")
FAIL = ("#3a1917", "#8a3a32", "#f4948a")
REVIEW = ("#26282d", "#44474e", INK)
ERROR = ("#26282d", "#8a3a32", "#f4948a")
INFO = ("#10241b", "#1e6a4a", INK)

STATUS_KIND = {"PASS": PASS, "REVIEW": NEAR, "ACTION": FAIL,
               "REJECTED": REVIEW, "ERROR": ERROR}

RADIUS = 8
FONT = '"Aptos", "Segoe UI", Tahoma, sans-serif'

# Plot series: brand green first, then light neutrals and the semantic tints.
PLOT_CYCLE = ["#00a869", "#c9d3e2", "#f0cf8a", "#78c8ff", "#f4948a", "#9edfc5",
              "#8fa0b8", "#e8a33d"]

PAGE_QSS = f"""
QWidget#gcPage {{ background: {GROUND}; }}
QLabel {{ color: {INK}; font-family: {FONT}; font-size: 12px; }}
QFrame#gcCard {{ background: {CARD}; border: 1px solid {LINE}; border-radius: {RADIUS}px; }}
QLabel {{ background: transparent; border: none; }}
QLabel#gcEyebrow {{ color: {GREEN_TEXT}; font-size: 10px; font-weight: 800;
                    letter-spacing: 1px; }}
QLabel#gcH2 {{ color: {INK_STRONG}; font-size: 14px; font-weight: 700; }}
QLabel#gcMetricLabel {{ color: {MUTED}; font-size: 10px; font-weight: 800; letter-spacing: 0.5px; }}
QLabel#gcMetricValue {{ color: {INK_STRONG}; font-size: 21px; font-weight: 700; }}
QLabel#gcMetricUnit {{ color: {MUTED}; font-size: 10px; }}
QLabel#gcMuted {{ color: {MUTED}; font-size: 11px; }}
QLabel#gcKey {{ color: {MUTED}; font-size: 11px; }}
QLabel#gcValue {{ color: {INK_STRONG}; font-size: 12px; }}
QFrame#gcRule {{ background: {LINE}; border: none; max-height: 1px; min-height: 1px; }}
QPushButton#gcPrimary {{ background: {GREEN}; color: white; border: 1px solid {GREEN};
                         border-radius: {RADIUS}px; min-height: 34px; padding: 6px 14px;
                         font-weight: 800; font-family: {FONT}; }}
QPushButton#gcPrimary:hover {{ background: #00b873; }}
QPushButton#gcPrimary:pressed {{ background: #008f5a; }}
QPushButton#gcPrimary:disabled {{ background: {BAND}; border-color: {LINE}; color: {MUTED}; }}
QPushButton#gcSecondary {{ background: {CARD}; color: {INK_STRONG}; border: 1px solid {LINE};
                           border-radius: {RADIUS}px; min-height: 34px; padding: 6px 14px;
                           font-weight: 800; font-family: {FONT}; }}
QPushButton#gcSecondary:hover {{ border-color: {MUTED}; }}
QScrollArea#gcScroll {{ background: {GROUND}; border: none; }}
"""


# ---- helpers ------------------------------------------------------------------
def page(widget: QWidget) -> QWidget:
    """Mark a widget as a design-system page (dark ground + label defaults)."""
    widget.setObjectName("gcPage")
    widget.setAttribute(Qt.WA_StyledBackground, True)
    widget.setStyleSheet(PAGE_QSS)
    return widget


def label(text: str, name: str = "", wrap: bool = True) -> QLabel:
    lab = QLabel(text)
    if name:
        lab.setObjectName(name)
    lab.setWordWrap(wrap)
    return lab


def eyebrow(text: str) -> QLabel:
    return label(text.upper(), "gcEyebrow", wrap=False)


def h2(text: str) -> QLabel:
    return label(text, "gcH2")


def rule() -> QFrame:
    f = QFrame()
    f.setObjectName("gcRule")
    f.setFrameShape(QFrame.NoFrame)
    return f


def card(margins: tuple[int, int, int, int] = (12, 10, 12, 10), spacing: int = 6) -> tuple[QFrame, QVBoxLayout]:
    """A flat card: CARD fill, 1 px LINE border, 8 px radius, no shadow."""
    f = QFrame()
    f.setObjectName("gcCard")
    f.setFrameShape(QFrame.NoFrame)
    f.setAttribute(Qt.WA_StyledBackground, True)
    lay = QVBoxLayout(f)
    lay.setContentsMargins(*margins)
    lay.setSpacing(spacing)
    return f, lay


def pill(text: str, kind: tuple[str, str, str], size: int = 10) -> QLabel:
    """Capsule status chip - uppercase, weight 800, 999 px radius. Status only."""
    bg, border, fg = kind
    lab = QLabel(text.upper())
    height = size + 12
    lab.setFixedHeight(height)
    lab.setStyleSheet(
        f"QLabel {{ background: {bg}; border: 1px solid {border}; color: {fg}; "
        f"border-radius: {height // 2}px; padding: 0 {size}px; font-size: {size}px; "
        f"font-weight: 800; letter-spacing: 0.5px; font-family: {FONT}; }}")
    return lab


def notice(text: str, kind: tuple[str, str, str]) -> QFrame:
    """Full-width notice box; full sentences ending with periods."""
    bg, border, fg = kind
    f = QFrame()
    f.setAttribute(Qt.WA_StyledBackground, True)
    f.setStyleSheet(f"QFrame {{ background: {bg}; border: 1px solid {border}; "
                    f"border-radius: {RADIUS}px; }} "
                    f"QLabel {{ color: {fg}; background: transparent; border: none; "
                    f"font-size: 12px; }}")
    lay = QVBoxLayout(f)
    lay.setContentsMargins(12, 9, 12, 9)
    lab = QLabel(text if text.endswith(".") else text + ".")
    lab.setWordWrap(True)
    lay.addWidget(lab)
    return f


def metric(title: str, value: str, unit: str = "") -> QFrame:
    """Metric card: uppercase 800 label over a 1.6 rem bold number with its unit."""
    f, lay = card((12, 9, 12, 9), 2)
    lay.addWidget(label(title.upper(), "gcMetricLabel", wrap=False))
    row = QHBoxLayout()
    row.setSpacing(4)
    row.addWidget(label(value, "gcMetricValue", wrap=False))
    if unit:
        u = label(unit, "gcMetricUnit", wrap=False)
        row.addWidget(u, 0)
    row.addStretch(1)
    lay.addLayout(row)
    return f


def kv_row(key: str, value: str) -> QWidget:
    """Facts row: muted key left, ink value right; a 1 px rule below."""
    w = QWidget()
    lay = QVBoxLayout(w)
    lay.setContentsMargins(0, 0, 0, 0)
    lay.setSpacing(4)
    row = QHBoxLayout()
    row.setContentsMargins(0, 3, 0, 3)
    k = label(key, "gcKey", wrap=False)
    v = label(value, "gcValue", wrap=False)
    v.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
    row.addWidget(k, 1)
    row.addWidget(v, 0)
    lay.addLayout(row)
    lay.addWidget(rule())
    return w


def primary_button(text: str) -> QPushButton:
    b = QPushButton(text)
    b.setObjectName("gcPrimary")
    b.setCursor(Qt.PointingHandCursor)
    return b


def secondary_button(text: str) -> QPushButton:
    b = QPushButton(text)
    b.setObjectName("gcSecondary")
    return b
