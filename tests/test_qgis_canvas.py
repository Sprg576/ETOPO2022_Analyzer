from qgis.core import QgsApplication
from qgis.gui import QgsMapCanvas
from qgis.PyQt.QtWidgets import QMainWindow


QGIS_PREFIX_PATH = r"D:\QGIS\apps\qgis-ltr"


def main():
    # 设置 QGIS 安装前缀
    QgsApplication.setPrefixPath(QGIS_PREFIX_PATH, True)

    # True = 启用 GUI
    app = QgsApplication([], True)

    # 初始化 QGIS
    app.initQgis()

    # 创建主窗口
    window = QMainWindow()
    window.setWindowTitle("ETOPO2022 Analyzer - QgsMapCanvas Test")
    window.resize(1000, 700)

    # 创建 QGIS 地图控件
    canvas = QgsMapCanvas()

    # 放到主窗口中央
    window.setCentralWidget(canvas)

    # 显示窗口
    window.show()

    # Qt 事件循环
    exit_code = app.exec()

    # 正确释放 QGIS
    app.exitQgis()

    return exit_code


if __name__ == "__main__":
    main()