"""Local-only application preferences and workspace diagnostics."""
from pathlib import Path
import webbrowser
from urllib.parse import urlparse
from PyQt6.QtCore import QSettings, Qt
from .google_sheets_link import parse_sheet_url, preview_public_sheet
from . import sheets_api, sheets_exchange
from .product_io import validate_products, COLUMNS
from .reports import report_rows, FIELDS as REPORT_FIELDS
from datetime import datetime, timezone
from PyQt6.QtWidgets import QWidget, QVBoxLayout, QLabel, QComboBox, QPushButton, QLineEdit, QFormLayout, QGroupBox, QPlainTextEdit, QFileDialog, QMessageBox, QTabWidget, QScrollArea, QSizePolicy, QLayout


class SettingsPage(QWidget):
    def __init__(self, storage, theme, parent=None):
        super().__init__(parent)
        self.storage = storage
        self.theme = theme
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        tabs = QTabWidget(self)
        tabs.setObjectName("SettingsSubtabs")
        root.addWidget(tabs, 1)
        tabs.setMinimumHeight(320)
        tabs.tabBar().setExpanding(False)

        def make_tab(name):
            scroll = QScrollArea()
            scroll.setWidgetResizable(True)
            scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
            scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
            scroll.setMinimumHeight(260)
            scroll.setFrameShape(QScrollArea.Shape.NoFrame)
            panel = QWidget()
            column = QVBoxLayout(panel)
            column.setContentsMargins(14, 14, 14, 14)
            column.setSpacing(14)
            column.setSizeConstraint(QLayout.SizeConstraint.SetMinimumSize)
            scroll.setWidget(panel)
            tabs.addTab(scroll, name)
            return column

        appearance_layout = make_tab("Appearance")
        accounts_layout = make_tab("Accounts")
        sheets_layout = make_tab("Google Sheets")
        diagnostics_layout = make_tab("Diagnostics")
        pinterest_layout = make_tab("Pinterest — імпорт")
        from .pinterest_import_page import PinterestImportPage
        self.pinterest_import = PinterestImportPage(storage)
        self.pinterest_import.imported.connect(self.refresh_after_pinterest_import)
        pinterest_layout.addWidget(self.pinterest_import)
        layout = appearance_layout
        layout.addWidget(QLabel("Appearance"))
        self.theme_selector = QComboBox()
        self.theme_selector.setAccessibleName("Application color theme")
        for name, key in (("System", "system"), ("Dark", "dark"), ("Light", "light")):
            self.theme_selector.addItem(name, key)
        self.theme_selector.setCurrentIndex(
            max(0, self.theme_selector.findData(theme.preference)))
        self.theme_selector.currentIndexChanged.connect(self.change_theme)
        layout.addWidget(self.theme_selector)
        self.preferences = QSettings("ITHutir", "PinterestOS")
        from .i18n_uk import apply_language
        language_label = QLabel("Language / Мова")
        layout.addWidget(language_label)
        self.language_selector = QComboBox()
        self.language_selector.addItem("English", "en")
        self.language_selector.addItem("Українська", "uk")
        selected_language = self.preferences.value("appearance/language", "en", str)
        self.language_selector.setCurrentIndex(max(0, self.language_selector.findData(selected_language)))
        self.language_selector.currentIndexChanged.connect(self.change_language)
        layout.addWidget(self.language_selector)
        accounts = QGroupBox("Accounts — browser sign-in (no stored passwords)")
        form = QFormLayout(accounts)
        form.setVerticalSpacing(12)
        form.setHorizontalSpacing(14)
        form.setSizeConstraint(QLayout.SizeConstraint.SetMinimumSize)
        self.pinterest_email = QLineEdit()
        self.pinterest_email.setText(self.preferences.value("accounts/pinterest_email", "", str))
        self.pinterest_email.setPlaceholderText("Pinterest account email")
        form.addRow("Pinterest email", self.pinterest_email)
        self.pinterest_profile = QLineEdit()
        self.pinterest_profile.setText(self.preferences.value("accounts/pinterest_profile", "", str))
        self.pinterest_profile.setPlaceholderText("https://www.pinterest.com/yourprofile/")
        form.addRow("Pinterest profile URL", self.pinterest_profile)
        self.google_email = QLineEdit()
        self.google_email.setText(self.preferences.value("accounts/google_email", "", str))
        self.google_email.setPlaceholderText("Google Drive account email")
        form.addRow("Google email", self.google_email)
        self.account_status = QLabel(
            "Emails and profile URL are local identifiers only. No account connection "
            "or Drive synchronization is established. Passwords are never collected.")
        self.account_status.setWordWrap(True)
        form.addRow(self.account_status)
        save_accounts = QPushButton("Save account identifiers")
        save_accounts.clicked.connect(self.save_accounts)
        form.addRow(save_accounts)
        pinterest_login = QPushButton("Open Pinterest sign-in in browser")
        pinterest_login.clicked.connect(lambda: webbrowser.open("https://www.pinterest.com/login/"))
        form.addRow(pinterest_login)
        google_login = QPushButton("Open Google Drive in browser")
        google_login.clicked.connect(lambda: webbrowser.open("https://drive.google.com/"))
        form.addRow(google_login)
        appearance_layout.addStretch(1)
        accounts.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Minimum)
        accounts_layout.addWidget(accounts)
        accounts_layout.addStretch(1)
        sheets = QGroupBox("Google Sheets — selected spreadsheet")
        sheet_form = QFormLayout(sheets)
        sheet_form.setVerticalSpacing(12)
        sheet_form.setHorizontalSpacing(14)
        sheet_form.setSizeConstraint(QLayout.SizeConstraint.SetMinimumSize)
        sheet_form.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.AllNonFixedFieldsGrow)
        self.sheet_url = QLineEdit()
        self.sheet_url.setPlaceholderText("https://docs.google.com/spreadsheets/d/.../edit#gid=0")
        self.sheet_url.setText(self.preferences.value("sheets/url", "", str))
        sheet_form.addRow("Spreadsheet URL", self.sheet_url)
        self.sheet_status = QLabel(
            "No Google authorization. Public CSV preview only; private sheets "
            "and writing require a separate authorized integration.")
        self.sheet_status.setWordWrap(True)
        sheet_form.addRow(self.sheet_status)
        save_sheet = QPushButton("Validate and save link")
        save_sheet.clicked.connect(self.save_sheet_link)
        sheet_form.addRow(save_sheet)
        preview_sheet = QPushButton("Preview public sheet (read-only)")
        preview_sheet.clicked.connect(self.preview_sheet)
        sheet_form.addRow(preview_sheet)
        self.sheet_preview = QPlainTextEdit()
        self.sheet_preview.setReadOnly(True)
        self.sheet_preview.setMinimumHeight(180)
        self.sheet_preview.setMaximumHeight(280)
        sheet_form.addRow(self.sheet_preview)
        connect_google = QPushButton("Connect Google (OAuth desktop)")
        connect_google.clicked.connect(self.connect_google)
        sheet_form.addRow(connect_google)
        disconnect_google = QPushButton("Disconnect Google (local credentials)")
        disconnect_google.clicked.connect(self.disconnect_google)
        sheet_form.addRow(disconnect_google)
        self.sheet_tab = QComboBox()
        sheet_form.addRow("Authorized worksheet", self.sheet_tab)
        list_tabs = QPushButton("List authorized worksheets")
        list_tabs.clicked.connect(self.list_google_tabs)
        sheet_form.addRow(list_tabs)
        preview_private = QPushButton("Preview selected private worksheet")
        preview_private.clicked.connect(self.preview_private)
        sheet_form.addRow(preview_private)
        import_products = QPushButton("Import selected worksheet as NEW products")
        import_products.clicked.connect(self.import_google_products)
        sheet_form.addRow(import_products)
        export_products = QPushButton("Export products to NEW worksheet")
        export_products.clicked.connect(lambda: self.export_google("products"))
        sheet_form.addRow(export_products)
        export_reports = QPushButton("Export USD report to NEW worksheet")
        export_reports.clicked.connect(lambda: self.export_google("reports"))
        sheet_form.addRow(export_reports)
        import_metrics = QPushButton("Import NEW Pinterest metrics from selected worksheet")
        import_metrics.clicked.connect(self.import_google_metrics)
        sheet_form.addRow(import_metrics)
        for kind, caption in (
            ("time", "Export TIME entries to NEW worksheet"),
            ("analytics", "Export imported Pinterest metrics to NEW worksheet"),
            ("tracking", "Export UTM tracking registry to NEW worksheet"),
        ):
            button = QPushButton(caption)
            button.clicked.connect(lambda checked=False, item=kind: self.export_google(item))
            sheet_form.addRow(button)
        sheets.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Minimum)
        sheets_layout.addWidget(sheets, 0)
        sheets_layout.addStretch(1)
        diagnostics_layout.addWidget(QLabel("Workspace diagnostics (read-only)"))
        self.diagnostics = QLabel()
        self.diagnostics.setWordWrap(True)
        diagnostics_layout.addWidget(self.diagnostics)
        refresh = QPushButton("Refresh diagnostics")
        refresh.clicked.connect(self.refresh)
        diagnostics_layout.addWidget(refresh)
        diagnostics_note = QLabel(
            "Data stays in the local SQLite workspace. Pinterest API is read-only; no "
            "automatic posting or paid advertising. Financial labor rates "
            "are configured in ANALYTICS; time is recorded in TIME.")
        diagnostics_note.setWordWrap(True)
        diagnostics_layout.addWidget(diagnostics_note)
        diagnostics_layout.addStretch(1)
        # Maintain readable controls even in a short application window.
        for control_type in (QPushButton, QComboBox, QLineEdit):
            for control in self.findChildren(control_type):
                control.setMinimumHeight(38)
        for button in self.findChildren(QPushButton):
            button.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.sheet_preview.setMinimumHeight(220)
        self.refresh()

    def change_language(self, _index):
        from .i18n_uk import apply_language
        language = self.language_selector.currentData()
        self.preferences.setValue("appearance/language", language)
        window = self.window()
        apply_language(window, language)

    def change_theme(self, index):
        preference = self.theme_selector.itemData(index)
        if preference in {"system", "dark", "light"}:
            self.theme.set_theme(preference)

    def set_storage(self, storage):
        self.storage = storage
        self.pinterest_import.set_storage(storage)
        self.refresh()

    def refresh_after_pinterest_import(self):
        window=self.window()
        if hasattr(window,"refresh") and hasattr(window,"tables"):
            window.refresh("boards")
            window.refresh("pins")
            window.pin_designer.reload_pins()
            window.calendar_page.refresh()
        self.refresh()

    def refresh(self):
        path = Path(self.storage.path)
        check = self.storage.conn.execute("PRAGMA quick_check").fetchone()
        status = check[0] if check else "Unknown"
        self.diagnostics.setText(
            f"Database: {path}\n"
            f"SQLite quick_check: {status}\n"
            f"Database size: {path.stat().st_size if path.exists() else 0} bytes\n"
            "Read-only inspection; this does not replace a verified backup.")

    def save_accounts(self):
        pinterest = self.pinterest_email.text().strip()
        google = self.google_email.text().strip()
        profile = self.pinterest_profile.text().strip()
        for address in (pinterest, google):
            if address and (address.count("@") != 1 or " " in address or "." not in address.split("@")[-1]):
                self.account_status.setText("Invalid email format. Nothing saved.")
                return
        if profile:
            parsed = urlparse(profile)
            if parsed.scheme != "https" or parsed.hostname not in (
                    "pinterest.com", "www.pinterest.com"):
                self.account_status.setText(
                    "Pinterest profile must use https://www.pinterest.com/ . Nothing saved.")
                return
        self.preferences.setValue("accounts/pinterest_email", pinterest)
        self.preferences.setValue("accounts/pinterest_profile", profile)
        self.preferences.setValue("accounts/google_email", google)
        self.preferences.sync()
        if self.preferences.status() != QSettings.Status.NoError:
            self.account_status.setText("Could not save local settings.")
            return
        self.account_status.setText(
            "Local account identifiers saved. Sign in separately in the browser; "
            "no passwords, OAuth tokens or automatic Drive access are stored.")

    def save_sheet_link(self):
        value = self.sheet_url.text().strip()
        if not value:
            self.sheet_status.setText("Enter a spreadsheet URL; existing link not changed.")
            return
        try:
            spreadsheet_id, gid = parse_sheet_url(value)
        except ValueError as exc:
            self.sheet_status.setText(str(exc))
            return
        self.preferences.setValue("sheets/url", value)
        self.preferences.sync()
        if self.preferences.status() != QSettings.Status.NoError:
            self.sheet_status.setText("Could not save spreadsheet URL.")
            return
        self.sheet_status.setText(
            f"Link saved locally (sheet gid={gid}). Access not yet tested. "
            "This does not grant permission to read or write.")

    def preview_sheet(self):
        value = self.sheet_url.text().strip()
        self.sheet_preview.clear()
        try:
            rows = preview_public_sheet(value)
        except Exception as exc:
            self.sheet_status.setText(
                f"Public preview unavailable: {type(exc).__name__}: {exc}. "
                "Private sheets require authorization.")
            return
        self.sheet_preview.setPlainText(
            "\n".join(" | ".join(cell[:100] for cell in row[:12]) for row in rows))
        self.sheet_status.setText(
            f"Read-only public CSV preview: {len(rows)} rows shown (up to 10). "
            "No records imported or modified.")

    def _google_id(self):
        return parse_sheet_url(self.sheet_url.text().strip())[0]

    def _google_error(self, exc):
        self.sheet_status.setText(f"Google Sheets operation failed: {type(exc).__name__}: {exc}")

    def connect_google(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "Select Google OAuth Desktop client JSON", "",
            "JSON files (*.json)")
        if not path:
            return
        try:
            sheets_api.connect(path)
        except Exception as exc:
            self._google_error(exc)
            return
        self.sheet_status.setText("Google OAuth completed. Credentials stored in OS keyring.")

    def disconnect_google(self):
        try:
            sheets_api.disconnect()
        except Exception as exc:
            self._google_error(exc)
            return
        self.sheet_tab.clear()
        self.sheet_status.setText("Local Google credentials removed. Revoke app access in Google separately.")

    def list_google_tabs(self):
        try:
            tabs = sheets_api.worksheets(self._google_id())
        except Exception as exc:
            self._google_error(exc)
            return
        self.sheet_tab.clear()
        for gid, title in tabs:
            self.sheet_tab.addItem(title, gid)
        self.sheet_status.setText(f"Authorized access: {len(tabs)} worksheets found.")

    def _selected_title(self):
        if self.sheet_tab.currentIndex() < 0:
            raise ValueError("List worksheets and select one first")
        return self.sheet_tab.currentText()

    def preview_private(self):
        try:
            rows = sheets_api.read_rows(self._google_id(), self._selected_title(), limit=20)
        except Exception as exc:
            self._google_error(exc)
            return
        self.sheet_preview.setPlainText(
            "\\n".join(" | ".join(str(cell)[:100] for cell in row[:12]) for row in rows[:10]))
        self.sheet_status.setText(f"Authorized preview: {len(rows[:10])} rows shown; no changes made.")

    def import_google_products(self):
        try:
            rows = sheets_api.read_rows(self._google_id(), self._selected_title())
            if not rows:
                raise ValueError("Worksheet is empty")
            headers = rows[0]
            if set(headers) != set(COLUMNS) or len(headers) != len(COLUMNS):
                raise ValueError("Expected exactly name, category, target_url columns")
            records = [
                dict(zip(headers, [*row, *([""] * (len(headers) - len(row)))]))
                for row in rows[1:]
            ]
            records = validate_products(records)
            existing = {r["name"].casefold() for r in self.storage.all("products")}
            if len({r["name"].casefold() for r in records}) != len(records):
                raise ValueError("Duplicate product names in worksheet")
            if any(r["name"].casefold() in existing for r in records):
                raise ValueError("Existing product name conflict; import cancelled")
        except Exception as exc:
            self._google_error(exc)
            return
        answer = QMessageBox.question(
            self, "Confirm Google Sheets import",
            f"Create {len(records)} NEW local products? Existing products are not modified.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No)
        if answer != QMessageBox.StandardButton.Yes:
            return
        try:
            from .storage import utc_now
            with self.storage.conn:
                for record in records:
                    self.storage.conn.execute(
                        "INSERT INTO products(name,category,target_url,created_at) VALUES(?,?,?,?)",
                        (record["name"], record["category"], record["target_url"], utc_now()))
            self.sheet_status.setText(f"Imported {len(records)} new products.")
            window = self.window()
            if hasattr(window, "refresh") and hasattr(window, "tables"):
                window.refresh("products")
        except Exception as exc:
            self._google_error(exc)

    def export_google(self, kind):
        try:
            spreadsheet_id = self._google_id()
            if kind == "products":
                headers = COLUMNS
                records = [{k: row.get(k, "") for k in headers}
                           for row in self.storage.all("products")]
            elif kind == "reports":
                headers = REPORT_FIELDS
                records = report_rows(self.storage, "USD")
            elif kind == "pins":
                headers = (*sheets_exchange.PIN_FIELDS, "tags", "pin_id")
                records = sheets_exchange.export_pin_rows_with_ids(self.storage)
            elif kind == "time":
                headers = sheets_exchange.TIME_FIELDS
                records = sheets_exchange.export_time_rows(self.storage)
            elif kind == "tracking":
                headers = sheets_exchange.TRACKING_FIELDS
                records = sheets_exchange.export_tracking_rows(self.storage)
            elif kind == "analytics":
                headers = sheets_exchange.METRIC_FIELDS
                records = sheets_exchange.export_metric_rows(self.storage)
            else:
                raise ValueError("Unknown export type")
            if kind == "pins":
                title = self._selected_title()
                answer = QMessageBox.question(
                    self, "Confirm append to Google Sheets",
                    f"Export missing pins to EXISTING worksheet '{title}'? "
                    "If empty, create and freeze column headers automatically. "
                    "Existing pin rows are never overwritten.",
                    QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                    QMessageBox.StandardButton.No)
                if answer != QMessageBox.StandardButton.Yes:
                    return
                added, skipped = sheets_api.append_unique_pins(
                    spreadsheet_id, title, headers, records)
                self.sheet_status.setText(
                    f"PIN export: appended {added} rows; skipped {skipped} duplicates.")
                return
            stamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
            title = f"ITHutir_{kind}_{stamp}"
        except Exception as exc:
            self._google_error(exc)
            return
        answer = QMessageBox.question(
            self, "Confirm export to Google",
            f"Create a NEW Google worksheet '{title}' with {len(records)} rows? "
            "This sends data to Google; existing worksheets are not overwritten.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No)
        if answer != QMessageBox.StandardButton.Yes:
            return
        try:
            _, count = sheets_api.create_export_tab(spreadsheet_id, title, headers, records)
            self.sheet_status.setText(f"Exported {count} rows to new worksheet '{title}'.")
            self.list_google_tabs()
        except Exception as exc:
            self._google_error(exc)

    def import_google_pins(self):
        """Import only genuinely new remote PIN IDs; never duplicate local pins."""
        headers = [*sheets_exchange.PIN_FIELDS, "tags", "pin_id"]
        try:
            rows = sheets_api.read_rows(self._google_id(), self._selected_title(),
                                        limit=10001)
            if not rows or list(rows[0]) != headers:
                raise ValueError("Expected 8 PIN columns: " + ", ".join(headers))
            if len(rows) > 10001:
                raise ValueError("Too many rows")
            local_rows = sheets_exchange.export_pin_rows_with_ids(self.storage)
            known_ids = {str(r["pin_id"]) for r in local_rows}
            known_titles = {str(r["title"]).strip().casefold() for r in local_rows}
            unseen = []
            incoming_ids = set()
            for index, raw in enumerate(rows[1:], 2):
                values = list(raw) + [""] * max(0, 8-len(raw))
                if len(values) > 8:
                    raise ValueError(f"Row {index}: too many columns")
                remote_id = str(values[7]).strip()
                if not remote_id:
                    raise ValueError(f"Row {index}: missing pin_id")
                if remote_id in incoming_ids:
                    raise ValueError(f"Row {index}: duplicate pin_id")
                incoming_ids.add(remote_id)
                if remote_id in known_ids:
                    continue
                if str(values[0]).strip().casefold() in known_titles:
                    raise ValueError(f"Row {index}: title already exists locally under another ID")
                unseen.append(values)
            if not unseen:
                self.sheet_status.setText("Import: 0 new pins; all remote IDs already exist locally.")
                return
            # Validate all rows before modifying SQLite; preserve imported tags.
            # Remote publication claims are never accepted as verified.
            for values in unseen:
                if values[3] == "PUBLISHED":
                    raise ValueError("Remote PUBLISHED status is unverified; change to DRAFT first")
            records = sheets_exchange.parse_pin_rows(
                [list(sheets_exchange.PIN_FIELDS)] + [r[:6] for r in unseen],
                self.storage)
            sheets_exchange.ensure_new_pins(self.storage, records)
        except Exception as exc:
            self._google_error(exc)
            return
        answer = QMessageBox.question(
            self, "Confirm Google Sheets pin import",
            f"Import {len(records)} NEW pins into local SQLite? "
            "Existing pins will not change. Continue?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No)
        if answer != QMessageBox.StandardButton.Yes:
            self.sheet_status.setText("Import cancelled.")
            return
        try:
            with self.storage.conn:
                previous_ids = {row["id"] for row in self.storage.all("pins")}
                count = sheets_exchange.import_pin_rows(self.storage, records)
                local_ids = sorted(
                    row["id"] for row in self.storage.all("pins")
                    if row["id"] not in previous_ids)
                if len(local_ids) != count:
                    raise RuntimeError("Imported pin ID count mismatch")
                self.storage.conn.execute(
                    "CREATE TABLE IF NOT EXISTS google_pin_export_ids "
                    "(pin_id INTEGER PRIMARY KEY, export_id TEXT NOT NULL UNIQUE)")
                for local_id, values in zip(local_ids, unseen):
                    self.storage.conn.execute(
                        "UPDATE pins SET tags=? WHERE id=?",
                        (values[6], local_id))
                    self.storage.conn.execute(
                        "INSERT INTO google_pin_export_ids(pin_id,export_id) VALUES(?,?)",
                        (local_id, values[7]))
            self.sheet_status.setText(f"Imported {count} new pins; existing pins unchanged.")
            window = self.window()
            if hasattr(window, "refresh") and hasattr(window, "tables"):
                window.refresh("pins")
        except Exception as exc:
            self._google_error(exc)

    def import_google_metrics(self):
        try:
            rows = sheets_api.read_rows(self._google_id(), self._selected_title(), limit=10001)
            records = sheets_exchange.parse_metric_rows(rows, self.storage)
        except Exception as exc:
            self._google_error(exc)
            return
        answer = QMessageBox.question(
            self, "Confirm metric import",
            f"Import {len(records)} date/pin metrics? Existing dates are never overwritten. "
            "Values are user-supplied and NOT verified with Pinterest.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No)
        if answer != QMessageBox.StandardButton.Yes:
            return
        try:
            count = sheets_exchange.import_metric_rows(self.storage, records)
            self.sheet_status.setText(f"Imported {count} new metric rows (unverified source).")
            window = self.window()
            if hasattr(window, "analytics_page"):
                window.analytics_page.refresh()
        except Exception as exc:
            self._google_error(exc)
