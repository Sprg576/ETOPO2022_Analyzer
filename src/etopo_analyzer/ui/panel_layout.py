"""侧栏缩放时表单换行，说明文字按实际宽度计算高度。"""

from qgis.PyQt.QtWidgets import QFormLayout, QLabel, QComboBox, QSizePolicy


def make_panel_responsive(panel):
    for form in panel.findChildren(QFormLayout):
        form.setRowWrapPolicy(QFormLayout.WrapLongRows)
        form.setFieldGrowthPolicy(QFormLayout.AllNonFixedFieldsGrow)
    for label in panel.findChildren(QLabel):
        if label.wordWrap():
            policy = label.sizePolicy()
            policy.setHeightForWidth(True)
            label.setSizePolicy(policy)
    for combo in panel.findChildren(QComboBox):
        combo.setSizeAdjustPolicy(QComboBox.AdjustToMinimumContentsLengthWithIcon)
        combo.setMinimumContentsLength(6)
        combo.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
