"""ITHutir Pinterest OS — responsive desktop shell and local workspace."""
from __future__ import annotations

import sys
import time
import webbrowser
from urllib.parse import quote
from pathlib import Path

from PyQt6.QtCore import Qt, QStandardPaths, QTimer, QSettings
from PyQt6.QtGui import QPixmap
from PyQt6.QtWidgets import (
    QApplication, QComboBox, QFrame, QHBoxLayout, QHeaderView, QLabel,
    QMainWindow, QMessageBox, QPushButton, QScrollArea, QFileDialog, QTabWidget, QLineEdit,
    QStackedWidget, QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget, QInputDialog, QLayout,
)

from .board_logic import CATEGORIES, board_plan, board_seo_issues
from .calendar import CalendarPage
from .analytics import AnalyticsPage
from .reports_page import ReportsPage
from .time_page import TimePage
from .settings_page import SettingsPage
from .help_page import HelpPage
from .publishing import PublishingPage
from .editor import RecordEditor
from .designer import PinDesigner
from .content_factory_page import ContentFactoryPage
from .carousel import CarouselPage
from .csv_io import import_pins, export_pins
from . import sheets_api, sheets_exchange
from .google_sheets_link import parse_sheet_url
from .storage import Storage
from .workspace import backup_database, verify_database
from .product_io import import_products, export_products
from .project_manager import project_summary, rename_project
from .project_files import (DB_NAME, MANIFEST, create_project, save_project,
                            verify_project, backup_project, restore_project)
from .theme import ThemeManager

MENU = ("FILE", "PIN", "CONTENT FACTORY", "BOARD", "CALENDAR", "PUBLISHING",
        "ANALYTICS", "REPORTS", "TIME", "SETTINGS", "HELP")
TITLES = {
    "FILE": ("Workspace", "Products and content destinations"),
    "PIN": ("Pin library", "Create, edit and organize organic pin drafts"),
    "CONTENT FACTORY": ("Content Factory", "Plan, design and review a monthly batch"),
    "BOARD": ("Boards", "Manage board names, links and descriptions"),
    "CALENDAR": ("Publishing calendar", "Plan organic pin publishing dates and times"),
    "PUBLISHING": ("Publishing", "Manual browser-based workflow"),
    "ANALYTICS": ("Analytics", "Local operations dashboard — no Pinterest API"),
    "REPORTS": ("Reports", "Product performance reports and local CSV export"),
    "TIME": ("Time tracking", "Track work sessions and production effort"),
    "SETTINGS": ("Settings", "Appearance and local preferences"),
    "HELP": ("Help", "Offline-first workflow and usage notes"),
}


def format_duration(seconds: int) -> str:
    h, rest = divmod(max(0, seconds), 3600)
    m, s = divmod(rest, 60)
    return f"{h:02}:{m:02}:{s:02}"


def label(text: str, object_name: str | None = None) -> QLabel:
    item = QLabel(text)
    if object_name:
        item.setObjectName(object_name)
    item.setWordWrap(True)
    return item


def card() -> tuple[QFrame, QVBoxLayout]:
    frame = QFrame()
    frame.setObjectName("Card")
    body = QVBoxLayout(frame)
    body.setContentsMargins(18, 16, 18, 16)
    body.setSpacing(12)
    return frame, body


class MainWindow(QMainWindow):
    def __init__(self, storage: Storage, theme: ThemeManager):
        super().__init__()
        self.storage, self.theme = storage, theme
        self.recent_settings = QSettings('ITHutir', 'PinterestOS')
        self.project_folder = (storage.path.parent if storage.path.name == DB_NAME
                               and (storage.path.parent / MANIFEST).exists() else None)
        self.session_id = storage.start_session()
        self.active_seconds = 0
        self.paused = False
        self.last_tick = time.monotonic()
        self.tables = {}
        self.nav_buttons = {}
        self.setWindowTitle("ITHutir Pinterest OS — Organic Studio")
        self.resize(1360, 820)
        self.setMinimumSize(850, 580)
        QTimer.singleShot(0, self.apply_ui_language)
        QTimer.singleShot(100, self.resume_editor_tab)

        root = QWidget()
        self.setCentralWidget(root)
        outer = QVBoxLayout(root)
        outer.setContentsMargins(14, 14, 14, 8)
        outer.setSpacing(12)

        header, head = card()
        header.setObjectName("Header")
        row = QHBoxLayout()
        brand_title = label("PINTEREST OS", "Brand")
        brand_title.setWordWrap(False)
        row.addWidget(brand_title)
        brand_logo = QLabel()
        logo_path = Path(__file__).parent / "assets" / "ithutir-logo.png"
        logo = QPixmap(str(logo_path))
        if not logo.isNull():
            brand_logo.setPixmap(logo.scaledToHeight(38, Qt.TransformationMode.SmoothTransformation))
            brand_logo.setFixedHeight(40)
            row.addWidget(brand_logo)
        row.addStretch()
        header_status = label("● OFFLINE FIRST  •  ORGANIC ONLY", "HeaderStatus")
        header_status.setWordWrap(False)
        row.addWidget(header_status)
        head.addLayout(row)
        outer.addWidget(header)

        navigation = QScrollArea()
        navigation.setWidgetResizable(True)
        navigation.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        navigation.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        navigation.setMaximumHeight(78)
        navigation.setMinimumHeight(65)
        nav_frame = QFrame()
        nav_frame.setObjectName("Navigation")
        nav = QHBoxLayout(nav_frame)
        nav.setContentsMargins(10, 8, 10, 8)
        nav.setSpacing(8)
        navigation_width = 20
        for name in MENU:
            button = QPushButton(name)
            button.setObjectName("NavButton")
            # Keep every label readable; scroll horizontally instead of squeezing tabs.
            button_width = 170
            button.setFixedWidth(button_width)
            navigation_width += button_width + 8
            button.setCheckable(True)
            button.clicked.connect(lambda checked=False, item=name: self.open_page(item))
            nav.addWidget(button)
            self.nav_buttons[name] = button
        nav.addStretch()
        nav_frame.setMinimumWidth(navigation_width + 12)
        navigation.setWidget(nav_frame)
        outer.addWidget(navigation)

        self.pages = QStackedWidget()
        outer.addWidget(self.pages, 1)
        for name in MENU:
            page = QWidget()
            content = QVBoxLayout(page)
            content.setContentsMargins(18, 6, 12, 12)
            content.setSpacing(16)
            title, subtitle = TITLES[name]
            heading = label(f"{title} — {subtitle}", "WorkspaceHeading")
            heading.setWordWrap(False)
            content.addWidget(heading)
            if name in {"FILE", "PIN", "BOARD"}:
                table = {"FILE": "products", "PIN": "pins", "BOARD": "boards"}[name]
                if name == "PIN":
                    tabs = QTabWidget()
                    self.pin_tabs = tabs
                    catalog = QWidget()
                    catalog_layout = QVBoxLayout(catalog)
                    self.build_catalog(catalog_layout, table)
                    tabs.addTab(catalog, "Pin Library / CSV")
                    self.build_pin_google_tab(tabs)
                    self.pin_designer = PinDesigner(self.storage)
                    self.pin_designer.pin_saved.connect(self.pin_google_local_preview)
                    self.pin_designer.pin_deleted.connect(self.pin_google_local_preview)
                    self.pin_designer.pin_deleted.connect(lambda _id: self.refresh("pins"))
                    self.pin_designer.pin_deleted.connect(lambda _id: self.calendar_page.refresh())
                    tabs.addTab(self.pin_designer, "Pin Designer")
                    free_page = QWidget()
                    free_layout = QVBoxLayout(free_page)
                    free_row = QHBoxLayout()
                    self.free_image_provider = QComboBox()
                    self.free_image_provider.addItems(["Unsplash", "Pexels", "Pixabay"])
                    self.free_image_query = QLineEdit()
                    self.free_image_query.setPlaceholderText("electronics workbench")
                    self.free_image_query.returnPressed.connect(self.search_free_images)
                    search_images = QPushButton("Search free images")
                    search_images.clicked.connect(self.search_free_images)
                    import_images = QPushButton("IMPORT Image → Pin Designer")
                    import_images.clicked.connect(self.import_free_image)
                    free_row.addWidget(self.free_image_provider)
                    free_row.addWidget(self.free_image_query, 1)
                    free_row.addWidget(search_images)
                    free_row.addWidget(import_images)
                    free_layout.addLayout(free_row)
                    notice = QLabel("Images open on the provider website in your browser. Download an image, then import it. Verify commercial-use license terms for each image.")
                    notice.setWordWrap(True)
                    free_layout.addWidget(notice)
                    free_layout.addStretch(1)
                    tabs.addTab(free_page, "Free Image Library")
                    canva_page = QWidget()
                    canva_layout = QVBoxLayout(canva_page)
                    canva_row = QHBoxLayout()
                    open_canva = QPushButton("Open Canva Templates")
                    open_canva.clicked.connect(self.pin_designer.open_canva_templates)
                    import_canva = QPushButton("IMPORT OF CANVA")
                    import_canva.clicked.connect(self.import_canva_from_tab)
                    export_canva = QPushButton("EXPOT_in_CANVAS")
                    export_canva.clicked.connect(self.pin_designer.export_canva_svg)
                    canva_row.addWidget(open_canva)
                    canva_row.addWidget(import_canva)
                    canva_row.addWidget(export_canva)
                    canva_layout.addLayout(canva_row)
                    canva_id_row = QHBoxLayout()
                    canva_id_row.addWidget(QLabel("Canva design ID"))
                    canva_id_row.addWidget(self.pin_designer.canva_id, 1)
                    link_canva = QPushButton("Link Canva design to pin")
                    link_canva.clicked.connect(self.pin_designer.link_canva)
                    canva_id_row.addWidget(link_canva)
                    canva_layout.addLayout(canva_id_row)
                    canva_help = QLabel(
                        "Uses your existing browser session. IMPORT opens Canva and selects a downloaded image; "
                        "EXPOT saves an SVG and opens Canva. Files are not transferred automatically.")
                    canva_help.setWordWrap(True)
                    canva_layout.addWidget(canva_help)
                    canva_layout.addStretch(1)
                    tabs.addTab(canva_page, "CANVA")
                    self.carousel_page = CarouselPage(self.storage)
                    tabs.addTab(self.carousel_page, "Carousel Builder")
                    content.addWidget(tabs, 1)
                else:
                    self.build_catalog(content, table)
                    if name == "FILE":
                        self.build_file_tools(content)
            elif name == "CONTENT FACTORY":
                self.content_factory_page = ContentFactoryPage(
                    self.storage, open_designer=self.open_factory_designer, open_page=self.open_page)
                content.addWidget(self.content_factory_page, 1)
            elif name == "CALENDAR":
                self.calendar_page = CalendarPage(self.storage)
                content.addWidget(self.calendar_page, 1)
            elif name == "SETTINGS":
                self.settings_page = SettingsPage(self.storage, self.theme)
                self.settings_page.language_selector.currentIndexChanged.connect(lambda _i: self.apply_ui_language())
                content.addWidget(self.settings_page, 1)
            elif name == "TIME":
                self.time_page = TimePage(self.storage, on_change=self.record_elapsed)
                content.addWidget(self.time_page, 1)
            elif name == "ANALYTICS":
                self.analytics_page = AnalyticsPage(self.storage)
                content.addWidget(self.analytics_page, 1)
            elif name == "REPORTS":
                self.reports_page = ReportsPage(self.storage)
                content.addWidget(self.reports_page, 1)
            elif name == "PUBLISHING":
                self.publishing_page = PublishingPage(self.storage)
                content.addWidget(self.publishing_page, 1)
            elif name == "HELP":
                self.help_page = HelpPage(self.storage)
                content.addWidget(self.help_page, 1)
            else:
                panel, body = card()
                body.addWidget(label("Planned module", "Heading"))
                body.addWidget(label("This section is reserved for the next development phase.", "Muted"))
                content.addWidget(panel)
            content.addStretch()
            self.pages.addWidget(page)

        self.apply_ui_standards()

        footer, foot = card()
        footer_row = QHBoxLayout()
        footer_row.addWidget(label("SESSION", "Muted"))
        self.timer_label = label("00:00:00", "Metric")
        footer_row.addWidget(self.timer_label)
        footer_row.addStretch()
        self.pause_button = QPushButton("Pause")
        self.pause_button.clicked.connect(self.toggle_pause)
        footer_row.addWidget(self.pause_button)
        self.stop_button = QPushButton("Stop session")
        self.stop_button.clicked.connect(self.stop_session)
        footer_row.addWidget(self.stop_button)
        foot.addLayout(footer_row)
        outer.addWidget(footer)
        self.statusBar().showMessage("SQLite connected  •  No API  •  Manual publishing")
        for table in self.tables:
            self.refresh(table)
        self.open_page("PIN")
        self.tick_timer = QTimer(self)
        self.tick_timer.timeout.connect(self.tick)
        self.tick_timer.start(1000)
        self.render_timer()

    def apply_ui_standards(self) -> None:
        """Apply shared spacing and table geometry to every existing tab."""
        for widget in self.pages.findChildren(QTableWidget):
            widget.verticalHeader().setDefaultSectionSize(36)
            widget.horizontalHeader().setMinimumHeight(36)
            widget.setAlternatingRowColors(True)
        for layout in self.pages.findChildren(QHBoxLayout):
            if layout.spacing() < 8:
                layout.setSpacing(10)

    def build_file_tools(self, content: QVBoxLayout) -> None:
        projects, project_body = card()
        project_body.addWidget(label("Project management", "SectionHeading"))
        self.project_label = label("Active: " + (str(self.project_folder) if self.project_folder else "Default workspace"))
        project_body.addWidget(self.project_label)
        project_actions = QHBoxLayout()
        for caption, action in (
            ("New Project", self.new_project),
            ("Open Project", self.open_project),
            ("Save Project", self.save_active_project),
            ("Save As", self.save_as_project),
        ):
            button = QPushButton(caption)
            button.clicked.connect(action)
            project_actions.addWidget(button)
        project_actions.setSpacing(10)
        project_body.addLayout(project_actions)
        archive_actions = QHBoxLayout()
        for caption, action in (
            ("Full ZIP backup", self.backup_full_project),
            ("Restore ZIP to new folder", self.restore_full_project),
        ):
            button = QPushButton(caption)
            button.clicked.connect(action)
            archive_actions.addWidget(button)
        archive_actions.setSpacing(10)
        project_body.addLayout(archive_actions)
        recent_row = QHBoxLayout()
        self.recent_projects = QComboBox()
        recent_row.addWidget(self.recent_projects, 1)
        for caption, action in (
            ("Open recent", self.open_recent_project),
            ("Rename selected (inactive)", self.rename_recent_project),
            ("Refresh inventory", self.refresh_project_inventory),
        ):
            button = QPushButton(caption)
            button.clicked.connect(action)
            recent_row.addWidget(button)
        recent_row.setSpacing(10)
        project_body.addLayout(recent_row)
        self.project_inventory = label("Project inventory is available for opened project folders.")
        project_body.addWidget(self.project_inventory)
        self.asset_search = QLineEdit()
        self.asset_search.setPlaceholderText("Filter assets by filename")
        self.asset_search.textChanged.connect(self.refresh_project_inventory)
        project_body.addWidget(self.asset_search)
        self.asset_table = QTableWidget()
        self.asset_table.setColumnCount(3)
        self.asset_table.setHorizontalHeaderLabels(["Asset", "Bytes", "Referenced"])
        self.asset_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.asset_table.setMinimumHeight(150)
        self.asset_table.verticalHeader().setDefaultSectionSize(34)
        self.asset_table.horizontalHeader().setStretchLastSection(True)
        project_body.addWidget(self.asset_table)
        content.addWidget(projects)
        self.reload_recent_projects()
        self.refresh_project_inventory()
        panel, body = card()
        body.addWidget(label("Workspace safety", "SectionHeading"))
        body.addWidget(label(
            "SQLite backup only. External images and design assets are NOT included.", "Muted"))
        actions = QHBoxLayout()
        actions.setSpacing(10)
        backup = QPushButton("Create database backup")
        backup.clicked.connect(self.backup_workspace)
        actions.addWidget(backup)
        verify = QPushButton("Verify database integrity")
        verify.clicked.connect(self.verify_workspace)
        actions.addWidget(verify)
        body.addLayout(actions)
        content.addWidget(panel)

    def _recent_paths(self) -> list[str]:
        values = self.recent_settings.value("recent_project_paths", [])
        return values if isinstance(values, list) else []

    def _remember_project(self, folder: Path) -> None:
        path = str(folder.resolve())
        values = [path] + [x for x in self._recent_paths() if x != path]
        self.recent_settings.setValue("recent_project_paths", values[:12])
        self.reload_recent_projects()

    def reload_recent_projects(self) -> None:
        if not hasattr(self, "recent_projects"):
            return
        current = self.recent_projects.currentData()
        self.recent_projects.clear()
        for path in self._recent_paths():
            self.recent_projects.addItem(Path(path).name + " — " + path, path)
        index = self.recent_projects.findData(current)
        if index >= 0:
            self.recent_projects.setCurrentIndex(index)

    def open_recent_project(self) -> None:
        path = self.recent_projects.currentData()
        if not path:
            return
        try:
            verify_project(path)
            self._switch_project(Path(path).resolve())
        except (OSError, ValueError, RuntimeError) as exc:
            QMessageBox.warning(self, "Open recent failed", str(exc))

    def rename_recent_project(self) -> None:
        path = self.recent_projects.currentData()
        if not path:
            return
        source = Path(path).resolve()
        if self.project_folder and source == self.project_folder.resolve():
            QMessageBox.warning(self, "Project is active",
                                "Switch to another project before renaming this folder.")
            return
        name, accepted = QInputDialog.getText(self, "Rename project", "New folder name:",
                                              text=source.name)
        if not accepted:
            return
        try:
            verify_project(source)
            renamed = rename_project(source, name)
            values = [str(renamed) if p == str(source) else p for p in self._recent_paths()]
            self.recent_settings.setValue("recent_project_paths", values)
            self.reload_recent_projects()
        except (OSError, ValueError, RuntimeError) as exc:
            QMessageBox.warning(self, "Rename failed", str(exc))

    def refresh_project_inventory(self, *_args) -> None:
        if not hasattr(self, "asset_table"):
            return
        self.asset_table.setRowCount(0)
        if self.project_folder is None:
            self.project_inventory.setText("Default workspace — use Save As to create a project folder.")
            return
        try:
            summary = project_summary(self.project_folder)
        except (OSError, ValueError, RuntimeError) as exc:
            self.project_inventory.setText("Inventory unavailable: " + str(exc))
            return
        self.project_inventory.setText(
            f"Products: {summary['products']}  |  Pins: {summary['pins']}  |  "
            f"Boards: {summary['boards']}  |  Assets: {summary['asset_count']}  |  "
            f"Unreferenced: {summary['unused_assets']}  |  "
            f"Size: {summary['bytes']:,} bytes. Unreferenced files are NOT deleted.")
        query = self.asset_search.text().casefold()
        assets = [a for a in summary["assets"] if query in a["path"].casefold()]
        self.asset_table.setRowCount(len(assets))
        for row, item in enumerate(assets):
            for column, value in enumerate(
                (item["path"], str(item["size"]), "Yes" if item["referenced"] else "No")
            ):
                self.asset_table.setItem(row, column, QTableWidgetItem(value))
        self.asset_table.resizeColumnsToContents()

    def _choose_new_folder(self, title: str) -> Path | None:
        parent = QFileDialog.getExistingDirectory(self, title + " — choose parent directory")
        if not parent:
            return None
        name, accepted = QInputDialog.getText(self, title, "New folder name:")
        if not accepted:
            return None
        name = name.strip()
        if not name or name in {".", ".."} or "/" in name or "\\\\" in name:
            QMessageBox.warning(self, "Invalid folder name", "Enter one valid folder name.")
            return None
        return Path(parent) / name

    def _switch_project(self, folder: Path) -> bool:
        # Never discard unsaved canvas work while changing workspaces.
        if not self.pin_designer.confirm_discard():
            return False
        # Open the target before closing the current workspace.
        if self.project_folder is not None and self.project_folder.resolve() != folder.resolve():
            save_project(self.storage.conn, self.project_folder)
        target = Storage(folder / DB_NAME)
        old = self.storage
        self.stop_session()
        self.storage = target
        self.project_folder = folder
        self.session_id = target.start_session()
        self.active_seconds = 0
        self.paused = False
        self.last_tick = time.monotonic()
        self.tick_timer.start(1000)
        self.pause_button.setEnabled(True)
        self.pause_button.setText("Pause")
        self.stop_button.setEnabled(True)
        self.carousel_page.storage = target
        self.carousel_page.reload_carousels()
        self.pin_designer.storage = target
        self.pin_designer.reload_pins()
        self.pin_designer._loading = True
        self.pin_designer.dirty = False
        try:
            self.pin_designer.apply_template()
        finally:
            self.pin_designer._loading = False
        self.pin_designer._canvas_pin_id = self.pin_designer.pin.currentData()
        self.pin_designer._saved_snapshot = self.pin_designer.snapshot()
        self.pin_designer.dirty = False
        self.pin_designer.dirty_label.setText("Saved / no pending changes")
        self.pin_designer.canva_id.clear()
        self.calendar_page.storage = target
        self.calendar_page.refresh()
        self.publishing_page.storage = target
        self.publishing_page.refresh()
        self.analytics_page.storage = target
        self.analytics_page.refresh()
        self.reports_page.storage = target
        self.reports_page.refresh()
        self.time_page.storage = target
        self.time_page.set_current(0)
        self.time_page.reset_attribution()
        self.settings_page.set_storage(target)
        self.content_factory_page.set_storage(target)
        for table in self.tables:
            self.refresh(table)
        self.project_label.setText("Active: " + str(folder))
        self._remember_project(folder)
        self.refresh_project_inventory()
        old.close()
        return True

    def new_project(self) -> None:
        folder = self._choose_new_folder("New Project")
        if folder is None:
            return
        try:
            import tempfile
            with tempfile.TemporaryDirectory() as tmp:
                blank = Storage(Path(tmp) / "blank.sqlite3")
                try:
                    create_project(blank.conn, folder)
                finally:
                    blank.close()
            self._switch_project(folder)
        except (OSError, ValueError, RuntimeError) as exc:
            QMessageBox.warning(self, "New project failed", str(exc))

    def open_project(self) -> None:
        folder = QFileDialog.getExistingDirectory(self, "Open ITHutir project")
        if not folder:
            return
        try:
            verify_project(folder)
            self._switch_project(Path(folder).resolve())
        except (OSError, ValueError, RuntimeError) as exc:
            QMessageBox.warning(self, "Open failed", str(exc))

    def save_active_project(self) -> None:
        if self.project_folder is None:
            QMessageBox.information(self, "Save Project", "Use Save As to create a project folder.")
            return
        try:
            save_project(self.storage.conn, self.project_folder)
            QMessageBox.information(self, "Saved", "Project manifest and database saved.")
        except (OSError, ValueError, RuntimeError) as exc:
            QMessageBox.warning(self, "Save failed", str(exc))

    def save_as_project(self) -> None:
        folder = self._choose_new_folder("Save As")
        if folder is None:
            return
        try:
            create_project(self.storage.conn, folder)
            self._switch_project(folder)
        except (OSError, ValueError, RuntimeError) as exc:
            QMessageBox.warning(self, "Save As failed", str(exc))

    def backup_full_project(self) -> None:
        if self.project_folder is None:
            QMessageBox.information(self, "Backup", "Use Save As first.")
            return
        destination, _ = QFileDialog.getSaveFileName(
            self, "Full project backup", "ithutir-project.zip", "ZIP (*.zip)")
        if not destination:
            return
        try:
            save_project(self.storage.conn, self.project_folder)
            backup_project(self.project_folder, destination)
            QMessageBox.information(self, "Backup complete", "ZIP backup created and source verified.")
        except (OSError, ValueError, RuntimeError) as exc:
            QMessageBox.warning(self, "Backup failed", str(exc))

    def restore_full_project(self) -> None:
        source, _ = QFileDialog.getOpenFileName(self, "Restore project ZIP", "", "ZIP (*.zip)")
        if not source:
            return
        folder = self._choose_new_folder("Restore to new folder")
        if folder is None:
            return
        try:
            restored = restore_project(source, folder)
            QMessageBox.information(
                self, "Restored", f"Project restored to {restored}. Open it using Open Project.")
        except (OSError, ValueError, RuntimeError, __import__("zipfile").BadZipFile) as exc:
            QMessageBox.warning(self, "Restore failed", str(exc))

    def backup_workspace(self) -> None:
        path, _ = QFileDialog.getSaveFileName(
            self, "Create SQLite backup", "ithutir-pinterest-backup.sqlite3",
            "SQLite database (*.sqlite3)")
        if not path:
            return
        try:
            saved = backup_database(self.storage.conn, path)
            QMessageBox.information(self, "Backup verified", f"Database backup: {saved}")
        except (OSError, ValueError, RuntimeError) as exc:
            QMessageBox.warning(self, "Backup failed", str(exc))

    def verify_workspace(self) -> None:
        ok, reason = verify_database(self.storage.path)
        title = "Database integrity OK" if ok else "Database integrity failed"
        (QMessageBox.information if ok else QMessageBox.warning)(self, title, reason)

    def import_canva_from_tab(self) -> None:
        self.pin_tabs.setCurrentWidget(self.pin_designer)
        self.pin_designer.import_canva()

    def search_free_images(self) -> None:
        query = self.free_image_query.text().strip()
        if not query:
            QMessageBox.warning(self, "Free Image Library", "Enter a search phrase.")
            return
        base = {
            "Unsplash": "https://unsplash.com/s/photos/",
            "Pexels": "https://www.pexels.com/search/",
            "Pixabay": "https://pixabay.com/images/search/",
        }.get(self.free_image_provider.currentText())
        if base:
            webbrowser.open(base + quote(query, safe="") + "/")

    def import_free_image(self) -> None:
        self.pin_tabs.setCurrentWidget(self.pin_designer)
        self.pin_designer.add_image()

    def build_pin_google_tab(self, tabs: QTabWidget) -> None:
        """Google Sheets workspace belongs to PIN, not connection settings."""
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.addWidget(label("Google Sheets — PIN worksheet", "SectionHeading"))
        layout.addWidget(label(
            "Configure OAuth and spreadsheet URL in SETTINGS. "
            "Select a worksheet here to preview, import or append pins."))
        controls = QHBoxLayout()
        self.pin_google_sheet = QComboBox()
        controls.addWidget(self.pin_google_sheet, 1)
        refresh = QPushButton("Load worksheets")
        refresh.clicked.connect(self.pin_google_load)
        controls.addWidget(refresh)
        layout.addLayout(controls)
        actions = QHBoxLayout()
        for caption, handler in (
            ("Preview Google rows", self.pin_google_preview),
            ("IMPOT", self.pin_google_import),
            ("EXPORT", self.pin_google_export),
            ("СИНХРОНІЗУВАТИ", self.pin_google_sync)):
            button = QPushButton(caption)
            button.clicked.connect(handler)
            actions.addWidget(button)
        open_sheet = QPushButton("ВІДКРИТИ ТАБЛИЦЮ")
        open_sheet.clicked.connect(self.pin_google_open_sheet)
        actions.addWidget(open_sheet)
        layout.addLayout(actions)
        self.pin_google_status = label("No worksheet loaded.")
        layout.addWidget(self.pin_google_status)
        self.pin_google_table = QTableWidget()
        self.pin_google_table.setColumnCount(8)
        self.pin_google_table.setHorizontalHeaderLabels(
            [*sheets_exchange.PIN_FIELDS, "tags", "pin_id"])
        self.pin_google_table.setEditTriggers(
            QTableWidget.EditTrigger.NoEditTriggers)
        # Distribute all eight columns across the full available table width.
        # Recalculate automatically when the window is resized/maximized.
        self.pin_google_table.horizontalHeader().setSectionResizeMode(
            QHeaderView.ResizeMode.Stretch)
        self.pin_google_table.horizontalHeader().setMinimumSectionSize(65)
        self.pin_google_table.setAlternatingRowColors(True)
        self.pin_google_table.setWordWrap(False)
        layout.addWidget(self.pin_google_table, 1)
        tabs.addTab(page, "Google Sheets")
        # Staging is a read-only view of SQLite, not a second unsaved table.
        # Rebuild it on every visit, including after remote previews.
        tabs.currentChanged.connect(
            lambda index: self.pin_google_local_preview()
            if index == tabs.indexOf(page) else None)
        self.pin_google_local_preview()

    def pin_google_id(self):
        url = self.recent_settings.value("sheets/url", "", str)
        if not url:
            raise ValueError("Set spreadsheet URL in SETTINGS first")
        return parse_sheet_url(url)[0]

    def pin_google_open_sheet(self):
        """Open configured spreadsheet in the user's default browser."""
        try:
            spreadsheet_id = self.pin_google_id()
            url = f"https://docs.google.com/spreadsheets/d/{spreadsheet_id}/edit"
            if self.pin_google_sheet.currentIndex() >= 0:
                gid = self.pin_google_sheet.currentData()
                if gid is not None:
                    url += f"#gid={int(gid)}"
            if not webbrowser.open(url):
                raise RuntimeError("Browser did not confirm opening the link")
            self.pin_google_status.setText("Opening Google Sheets in browser.")
        except Exception as exc:
            self.pin_google_status.setText(f"Open sheet failed: {exc}")

    def pin_google_load(self):
        try:
            tabs = sheets_api.worksheets(self.pin_google_id())
            self.pin_google_sheet.clear()
            for gid, title in tabs:
                self.pin_google_sheet.addItem(title, gid)
            index = self.pin_google_sheet.findText("PIN")
            if index >= 0:
                self.pin_google_sheet.setCurrentIndex(index)
            self.pin_google_status.setText(f"Loaded {len(tabs)} worksheets")
        except Exception as exc:
            self.pin_google_status.setText(f"Google error: {exc}")

    def pin_google_title(self):
        if self.pin_google_sheet.currentIndex() < 0:
            raise ValueError("Load worksheets first")
        return self.pin_google_sheet.currentText()

    def pin_google_local_preview(self, saved_pin_id=None):
        """Refresh the Google Sheets staging grid from locally saved pins.

        This never accesses Google or changes the remote spreadsheet.
        """
        headers = [*sheets_exchange.PIN_FIELDS, "tags", "pin_id"]
        rows = sheets_exchange.export_pin_rows_with_ids(self.storage)
        grid = self.pin_google_table
        grid.setColumnCount(len(headers))
        grid.setHorizontalHeaderLabels(headers)
        grid.setRowCount(len(rows))
        for i, record in enumerate(rows):
            for j, key in enumerate(headers):
                grid.setItem(i, j, QTableWidgetItem(str(record.get(key, ""))))
        self.pin_google_status.setText(
            f"Локально підготовлено {len(rows)} пінів. "
            "Google Sheets не змінено — для експорту натисніть СИНХРОНІЗУВАТИ.")

    def pin_google_preview(self):
        try:
            rows = sheets_api.read_rows(
                self.pin_google_id(), self.pin_google_title(), limit=101)
            grid = self.pin_google_table
            headers = rows[0] if rows else [*sheets_exchange.PIN_FIELDS, "tags", "pin_id"]
            grid.setColumnCount(max(8, len(headers)))
            grid.setHorizontalHeaderLabels(
                list(headers) + [""] * (grid.columnCount()-len(headers)))
            data = rows[1:] if rows else []
            grid.setRowCount(len(data))
            for i, row in enumerate(data):
                for j, cell in enumerate(row):
                    grid.setItem(i, j, QTableWidgetItem(str(cell)))
            self.pin_google_status.setText(f"Preview: {len(data)} rows (max 100)")
        except Exception as exc:
            self.pin_google_status.setText(f"Preview error: {exc}")

    def pin_google_sync(self):
        """Preview ID-based outbound sync; explicit approval before append."""
        try:
            title = self.pin_google_title()
            headers = [*sheets_exchange.PIN_FIELDS, "tags", "pin_id"]
            local = sheets_exchange.export_pin_rows_with_ids(self.storage)
            remote = sheets_api.read_rows(
                self.pin_google_id(), title, limit=100001)
            if remote and list(remote[0]) != headers:
                raise ValueError(
                    "Google worksheet columns differ. Sync cancelled; no changes.")
            if remote and any(row and (len(row) < 8 or not str(row[7]).strip())
                              for row in remote[1:]):
                raise ValueError(
                    "Existing rows without pin_id. Sync cancelled to prevent duplicates.")
            ids = [str(row[7]).strip() for row in remote[1:]]
            if len(ids) != len(set(ids)):
                raise ValueError("Duplicate pin_id in Google Sheets; sync cancelled.")
            existing = set(ids)
            new = sum(str(record["pin_id"]) not in existing for record in local)
            skipped = len(local) - new
            answer = QMessageBox.question(
                self, "Confirm PIN synchronization",
                f"Worksheet: {title}\n"
                f"New pins to append: {new}\n"
                f"Already synchronized: {skipped}\n"
                "Direction: Pinterest OS → Google Sheets only.\n"
                "Existing rows will not be updated or deleted. Continue?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No)
            if answer != QMessageBox.StandardButton.Yes:
                self.pin_google_status.setText("Synchronization cancelled; no Google changes.")
                return
            added, skipped = sheets_api.append_unique_pins(
                self.pin_google_id(), title, headers, local)
            self.pin_google_preview()
            self.pin_google_status.setText(
                f"Sync complete: {added} new rows, {skipped} skipped. "
                "Existing rows unchanged.")
        except Exception as exc:
            self.pin_google_status.setText(f"Sync failed (no confirmed completion): {exc}")

    def pin_google_import(self):
        try:
            self.settings_page.sheet_tab.clear()
            self.settings_page.sheet_tab.addItem(self.pin_google_title())
            self.settings_page.import_google_pins()
            self.pin_google_local_preview()
            self.pin_google_status.setText(self.settings_page.sheet_status.text())
        except Exception as exc:
            self.pin_google_status.setText(f"Import error: {exc}")

    def pin_google_export(self):
        """Export the saved SQLite pins to the selected remote worksheet.

        Only append missing pin IDs. An empty worksheet gets eight headers.
        Never overwrite incompatible or existing user rows.
        """
        try:
            title = self.pin_google_title()
            spreadsheet_id = self.pin_google_id()
            headers = [*sheets_exchange.PIN_FIELDS, "tags", "pin_id"]
            records = sheets_exchange.export_pin_rows_with_ids(self.storage)
            if not records:
                self.pin_google_status.setText(
                    "Немає збережених локальних пінів для експорту.")
                return
            # Read-only preflight: surface incompatible headers before approval.
            remote = sheets_api.read_rows(spreadsheet_id, title, limit=100001)
            if remote and list(remote[0]) != headers:
                raise ValueError(
                    "У Google аркуші інші заголовки. Експорт зупинено "
                    "без зміни наявних даних.")
            existing = {str(row[7]).strip() for row in remote[1:]
                        if len(row) > 7 and str(row[7]).strip()}
            new_count = sum(str(r["pin_id"]) not in existing for r in records)
            answer = QMessageBox.question(
                self, "Підтвердити експорт пінів",
                f"Аркуш: {title}\n"
                f"Локальних пінів: {len(records)}\n"
                f"Нових для додавання: {new_count}\n"
                "Порожній аркуш отримає 8 заголовків (A:H).\n"
                "Існуючі рядки не перезаписуються. Продовжити?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No)
            if answer != QMessageBox.StandardButton.Yes:
                self.pin_google_status.setText(
                    "Експорт скасовано; Google Sheets не змінено.")
                return
            added, skipped = sheets_api.append_unique_pins(
                spreadsheet_id, title, headers, records)
            self.pin_google_status.setText(
                f"Експорт завершено: додано {added}; пропущено {skipped}.")
            # Keep the local staging grid visible and refresh it from SQLite.
            self.pin_google_local_preview()
            self.pin_google_status.setText(
                f"Експорт завершено: додано {added}; пропущено {skipped}. "
                "Перевірте результат кнопкою Preview Google rows.")
        except Exception as exc:
            self.pin_google_status.setText(
                f"Помилка експорту ({type(exc).__name__}): {exc}")

    def build_catalog(self, content: QVBoxLayout, table: str) -> None:
        panel, body = card()
        actions = QHBoxLayout()
        actions.addWidget(label("PRODUCTS" if table == "products" else "LOCAL RECORDS", "SectionHeading"))
        actions.addStretch()
        add = QPushButton("+ New")
        add.setObjectName("Primary")
        add.clicked.connect(lambda checked=False, t=table: self.edit_record(t))
        actions.addWidget(add)
        edit = QPushButton("Edit selected")
        edit.clicked.connect(lambda checked=False, t=table: self.edit_selected(t))
        actions.addWidget(edit)
        refresh = QPushButton("Refresh")
        refresh.clicked.connect(lambda checked=False, t=table: self.refresh(t))
        actions.addWidget(refresh)
        if table == "pins":
            duplicate = QPushButton("Duplicate as draft")
            duplicate.clicked.connect(self.duplicate_selected_pin)
            actions.addWidget(duplicate)
            remove = QPushButton("Delete pin")
            remove.clicked.connect(self.delete_selected_pin)
            actions.addWidget(remove)
            import_button = QPushButton("Import CSV")
            import_button.clicked.connect(self.import_csv)
            actions.addWidget(import_button)
            export_button = QPushButton("Export CSV")
            export_button.clicked.connect(self.export_csv)
            actions.addWidget(export_button)
        if table == "boards":
            assign = QPushButton("Assign pin to board")
            assign.clicked.connect(self.assign_pin_to_board)
            actions.addWidget(assign)
            plan = QPushButton("Content plan")
            plan.clicked.connect(self.show_board_plan)
            actions.addWidget(plan)
            remove = QPushButton("Delete board")
            remove.clicked.connect(self.delete_selected_board)
            actions.addWidget(remove)
        if table == "products":
            remove = QPushButton("Delete selected")
            remove.clicked.connect(self.delete_selected_product)
            actions.addWidget(remove)
            import_button = QPushButton("Import CSV/JSON")
            import_button.clicked.connect(self.import_product_file)
            actions.addWidget(import_button)
            export_button = QPushButton("Export CSV/JSON")
            export_button.clicked.connect(self.export_product_file)
            actions.addWidget(export_button)
        body.addLayout(actions)
        if table == "pins":
            filters = QHBoxLayout()
            self.pin_search = QLineEdit()
            self.pin_search.setPlaceholderText("Search title, description or destination URL")
            self.pin_search.textChanged.connect(lambda _: self.refresh("pins"))
            filters.addWidget(self.pin_search)
            self.pin_status = QComboBox()
            for status in ("ALL", "DRAFT", "IN_REVIEW", "READY", "PUBLISHED"):
                self.pin_status.addItem(status, status)
            self.pin_status.currentIndexChanged.connect(lambda _: self.refresh("pins"))
            filters.addWidget(self.pin_status)
            body.addLayout(filters)
        if table == "boards":
            self.board_search = QLineEdit()
            self.board_search.setPlaceholderText("Search board name, SEO description or URL")
            self.board_search.textChanged.connect(lambda _: self.refresh("boards"))
            body.addWidget(self.board_search)
            self.board_category = QComboBox()
            self.board_category.addItem("ALL", "ALL")
            for category in CATEGORIES:
                self.board_category.addItem(category, category)
            self.board_category.currentIndexChanged.connect(lambda _: self.refresh("boards"))
            body.addWidget(self.board_category)
            self.board_summary = label("Board statistics")
            body.addWidget(self.board_summary)
        if table == "products":
            filters = QHBoxLayout()
            search = QLineEdit()
            search.setPlaceholderText("Search product name, category or URL")
            search.textChanged.connect(lambda _: self.refresh("products"))
            filters.addWidget(search)
            category = QComboBox()
            for value in ("ALL", "POD", "KDP", "DIGITAL", "FREE_TOOL", "OTHER"):
                category.addItem(value, value)
            category.currentIndexChanged.connect(lambda _: self.refresh("products"))
            filters.addWidget(category)
            body.addLayout(filters)
            self.product_search = search
            self.product_category = category
        grid = QTableWidget()
        grid.setAlternatingRowColors(True)
        grid.verticalHeader().setDefaultSectionSize(36)
        grid.setMinimumHeight(185)
        grid.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        grid.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        grid.setSelectionMode(QTableWidget.SelectionMode.SingleSelection)
        grid.verticalHeader().setVisible(False)
        grid.horizontalHeader().setStretchLastSection(True)
        grid.doubleClicked.connect(lambda index, t=table: self.edit_selected(t))
        grid.setMinimumHeight(300)
        body.addWidget(grid)
        content.addWidget(panel, 1)
        self.tables[table] = grid

    def assign_pin_to_board(self) -> None:
        board_id = self.selected_board_id()
        if board_id is None:
            QMessageBox.information(self, "Select board", "Select a board first.")
            return
        pins = self.storage.all("pins")
        if not pins:
            QMessageBox.information(self, "No pins", "Create a pin in PIN first.")
            return
        options = [f"#{pin['id']} {pin['title']} [{pin['status']}]" for pin in pins]
        selected, accepted = QInputDialog.getItem(
            self, "Assign pin", "Choose pin:", options, 0, False)
        if not accepted:
            return
        pin = pins[options.index(selected)]
        try:
            self.storage.update("pins", pin["id"], board_id=board_id)
            self.refresh("boards")
            self.refresh("pins")
            self.calendar_page.refresh()
        except Exception as exc:
            QMessageBox.warning(self, "Assignment failed", str(exc))

    def show_board_plan(self) -> None:
        board_id = self.selected_board_id()
        if board_id is None:
            QMessageBox.information(self, "Select board", "Select a board first.")
            return
        board = self.storage.get("boards", board_id)
        if not board:
            return
        from datetime import date
        planned = board_plan(board, self.storage.all("pins"), start=date.today())
        issues = board_seo_issues(board["name"], board["description"], board["url"])
        stats = {status: 0 for status in ("DRAFT", "IN_REVIEW", "READY", "PUBLISHED")}
        for pin in self.storage.all("pins"):
            if pin["board_id"] == board_id:
                stats[pin["status"]] += 1
        report = (f"Board: {board['name']}\\nCategory: {board['category']}\\n"
                  + "Statuses: " + ", ".join(f"{k}: {v}" for k, v in stats.items())
                  + "\\n\\nSEO review:\\n"
                  + ("\\n".join(issues) if issues else "No editorial warnings")
                  + "\\n\\nSuggested content dates (not scheduled):\\n"
                  + ("\\n".join(f"{p['date']} — #{p['pin_id']} {p['title']} ({p['status']})"
                               for p in planned) if planned else "No pending pins"))
        QMessageBox.information(self, "Board content plan", report)

    def selected_board_id(self) -> int | None:
        grid = self.tables["boards"]
        row = grid.currentRow()
        item = grid.item(row, 0) if row >= 0 else None
        return int(item.text()) if item else None

    def delete_selected_board(self) -> None:
        board_id = self.selected_board_id()
        if board_id is None:
            QMessageBox.information(self, "Select board", "Select a board first.")
            return
        board = self.storage.get("boards", board_id)
        if not board:
            return
        count = self.storage.board_pin_count(board_id)
        message = (f"Delete board '{board['name']}'?\\n"
                   f"{count} linked pin(s) will remain, but their board link will be cleared.\\n"
                   "This action cannot be undone.")
        if QMessageBox.question(
            self, "Confirm board deletion", message,
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No
        ) != QMessageBox.StandardButton.Yes:
            return
        try:
            self.storage.delete_board(board_id)
            self.refresh("boards")
            self.refresh("pins")
            self.pin_designer.reload_pins()
        except Exception as exc:
            QMessageBox.warning(self, "Delete board failed", str(exc))

    def selected_pin_id(self) -> int | None:
        grid = self.tables["pins"]
        row = grid.currentRow()
        item = grid.item(row, 0) if row >= 0 else None
        return int(item.text()) if item else None

    def duplicate_selected_pin(self) -> None:
        pin_id = self.selected_pin_id()
        if pin_id is None:
            QMessageBox.information(self, "Select pin", "Select a pin first.")
            return
        try:
            copied = self.storage.duplicate_pin(pin_id)
            self.refresh("pins")
            self.pin_designer.reload_pins()
            QMessageBox.information(self, "Draft created", f"Created draft pin #{copied}.")
        except (ValueError, OSError) as exc:
            QMessageBox.warning(self, "Duplicate failed", str(exc))

    def delete_selected_pin(self) -> None:
        pin_id = self.selected_pin_id()
        if pin_id is None:
            QMessageBox.information(self, "Select pin", "Select a pin first.")
            return
        record = self.storage.get("pins", pin_id)
        if record is None:
            return
        answer = QMessageBox.question(
            self, "Delete pin?",
            f"Delete pin #{pin_id}: {record['title']}?\n"
            "Its saved design and calendar entries will also be deleted. "
            "Exported image files will NOT be deleted. This cannot be undone.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No)
        if answer != QMessageBox.StandardButton.Yes:
            return
        self.storage.delete_pin(pin_id)
        self.refresh("pins")
        self.pin_designer.reload_pins()
        self.calendar_page.refresh()

    def selected_product_id(self) -> int | None:
        grid = self.tables["products"]
        row = grid.currentRow()
        if row < 0 or grid.item(row, 0) is None:
            return None
        return int(grid.item(row, 0).text())

    def delete_selected_product(self) -> None:
        product_id = self.selected_product_id()
        if product_id is None:
            QMessageBox.information(self, "Select product", "Select a product first.")
            return
        product = self.storage.get("products", product_id)
        if not product:
            return
        count = self.storage.product_pin_count(product_id)
        warning = (
            f"Delete product '{product['name']}'?\\n"
            f"{count} linked pin(s) will remain, but their product link will be cleared.\\n"
            "This cannot be undone."
        )
        if QMessageBox.question(self, "Confirm product deletion", warning,
                                QMessageBox.StandardButton.Yes |
                                QMessageBox.StandardButton.No,
                                QMessageBox.StandardButton.No) != QMessageBox.StandardButton.Yes:
            return
        self.storage.delete_product(product_id)
        self.refresh("products")
        self.refresh("pins")

    def import_product_file(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self, "Import products", "", "Product files (*.csv *.json)")
        if not path:
            return
        try:
            count = import_products(self.storage, path)
            self.refresh("products")
            QMessageBox.information(self, "Import complete", f"Imported {count} products.")
        except (OSError, ValueError, UnicodeError) as exc:
            QMessageBox.warning(self, "Import failed", str(exc))

    def export_product_file(self) -> None:
        path, _ = QFileDialog.getSaveFileName(
            self, "Export products", "ithutir-products.csv",
            "CSV (*.csv);;JSON (*.json)")
        if not path:
            return
        try:
            count = export_products(self.storage, path)
            QMessageBox.information(self, "Export complete", f"Exported {count} products.")
        except (OSError, ValueError) as exc:
            QMessageBox.warning(self, "Export failed", str(exc))

    def import_csv(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self, "Import pin metadata", "", "CSV (*.csv)")
        if not path:
            return
        try:
            count = import_pins(self.storage, path)
            self.refresh("pins")
            self.pin_designer.reload_pins()
            QMessageBox.information(self, "Import complete", f"Imported {count} pins.")
        except (ValueError, OSError, UnicodeError, Exception) as exc:
            QMessageBox.warning(self, "Import failed", str(exc))

    def export_csv(self) -> None:
        path, _ = QFileDialog.getSaveFileName(self, "Export pin metadata", "ithutir-pins.csv", "CSV (*.csv)")
        if not path:
            return
        try:
            export_pins(self.storage, path)
            QMessageBox.information(self, "Export complete", f"Saved: {path}")
        except OSError as exc:
            QMessageBox.warning(self, "Export failed", str(exc))

    def refresh(self, table: str) -> None:
        grid = self.tables[table]
        rows = (self.storage.search_products(self.product_search.text(), self.product_category.currentData())
                if table == "products" else
                self.storage.search_pins(self.pin_search.text(), self.pin_status.currentData())
                if table == "pins" else
                [board for board in self.storage.search_boards(self.board_search.text())
                 if self.board_category.currentData() == "ALL"
                 or board["category"] == self.board_category.currentData()]
                if table == "boards" else self.storage.all(table))
        if table == "boards":
            counts = self.storage.board_pin_counts()
            self.board_summary.setText(
                f"Boards: {len(rows)} shown  |  "
                f"Linked pins: {sum(counts.values())}  |  "
                f"Unassigned pins: {sum(1 for p in self.storage.all('pins') if p['board_id'] is None)}")
        fields = {
            "products": ("id", "name", "category", "target_url"),
            "boards": ("id", "name", "category", "url", "description", "linked_pins"),
            "pins": ("id", "title", "status", "board_id", "product_id", "destination_url"),
        }[table]
        grid.setColumnCount(len(fields))
        grid.setHorizontalHeaderLabels([x.replace("_", " ").title() for x in fields])
        grid.setRowCount(len(rows))
        for i, row in enumerate(rows):
            for j, field in enumerate(fields):
                value = (counts.get(row["id"], 0) if table == "boards" and field == "linked_pins"
                         else row.get(field))
                grid.setItem(i, j, QTableWidgetItem(str(value if value is not None else "")))
        grid.resizeColumnsToContents()

    def edit_record(self, table: str, record: dict | None = None) -> None:
        if RecordEditor(self.storage, table, record, self).exec():
            self.refresh(table)
            if table == "pins":
                self.pin_designer.reload_pins()
            if table in {"boards", "products"}:
                self.refresh("pins")

    def edit_selected(self, table: str) -> None:
        grid = self.tables[table]
        row = grid.currentRow()
        if row < 0:
            QMessageBox.information(self, "Select a record", "Select a row first.")
            return
        record = self.storage.get(table, int(grid.item(row, 0).text()))
        if record:
            self.edit_record(table, record)

    def open_factory_designer(self, pin_id: int) -> None:
        if not self.pin_designer.confirm_discard():
            return
        self.pin_designer.dirty = False
        self.pin_designer._saved_snapshot = self.pin_designer.snapshot()
        self.pin_designer.pin.blockSignals(True)
        self.pin_designer.reload_pins()
        self.pin_designer.pin.setCurrentIndex(self.pin_designer.pin.findData(pin_id))
        self.pin_designer.pin.blockSignals(False)
        if self.storage.get_pin_design(pin_id):
            self.pin_designer.load_pin()
        else:
            self.pin_designer.apply_template()
        self.pin_tabs.setCurrentIndex(1)
        self.open_page('PIN')

    def resume_editor_tab(self):
        if getattr(self.pin_designer, "_canvas_pin_id", None) is None:
            return
        self.open_page("PIN")
        self.pin_tabs.setCurrentWidget(self.pin_designer)

    def apply_ui_language(self):
        from .i18n_uk import apply_language, UK
        language = self.recent_settings.value("appearance/language", "en", str)
        apply_language(self, language)
        for key, button in self.nav_buttons.items():
            button.setText(UK.get(key, key) if language == "uk" else key)

    def open_page(self, name: str) -> None:
        if name == 'PIN':
            self.refresh('pins')
        elif name == 'CONTENT FACTORY':
            self.content_factory_page.reload()
        elif name in ('CALENDAR', 'PUBLISHING', 'ANALYTICS'):
            getattr(self, name.lower() + '_page').refresh()
        self.pages.setCurrentIndex(MENU.index(name))
        for key, button in self.nav_buttons.items():
            button.setChecked(key == name)
        self.statusBar().showMessage(f"{name}  •  SQLite connected  •  No API")

    def record_elapsed(self) -> None:
        if self.session_id is None:
            return
        now = time.monotonic()
        if not self.paused:
            elapsed = max(0, int(now - self.last_tick))
            if elapsed:
                self.active_seconds += elapsed
                self.storage.save_elapsed(self.session_id, elapsed,
                                          self.time_page.active_task,
                                          self.time_page.active_pin_id)
                self.last_tick += elapsed
        else:
            self.last_tick = now

    def tick(self) -> None:
        self.record_elapsed()
        self.render_timer()

    def render_timer(self) -> None:
        value = format_duration(self.active_seconds)
        self.timer_label.setText(value)
        if hasattr(self, "time_page"):
            self.time_page.set_current(self.active_seconds)

    def toggle_pause(self) -> None:
        if self.session_id is None:
            return
        self.record_elapsed()
        self.paused = not self.paused
        self.last_tick = time.monotonic()
        self.pause_button.setText("Resume" if self.paused else "Pause")

    def stop_session(self) -> None:
        if self.session_id is None:
            return
        self.record_elapsed()
        self.storage.end_session(self.session_id)
        self.session_id = None
        self.tick_timer.stop()
        self.pause_button.setEnabled(False)
        self.stop_button.setEnabled(False)
        self.statusBar().showMessage("Session stopped. Data saved.")

    def closeEvent(self, event) -> None:
        worker = self.content_factory_page.worker
        if worker and worker.isRunning():
            self.statusBar().showMessage('RSS refresh is finishing. Please close again once it completes.')
            event.ignore()
            return
        if not self.pin_designer.confirm_discard():
            event.ignore()
            return
        if self.project_folder is not None:
            try:
                save_project(self.storage.conn, self.project_folder)
            except Exception as exc:
                QMessageBox.warning(self, "Project save failed", str(exc))
                event.ignore()
                return
        self.stop_session()
        self.storage.close()
        event.accept()


def main() -> int:
    app = QApplication(sys.argv)
    app.setOrganizationName("ITHutir")
    app.setApplicationName("PinterestOS")
    theme = ThemeManager(app)
    data_dir = QStandardPaths.writableLocation(QStandardPaths.StandardLocation.AppLocalDataLocation)
    if not data_dir:
        raise RuntimeError("Cannot locate platform application data directory")
    storage = Storage(Path(data_dir) / "pinterest_os.sqlite3")
    window = MainWindow(storage, theme)
    window.show()
    return app.exec()
