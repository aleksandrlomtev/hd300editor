"""
ParamRow — parameter row (slider/combobox) and DiModeButton (button with RMB handling).
"""

import time
from PyQt6.QtCore import Qt, pyqtSignal, QPropertyAnimation, QEasingCurve, QTimer
from PyQt6.QtWidgets import (
    QWidget, QHBoxLayout, QLabel, QPushButton, QSlider,
    QCheckBox, QLineEdit, QComboBox, QSpinBox, QDoubleSpinBox,
    QGraphicsOpacityEffect,
)


class ParamRow(QWidget):
    """Editor parameter row widget."""
    value_changed = pyqtSignal(int, float)  # hw_idx, pct
    learn_clicked = pyqtSignal(object)      # self

    def __init__(self, cfg, pct=50.0, mapping_mode=False, parent=None, color="#d6923c"):
        super().__init__(parent)
        self.cfg          = cfg
        self._mapping     = mapping_mode
        self.color        = color
        self._anim_qtimer = None
        self._anim_timer_count = 0
        self._last_user_edit = 0
        self._target_pct = pct # Store target value
        
        # Effect for smooth appearance
        self._opacity_effect = QGraphicsOpacityEffect(self)
        self._opacity_effect.setOpacity(0.0)
        self.setGraphicsEffect(self._opacity_effect)
        
        self._build(pct)

    def show_animated(self, delay=0):
        """Smooth appearance of the entire row with delay."""
        try:
            self._opacity_effect.setOpacity(0.0)
            self._anim_fade = QPropertyAnimation(self._opacity_effect, b"opacity")
            self._anim_fade.setDuration(250)
            self._anim_fade.setStartValue(0.0)
            self._anim_fade.setEndValue(1.0)
            self._anim_fade.setEasingCurve(QEasingCurve.Type.OutCubic)
            QTimer.singleShot(delay, self._anim_fade.start)
        except RuntimeError: pass

    def _build(self, pct):
        lay = QHBoxLayout(self)
        lay.setContentsMargins(4, 2, 4, 2)
        lay.setSpacing(8)

        if self._mapping:
            # 3. METADATA (NAME)
            self.name_edit = QLineEdit(self.cfg.get("name", ""))
            self.name_edit.setFixedWidth(140)
            self.name_edit.setPlaceholderText("Name...")
            self.name_edit.setStyleSheet("background: #1a1a1a; border: 1px solid #333; padding-left: 4px; height: 20px;")
            self.name_edit.textChanged.connect(self._on_name)
            lay.addWidget(self.name_edit)
            
            # 2. BINDING (HW ID)
            self.idx_spin = QSpinBox()
            self.idx_spin.setRange(0, 63)
            self.idx_spin.setValue(self.cfg.get("hw_idx", 0))
            self.idx_spin.setFixedWidth(65)
            self.idx_spin.setStyleSheet("background: #1a1a1a; border: 1px solid #333; padding: 2px;")
            self.idx_spin.valueChanged.connect(self._on_idx)
            lay.addWidget(self.idx_spin)
            
            # 2. BINDING (Learn)
            self.btn_learn = QPushButton("LEARN")
            self.btn_learn.setFixedWidth(65)
            self.btn_learn.setFixedHeight(24)
            self.btn_learn.setCheckable(True)
            self.btn_learn.setToolTip("Learn: Click and turn a knob on the processor")
            self.btn_learn.setStyleSheet(f"QPushButton {{ background: #333; font-size: 7pt; font-weight: bold; }} QPushButton:checked {{ background: {self.color}; color: white; border-radius: 4px; }}")
            self.btn_learn.clicked.connect(self._on_learn)
            lay.addWidget(self.btn_learn)

            # 3. METADATA (STEP)
            self.step_spin = QDoubleSpinBox()
            self.step_spin.setRange(0.1, 100.0)
            self.step_spin.setSingleStep(0.5)
            self.step_spin.setValue(self.cfg.get("step", 1.0))
            self.step_spin.setFixedWidth(75)
            self.step_spin.setStyleSheet("background: #1a1a1a; border: 1px solid #333; padding: 2px;")
            lay.addWidget(self.step_spin)

            lay.addSpacing(10)

            # 1. MASTER ENABLE (ON)
            self.en_chk = QCheckBox("ON")
            self.en_chk.setFixedWidth(44)
            self.en_chk.setChecked(self.cfg.get("enabled", True))
            self.en_chk.toggled.connect(self._on_enable)
            self.en_chk.setStyleSheet("color: #27ae60; font-weight: bold;")
            lay.addWidget(self.en_chk)
            
            lay.addSpacing(10)
        else:
            name = self.cfg.get("name", "?")
            lbl = QLabel(name.upper())
            lbl.setFixedWidth(110)
            lbl.setStyleSheet("color: #9aa; font-size: 8pt; font-weight: bold;")
            lay.addWidget(lbl)

        # Either a dropdown list or a classic slider
        vals = self.cfg.get("values", [])
        if vals:
            self.combo = QComboBox()
            self.combo.addItems(vals)
            self.combo.setFixedWidth(130)
            idx = int(round((pct / 100.0) * (len(vals) - 1)))
            self.combo.setCurrentIndex(max(0, min(len(vals)-1, idx)))
            self.combo.currentIndexChanged.connect(self._on_combo)
            lay.addWidget(self.combo)
            self.slider = None
        else:
            self.slider = QSlider(Qt.Orientation.Horizontal)
            self.slider.setRange(0, 1000)
            self.slider.setValue(int(pct * 10))
            self.slider.setMaximumWidth(400)
            self.slider.valueChanged.connect(self._on_slide)
            self.slider.setStyleSheet(f"""
                QSlider::groove:horizontal {{
                    background: #252830;
                    height: 8px;
                    border-radius: 2px;
                }}
                QSlider::handle:horizontal {{
                    background: {self.color};
                    width: 14px; 
                    height: 14px; 
                    margin: -3px 0;
                    border-radius: 2px;
                }}
                QSlider::sub-page:horizontal {{
                    background: {self.color};
                    border-radius: 2px;
                }}
                QSlider::add-page:horizontal {{
                    background: #252830;
                    border-radius: 2px;
                }}
            """)
            lay.addWidget(self.slider, 1)
            self.combo = None

        if not self.combo:
            self.val_lbl = QLabel()
            self.val_lbl.setFixedWidth(44)
            self.val_lbl.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            self.val_lbl.setStyleSheet("color: #ccc; font-size: 9pt;")
            self._update_text(pct)
            lay.addWidget(self.val_lbl)
        else:
            self.val_lbl = None

    def _update_text(self, pct):
        if not getattr(self, "val_lbl", None):
            return
        unit = self.cfg.get("unit", "%")
        decimals = self.cfg.get("decimals", 1)
        if unit == "steps":
            # Map 0..100% to -24..+24
            steps = round((pct / 100.0) * 48.0 - 24.0)
            self.val_lbl.setText(f"{steps:+d}")
        elif unit == "%":
            self.val_lbl.setText(f"{pct:.{decimals}f}%")
        else:
            min_d = self.cfg.get("min_disp", 0.0)
            max_d = self.cfg.get("max_disp", 100.0)
            disp = min_d + (pct / 100.0) * (max_d - min_d)
            self.val_lbl.setText(f"{disp:.{decimals}f}{unit}")

    def _on_slide(self, v):
        self._last_user_edit = time.time()
        pct = v / 10.0
        self._update_text(pct)
        self.value_changed.emit(self.cfg.get("hw_idx", 0), pct)

    def _on_combo(self, idx):
        self._last_user_edit = time.time()
        vals = self.cfg.get("values", [])
        if not vals: return
        pct = (idx / (len(vals) - 1)) * 100.0 if len(vals) > 1 else 0.0
        self._update_text(pct)
        self.value_changed.emit(self.cfg.get("hw_idx", 0), pct)

    def _on_name(self, t):   self.cfg["name"]    = t
    def _on_idx(self, v):    self.cfg["hw_idx"]  = v
    def _on_enable(self, v): self.cfg["enabled"] = v
    def _on_learn(self):     self.learn_clicked.emit(self)

    def prepare_for_deletion(self):
        """Stops all processes before deleting the widget."""
        self.blockSignals(True)
        if hasattr(self, "_anim_qtimer") and self._anim_qtimer:
            self._anim_qtimer.stop()
            self._anim_qtimer.deleteLater()
            self._anim_qtimer = None
        if hasattr(self, "_anim_fade"):
            self._anim_fade.stop()

    def set_pct(self, pct):
        self._target_pct = pct
        if self.slider:
            self.slider.blockSignals(True)
            self.slider.setValue(int(pct * 10))
            self.slider.blockSignals(False)
        elif self.combo:
            vals = self.cfg.get("values", [])
            if vals:
                idx = int(round((pct / 100.0) * (len(vals) - 1)))
                self.combo.blockSignals(True)
                self.combo.setCurrentIndex(max(0, min(len(vals) - 1, idx)))
                self.combo.blockSignals(False)
        self._update_text(pct)

    def animate_to(self, target_pct, start_pct=None, duration=300, easing=QEasingCurve.Type.OutCubic):
        """Smoothly animates the slider to the target value (% 0-100)."""
        self._target_pct = target_pct
        if not self.slider or not self.isVisible():
            self.set_pct(target_pct)
            return

        if start_pct is not None:
            self.set_pct(start_pct)

        start_val = self.slider.value()
        end_val = int(target_pct * 10)
        
        if abs(start_val - end_val) < 2:
            self.set_pct(target_pct)
            return

        # Stop previous animation if active
        if self._anim_qtimer and self._anim_qtimer.isActive():
            self._anim_qtimer.stop()
        
        if not self._anim_qtimer:
            self._anim_qtimer = QTimer(self)
            self._anim_qtimer.setInterval(16)
            self._anim_qtimer.timeout.connect(self._on_anim_tick)

        self._anim_timer_count = 0
        self._anim_total_steps = max(1, duration // 16)
        self._anim_start_val = start_val
        self._anim_end_val = end_val
        self._anim_qtimer.start()

    def _on_anim_tick(self):
        try:
            self._anim_timer_count += 1
            t = min(1.0, self._anim_timer_count / self._anim_total_steps)
            # OutCubic approximation
            t2 = 1.0 - (1.0 - t) ** 3
            cur = int(self._anim_start_val + (self._anim_end_val - self._anim_start_val) * t2)
            
            self.slider.blockSignals(True)
            self.slider.setValue(cur)
            self.slider.blockSignals(False)
            self._update_text(cur / 10.0)
            
            if t >= 1.0:
                self._anim_qtimer.stop()
                self.set_pct(self._target_pct)
        except RuntimeError:
            if self._anim_qtimer: self._anim_qtimer.stop()


class DiModeButton(QPushButton):
    """Button with Right Click handling (used for DI Mode)."""
    rightClicked = pyqtSignal()

    def __init__(self, text="", parent=None):
        super().__init__(text, parent)
        
    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.RightButton:
            self.rightClicked.emit()
        else:
            super().mousePressEvent(event)
