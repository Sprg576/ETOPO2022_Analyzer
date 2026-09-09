"""ETOPO2022 Analyzer ArcGIS Pro 风格浅色主题。"""


LIGHT_THEME = """
QMainWindow {
    background: #EDF2F7;
}

QWidget {
    color: #26313D;
    font-family: "Microsoft YaHei UI";
    font-size: 9pt;
}

QMenuBar {
    background: #FFFFFF;
    border-bottom: 1px solid #CED7E2;
    padding: 2px 8px;
}

QMenuBar::item {
    background: transparent;
    padding: 6px 10px;
}

QMenuBar::item:selected,
QMenu::item:selected {
    background: #E5F0FB;
    color: #174A7E;
}

QMenu {
    background: #FFFFFF;
    border: 1px solid #BFCAD7;
    padding: 4px;
}

QMenu::item {
    padding: 6px 28px 6px 24px;
}

QMenu::separator {
    background: #D8E0E9;
    height: 1px;
    margin: 4px 8px;
}

QToolBar {
    background: #FFFFFF;
    border: none;
    border-bottom: 1px solid #BFCAD7;
    padding: 7px 9px;
    spacing: 3px;
}

QToolBar::separator {
    background: #D5DDE6;
    width: 1px;
    margin: 3px 7px;
}

QToolBar QToolButton {
    background: transparent;
    border: 1px solid transparent;
    border-radius: 2px;
    min-height: 31px;
    padding: 4px 8px;
}

QToolBar QToolButton:hover {
    background: #EAF2FB;
    border-color: #BDD3EA;
}

QToolBar QToolButton:pressed,
QToolBar QToolButton:checked {
    background: #DCEAF8;
    border-color: #8FB7DE;
    color: #174A7E;
}

QToolButton:disabled {
    color: #9AA5B1;
}

QTabWidget#MapTabs::pane {
    background: #FFFFFF;
    border: 1px solid #BFCAD7;
    top: -1px;
}

QTabWidget#MapTabs QTabBar::tab {
    background: #E8EFF6;
    border: 1px solid #BFCAD7;
    border-bottom: none;
    min-width: 92px;
    padding: 7px 12px;
}

QTabWidget#MapTabs QTabBar::tab:selected {
    background: #FFFFFF;
    color: #174A7E;
}

QTabWidget#MapTabs QTabBar::tab:hover:!selected {
    background: #F4F8FC;
}

QDockWidget {
    background: #FFFFFF;
    color: #174A7E;
    font-size: 9.5pt;
}

QDockWidget::title {
    background: #E3EDF7;
    border: 1px solid #B8C8D8;
    padding: 7px 9px;
    text-align: left;
}

QTreeWidget {
    background: #FFFFFF;
    border: none;
    outline: none;
    padding: 4px;
}

QTreeWidget::item {
    min-height: 24px;
    padding: 1px 3px;
}

QTreeWidget::item:hover {
    background: #EFF5FB;
}

QTreeWidget::item:selected {
    background: #D9E9F8;
    color: #1D3550;
}

QLabel#PanelTitle {
    background: #E3EDF7;
    border-top: 1px solid #B8C8D8;
    border-bottom: 1px solid #B8C8D8;
    color: #174A7E;
    padding: 7px 9px;
}

QLabel#PanelHint,
QLabel#LayerPanelHint {
    color: #687585;
    font-size: 8.5pt;
}

QTableWidget#LayerPropertiesTable {
    background: #FFFFFF;
    alternate-background-color: #F7F9FB;
    border: none;
    gridline-color: #DCE3EA;
}

QTableWidget#LayerPropertiesTable::item {
    padding: 4px 6px;
}

QSplitter#LayerSplitter::handle {
    background: #CBD5DF;
    height: 3px;
}

QScrollArea#AnalysisScrollArea,
QWidget#AnalysisPanel {
    background: #FFFFFF;
    border: none;
}

QToolButton#SectionHeader {
    background: #E8F1FA;
    border: none;
    border-top: 1px solid #C1CFDD;
    border-bottom: 1px solid #C1CFDD;
    border-radius: 0;
    color: #174A7E;
    min-height: 28px;
    padding: 2px 8px;
    text-align: left;
}

QToolButton#SectionHeader:hover {
    background: #DCEAF8;
}

QWidget#SectionBody {
    background: #FFFFFF;
}

QLabel#SourceValue {
    color: #174A7E;
}

QToolButton#PanelActionButton {
    background: #FFFFFF;
    border: 1px solid #BFCAD7;
    border-radius: 3px;
    min-height: 29px;
    padding: 3px 8px;
    text-align: left;
}

QToolButton#PanelActionButton:hover {
    background: #EAF2FB;
    border-color: #8FB7DE;
}

QToolButton#PanelActionButton[primary="true"] {
    background: #2F6FED;
    border-color: #255DCB;
    color: #FFFFFF;
}

QToolButton#PanelActionButton[primary="true"]:hover {
    background: #285FCE;
}

QToolButton#PanelActionButton:disabled {
    background: #F3F5F7;
    border-color: #D6DCE3;
    color: #9AA5B1;
}

QDoubleSpinBox {
    background: #FFFFFF;
    border: 1px solid #BFCAD7;
    border-radius: 2px;
    min-height: 25px;
    padding: 1px 5px;
    selection-background-color: #2F6FED;
}

QDoubleSpinBox:focus {
    border-color: #2F6FED;
}

QStatusBar {
    background: #FFFFFF;
    border-top: 1px solid #BFCAD7;
    color: #26313D;
    min-height: 40px;
}

QStatusBar QLabel {
    border-left: 1px solid #E0E5EB;
    color: #4F5D6C;
    padding: 4px 7px;
}
"""
