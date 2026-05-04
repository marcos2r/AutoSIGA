import sys
import os

# Garante que os imports modulares (models, controllers, bot) funcionem corretamente
sys.path.insert(0, os.path.abspath(os.path.dirname(__file__)))

from ui.main_window import MainWindow

if __name__ == "__main__":
    app = MainWindow()
    app.mainloop()
