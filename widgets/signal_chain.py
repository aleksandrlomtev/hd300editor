"""
SignalChainPanel — горизонтальная панель сигнальной цепочки с drag-n-drop.

Три зоны дропа:
  Зона 1 (Global):   drop в пустое место → только flip pre/post
  Зона 2 (Insert):   drop в зазор между блоками → swap + возможно флаги
  Зона 3 (Swap):     drop прямо на блок → безусловный свап содержимого
"""

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QPainter, QPen, QColor, QFont
from PyQt6.QtWidgets import QFrame, QHBoxLayout, QLabel, QGraphicsOpacityEffect

from .block_button import BlockButton

# Блоки, которые могут быть целью свапа
# VOL, WAH, GATE, AMP, CAB — нельзя свапать содержимое
_SWAP_TARGETS = frozenset({"FX1", "FX2", "FX3", "REV"})

# Ширина зоны «вставки между блоками» — кол-во пикселей, которые откусываем
# от края каждого блока. Итоговая ширина Zone 2 = gap + 2 * _ZONE2_MARGIN.
# При gap=6px и MARGIN=14 → Zone 2 = 34px. Увеличь если промахиваешься.
_ZONE2_MARGIN = 14


class SignalChainPanel(QFrame):
    block_clicked           = pyqtSignal(str)
    block_right_clicked     = pyqtSignal(str)
    pre_post_changed        = pyqtSignal(str, int)        # bid, new_pp   — Зона 1
    block_swap_requested    = pyqtSignal(str, str, int)   # src, tgt, new_pp_src — Зона 2
    block_unconditional_swap = pyqtSignal(str, str)       # src, tgt      — Зона 3

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("chainPanel")
        self.setFixedHeight(120)
        self.setAcceptDrops(True)
        self.experimental_routing = False # Если False — только pre/post флип
        self._buttons = []   # list of BlockButton currently shown
        self._amp_x   = 0    # X-mid of AMP block (для разделения PRE/POST)

        self._layout = QHBoxLayout(self)
        self._layout.setContentsMargins(16, 8, 16, 8)
        self._layout.setSpacing(4)

    def rebuild(self, ordered_ids, states, selected_id):
        # убираем всё
        while self._layout.count():
            item = self._layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
            else:
                self._layout.removeItem(item)
        self._buttons.clear()

        # Центрируем цепочку
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
            btn = BlockButton(st, selected=(bid == selected_id))
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

        # ── Сигнальная цепь (линия между блоками) ──
        pen = QPen(QColor("#d6923c"), 2)
        painter.setPen(pen)
        y = self.height() // 2 - 8
        if len(self._buttons) >= 2:
            for i in range(len(self._buttons) - 1):
                b1 = self._buttons[i]
                b2 = self._buttons[i+1]
                x1 = b1.mapTo(self, b1.rect().center()).x()
                x2 = b2.mapTo(self, b2.rect().center()).x()
                painter.drawLine(x1, y, x2, y)

        # ── Drag-zone оверлеи ──
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
            # Zone 1: подсвечиваем PRE или POST зону
            if new_pp == 0:
                # PRE — левая часть (до AMP)
                color = QColor(41, 128, 185, 28)   # синий
                text_color = QColor("#5dade2")
                rx, rw = 0, int(amp_x)
                label = "→  PRE"
            else:
                # POST — правая часть (после AMP)
                color = QColor(230, 126, 34, 28)   # оранжевый
                text_color = QColor("#e59866")
                rx, rw = int(amp_x), w - int(amp_x)
                label = "POST  ←"

            painter.fillRect(rx, 0, rw, h, color)
            painter.setPen(text_color)
            painter.drawText(rx + 8, h - 10, label)

        elif zone == 2:
            # Zone 2: вертикальная линия вставки
            pen_ins = QPen(QColor("#3498db"), 2, Qt.PenStyle.SolidLine)
            painter.setPen(pen_ins)
            ix = int(drop_x)
            painter.drawLine(ix, 6, ix, h - 6)

            # Треугольник-стрелка сверху
            painter.setBrush(QColor("#3498db"))
            painter.setPen(Qt.PenStyle.NoPen)
            from PyQt6.QtGui import QPolygon
            from PyQt6.QtCore import QPoint
            painter.drawPolygon(QPolygon([
                QPoint(ix - 5, 6),
                QPoint(ix + 5, 6),
                QPoint(ix, 14),
            ]))

            # Подпись
            painter.setPen(QColor("#3498db"))
            painter.drawText(ix + 8, 20, "⇄ SWAP")

        painter.end()


    # ── Drag visual feedback ──────────────────────────────────────────

    def _update_drag_visuals(self, src_bid, zone, tgt_bid, new_pp, drop_x):
        """Обновляет визуальное состояние кнопок и метаданные для paintEvent."""
        self._dv_zone   = zone
        self._dv_tgt    = tgt_bid
        self._dv_src    = src_bid
        self._dv_drop_x = drop_x
        self._dv_new_pp = new_pp

        for btn in self._buttons:
            bid = btn.state.block_id
            col = btn.state.color()
            hm  = getattr(btn.window(), "helix_mode", False)
            bg  = "#000000" if hm else "#1e2126"

            if bid == src_bid:
                # Тащимый блок: пунктирная рамка + полупрозрачность
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
                # Zone 3: цель свапа — красное свечение
                btn.setStyleSheet("""
                    BlockButton {
                        background: rgba(231, 76, 60, 35);
                        border: 2px solid #e74c3c;
                        border-radius: 8px;
                    }
                """)
                btn.setGraphicsEffect(None)

            elif zone == 2 and bid == tgt_bid:
                # Zone 2: жертва вставки — синее свечение
                btn.setStyleSheet("""
                    BlockButton {
                        background: rgba(52, 152, 219, 30);
                        border: 2px solid #3498db;
                        border-radius: 8px;
                    }
                """)
                btn.setGraphicsEffect(None)

            elif bid in _SWAP_TARGETS and bid != src_bid and getattr(self, "experimental_routing", False):
                # Другие свапаемые блоки: слегка тускнеют (только если Free Routing включен)
                btn._refresh_style()
                eff = QGraphicsOpacityEffect(btn)
                eff.setOpacity(0.4)
                btn.setGraphicsEffect(eff)

            else:
                # Несвапаемые (WAH, GATE, AMP, CAB, VOL): без изменений
                btn._refresh_style()
                btn.setGraphicsEffect(None)

        self.update()

    def _clear_drag_visuals(self):
        """Сбрасывает все визуальные подсказки drag'а."""
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
            # Безусловный свап — pre/post не трогаем
            if tgt_bid and tgt_bid != src_bid:
                self.block_unconditional_swap.emit(src_bid, tgt_bid)
        elif zone == 2:
            # Свап с жертвой (правым блоком зазора) + возможно флаги
            if tgt_bid and tgt_bid != src_bid:
                self.block_swap_requested.emit(src_bid, tgt_bid, new_pp)
        else:
            # Зона 1: только flip pre/post
            self.pre_post_changed.emit(src_bid, new_pp)

    def _detect_drop_zone(self, drop_x: float, src_bid: str) -> tuple[int, str | None]:
        """Определяем зону дропа и цель.

        Порядок проверки: Zone 2 (с расширением) → Zone 3 → Zone 1.
        Zone 2 проверяется первой, чтобы края блоков триггерили вставку,
        а не безусловный свап.

        Returns:
            (zone, target_bid)
            zone 3 → drop в центральную зону блока (безусловный свап)
            zone 2 → drop на край блока или в зазор (вставка со свапом)
            zone 1 → drop в пустое пространство (только pre/post флип)
        """
        # Защита: VOL, WAH, GATE, AMP, CAB не могут свапаться вообще.
        # Или если экспериментальный роутинг выключен в настройках.
        if src_bid not in _SWAP_TARGETS or not getattr(self, "experimental_routing", False):
            return (1, None)

        # Зона 2: зазор между блоками + _ZONE2_MARGIN пикселей с каждой стороны.
        # Проверяем ПЕРВОЙ — если попали на край блока, это вставка, не свап.
        for i in range(len(self._buttons) - 1):
            b1 = self._buttons[i]
            b2 = self._buttons[i + 1]
            right_of_b1 = b1.mapTo(self, b1.rect().topRight()).x()
            left_of_b2  = b2.mapTo(self, b2.rect().topLeft()).x()
            # Расширенная зона: от правого края b1 минус марджин до левого b2 плюс марджин
            if (right_of_b1 - _ZONE2_MARGIN) <= drop_x <= (left_of_b2 + _ZONE2_MARGIN):
                if b2.state.block_id in _SWAP_TARGETS:
                    return (2, b2.state.block_id)
                if b1.state.block_id in _SWAP_TARGETS:
                    return (2, b1.state.block_id)
                # Оба не свапаемые — Zone 1
                return (1, None)

        # Зона 3: попали строго в центральную часть блока (за пределами Zone 2 марджина)
        for btn in self._buttons:
            btn_left  = btn.mapTo(self, btn.rect().topLeft()).x()
            btn_right = btn.mapTo(self, btn.rect().topRight()).x()
            if btn_left <= drop_x <= btn_right:
                if btn.state.block_id in _SWAP_TARGETS:
                    return (3, btn.state.block_id)
                # WAH/GATE/AMP/CAB/VOL — Zone 1 (не свапаем)
                return (1, None)

        # Зона 1: пустое пространство
        return (1, None)


    def _get_amp_center_x(self):
        for btn in self._buttons:
            if btn.state.block_id == "AMP":
                return btn.mapTo(self, btn.rect().center()).x()
        return self.width() // 2
