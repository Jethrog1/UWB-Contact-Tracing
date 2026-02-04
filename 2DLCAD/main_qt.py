import sys
from PyQt6.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout, 
                             QHBoxLayout, QLabel, QPushButton, QListWidget, 
                             QFrame, QSizePolicy, QSpacerItem)
from PyQt6.QtCore import Qt, QSize
from PyQt6.QtGui import QFont, QIcon, QColor, QPalette

class ModernButton(QPushButton):
    def __init__(self, title, subtitle, icon_name=None, parent=None):
        super().__init__(parent)
        self.setFixedSize(200, 120)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        
        layout = QVBoxLayout(self)
        
        # Title
        title_lbl = QLabel(title)
        title_lbl.setStyleSheet("font-weight: bold; font-size: 16px; color: #E0E0E0;")
        layout.addWidget(title_lbl)
        
        # Subtitle
        sub_lbl = QLabel(subtitle)
        sub_lbl.setStyleSheet("color: #AAAAAA; font-size: 12px;")
        sub_lbl.setWordWrap(True)
        layout.addWidget(sub_lbl)
        
        layout.addStretch()
        
        self.setStyleSheet("""
            ModernButton {
                background-color: #3C3C3C;
                border: 1px solid #555555;
                border-radius: 8px;
                text-align: left;
                padding: 10px;
            }
            ModernButton:hover {
                background-color: #4A4A4A;
                border: 1px solid #007ACC;
            }
            ModernButton:pressed {
                background-color: #333333;
            }
        """)

class HomeScreen(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.layout = QHBoxLayout(self)
        self.layout.setContentsMargins(0, 0, 0, 0)
        
        # Left Panel (Welcome & Actions)
        left_panel = QFrame()
        left_panel.setStyleSheet("background-color: #2D2D30; border-right: 1px solid #3E3E42;")
        left_layout = QVBoxLayout(left_panel)
        left_layout.setContentsMargins(40, 40, 40, 40)
        
        # Logo / Header
        header = QLabel("SOLID-CAD")
        header.setStyleSheet("color: #FFFFFF; font-size: 32px; font-weight: bold;")
        left_layout.addWidget(header)
        
        welcome = QLabel("Welcome back, User")
        welcome.setStyleSheet("color: #CCCCCC; font-size: 18px; margin-bottom: 30px;")
        left_layout.addWidget(welcome)
        
        # Action Buttons
        btn_new = ModernButton("New Part", "Create a new 2D/3D design component.")
        left_layout.addWidget(btn_new)
        
        btn_assem = ModernButton("New Assembly", "Combine parts into an assembly.")
        left_layout.addWidget(btn_assem)
        
        btn_open = ModernButton("Open", "Browse for existing files.")
        left_layout.addWidget(btn_open)
        
        left_layout.addStretch()
        
        # Bottom info
        info = QLabel("v2.0.0 (PyQt6 Prototype)")
        info.setStyleSheet("color: #666666;")
        left_layout.addWidget(info)
        
        self.layout.addWidget(left_panel, 1) # Stretch factor 1
        
        # Right Panel (Recent Documents)
        right_panel = QFrame()
        right_panel.setStyleSheet("background-color: #1E1E1E;")
        right_layout = QVBoxLayout(right_panel)
        right_layout.setContentsMargins(40, 40, 40, 40)
        
        recent_header = QLabel("Recent Documents")
        recent_header.setStyleSheet("color: #FFFFFF; font-size: 18px; font-weight: bold; margin-bottom: 10px;")
        right_layout.addWidget(recent_header)
        
        self.recent_list = QListWidget()
        self.recent_list.setStyleSheet("""
            QListWidget {
                background-color: #252526;
                border: none;
                color: #D4D4D4;
                font-size: 14px;
            }
            QListWidget::item {
                padding: 10px;
                border-bottom: 1px solid #333333;
            }
            QListWidget::item:hover {
                background-color: #3E3E42;
            }
        """)
        
        # Mock Data
        self.recent_list.addItem("floor_plan_v1.dxf")
        self.recent_list.addItem("bracket_arm_rev3.scad")
        self.recent_list.addItem("connector_plate.dwg")
        
        right_layout.addWidget(self.recent_list)
        
        self.layout.addWidget(right_panel, 2) # Stretch factor 2

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Solid-CAD Prototype")
        self.resize(1000, 700)
        
        # Set Dark Theme
        self.setStyleSheet("background-color: #1E1E1E;")
        
        self.home_screen = HomeScreen()
        self.setCentralWidget(self.home_screen)

if __name__ == '__main__':
    app = QApplication(sys.argv)
    
    # Global Font
    font = QFont("Segoe UI", 10)
    app.setFont(font)
    
    window = MainWindow()
    window.show()
    
    sys.exit(app.exec())
