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
            self.idx_spin.setFixedWidth(75)
            self.idx_spin.setButtonSymbols(QSpinBox.ButtonSymbols.NoButtons)
            self.idx_spin.setStyleSheet("background: #1a1a1a; border: 1px solid #333; padding: 2px; font-size: 8pt;")
            self.idx_spin.valueChanged.connect(self._on_idx)
            lay.addWidget(self.idx_spin)
            
            # 2. BINDING (Mode)
            self.mode_combo = QComboBox()
            self.mode_combo.addItem("Linear", 0)
            for s in range(2, 19):
                self.mode_combo.addItem(f"{s} steps", s)
            
            cur_steps = self.cfg.get("discrete_steps", 0)
            if 2 <= cur_steps <= 18:
                self.mode_combo.setCurrentIndex(cur_steps - 1)
            else:
                self.mode_combo.setCurrentIndex(0)
                
            self.mode_combo.setFixedWidth(85)
            self.mode_combo.setStyleSheet("background: #1a1a1a; border: 1px solid #333; font-size: 7pt;")
            self.mode_combo.currentIndexChanged.connect(self._on_mode_changed)
            lay.addWidget(self.mode_combo)

            # 4. SCALING (Min/Max/Unit/Dec)
            self.min_edit = QLineEdit(str(self.cfg.get("min_disp", 0.0)))
            self.min_edit.setFixedWidth(40)
            self.min_edit.setToolTip("Min Display")
            self.min_edit.setStyleSheet("background: #1a1a1a; border: 1px solid #333; font-size: 7pt;")
            self.min_edit.textChanged.connect(lambda t: self._on_meta_update("min_disp", t, float))
            lay.addWidget(self.min_edit)
            
            self.max_edit = QLineEdit(str(self.cfg.get("max_disp", 100.0)))
            self.max_edit.setFixedWidth(40)
            self.max_edit.setToolTip("Max Display")
            self.max_edit.setStyleSheet("background: #1a1a1a; border: 1px solid #333; font-size: 7pt;")
            self.max_edit.textChanged.connect(lambda t: self._on_meta_update("max_disp", t, float))
            lay.addWidget(self.max_edit)
            
            self.unit_edit = QLineEdit(self.cfg.get("suffix", self.cfg.get("unit", "%")))
            self.unit_edit.setFixedWidth(35)
            self.unit_edit.setToolTip("Unit/Suffix")
            self.unit_edit.setStyleSheet("background: #1a1a1a; border: 1px solid #333; font-size: 7pt;")
            self.unit_edit.textChanged.connect(lambda t: self._on_meta_update("suffix", t))
            lay.addWidget(self.unit_edit)

            self.dec_spin = QSpinBox()
            self.dec_spin.setRange(0, 3)
            self.dec_spin.setValue(self.cfg.get("decimals", 1))
            self.dec_spin.setFixedWidth(45)
            self.dec_spin.setButtonSymbols(QSpinBox.ButtonSymbols.NoButtons)
            self.dec_spin.setToolTip("Decimals")
            self.dec_spin.setStyleSheet("background: #1a1a1a; border: 1px solid #333; font-size: 7pt;")
            self.dec_spin.valueChanged.connect(lambda v: self._on_meta_update("decimals", v))
            lay.addWidget(self.dec_spin)

            self.disp_step_spin = QDoubleSpinBox()
            self.disp_step_spin.setRange(0.0, 1000.0)
            self.disp_step_spin.setSingleStep(0.1)
            self.disp_step_spin.setValue(self.cfg.get("display_step", 0.0))
            self.disp_step_spin.setFixedWidth(50)
            self.disp_step_spin.setButtonSymbols(QSpinBox.ButtonSymbols.NoButtons)
            self.disp_step_spin.setToolTip("Display Step (Pseudo-discrete)")
            self.disp_step_spin.setStyleSheet("background: #1a1a1a; border: 1px solid #333; font-size: 7pt;")
            self.disp_step_spin.valueChanged.connect(lambda v: self._on_meta_update("display_step", v))
            lay.addWidget(self.disp_step_spin)

            lay.addSpacing(5)

            # 1. MASTER ENABLE (ON)
            self.en_chk = QCheckBox("ON")
            self.en_chk.setFixedWidth(44)
            self.en_chk.setChecked(self.cfg.get("enabled", True))
            self.en_chk.toggled.connect(self._on_enable)
            self.en_chk.setStyleSheet("color: #27ae60; font-weight: bold; font-size: 8pt;")
            lay.addWidget(self.en_chk)
            
            lay.addSpacing(5)
        else:
            name = self.cfg.get("name", "?")
            lbl = QLabel(name.upper())
            lbl.setFixedWidth(90)
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
            
            d_steps = self.cfg.get("discrete_steps", 0)
            if d_steps > 1:
                self.slider.setRange(0, d_steps - 1)
                self.slider.setValue(int(round((pct / 100.0) * (d_steps - 1))))
                self.slider.setSingleStep(1)
                self.slider.setPageStep(1)
            else:
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
            self.val_lbl.setFixedWidth(70)
            self.val_lbl.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            self.val_lbl.setStyleSheet("color: #ccc; font-size: 9pt;")
            self._update_text(pct)
            lay.addWidget(self.val_lbl)
        else:
            self.val_lbl = None

    def _update_text(self, pct):
        if not getattr(self, "val_lbl", None):
            return
            
        d_steps = self.cfg.get("discrete_steps", 0)
        if d_steps > 1:
            idx = int(round((pct / 100.0) * (d_steps - 1)))
            self.val_lbl.setText(f"{idx + 1}")
            return

        unit = self.cfg.get("unit", "%")
        decimals = self.cfg.get("decimals", 1)
        
        if unit == "steps":
            # Map 0..100% to -24..+24
            steps = round((pct / 100.0) * 48.0 - 24.0)
            self.val_lbl.setText(f"{steps:+d}")
            return

        # --- ADVANCED SCALING & DISPLAY ---
        min_d = self.cfg.get("min_disp", 0.0)
        max_d = self.cfg.get("max_disp", 100.0)
        
        # Основная формула масштабирования
        disp = min_d + (pct / 100.0) * (max_d - min_d)
        
        # Псевдодискретность (округление только для текста)
        d_step = self.cfg.get("display_step")
        if d_step is not None and d_step > 0:
            disp = round(disp / d_step) * d_step
            
        # Форматирование суффикса и пробелов
        suffix = self.cfg.get("suffix", unit)
        spacer = ""
        if suffix and suffix[0].isalnum(): # Если суффикс начинается с буквы/цифры (ms, Hz, dB)
            spacer = " "
            
        self.val_lbl.setText(f"{disp:.{decimals}f}{spacer}{suffix}")

    def _on_slide(self, v):
        self._last_user_edit = time.time()
        d_steps = self.cfg.get("discrete_steps", 0)
        if d_steps > 1:
            pct = (v / (d_steps - 1)) * 100.0
        else:
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
    
    def _on_meta_update(self, key, val, type_conv=None):
        try:
            final_val = type_conv(val) if type_conv else val
            self.cfg[key] = final_val
            # Сразу обновляем текст лейбла для предпросмотра
            self._update_text(self._target_pct)
        except: pass
    def _on_mode_changed(self, idx):
        val = self.mode_combo.currentData()
        self.cfg["discrete_steps"] = val
        # Если мы в режиме маппинга, то слайдер не обязательно перерисовывать сразу, 
        # но для наглядности можно было бы. Однако маппинг мод обычно статический.
        # Но если мы хотим чтобы слайдер СРАЗУ стал дискретным:
        if self.slider:
            if val > 1:
                self.slider.setRange(0, val - 1)
                # Сохраняем текущий pct
                pct = self._target_pct
                self.slider.blockSignals(True)
                self.slider.setValue(int(round((pct / 100.0) * (val - 1))))
                self.slider.blockSignals(False)
            else:
                self.slider.setRange(0, 1000)
                self.slider.blockSignals(True)
                self.slider.setValue(int(self._target_pct * 10))
                self.slider.blockSignals(False)
        self._update_text(self._target_pct)

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
            d_steps = self.cfg.get("discrete_steps", 0)
            if d_steps > 1:
                idx = int(round((pct / 100.0) * (d_steps - 1)))
                self.slider.setValue(idx)
            else:
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
