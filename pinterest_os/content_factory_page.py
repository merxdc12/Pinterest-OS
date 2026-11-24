"""Content Factory UI; delegates design, scheduling and publishing to existing pages."""
from __future__ import annotations

from datetime import date
import sqlite3

from PyQt6.QtCore import Qt, QThread, pyqtSignal
from PyQt6.QtGui import QPixmap
from PyQt6.QtWidgets import (
    QApplication, QCheckBox, QComboBox, QDialog, QDialogButtonBox, QFormLayout,
    QHBoxLayout, QHeaderView, QLabel, QLineEdit, QMessageBox, QPlainTextEdit,
    QPushButton, QScrollArea, QSpinBox, QTabWidget, QTableWidget, QTableWidgetItem,
    QVBoxLayout, QWidget,
)

from .content_factory import CONTENT_TYPES, SOURCE_TYPES, ContentFactory
from .content_feed import FEED_URL, fetch_feed, parse_feed


class FeedWorker(QThread):
    loaded = pyqtSignal(object)
    failed = pyqtSignal(str)

    def run(self):
        try:
            self.loaded.emit(parse_feed(fetch_feed()))
        except Exception as exc:
            self.failed.emit(str(exc))


def combo(items):
    widget = QComboBox()
    widget.addItems(items)
    return widget


def table(headers):
    widget = QTableWidget(0, len(headers))
    widget.setHorizontalHeaderLabels(headers)
    widget.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
    widget.horizontalHeader().setStretchLastSection(True)
    widget.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
    widget.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
    widget.setMinimumHeight(170)
    return widget


def fill_table(widget, rows):
    widget.setRowCount(len(rows))
    for row_index, row in enumerate(rows):
        for column, value in enumerate(row):
            item = QTableWidgetItem('—' if value is None else str(value))
            item.setToolTip(item.text())
            widget.setItem(row_index, column, item)


class ContentFactoryPage(QWidget):
    def __init__(self, storage, *, open_designer=None, open_page=None, parent=None):
        super().__init__(parent)
        self.factory = ContentFactory(storage)
        self.open_designer_callback = open_designer
        self.open_page_callback = open_page
        self.worker = None
        self.preview_hash = ''
        layout = QVBoxLayout(self)
        self.notice = QLabel('Prepare locally • Human approval required • Pinterest connection unknown')
        self.notice.setWordWrap(True)
        self.notice.setTextFormat(Qt.TextFormat.PlainText)
        layout.addWidget(self.notice)
        selectors = QHBoxLayout()
        self.campaign = QComboBox()
        self.selected_slot = QComboBox()
        selectors.addWidget(QLabel('Campaign'))
        selectors.addWidget(self.campaign, 2)
        selectors.addWidget(QLabel('Slot'))
        selectors.addWidget(self.selected_slot, 1)
        selectors.addWidget(self.button('Reload', self.reload))
        layout.addLayout(selectors)
        self.tabs = QTabWidget()
        layout.addWidget(self.tabs)
        self.build_planner()
        self.build_keywords()
        self.build_copy()
        self.build_design()
        self.build_review()
        self.build_export()
        self.campaign.currentIndexChanged.connect(self.reload_slots)
        self.selected_slot.currentIndexChanged.connect(self.load_slot)
        self.reload()

    def button(self, title, callback):
        button = QPushButton(title)
        button.setMinimumHeight(38)
        button.clicked.connect(lambda: self.action(callback))
        return button

    def action(self, callback):
        try:
            return callback()
        except (ValueError, OSError, sqlite3.Error) as exc:
            QMessageBox.warning(self, 'Content Factory', str(exc))

    def tab(self, title):
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        body = QWidget()
        layout = QVBoxLayout(body)
        scroll.setWidget(body)
        self.tabs.addTab(scroll, title)
        return layout

    def build_planner(self):
        layout = self.tab('Planner')
        form = QFormLayout()
        self.campaign_name = QLineEdit('Monthly content')
        self.month = QLineEdit(date.today().strftime('%Y-%m'))
        form.addRow('Campaign name', self.campaign_name)
        form.addRow('Month (YYYY-MM)', self.month)
        mix = QHBoxLayout()
        self.mix = []
        for title, count in zip(('Educational', 'Lead-gen', 'Product'), (6, 3, 3)):
            spin = QSpinBox()
            spin.setRange(0, 12)
            spin.setValue(count)
            mix.addWidget(QLabel(title))
            mix.addWidget(spin)
            self.mix.append(spin)
        form.addRow('12-slot mix', mix)
        layout.addLayout(form)
        layout.addWidget(self.button('Create / reopen 12-slot campaign', self.create_campaign))
        actions = QHBoxLayout()
        self.feed_button = self.button('Refresh ITHutir RSS (read only)', self.refresh_feed)
        actions.addWidget(self.feed_button)
        actions.addWidget(self.button('Add manual / product source', self.add_source))
        layout.addLayout(actions)
        self.feed_state = QLabel(FEED_URL + ' • Not fetched in this workspace')
        self.feed_state.setWordWrap(True)
        self.feed_state.setTextFormat(Qt.TextFormat.PlainText)
        layout.addWidget(self.feed_state)
        self.plan = table(('Slot', 'Type', 'Source', 'Board', 'Local schedule', 'Status', 'Pin'))
        self.plan.cellClicked.connect(lambda row, _: self.selected_slot.setCurrentIndex(row))
        layout.addWidget(self.plan)
        form = QFormLayout()
        self.source = QComboBox()
        self.source_info = QLabel()
        self.source_info.setWordWrap(True)
        self.source_info.setTextFormat(Qt.TextFormat.PlainText)
        self.source.currentIndexChanged.connect(self.show_source_info)
        self.board = QComboBox()
        self.kind = combo(CONTENT_TYPES)
        self.when = QLineEdit()
        form.addRow('Source', self.source)
        form.addRow('Explicit board', self.board)
        form.addRow('Content type', self.kind)
        form.addRow('Local date / time', self.when)
        layout.addLayout(form)
        layout.addWidget(self.source_info)
        layout.addWidget(self.button('Save selected slot', self.save_slot))
        layout.addWidget(self.button('Edit selected source topic / product / suggested board', self.edit_source))

    def build_keywords(self):
        layout = self.tab('Keywords')
        layout.addWidget(QLabel('Evidence for the selected slot’s source. Blank metrics mean unknown.'))
        self.keywords = table(('Phrase', 'Origin', 'Observed', 'Status', 'Volume', 'Competition', 'Evidence URL', 'Scale / period'))
        layout.addWidget(self.keywords)
        layout.addWidget(self.button('Record keyword evidence', self.add_keyword))
        layout.addStretch()

    def build_copy(self):
        layout = self.tab('AI SEO')
        info = QLabel('Manual copy works offline. Optionally copy a prompt into your chosen AI tool, then paste its JSON response. '
                      'All imported copy remains draft. No credentials are needed or stored here.')
        info.setWordWrap(True)
        layout.addWidget(info)
        row = QHBoxLayout()
        row.addWidget(self.button('Copy optional AI prompt', self.copy_prompt))
        row.addWidget(self.button('Paste AI draft JSON', self.import_ai))
        layout.addLayout(row)
        form = QFormLayout()
        self.copy_title = QLineEdit()
        self.copy_description = QPlainTextEdit()
        self.copy_description.setMaximumHeight(110)
        self.alt = QPlainTextEdit()
        self.alt.setMaximumHeight(90)
        self.disclosure = QLineEdit()
        form.addRow('Title (100 max)', self.copy_title)
        form.addRow('Description (500 max)', self.copy_description)
        form.addRow('Alt text (500 max)', self.alt)
        form.addRow('Affiliate disclosure', self.disclosure)
        layout.addLayout(form)
        layout.addWidget(self.button('Preview exported image for alt-text review', self.preview_image))
        self.preview = QLabel('No image reviewed')
        self.preview.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self.preview)
        self.image_reviewed = QCheckBox('I inspected this image and confirm the alt text describes its visible content.')
        self.image_reviewed.setEnabled(False)
        layout.addWidget(self.image_reviewed)
        layout.addWidget(self.button('Save draft copy', self.save_copy))

    def build_design(self):
        layout = self.tab('Design')
        note = QLabel('Create or reopen the selected slot’s DRAFT pin in the existing Pin Designer. '
                      'Use its templates, local images and PNG export at 1000 × 1500. '
                      'An RSS image URL is only source metadata; it is not proof of a reviewed creative.')
        note.setWordWrap(True)
        layout.addWidget(note)
        layout.addWidget(self.button('Open selected slot in Pin Designer', self.open_design))
        layout.addStretch()

    def build_review(self):
        layout = self.tab('Review')
        self.review_queue = table(('Slot', 'Status', 'Title', 'Latest decision', 'Reviewer note'))
        self.review_queue.cellClicked.connect(lambda row, _: self.selected_slot.setCurrentIndex(row))
        layout.addWidget(self.review_queue)
        self.checklist = QPlainTextEdit()
        self.checklist.setReadOnly(True)
        layout.addWidget(self.checklist)
        layout.addWidget(self.button('Run editorial checks', self.run_checks))
        self.reviewer_note = QLineEdit()
        self.reviewer_note.setPlaceholderText('Reviewer name / initials and review note (required for approval)')
        layout.addWidget(self.reviewer_note)
        actions = QHBoxLayout()
        actions.addWidget(self.button('Approve selected slot', lambda: self.review(True)))
        actions.addWidget(self.button('Request changes', lambda: self.review(False)))
        layout.addLayout(actions)
        layout.addWidget(self.button('Return unpublished export to review', self.reopen_review))

    def build_export(self):
        layout = self.tab('Export')
        note = QLabel('Approved slots become READY in PIN and Calendar. Publishing stays manual. '
                      'RSS eligibility, account connection and confirmed publication are separate facts.')
        note.setWordWrap(True)
        layout.addWidget(note)
        actions = QHBoxLayout()
        actions.addWidget(self.button('Export selected approved slot', self.export_selected))
        actions.addWidget(self.button('Export all approved slots', self.export_approved))
        layout.addLayout(actions)
        actions = QHBoxLayout()
        for title in ('CALENDAR', 'PUBLISHING', 'ANALYTICS', 'TIME'):
            actions.addWidget(self.button(title.title(), lambda name=title: self.navigate(name)))
        layout.addLayout(actions)
        self.ledger = table(('ID', 'Record', 'Source', 'Pin', 'Eligibility', 'Pinterest connection', 'Publication', 'Evidence'))
        layout.addWidget(self.ledger)
        layout.addWidget(self.button('Record published pin URL for selected ledger row', self.confirm_publication))
        self.metrics = QPlainTextEdit()
        self.metrics.setReadOnly(True)
        layout.addWidget(self.metrics)

    def set_storage(self, storage):
        self.factory = ContentFactory(storage)
        self.reload()

    def reload(self):
        current = self.campaign.currentData()
        self.campaign.blockSignals(True)
        self.campaign.clear()
        for row in self.factory.rows('SELECT * FROM content_campaigns ORDER BY month DESC,id DESC'):
            self.campaign.addItem(f"{row['month']} · {row['name']}", row['id'])
        index = self.campaign.findData(current)
        if index >= 0:
            self.campaign.setCurrentIndex(index)
        self.campaign.blockSignals(False)
        self.reload_slots()
        states = self.factory.rows('SELECT * FROM content_feed_refresh WHERE feed_url=?', (FEED_URL,))
        self.feed_state.setText((f"{states[0]['status']} · Last attempt {states[0]['attempted_at']} · "
                                 f"Last success {states[0]['succeeded_at'] or 'never'} · {states[0]['message']}")
                                if states else FEED_URL + ' · Not fetched in this workspace')

    def reload_slots(self, *_):
        old = self.selected_slot.currentData()
        self.selected_slot.blockSignals(True)
        self.selected_slot.clear()
        slots = self.factory.slots(self.campaign.currentData())
        for slot in slots:
            self.selected_slot.addItem(f"{slot['slot_index']:02} · {slot['status']}", slot['id'])
        index = self.selected_slot.findData(old)
        if index >= 0:
            self.selected_slot.setCurrentIndex(index)
        self.selected_slot.blockSignals(False)
        sources = {s['id']: s['title'] for s in self.factory.sources()}
        boards = {b['id']: b['name'] for b in self.factory.storage.all('boards')}
        fill_table(self.plan, [(s['slot_index'], s['content_type'], sources.get(s['source_id'], 'Unassigned'),
                               boards.get(s['board_id'], 'Unassigned'), s['scheduled_at'], s['status'], s['pin_id']) for s in slots])
        review_rows = []
        for slot in slots:
            reviews = self.factory.rows('SELECT decision,reviewer_note FROM content_reviews WHERE slot_id=? ORDER BY id DESC LIMIT 1', (slot['id'],))
            copy = self.factory.copy(slot['id']) or {}
            review_rows.append((slot['slot_index'], slot['status'], copy.get('title'),
                                reviews[0]['decision'] if reviews else None, reviews[0]['reviewer_note'] if reviews else None))
        fill_table(self.review_queue, review_rows)
        entries = self.factory.rows('SELECT * FROM rss_publication_ledger ORDER BY id DESC')
        fill_table(self.ledger, [(e['id'], 'Article' if e['entry_kind'] == 'SOURCE' else 'Creative', sources.get(e['source_id']), e['local_pin_id'], e['eligibility_state'],
                                 e['pinterest_connection_state'], e['remote_publication_state'], e['evidence_ref']) for e in entries])
        metrics = self.factory.campaign_metrics(self.campaign.currentData())
        show = lambda value: 'Unknown' if value is None else str(value)
        lines = [f"Linked pins: {len(metrics['pin_ids'])} · Outbound clicks: {show(metrics['outbound_clicks'])} · Tracked seconds: {show(metrics['time_seconds'])}"]
        for currency, values in metrics['currencies'].items():
            lines.append(currency + ': ' + ' · '.join(f"{key.replace('_', ' ')}: {show(value)}" for key, value in values.items()))
        lines.append(metrics['attribution'])
        self.metrics.setPlainText('\n'.join(lines))
        self.load_slot()

    def slot_id(self):
        value = self.selected_slot.currentData()
        if value is None:
            raise ValueError('Create or select a campaign and slot first.')
        return value

    def load_slot(self, *_):
        self.preview_hash = ''
        self.preview.setText('No image reviewed')
        self.image_reviewed.setChecked(False)
        self.image_reviewed.setEnabled(False)
        self.checklist.clear()
        self.reviewer_note.clear()
        self.source.clear()
        self.source.addItem('Select source', None)
        for source in self.factory.sources():
            self.source.addItem(f"{source['source_type']} · {source['title']}", source['id'])
        self.board.clear()
        self.board.addItem('Unassigned', None)
        for board in self.factory.storage.all('boards'):
            self.board.addItem(board['name'], board['id'])
        sid = self.selected_slot.currentData()
        slot = self.factory.slot(sid) if sid else {}
        self.source.setCurrentIndex(max(0, self.source.findData(slot.get('source_id'))))
        self.board.setCurrentIndex(max(0, self.board.findData(slot.get('board_id'))))
        self.kind.setCurrentText(slot.get('content_type', CONTENT_TYPES[0]))
        self.when.setText(slot.get('scheduled_at', ''))
        copy = self.factory.copy(sid) if sid else None
        copy = copy or {}
        self.copy_title.setText(copy.get('title', ''))
        self.copy_description.setPlainText(copy.get('description', ''))
        self.alt.setPlainText(copy.get('alt_text', ''))
        self.disclosure.setText(copy.get('disclosure', ''))
        evidence = self.factory.rows('SELECT * FROM keyword_evidence WHERE source_id=? ORDER BY id DESC', (slot.get('source_id'),))
        fill_table(self.keywords, [(e['phrase'], e['evidence_source'], e['observed_at'], e['verification_status'],
                                   e['search_volume'], e['competition'], e['evidence_url'], e['metric_definition']) for e in evidence])

    def create_campaign(self):
        cid = self.factory.create_campaign(self.campaign_name.text(), self.month.text(), tuple(s.value() for s in self.mix))
        self.reload()
        self.campaign.setCurrentIndex(self.campaign.findData(cid))

    def save_slot(self):
        self.factory.edit_slot(self.slot_id(), source_id=self.source.currentData(), board_id=self.board.currentData(),
                               content_type=self.kind.currentText(), scheduled_at=self.when.text())
        self.reload_slots()

    def show_source_info(self, *_):
        sid = self.source.currentData()
        if sid is None:
            self.source_info.setText('Select a source. RSS image metadata does not replace a reviewed local creative.')
            return
        source = self.factory.source(sid)
        self.source_info.setText(f"Destination: {source['canonical_url']}\nTopic: {source['topic'] or 'Unassigned'}\n"
                                 f"Source image URL: {source['image_url'] or 'Missing — choose an image in Designer'}")

    def dialog(self, title, fields):
        dialog = QDialog(self)
        dialog.setWindowTitle(title)
        dialog.resize(660, 400)
        form = QFormLayout(dialog)
        for label, widget in fields:
            form.addRow(label, widget)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(dialog.accept)
        buttons.rejected.connect(dialog.reject)
        form.addRow(buttons)
        return dialog.exec() == QDialog.DialogCode.Accepted

    def add_source(self):
        kind, title, url, topic, summary = combo(SOURCE_TYPES[1:]), QLineEdit(), QLineEdit(), QLineEdit(), QPlainTextEdit()
        product, board = QComboBox(), QComboBox()
        for control, table_name in ((product, 'products'), (board, 'boards')):
            control.addItem('Unassigned', None)
            for row in self.factory.storage.all(table_name):
                control.addItem(row['name'], row['id'])
        if self.dialog('Add content source', [('Type', kind), ('Title', title), ('Destination URL', url),
                                            ('Topic', topic), ('Summary', summary), ('Product', product), ('Suggested board', board)]):
            self.factory.add_source(kind.currentText(), url.text(), title.text(), topic=topic.text(), summary=summary.toPlainText(),
                                    board_id=board.currentData(), product_id=product.currentData())
            self.reload()

    def add_keyword(self):
        source_id = self.factory.slot(self.slot_id())['source_id']
        self.factory.source(source_id)
        phrase, origin, url = QLineEdit(), QLineEdit(), QLineEdit()
        observed, status = QLineEdit(date.today().isoformat()), combo(('UNVERIFIED', 'VERIFIED'))
        volume, competition, definition = QLineEdit(), QLineEdit(), QLineEdit()
        volume.setPlaceholderText('Leave blank if unknown')
        competition.setPlaceholderText('Leave blank if unknown')
        if self.dialog('Keyword evidence', [('Phrase', phrase), ('Origin / provider', origin), ('Evidence URL', url),
                                           ('Observed (YYYY-MM-DD)', observed), ('Status', status), ('Verified volume', volume),
                                           ('Verified competition', competition), ('Metric scale / period', definition)]):
            self.factory.add_keyword(source_id, phrase.text(), origin.text(), observed.text(), evidence_url=url.text(), status=status.currentText(),
                                     search_volume=int(volume.text()) if volume.text().strip() else None,
                                     competition=float(competition.text()) if competition.text().strip() else None, metric_definition=definition.text())
            self.load_slot()

    def edit_source(self):
        source = self.factory.source(self.source.currentData())
        topic, product, board = QLineEdit(source['topic']), QComboBox(), QComboBox()
        for control, table_name, field in ((product, 'products', 'product_id'), (board, 'boards', 'board_id')):
            control.addItem('Unassigned', None)
            for row in self.factory.storage.all(table_name):
                control.addItem(row['name'], row['id'])
            control.setCurrentIndex(max(0, control.findData(source[field])))
        if self.dialog('Source metadata', [('Topic', topic), ('Product', product), ('Suggested board', board)]):
            self.factory.update_source_metadata(source['id'], topic=topic.text(), board_id=board.currentData(), product_id=product.currentData())
            self.reload()

    def refresh_feed(self):
        if self.worker and self.worker.isRunning():
            return
        self.feed_button.setEnabled(False)
        self.feed_state.setText('Fetching the public ITHutir RSS feed…')
        factory = self.factory
        self.worker = FeedWorker(self)
        self.worker.loaded.connect(lambda items: self.action(lambda: self.feed_loaded(factory, items)))
        self.worker.failed.connect(lambda message: self.feed_failed(factory, message))
        self.worker.finished.connect(lambda: self.feed_button.setEnabled(True))
        self.worker.start()

    def feed_loaded(self, factory, items):
        if factory is self.factory:
            self.notice.setText(factory.import_feed(items))
            self.reload()

    def feed_failed(self, factory, message):
        if factory is self.factory:
            factory.record_feed_error(message)
            self.reload()

    def copy_prompt(self):
        QApplication.clipboard().setText(self.factory.seo_prompt(self.slot_id()))
        self.notice.setText('Prompt copied. Attach your exported image in the AI tool if requesting image-grounded alt text.')

    def import_ai(self):
        response = QPlainTextEdit()
        if self.dialog('Paste optional AI draft', [('JSON response', response)]):
            self.factory.import_ai_copy(self.slot_id(), response.toPlainText())
            self.reload_slots()

    def preview_image(self):
        sid = self.slot_id()
        self.preview_hash = self.factory.image_hash(sid)
        pixmap = QPixmap(str(self.factory.image_path(sid)))
        self.preview.setPixmap(pixmap.scaled(260, 390, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation))
        self.image_reviewed.setEnabled(True)
        self.image_reviewed.setChecked(False)

    def save_copy(self):
        self.factory.save_copy(self.slot_id(), self.copy_title.text(), self.copy_description.toPlainText(), self.alt.toPlainText(),
                               disclosure=self.disclosure.text(), image_review_hash=self.preview_hash if self.image_reviewed.isChecked() else '')
        self.reload_slots()
        self.notice.setText('Copy saved as draft. Editorial approval is still required.')

    def open_design(self):
        if not self.open_designer_callback:
            raise ValueError('Open Content Factory from the main workspace to use Pin Designer.')
        pid = self.factory.ensure_design_pin(self.slot_id())
        self.open_designer_callback(pid)
        self.reload_slots()

    def navigate(self, name):
        if self.open_page_callback:
            self.open_page_callback(name)

    def run_checks(self):
        problems, _ = self.factory.checks(self.slot_id())
        self.checklist.setPlainText('\n'.join('• ' + p for p in problems) if problems else 'Checks passed. Human approval is still required.')

    def review(self, approve):
        self.factory.review(self.slot_id(), approve=approve, note=self.reviewer_note.text())
        self.reload_slots()
        self.run_checks()

    def export_selected(self):
        pid = self.factory.export_slot(self.slot_id())
        self.reload_slots()
        self.notice.setText(f'Pin #{pid} is READY in PIN and Calendar. No publication has occurred.')

    def reopen_review(self):
        self.factory.reopen_review(self.slot_id())
        self.reload_slots()
        self.notice.setText('Slot returned to draft. Pending calendar entries were cancelled locally; review and export again when ready.')

    def export_approved(self):
        exported, failures = 0, []
        for slot in self.factory.slots(self.campaign.currentData()):
            if slot['status'] == 'APPROVED':
                try:
                    self.factory.export_slot(slot['id'])
                    exported += 1
                except (ValueError, OSError, sqlite3.Error) as exc:
                    failures.append(f"Slot {slot['slot_index']}: {exc}")
        self.reload_slots()
        self.notice.setText(f'{exported} slots exported locally. ' + ' '.join(failures))

    def confirm_publication(self):
        row = self.ledger.currentRow()
        if row < 0:
            raise ValueError('Select a ledger row first.')
        evidence = QLineEdit()
        if self.dialog('Record human-confirmed publication evidence', [('Published Pinterest pin URL', evidence)]):
            self.factory.confirm_publication(int(self.ledger.item(row, 0).text()), evidence.text())
            self.reload_slots()
