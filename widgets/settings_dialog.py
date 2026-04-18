"""
SettingsDialog — диалог настроек редактора.
"""

from PyQt6.QtWidgets import QDialog, QVBoxLayout, QCheckBox


class SettingsDialog(QDialog):
    """Диалог настроек Editor'a. Все изменения применяются мгновенно через колбэки."""
    
    def __init__(self, parent=None, **kwargs):
        super().__init__(parent)
        self.setWindowTitle("Настройки Editor'a")
        self.setFixedSize(320, 200)
        self.setStyleSheet("background: #1e2126; color: #eee; font-size: 10pt;")
        
        lay = QVBoxLayout(self)
        
        self.cb_anim = QCheckBox("Анимации интерфейса")
        self.cb_anim.setChecked(kwargs.get("animations_enabled", True))
        
        self.cb_sync = QCheckBox("Синхронизировать пресеты при старте")
        self.cb_sync.setChecked(kwargs.get("sync_on_launch", True))
        
        self.cb_helix = QCheckBox("AMOLED-режим (Черный фон)")
        self.cb_helix.setChecked(kwargs.get("helix_mode", False))
        
        self.cb_buf = QCheckBox("Грузить Edit Buffer при старте")
        self.cb_buf.setChecked(kwargs.get("load_edit_buffer", True))
        self.cb_buf.setToolTip(
            "Если активно: при коннекте прогружается текущее состояние с ручек процессора "
            "(даже если пресет не был сохранен).\nИначе - скачивается сохраненная версия пресета из памяти."
        )

        self.cb_free = QCheckBox("Экспериментальный Free Routing (Drag-n-Drop)")
        self.cb_free.setChecked(kwargs.get("experimental_free_routing", False))
        self.cb_free.setToolTip(
            "ВНИМАНИЕ: Позволяет произвольно менять местами блоки FX1-3 и REV.\n"
            "Может вызывать щелчки/паузы в звуке при перемещении."
        )
        self.cb_free.setStyleSheet("color: #e67e22; font-weight: bold;")
        
        lay.addWidget(self.cb_anim)
        lay.addWidget(self.cb_sync)
        lay.addWidget(self.cb_helix)
        lay.addWidget(self.cb_buf)
        lay.addWidget(self.cb_free)
