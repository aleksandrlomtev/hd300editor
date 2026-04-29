"""
SettingsDialog — editor settings dialog.
"""

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QDialog, QVBoxLayout, QHBoxLayout, QCheckBox, QSpinBox, QLabel


class SettingsDialog(QDialog):
    """Editor settings dialog. Changes are applied instantly via callbacks."""
    
    def __init__(self, parent=None, **kwargs):
        super().__init__(parent)
        self.setWindowTitle("Editor Settings")
        self.setFixedSize(340, 220)
        self.setStyleSheet("background: #1e2126; color: #eee; font-size: 10pt;")
        
        lay = QVBoxLayout(self)
        
        self.cb_sync = QCheckBox("Sync presets on startup")
        self.cb_sync.setChecked(kwargs.get("sync_on_launch", True))
        
        self.cb_black = QCheckBox("Black Mode (AMOLED background)")
        self.cb_black.setChecked(kwargs.get("black_mode", False))
        
        self.cb_buf = QCheckBox("Load Edit Buffer on startup")
        self.cb_buf.setChecked(kwargs.get("load_edit_buffer", True))
        self.cb_buf.setToolTip(
            "If active: loads current state from processor knobs on connect "
            "(even if preset was not saved).\nOtherwise, downloads saved version from memory."
        )

        self.cb_free = QCheckBox("Experimental Free Routing (Drag-n-Drop)")
        self.cb_free.setChecked(kwargs.get("experimental_free_routing", False))
        self.cb_free.setToolTip(
            "WARNING: Allows arbitrary swapping of FX1-3 and REV blocks.\n"
            "May cause clicks/pauses in sound during movement."
        )
        self.cb_free.setStyleSheet("color: #e67e22; font-weight: bold;")
        
        # DI Preset Selection
        di_lay = QHBoxLayout()
        di_lay.addWidget(QLabel("DI Mode Preset:"))
        
        self.sb_di = QSpinBox()
        self.sb_di.setRange(1, 128)
        self.sb_di.setValue(kwargs.get("di_preset", 124) + 1)
        self.sb_di.setButtonSymbols(QSpinBox.ButtonSymbols.NoButtons)
        self.sb_di.setFixedWidth(50)
        self.sb_di.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.sb_di.setStyleSheet("background: #2c313a; border: 1px solid #444; padding: 2px; font-weight: bold;")
        
        self.lbl_di_info = QLabel()
        self.lbl_di_info.setStyleSheet("color: #d6923c; font-weight: bold;")
        
        di_lay.addWidget(self.sb_di)
        di_lay.addWidget(self.lbl_di_info)
        di_lay.addStretch()
        
        self.sb_di.valueChanged.connect(self._update_di_info)
        self._update_di_info(self.sb_di.value())
        
        self.cb_mapping = QCheckBox("Unlock Mapping Mode (🔧 icon in top bar)")
        self.cb_mapping.setChecked(kwargs.get("unlock_mapping", False))
        self.cb_mapping.setToolTip("Enables the button to enter Mapping Mode for editing parameter ranges and IDs.")

        lay.addWidget(self.cb_sync)
        lay.addWidget(self.cb_black)
        lay.addWidget(self.cb_buf)
        lay.addWidget(self.cb_free)
        lay.addWidget(self.cb_mapping)
        lay.addSpacing(10)
        lay.addLayout(di_lay)

    def _update_di_info(self, val_1_128):
        val = val_1_128 - 1
        bank = (val // 4) + 1
        sub = ["A", "B", "C", "D"][val % 4]
        self.lbl_di_info.setText(f"({bank:02d}{sub})")
