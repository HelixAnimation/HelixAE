# -*- coding: utf-8 -*-
"""
Entity Dialog for Import Media
Reused from Import Media functionality
"""

from qtpy.QtCore import *
from qtpy.QtGui import *
from qtpy.QtWidgets import *

from PrismUtils.Decorators import err_catcher as err_catcher


class EntityDlg(QDialog):
    """Dialog for selecting shots via MediaBrowser - like Import Media"""

    entitiesSelected = Signal(object)

    def __init__(self, parent):
        super(EntityDlg, self).__init__()
        self.parentDlg = parent
        self.plugin = self.parentDlg.plugin
        self.core = self.plugin.core
        self.setupUi()

    @err_catcher(name=__name__)
    def setupUi(self):
        title = "Choose Shots"

        self.setWindowTitle(title)
        self.core.parentWindow(self, parent=self.parentDlg)

        import MediaBrowser
        self.w_browser = MediaBrowser.MediaBrowser(core=self.core, refresh=False)
        self.w_browser.w_entities.getPage("Assets").tw_tree.itemDoubleClicked.connect(self.itemDoubleClicked)
        self.w_browser.w_entities.getPage("Shots").tw_tree.itemDoubleClicked.connect(self.itemDoubleClicked)
        self.setExpanded(False)

        self.lo_main = QVBoxLayout()
        self.setLayout(self.lo_main)

        self.bb_main = QDialogButtonBox()
        self.bb_main.addButton("Select", QDialogButtonBox.AcceptRole)
        self.bb_main.addButton("Cancel", QDialogButtonBox.RejectRole)
        self.b_expand = self.bb_main.addButton("▶", QDialogButtonBox.RejectRole)
        self.b_expand.setToolTip("Expand")

        self.bb_main.clicked.connect(self.buttonClicked)

        self.lo_main.addWidget(self.w_browser)
        self.lo_main.addWidget(self.bb_main)

    @err_catcher(name=__name__)
    def itemDoubleClicked(self, item, column):
        self.buttonClicked("select")

    @err_catcher(name=__name__)
    def buttonClicked(self, button):
        if button == "select" or button.text() == "Select":
            entities = self.w_browser.w_entities.getCurrentData(returnOne=False)
            if isinstance(entities, dict):
                entities = [entities]

            validEntities = []
            for entity in entities:
                if entity.get("type", "") not in ["asset", "shot"]:
                    continue

                validEntities.append(entity)

            if not validEntities:
                msg = "Invalid entity selected."
                self.core.popup(msg, parent=self)
                return

            self.entitiesSelected.emit(validEntities)
        elif button.text() == "▶":
            self.setExpanded(True)
            button.setVisible(False)
            return

        self.close()

    @err_catcher(name=__name__)
    def setExpanded(self, expand):
        self.w_browser.w_identifier.setVisible(expand)
        self.w_browser.w_version.setVisible(expand)
        self.w_browser.w_preview.setVisible(expand)

        if expand:
            newwidth = 1200
            curwidth = self.geometry().width()
            self.resize(newwidth, self.geometry().height())
            self.move(self.pos().x()-((newwidth-curwidth)/2), self.pos().y())

    @err_catcher(name=__name__)
    def sizeHint(self):
        return QSize(500, 500)
