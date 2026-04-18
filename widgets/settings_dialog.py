"""
SettingsDialog — editor settings dialog.
"""

from PyQt6.QtWidgets import QDialog, QVBoxLayout, QCheckBox


class SettingsDialog(QDialog):
    """Editor settings dialog. Changes are applied instantly via callbacks."""
    
    def __init__(self, parent=None, **kwargs):
        super().__init__(parent)
        self.setWindowTitle("Editor Settings")
        self.setFixedSize(320, 170)
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
        
        lay.addWidget(self.cb_sync)
        lay.addWidget(self.cb_black)
        lay.addWidget(self.cb_buf)
        lay.addWidget(self.cb_free)
