"""
POD HD300 Visual Editor v2 (Refactored)
Точка входа: python -m refactor
"""

import sys
import builtins
f = open("startup_log.txt", "w")
def mprint(s):
    f.write(str(s) + "\n")
    f.flush()

mprint("Imports starting...")
import os

def custom_excepthook(exc_type, exc_value, exc_traceback):
    import traceback
    with open("qt_crash.txt", "w") as f:
        traceback.print_exception(exc_type, exc_value, exc_traceback, file=f)
    mprint("CRASH: " + str(exc_value))
    sys.__excepthook__(exc_type, exc_value, exc_traceback)

sys.excepthook = custom_excepthook

from PyQt6.QtWidgets import QApplication
from PyQt6.QtGui import QIcon

mprint("Imported PyQt6")
from constants import SCRIPT_DIR
mprint("Imported SCRIPT_DIR")
from main_window import MainWindow
mprint("Imported MainWindow")

def main():
    mprint("Inside main()")
    if sys.platform == "win32":
        import ctypes
        myappid = u"aleks.pod_hd300.visual_editor.v2"
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(myappid)

    mprint("Creating QApplication...")
    app = QApplication(sys.argv)
    app.setApplicationName("POD HD300 Visual Editor v2")
    
    icon_path = os.path.join(SCRIPT_DIR, "icons", "amp.webp")
    if os.path.exists(icon_path):
        app.setWindowIcon(QIcon(icon_path))
    
    mprint("Creating MainWindow...")
    win = MainWindow()
    if os.path.exists(icon_path):
        win.setWindowIcon(QIcon(icon_path))
        
    mprint("Showing window...")
    win.show()
    mprint("Execing app...")
    sys.exit(app.exec())


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        import traceback
        with open("crash.txt", "w") as f:
            traceback.print_exc(file=f)
