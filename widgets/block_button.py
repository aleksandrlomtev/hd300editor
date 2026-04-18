"""
BlockButton — icon button for an effect block in the signal chain.
"""

import os
from PyQt6.QtCore import Qt, pyqtSignal, QPoint, QMimeData
from PyQt6.QtGui import QPainter, QColor, QDrag, QPixmap
from PyQt6.QtWidgets import QFrame, QVBoxLayout, QLabel, QGraphicsOpacityEffect

from constants import CATEGORY_IMG, SCRIPT_DIR


class BlockButton(QFrame):
    clicked_sig = pyqtSignal(str)
    right_clicked_sig = pyqtSignal(str)

    def __init__(self, state, selected=False, parent=None):
        super().__init__(parent)
        self.state    = state
        self.selected = selected
        self.setFixedSize(70, 90)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        if state.movable:
            self.setAcceptDrops(False)  # drag source

        self.setToolTip(f"<b>{state.block_id}</b>: {state.name}")
        
        layout = QVBoxLayout(self)
        layout.setContentsMargins(2, 4, 2, 2)
        layout.setSpacing(2)

        self.icon_lbl = QLabel()
        self.icon_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        
        img_name = CATEGORY_IMG.get(state.category)
        icon_path = os.path.join(SCRIPT_DIR, "icons", img_name) if img_name else ""
        
        if img_name and os.path.exists(icon_path):
            pixmap = QPixmap(icon_path)
            pixmap = pixmap.scaled(48, 48, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation)
            self.icon_lbl.setPixmap(pixmap)
            self.icon_lbl.setStyleSheet("background: transparent;")
        else:
            self.icon_lbl.setText(state.icon())
            self.icon_lbl.setStyleSheet("font-size: 22px; background: transparent;")

        self.name_lbl = QLabel(self._short(state.name))
        self.name_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.name_lbl.setWordWrap(True)
        self.name_lbl.setStyleSheet("font-size: 7pt; background: transparent;")

        pp_color = "#e67e22" if state.pre_post == 1 else "#2980b9"
        pp_text  = "POST" if state.pre_post == 1 else "PRE"
        self.pp_lbl = QLabel(pp_text)
        self.pp_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.pp_lbl.setStyleSheet(f"font-size: 7pt; color: {pp_color}; font-weight: bold; background: transparent;")

        layout.addWidget(self.icon_lbl)
        layout.addWidget(self.name_lbl)
        if state.block_id in ("VOL","FX1","FX2","FX3","REV"):
            layout.addWidget(self.pp_lbl)

        self._refresh_style()

    def _short(self, name):
        return name[:9] + "…" if len(name) > 10 else name

    def _refresh_style(self):
        col  = self.state.color()
        sel  = f"border: 2px solid {col};" if self.selected else "border: 1px solid #3a3a3a;"
        # In Black Mode the block background is black, otherwise dark grey
        main_win = self.window()
        hm = getattr(main_win, "black_mode", False) if main_win else False
        bg = "#000000" if hm else "#1e2126"
        self.setStyleSheet(f"""
            BlockButton {{
                background: {bg};
                {sel}
                border-radius: 8px;
            }}
        """)
        
        # Dim the icon if block is off (keep text readable)
        if not self.state.is_on:
            eff_icon = QGraphicsOpacityEffect(self)
            eff_icon.setOpacity(0.55)
            self.icon_lbl.setGraphicsEffect(eff_icon)
        else:
            self.icon_lbl.setGraphicsEffect(None)
            self.name_lbl.setGraphicsEffect(None)

    def paintEvent(self, event):
        super().paintEvent(event)
        if not self.state.is_on:
            painter = QPainter(self)
            painter.setBrush(QColor(0, 0, 0, 150))
            painter.setPen(Qt.PenStyle.NoPen)
            painter.drawRoundedRect(self.rect(), 8, 8)

    def mousePressEvent(self, e):
        if e.button() == Qt.MouseButton.LeftButton:
            self._drag_start = e.position().toPoint()
            self.clicked_sig.emit(self.state.block_id)
        elif e.button() == Qt.MouseButton.RightButton:
            self.right_clicked_sig.emit(self.state.block_id)

    def mouseMoveEvent(self, e):
        # Drag-n-drop: free routing of FX chain
        if not self.state.movable:
            return
        if e.buttons() != Qt.MouseButton.LeftButton:
            return
        # Only if passed 8px threshold — otherwise accidental click starts drag
        if not hasattr(self, '_drag_start'):
            return
        delta = e.position().toPoint() - self._drag_start
        if delta.manhattanLength() < 8:
            return
        drag  = QDrag(self)
        mime  = QMimeData()
        mime.setText(self.state.block_id)
        drag.setMimeData(mime)
        # Semi-transparent ghost — like it's floating
        src_px = self.grab()
        ghost  = QPixmap(src_px.size())
        ghost.fill(Qt.GlobalColor.transparent)
        p = QPainter(ghost)
        p.setOpacity(0.7)
        p.drawPixmap(0, 0, src_px)
        p.end()
        drag.setPixmap(ghost)
        drag.setHotSpot(QPoint(ghost.width() // 2, ghost.height() // 2))
        drag.exec(Qt.DropAction.MoveAction)

