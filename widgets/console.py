
from PyQt6.QtWidgets import QDialog, QVBoxLayout, QPlainTextEdit, QPushButton, QHBoxLayout, QLabel
from PyQt6.QtCore import Qt, pyqtSignal, QSize
from PyQt6.QtGui import QFont, QColor, QTextCharFormat, QTextCursor

class LogConsole(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("HD300 Unchained | Debug Console")
        self.setMinimumSize(700, 450)
        self.setWindowFlags(self.windowFlags() | Qt.WindowType.WindowMaximizeButtonHint)
        
        # UI
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        
        # Header
        header = QHBoxLayout()
        header.setContentsMargins(10, 5, 10, 5)
        self.lbl_title = QLabel("SYSTEM LOGS")
        self.lbl_title.setStyleSheet("font-weight: bold; color: #d6923c; font-size: 9pt;")
        header.addWidget(self.lbl_title)
        header.addStretch()
        
        self.btn_copy = QPushButton("Copy")
        self.btn_copy.setFixedWidth(60)
        self.btn_copy.setStyleSheet("background: #333; border: 1px solid #444; font-size: 8pt; padding: 2px; margin-right: 5px;")
        self.btn_copy.clicked.connect(self.copy_to_clipboard)
        header.addWidget(self.btn_copy)

        self.btn_clear = QPushButton("Clear")
        self.btn_clear.setFixedWidth(60)
        self.btn_clear.setStyleSheet("background: #333; border: 1px solid #444; font-size: 8pt; padding: 2px;")
        self.btn_clear.clicked.connect(self.clear_logs)
        header.addWidget(self.btn_clear)
        
        layout.addLayout(header)
        
        # Text area
        self.editor = QPlainTextEdit()
        self.editor.setReadOnly(True)
        # Terminal-like style
        self.editor.setStyleSheet("""
            QPlainTextEdit {
                background-color: #0c0c0c;
                color: #cccccc;
                border: none;
                font-family: 'Consolas', 'Courier New', monospace;
                font-size: 10pt;
                selection-background-color: #d6923c;
                selection-color: #000;
            }
        """)
        layout.addWidget(self.editor)
        
        # Apply dark theme to dialog itself
        self.setStyleSheet("""
            QDialog {
                background-color: #1a1c1f;
            }
            QLabel { color: #888; }
        """)

    def append_log(self, msg):
        # Determine color/style based on message content
        color = "#cccccc"
        if "[MIDI-TX]" in msg or "🛰" in msg:
            color = "#d6923c" # Amber for hardware talk
        elif "[MIDI-RX]" in msg:
            color = "#00bcd4" # Cyan for response
        elif "✅" in msg or "SUCCESS" in msg.upper():
            color = "#4caf50" # Green for success
        elif "❌" in msg or "ERROR" in msg.upper() or "⚠️" in msg:
            color = "#e74c3c" # Red for problems
        elif "[UI]" in msg:
            color = "#2196f3" # Blue for UI events
            
        cursor = self.editor.textCursor()
        cursor.movePosition(QTextCursor.MoveOperation.End)
        
        fmt = QTextCharFormat()
        fmt.setForeground(QColor(color))
        cursor.setCharFormat(fmt)
        
        cursor.insertText(msg + "\n")
        
        # Auto-scroll
        self.editor.setTextCursor(cursor)
        self.editor.ensureCursorVisible()

    def clear_logs(self):
        self.editor.clear()

    def copy_to_clipboard(self):
        from PyQt6.QtWidgets import QApplication
        QApplication.clipboard().setText(self.editor.toPlainText())
        self.lbl_title.setText("COPIED!")
        from PyQt6.QtCore import QTimer
        QTimer.singleShot(1000, lambda: self.lbl_title.setText("SYSTEM LOGS"))

class ClickableStatusLabel(QLabel):
    doubleClicked = pyqtSignal()
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setToolTip("Double click to open debug console")

    def mouseDoubleClickEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.doubleClicked.emit()
        super().mouseDoubleClickEvent(event)
