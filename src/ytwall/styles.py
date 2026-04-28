"""Tailwind-inspired dark theme for the ytwall UI."""

from __future__ import annotations

QSS = """
* { font-family: "Inter", "Segoe UI Variable", "Segoe UI", sans-serif; font-size: 13px; color: #e5e7eb; }

QMainWindow, QWidget#root { background-color: #0b0d12; }

QFrame#sidebar {
    background-color: #0f1218;
    border-right: 1px solid #1f2330;
    min-width: 220px; max-width: 220px;
}

QLabel#brand { font-size: 18px; font-weight: 700; color: #fafafa; padding: 18px 18px 6px; }
QLabel#brand-sub { color: #6b7280; padding: 0 18px 18px; font-size: 11px; letter-spacing: 0.08em; }

QPushButton#nav {
    background: transparent; border: none; padding: 10px 16px; margin: 2px 10px;
    text-align: left; border-radius: 10px; color: #c7cad1;
}
QPushButton#nav:hover { background: #1a1f2c; color: #ffffff; }
QPushButton#nav[active="true"] {
    background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #6d28d9, stop:1 #7c3aed);
    color: #ffffff; font-weight: 600;
}

QFrame#card {
    background-color: #11151d; border: 1px solid #1f2330; border-radius: 16px;
}

QLabel#h1 { font-size: 22px; font-weight: 700; color: #fafafa; }
QLabel#h2 { font-size: 16px; font-weight: 600; color: #e5e7eb; }
QLabel#muted { color: #8b8f99; }
QLabel#error { color: #f87171; }
QLabel#success { color: #34d399; }

QLineEdit, QComboBox, QSpinBox {
    background: #0d1118; border: 1px solid #232838; border-radius: 10px;
    padding: 10px 12px; selection-background-color: #6d28d9;
}
QLineEdit:focus, QComboBox:focus, QSpinBox:focus { border-color: #7c3aed; }

QPushButton {
    background: #1b1f2a; border: 1px solid #232838; border-radius: 10px;
    padding: 9px 16px; font-weight: 500;
}
QPushButton:hover { background: #232838; }
QPushButton:disabled { color: #6b7280; background: #161a23; }

QPushButton#primary {
    background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #6d28d9, stop:1 #db2777);
    border: none; color: white; font-weight: 600;
}
QPushButton#primary:hover {
    background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #7c3aed, stop:1 #ec4899);
}
QPushButton#primary:disabled {
    background: #2a2330; color: #6b7280;
}

QPushButton#danger { background: #7f1d1d; border: none; color: #fee2e2; }
QPushButton#danger:hover { background: #991b1b; }

QPushButton#ghost { background: transparent; border: 1px solid #232838; }
QPushButton#ghost:hover { background: #161a23; }

QProgressBar {
    background: #161a23; border: 1px solid #232838; border-radius: 8px;
    text-align: center; height: 18px; color: #e5e7eb;
}
QProgressBar::chunk {
    background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #6d28d9, stop:1 #db2777);
    border-radius: 7px;
}

QScrollArea, QScrollArea > QWidget > QWidget { background: transparent; }
QScrollBar:vertical { background: transparent; width: 10px; margin: 4px 2px; }
QScrollBar::handle:vertical { background: #2a3040; border-radius: 5px; min-height: 24px; }
QScrollBar::handle:vertical:hover { background: #394155; }
QScrollBar::add-line, QScrollBar::sub-line { background: none; height: 0; }

QFrame#clipCard {
    background: #11151d; border: 1px solid #1f2330; border-radius: 14px;
}
QFrame#clipCard:hover { border-color: #2d3346; background: #131822; }
QFrame#clipCard[active="true"] { border-color: #7c3aed; }

QLabel#thumb { background: #050608; border-radius: 10px; }
QLabel#playing { background: #16a34a; color: white; padding: 2px 8px; border-radius: 999px; font-size: 10px; font-weight: 700; }

QCheckBox { spacing: 10px; }
QCheckBox::indicator {
    width: 18px; height: 18px; border-radius: 5px;
    border: 1px solid #2d3346; background: #0d1118;
}
QCheckBox::indicator:checked {
    background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #6d28d9, stop:1 #db2777);
    border: none;
    image: none;
}

QSlider::groove:horizontal { background: #1f2330; height: 6px; border-radius: 3px; }
QSlider::sub-page:horizontal {
    background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #6d28d9, stop:1 #db2777);
    border-radius: 3px;
}
QSlider::handle:horizontal {
    width: 16px; margin: -6px 0; background: white; border-radius: 8px;
}

QStatusBar { background: #0b0d12; color: #6b7280; border-top: 1px solid #1f2330; }

QToolTip { background: #11151d; color: #e5e7eb; border: 1px solid #2d3346; padding: 6px 8px; border-radius: 6px; }
"""
