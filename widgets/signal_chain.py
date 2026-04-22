"""
SignalChainPanel — horizontal signal chain panel with drag-n-drop support.

Three drop zones:
  Zone 1 (Global):   drop on empty space → only flip pre/post
  Zone 2 (Insert):   drop between blocks → swap + optional flags
  Zone 3 (Swap):     drop directly on block → unconditional content swap
"""

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QPainter, QPen, QColor, QFont
from PyQt6.QtWidgets import QFrame, QHBoxLayout, QLabel, QGraphicsOpacityEffect

from .block_button import BlockButton

# Blocks that can be swap targets
# VOL, WAH, GATE, AMP, CAB — content cannot be swapped
_SWAP_TARGETS = frozenset({"FX1", "FX2", "FX3", "REV"})

# Width of "insertion between blocks" zone — number of pixels we take
# from the edge of each block. Total width Zone 2 = gap + 2 * _ZONE2_MARGIN.
# With gap=6px and MARGIN=14 → Zone 2 = 34px. Increase if you miss.
_ZONE2_MARGIN = 14


class SignalChainPanel(QFrame):
    block_clicked           = pyqtSignal(str)
    block_right_clicked     = pyqtSignal(str)
    pre_post_changed        = pyqtSignal(str, int)        # bid, new_pp   — Zone 1
    block_shift_requested   = pyqtSignal(str, str, int)   # src, tgt (insert_before), new_pp — Zone 2
    block_unconditional_swap = pyqtSignal(str, str)       # src, tgt      — Zone 3

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("chainPanel")
        self.setFixedHeight(120)
        self.setAcceptDrops(True)
        self.experimental_routing = False # If False — only pre/post flip
        self._buttons = []   # list of BlockButton currently shown
        self._amp_x   = 0    # X-mid of AMP block (for PRE/POST separation)

        self._layout = QHBoxLayout(self)
        self._layout.setContentsMargins(16, 8, 16, 8)
        self._layout.setSpacing(4)

    def rebuild(self, ordered_ids, states, selected_id):
        # clear everything
        while self._layout.count():
            item = self._layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
            else:
                self._layout.removeItem(item)
        self._buttons.clear()

        # Center the chain
        self._layout.setContentsMargins(16, 2, 16, 2)
        self._layout.setSpacing(6)
        self._layout.addStretch(1)

        # IO dots (In)
        def make_io(char):
            lbl = QLabel(char)
            lbl.setFixedSize(20, 70)
            lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
            lbl.setStyleSheet("color: #444; font-size: 18px;")
            return lbl

        self._layout.addWidget(make_io("○"))

        amp_seen = False
        for bid in ordered_ids:
            st  = states[bid]
            btn = BlockButton(st, selected=(bid == selected_id), parent=self)
            btn.clicked_sig.connect(self.block_clicked)
            btn.right_clicked_sig.connect(self.block_right_clicked)
            self._buttons.append(btn)
            self._layout.addWidget(btn)
            if bid == "AMP" and not amp_seen:
                amp_seen = True

        self._layout.addWidget(make_io("○"))
        self._layout.addStretch(1)
        self.update()

    def update_selection(self, selected_id: str):
        """Only updates the visual highlight of the selected block.
        Does NOT rebuild the layout — safe to call during drag.
        """
        for btn in self._buttons:
            was_selected = btn.selected
            btn.selected = (btn.state.block_id == selected_id)
            if btn.selected != was_selected:
                btn._refresh_style()

    def paintEvent(self, event):
        super().paintEvent(event)
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        # ── Signal chain (line between blocks) ──
        pen = QPen(QColor("#d6923c"), 2)
        painter.setPen(pen)
        y = self.height() // 2 - 8
        if len(self._buttons) >= 2:
            for i in range(len(self._buttons) - 1):
                b1 = self._buttons[i]
                b2 = self._buttons[i+1]
                x1 = b1.mapTo(self, b1.rect().center()).x()
                x2 = b2.mapTo(self, b2.rect().center()).x()
                # Due to async layout during rebuild, buttons can momentarily stick at 0, 0
                if x2 > x1 + 10:
                    painter.drawLine(x1, y, x2, y)

        # ── Drag-zone overlays ──
        zone = getattr(self, "_dv_zone", None)
        if zone is None:
            painter.end()
            return

        amp_x   = self._get_amp_center_x()
        drop_x  = getattr(self, "_dv_drop_x", 0)
        new_pp  = getattr(self, "_dv_new_pp", 0)
        h = self.height()
        w = self.width()

        font = QFont("Segoe UI", 8, QFont.Weight.Bold)
        painter.setFont(font)

        if zone == 1:
            # Zone 1: highlight PRE or POST zone
            if new_pp == 0:
                # PRE — left part (before AMP)
                color = QColor(41, 128, 185, 28)   # blue
                text_color = QColor("#5dade2")
                rx, rw = 0, int(amp_x)
                label = "→  PRE"
            else:
                # POST — right part (after AMP)
                color = QColor(230, 126, 34, 28)   # orange
                text_color = QColor("#e59866")
                rx, rw = int(amp_x), w - int(amp_x)
                label = "POST  ←"

            painter.fillRect(rx, 0, rw, h, color)
            painter.setPen(text_color)
            painter.drawText(rx + 8, h - 10, label)

        elif zone == 2:
            # Zone 2: vertical insertion line
            pen_ins = QPen(QColor("#3498db"), 2, Qt.PenStyle.SolidLine)
            painter.setPen(pen_ins)
            ix = int(drop_x)
            painter.drawLine(ix, 6, ix, h - 6)

            # Arrow triangle at top
            painter.setBrush(QColor("#3498db"))
            painter.setPen(Qt.PenStyle.NoPen)
            from PyQt6.QtGui import QPolygon
            from PyQt6.QtCore import QPoint
            painter.drawPolygon(QPolygon([
                QPoint(ix - 5, 6),
                QPoint(ix + 5, 6),
                QPoint(ix, 14),
            ]))

            # Label
            painter.setPen(QColor("#3498db"))
            painter.drawText(ix + 8, 20, "⇄ SWAP")

        painter.end()


    # ── Drag visual feedback ──────────────────────────────────────────

    def _update_drag_visuals(self, src_bid, zone, tgt_bid, new_pp, drop_x):
        """Updates button visual state and metadata for paintEvent."""
        self._dv_zone   = zone
        self._dv_tgt    = tgt_bid
        self._dv_src    = src_bid
        self._dv_drop_x = drop_x
        self._dv_new_pp = new_pp

        for btn in self._buttons:
            bid = btn.state.block_id
            col = btn.state.color()
            hm  = getattr(btn.window(), "black_mode", False)
            bg  = "#000000" if hm else "#1e2126"

            if bid == src_bid:
                # Dragged block: dashed border + semi-transparency
                btn.setStyleSheet(f"""
                    BlockButton {{
                        background: {bg};
                        border: 2px dashed {col};
                        border-radius: 8px;
                    }}
                """)
                eff = QGraphicsOpacityEffect(btn)
                eff.setOpacity(0.5)
                btn.setGraphicsEffect(eff)

            elif zone == 3 and bid == tgt_bid:
                # Zone 3: swap target — red glow
                btn.setStyleSheet("""
                    BlockButton {
                        background: rgba(231, 76, 60, 35);
                        border: 2px solid #e74c3c;
                        border-radius: 8px;
                    }
                """)
                btn.setGraphicsEffect(None)

            elif zone == 2 and bid == tgt_bid:
                # Zone 2: insertion victim — blue glow
                btn.setStyleSheet("""
                    BlockButton {
                        background: rgba(52, 152, 219, 30);
                        border: 2px solid #3498db;
                        border-radius: 8px;
                    }
                """)
                btn.setGraphicsEffect(None)

            elif bid in _SWAP_TARGETS and bid != src_bid and getattr(self, "experimental_routing", False):
                # Other swappable blocks: dim slightly (only if Free Routing is enabled)
                btn._refresh_style()
                eff = QGraphicsOpacityEffect(btn)
                eff.setOpacity(0.4)
                btn.setGraphicsEffect(eff)

            else:
                # Non-swappable (WAH, GATE, AMP, CAB, VOL): no change
                btn._refresh_style()
                btn.setGraphicsEffect(None)

        self.update()

    def _clear_drag_visuals(self):
        """Resets all drag visual hints."""
        self._dv_zone = None
        for btn in self._buttons:
            btn.setGraphicsEffect(None)
            btn._refresh_style()
        self.update()

    # ── Drop zone detection ───────────────────────────────────────────

    def dragEnterEvent(self, e):
        if e.mimeData().hasText():
            e.acceptProposedAction()

    def dragMoveEvent(self, e):
        if not e.mimeData().hasText():
            return
        e.acceptProposedAction()
        drop_x  = e.position().x()
        src_bid = e.mimeData().text()
        zone, tgt_bid = self._detect_drop_zone(drop_x, src_bid)
        amp_x   = self._get_amp_center_x()
        new_pp  = 1 if (amp_x > 0 and drop_x > amp_x) else 0
        self._update_drag_visuals(src_bid, zone, tgt_bid, new_pp, drop_x)

    def dragLeaveEvent(self, e):
        self._clear_drag_visuals()

    def dropEvent(self, e):
        self._clear_drag_visuals()
        src_bid = e.mimeData().text()
        if not src_bid:
            return

        drop_x = e.position().x()
        zone, tgt_bid = self._detect_drop_zone(drop_x, src_bid)
        amp_x = self._get_amp_center_x()
        new_pp = 1 if (amp_x > 0 and drop_x > amp_x) else 0

        if zone == 3:
            # Unconditional swap — don't touch pre/post
            if tgt_bid and tgt_bid != src_bid:
                self.block_unconditional_swap.emit(src_bid, tgt_bid)
        elif zone == 2:
            # Shift operation (Zone 2) - insert src before tgt
            if tgt_bid != src_bid:
                self.block_shift_requested.emit(src_bid, tgt_bid if tgt_bid else "", new_pp)
        else:
            # Zone 1: only flip pre/post
            self.pre_post_changed.emit(src_bid, new_pp)

    def _detect_drop_zone(self, drop_x: float, src_bid: str) -> tuple[int, str | None]:
        """Detect drop zone and target.

        Check order: Zone 2 (with margin) → Zone 3 → Zone 1.
        Zone 2 is checked first so block edges trigger insertion,
        not unconditional swap.

        Returns:
            (zone, target_bid)
            zone 3 → drop on block central area (unconditional swap)
            zone 2 → drop on block edge or gap (insertion swap)
            zone 1 → drop on empty space (only pre/post flip)
        """
        # Guard: VOL, WAH, GATE, AMP, CAB cannot swap at all.
        # Or if experimental routing is disabled in settings.
        if src_bid not in _SWAP_TARGETS or not getattr(self, "experimental_routing", False):
            return (1, None)

        # Zone 2: gap between blocks + _ZONE2_MARGIN pixels on each side.
        # Check FIRST — if hit block edge, it's an insertion, not a swap.
        for i in range(len(self._buttons) - 1):
            b1 = self._buttons[i]
            b2 = self._buttons[i + 1]
            right_of_b1 = b1.mapTo(self, b1.rect().topRight()).x()
            left_of_b2  = b2.mapTo(self, b2.rect().topLeft()).x()
            # Expanded zone: from right of b1 minus margin to left of b2 plus margin
            if (right_of_b1 - _ZONE2_MARGIN) <= drop_x <= (left_of_b2 + _ZONE2_MARGIN):
                # Find the next swappable block at or after this gap
                insert_before_bid = None
                for btn in self._buttons[i+1:]:
                    if btn.state.block_id in _SWAP_TARGETS:
                        insert_before_bid = btn.state.block_id
                        break
                return (2, insert_before_bid)

        # Zone 3: hit strictly the central part of the block (outside Zone 2 margin)
        for btn in self._buttons:
            btn_left  = btn.mapTo(self, btn.rect().topLeft()).x()
            btn_right = btn.mapTo(self, btn.rect().topRight()).x()
            if btn_left <= drop_x <= btn_right:
                if btn.state.block_id in _SWAP_TARGETS:
                    return (3, btn.state.block_id)
                # WAH/GATE/AMP/CAB/VOL — Zone 1 (no swap)
                return (1, None)

        # Zone 1: empty space
        return (1, None)


    def _get_amp_center_x(self):
        for btn in self._buttons:
            if btn.state.block_id == "AMP":
                return btn.mapTo(self, btn.rect().center()).x()
        return self.width() // 2
