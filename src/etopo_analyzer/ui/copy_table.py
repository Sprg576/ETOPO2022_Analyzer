"""以 TSV 复制选中单元格，可直接粘贴到电子表格。"""

from qgis.PyQt.QtGui import QKeySequence
from qgis.PyQt.QtWidgets import QTableWidget, QApplication, QAction
from qgis.PyQt.QtCore import Qt


class CopyTable(QTableWidget):
    def __init__(self, *args):
        super().__init__(*args)
        action = QAction("复制选中单元格", self)
        action.triggered.connect(self.copy_selection)
        self.addAction(action)
        self.setContextMenuPolicy(Qt.ActionsContextMenu)

    def keyPressEvent(self, event):
        if event.matches(QKeySequence.Copy):
            self.copy_selection()
        else:
            super().keyPressEvent(event)

    def copy_selection(self):
        cells = {(i.row(), i.column()) for i in self.selectedIndexes()}
        if not cells:
            return
        rows, cols = zip(*cells)
        text = "\n".join("\t".join(self.item(r, c).text() if (r, c) in cells and self.item(r, c) else ""
            for c in range(min(cols), max(cols) + 1)) for r in range(min(rows), max(rows) + 1))
        QApplication.clipboard().setText(text)
