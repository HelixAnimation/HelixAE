# -*- coding: utf-8 -*-
"""
Helix AE UI Components
Contains Render Dialog and Import Media Dialog
"""

import copy
from qtpy.QtCore import *
from qtpy.QtGui import *
from qtpy.QtWidgets import *

from PrismUtils.Decorators import err_catcher as err_catcher


class RenderDlg(QDialog):
    """Dialog for rendering compositions in After Effects"""

    def __init__(self, plugin):
        super(RenderDlg, self).__init__()
        self.plugin = plugin
        self.core = plugin.core
        self.main = plugin

        self.setWindowTitle("Helix AE - Render")
        self.resize(450, 200)

        layout = QVBoxLayout()
        self.setLayout(layout)

        # Instructions
        info_label = QLabel("Select a render template and click Add to Render Queue")
        layout.addWidget(info_label)

        # Template combo
        template_layout = QHBoxLayout()
        template_label = QLabel("Template:")
        template_layout.addWidget(template_label)

        self.template_combo = QComboBox()
        template_layout.addWidget(self.template_combo)
        layout.addLayout(template_layout)

        # Buttons (must be created BEFORE loadTemplates)
        button_layout = QHBoxLayout()
        button_layout.addStretch()

        self.render_save_btn = QPushButton("Add to Render Queue")
        self.render_save_btn.clicked.connect(self.renderAndSave)
        self.render_save_btn.setEnabled(False)  # Disabled until templates load
        button_layout.addWidget(self.render_save_btn)

        close_btn = QPushButton("Close")
        close_btn.clicked.connect(self.close)
        button_layout.addWidget(close_btn)

        layout.addLayout(button_layout)

        # Load templates AFTER buttons are created
        self.loadTemplates()

    @err_catcher(name=__name__)
    def loadTemplates(self):
        """Load render templates from After Effects"""
        self.template_combo.clear()
        self.template_combo.addItem("Loading...")

        templates = self.main.getRenderTemplates()

        self.template_combo.clear()
        if templates:
            for template in templates:
                self.template_combo.addItem(template)
            self.render_save_btn.setEnabled(True)
        else:
            self.template_combo.addItem("No templates available")
            self.render_save_btn.setEnabled(False)

    @err_catcher(name=__name__)
    def render(self):
        """Render current composition with selected template"""
        template = self.template_combo.currentText()
        if not template or template == "No templates available":
            self.core.popup("Please select a valid render template.")
            return

        # Render command for After Effects
        cmd = f'''
if (app.project && app.project.activeItem && app.project.activeItem instanceof CompItem) {{
    var comp = app.project.activeItem;
    var renderQueueItem = app.project.renderQueue.items.add(comp);

    // Find the requested template
    var outputModule = renderQueueItem.outputModule(1);
    var templates = outputModule.templates;
    var templateFound = false;

    for (var i = 0; i < templates.length; i++) {{
        if (templates[i] == "{template}") {{
            outputModule.template = templates[i];
            templateFound = true;
            break;
        }}
    }}

    if (templateFound) {{
        // Start rendering
        app.project.renderQueue.render();
        "{{\\"result\\": True, \\"template\\": \\"{template}\\"}}";
    }} else {{
        renderQueueItem.remove();
        "{{\\"result\\": False, \\"details\\": \\"Template not found: {template}\\"}}";
    }}
}} else {{
    "{{\\"result\\": False, \\"details\\": \\"No active composition found.\\"}}";
}}
'''

        result = self.main.sendCmd(cmd)
        if not result:
            self.core.popup("Failed to send render command to After Effects.")
            return

        try:
            result_str = result.decode("utf-8").strip()
            if result_str == "null":
                self.core.popup("After Effects returned no response.")
                return

            result_data = eval(result_str)
            if result_data.get("result") is True:
                self.core.popup(
                    f"Rendering started with template: {template}"
                    "\n\nCheck After Effects Render Queue for progress."
                )
                self.close()
            else:
                details = result_data.get("details", "Unknown error")
                self.core.popup(f"Render failed:\n{details}")
        except Exception as e:
            self.core.popup(f"Error parsing render result:\n{str(e)}")

    @err_catcher(name=__name__)
    def renderAndSave(self):
        """Save the project and then render current composition with selected template"""
        template = self.template_combo.currentText()
        if not template or template == "No templates available":
            self.core.popup("Please select a valid render template.")
            return

        # First, save the current project
        try:
            current_file = self.core.getCurrentFileName()
            if current_file:
                # Save using ae_core.saveScene which includes archive info generation
                result = self.main.ae_core.saveScene(origin="renderAndSave", filepath=current_file)
                if not result:
                    self.core.popup("Save failed. Render cancelled.")
                    return
            else:
                self.core.popup("Please save the project first using Project Browser.")
                return
        except Exception as e:
            self.core.popup(f"Save failed: {str(e)}\n\nRender cancelled.")
            return

        # After successful save, proceed with render
        self.render()


class ImportMediaDlg(QDialog):
    def __init__(self, plugin):
        super(ImportMediaDlg, self).__init__()
        self.plugin = plugin
        self.core = self.plugin.core
        self.identifiers = []
        self.shots = None
        self.setupUi()

    @err_catcher(name=__name__)
    def setupUi(self):
        self.setWindowTitle("Import Media")
        self.core.parentWindow(self)
        self.lo_main = QVBoxLayout()
        self.setLayout(self.lo_main)

        self.lo_widgets = QGridLayout()

        self.lo_entity = QHBoxLayout()
        self.l_entity = QLabel("Shots:")
        self.l_entityName = QLabel("")
        self.l_entityName.setWordWrap(True)
        self.b_entity = QPushButton("Choose...")
        self.b_entity.setStyleSheet("color: rgb(240, 50, 50); border-color: rgb(240, 50, 50);")
        self.b_entity.clicked.connect(self.chooseEntity)
        self.b_entity.setFocusPolicy(Qt.NoFocus)
        self.lo_widgets.addWidget(self.l_entity, 0, 0)
        self.lo_widgets.setColumnStretch(1, 1)
        self.lo_widgets.addWidget(self.l_entityName, 0, 1)
        self.lo_widgets.addWidget(self.b_entity, 0, 2, 1, 2)

        self.l_identifier = QLabel("Identifier:    ")
        self.e_identifier = QLineEdit("")
        self.b_identifier = QToolButton()
        self.b_identifier.setFocusPolicy(Qt.NoFocus)
        self.b_identifier.setArrowType(Qt.DownArrow)
        self.b_identifier.clicked.connect(self.showIdentifiers)
        self.b_identifier.setVisible(False)
        self.lo_widgets.addWidget(self.l_identifier, 1, 0)
        self.lo_widgets.addWidget(self.e_identifier, 1, 1, 1, 3)
        self.lo_widgets.addWidget(self.b_identifier, 1, 3)

        self.l_addToComp = QLabel("Add to Current Composition:")
        self.chb_addToComp = QCheckBox()
        self.chb_addToComp.setChecked(True)
        self.lo_widgets.addWidget(self.l_addToComp, 2, 0)
        self.lo_widgets.addWidget(self.chb_addToComp, 2, 1, 1, 3)

        self.lo_main.addLayout(self.lo_widgets)

        self.bb_main = QDialogButtonBox()
        self.bb_main.addButton("Preview", QDialogButtonBox.AcceptRole)
        self.bb_main.addButton("Import", QDialogButtonBox.AcceptRole)
        self.bb_main.addButton("Cancel", QDialogButtonBox.RejectRole)

        self.bb_main.clicked.connect(self.buttonClicked)

        self.lo_main.addStretch()
        self.lo_main.addWidget(self.bb_main)

    @err_catcher(name=__name__)
    def sizeHint(self):
        return QSize(400, 150)

    @err_catcher(name=__name__)
    def getIdentifiers(self):
        return [x.strip() for x in self.e_identifier.text().split(",")]

    @err_catcher(name=__name__)
    def setShots(self, shots):
        if not isinstance(shots, list):
            shots = [shots]

        self.shots = shots
        self.b_entity.setStyleSheet("")

        shotNames = []
        self.identifiers = []
        identifiers = []
        for shot in self.shots:
            shotName = self.core.entities.getShotName(shot)
            if not shotName:
                continue

            shotNames.append(shotName)
            taskTypes = ["3d", "2d", "playblast", "external"]
            for taskType in taskTypes:
                ids = self.core.getTaskNames(taskType=taskType, context=copy.deepcopy(shot), addDepartments=False)
                if taskType == "playblast":
                    ids = [i + " (playblast)" for i in ids if i]
                elif taskType == "2d":
                    ids = [i + " (2d)" for i in ids if i]
                elif taskType == "external":
                    ids = [i + " (external)" for i in ids if i]

                identifiers += ids

        self.identifiers = sorted(list(set(identifiers)))
        shotStr = ", ".join(shotNames)
        self.l_entityName.setText(shotStr)

        self.b_identifier.setVisible(bool(self.identifiers))
        if self.identifiers:
            self.lo_widgets.addWidget(self.e_identifier, 1, 1, 1, 2)
        else:
            self.lo_widgets.addWidget(self.e_identifier, 1, 1, 1, 3)

    @err_catcher(name=__name__)
    def chooseEntity(self):
        dlg = EntityDlg(self)
        dlg.w_browser.w_entities.getPage("Shots").tw_tree.setSelectionMode(QAbstractItemView.ExtendedSelection)
        dlg.w_browser.w_entities.tb_entities.removeTab(0)
        dlg.w_browser.w_entities.navigate({"type": "shot"})
        dlg.w_browser.entered(navData={"type": "shot"})
        dlg.entitiesSelected.connect(self.setShots)
        if self.shots:
            dlg.w_browser.w_entities.navigate(self.shots)

        dlg.exec_()

    @err_catcher(name=__name__)
    def showIdentifiers(self):
        pos = QCursor.pos()
        tmenu = QMenu(self)

        for identifier in self.identifiers:
            tAct = QAction(identifier, self)
            tAct.triggered.connect(lambda x=None, t=identifier: self.addIdentifier(t))
            tmenu.addAction(tAct)

        tmenu.exec_(pos)

    @err_catcher(name=__name__)
    def addIdentifier(self, identifier):
        idfs = [idf.strip() for idf in self.e_identifier.text().split(",") if idf]
        if identifier in idfs:
            newIdfs = [idf for idf in idfs if idf != identifier]
        else:
            newIdfs = idfs + [identifier]

        self.e_identifier.setText(", ".join(newIdfs))

    @err_catcher(name=__name__)
    def validate(self):
        if not self.shots:
            msg = "No shots are selected."
            self.core.popup(msg, parent=self)
            return False

        if not self.getIdentifiers():
            msg = "No identifier is specified."
            self.core.popup(msg, parent=self)
            return False

        return True

    @err_catcher(name=__name__)
    def buttonClicked(self, button):
        if button.text() == "Import":
            if not self.validate():
                return

            identifiers = self.getIdentifiers()
            result = self.plugin.importMediaVersions(
                entities=self.shots, identifiers=identifiers,
                addToComp=self.chb_addToComp.isChecked()
            )
            if not result and not isinstance(result, list) and result is not False:
                msg = "Importing media failed."
                self.core.popup(msg, parent=self)

            self.close()
        elif button.text() == "Preview":
            if not self.validate():
                return

            versions = []
            identifiers = self.getIdentifiers()
            for identifier in identifiers:
                versions += self.plugin.getMediaFromEntities(entities=self.shots, identifier=identifier)

            if self.chb_addToComp.isChecked():
                msg = "The following media will be added to the current composition:\n\n"
            else:
                msg = "The following media will be added as sources to the current project:\n\n"

            for version in versions:
                shotName = self.core.entities.getShotName(version)
                pattern = self.core.media.getSequenceFromFilename(version["filepaths"][0])
                line = "Shot: %s\nPath: %s\n" % (shotName, pattern)
                msg += line

            self.core.popup(msg, parent=self, severity="info")
        else:
            self.close()


class EntityDlg(QDialog):

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