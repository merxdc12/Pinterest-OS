"""ITHutir layered pin editor: editable Qt scene, templates and linked exports."""
from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path
import re
import unicodedata
import webbrowser
from urllib.parse import quote, urlsplit
from .canva_bridge import project_to_svg, validate_canva_design_id
from .sheets_exchange import export_pin_rows_with_ids

from PyQt6.QtCore import Qt, QRectF, QTimer, QSettings, pyqtSignal
from PyQt6.QtGui import QShortcut, QKeySequence, QColor, QFont, QImage, QPainter, QPixmap, QPen
from PyQt6.QtWidgets import (
    QComboBox, QColorDialog, QFileDialog, QFontComboBox, QFormLayout,
    QGraphicsItem, QGraphicsPixmapItem, QGraphicsRectItem, QGraphicsScene,
    QGraphicsTextItem, QGraphicsView, QHBoxLayout, QLabel, QLineEdit,
    QMessageBox, QPushButton, QSpinBox, QVBoxLayout, QWidget, QListWidget,
    QScrollArea, QSplitter, QSizePolicy, QInputDialog, QCheckBox,
)

WIDTH, HEIGHT = 1000, 1500
TEMPLATES = {
    "ITHutir Dark": {"background": "#0B1110", "foreground": "#43E58A"},
    "ITHutir Light": {"background": "#F3F8F4", "foreground": "#147D45"},
    "Minimal Black": {"background": "#000000", "foreground": "#FFFFFF"},
}


class LayerText(QGraphicsTextItem):
    def __init__(self, text, x, y, size, color, width=820, font="DejaVu Sans", align="center"):
        super().__init__(text)
        self.setTextWidth(width)
        self.setPos(x, y)
        self.setFont(QFont(font, size, QFont.Weight.Bold))
        self.setDefaultTextColor(QColor(color))
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsMovable, True)
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsSelectable, True)
        self.setTextInteractionFlags(Qt.TextInteractionFlag.NoTextInteraction)
        self.set_alignment(align)

    def set_alignment(self, value):
        option = self.document().defaultTextOption()
        option.setAlignment({"left": Qt.AlignmentFlag.AlignLeft,
                             "center": Qt.AlignmentFlag.AlignCenter,
                             "right": Qt.AlignmentFlag.AlignRight}[value])
        self.document().setDefaultTextOption(option)
        self.align_value = value

    def to_dict(self):
        return {"kind": "text", "text": self.toPlainText(), "x": self.x(), "y": self.y(),
                "size": self.font().pointSize(), "font": self.font().family(),
                "color": self.defaultTextColor().name(), "width": self.textWidth(),
                "align": self.align_value, "bold": self.font().bold(),
                "z": self.zValue()}


class LayerImage(QGraphicsPixmapItem):
    def __init__(self, path, x=0, y=0, width=1000, height=1500):
        pix = QPixmap(path)
        if pix.isNull():
            raise ValueError(f"Cannot load image: {path}")
        super().__init__(pix.scaled(int(width), int(height),
                                    Qt.AspectRatioMode.IgnoreAspectRatio,
                                    Qt.TransformationMode.SmoothTransformation))
        self.source_path = str(Path(path).resolve())
        self.setPos(x, y)
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsMovable, True)
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsSelectable, True)

    def to_dict(self):
        return {"kind": "image", "path": self.source_path, "x": self.x(), "y": self.y(),
                "width": self.pixmap().width(), "height": self.pixmap().height(),
                "z": self.zValue()}


class PinDesigner(QWidget):
    pin_saved = pyqtSignal(int)
    pin_deleted = pyqtSignal(int)
    plan_requested = pyqtSignal(int)

    def __init__(self, storage=None, parent=None):
        super().__init__(parent)
        self.storage = storage
        self.background = "#0B1110"
        self.dirty = False
        self._loading = False
        self._saved_snapshot = None
        self._canvas_pin_id = None
        self._blank_draft = False
        self._resume_settings = QSettings("ITHutir", "PinterestOS")
        self._resume_key = ("editor/last_pin/" + str(storage.path.resolve())
                            if storage else None)
        self.scene = QGraphicsScene(0, 0, WIDTH, HEIGHT, self)
        self.scene.setSceneRect(0, 0, WIDTH, HEIGHT)
        self.scene.selectionChanged.connect(self.update_selection)
        self.scene.changed.connect(self.schedule_dirty_check)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(6, 6, 6, 6)
        splitter = QSplitter(Qt.Orientation.Horizontal, self)
        splitter.setChildrenCollapsible(False)
        layout.addWidget(splitter)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.setMinimumWidth(310)
        # Allow the metadata editor to occupy up to half of the workspace.
        # The splitter handle remains draggable for manual adjustment.
        left = QWidget()
        left.setMinimumWidth(290)
        form = QFormLayout(left)
        form.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.ExpandingFieldsGrow)
        form.setRowWrapPolicy(QFormLayout.RowWrapPolicy.WrapLongRows)
        form.setSpacing(9)
        form.setContentsMargins(10, 10, 10, 10)
        self.pin = QComboBox()
        self.new_pin_button = QPushButton("Create new pin")
        self.new_pin_button.setObjectName("Primary")
        self.new_pin_button.clicked.connect(self.start_new_pin)
        self.save_button = QPushButton("ЗБЕРЕГТИ ПІН (Ctrl+S)")
        self.save_button.setObjectName("Primary")
        self.save_button.clicked.connect(self.save_pin_simple)
        pin_save_row = QHBoxLayout()
        pin_save_row.addWidget(self.new_pin_button, 1)
        pin_save_row.addWidget(self.save_button, 1)
        form.addRow("Пов'язаний пін", self.pin)
        form.addRow(pin_save_row)
        self.plan_button=QPushButton("ДОДАТИ В КОНТЕНТ-ПЛАН")
        self.plan_button.setToolTip("Планує збережений пін на конкретну дошку, дату та час.")
        self.plan_button.clicked.connect(self.request_plan)
        form.addRow(self.plan_button)
        self.export_pin_id = QLineEdit()
        self.export_pin_id.setReadOnly(True)
        form.addRow("PIN ID (image + Sheets)", self.export_pin_id)
        self.pin_title = QLineEdit()
        self.pin_title.setPlaceholderText("SEO title for Pinterest")
        form.addRow("Pin title / Заголовок", self.pin_title)
        self.pin_description = QLineEdit()
        self.pin_description.setPlaceholderText("Pin description / Опис")
        form.addRow("Description / Опис", self.pin_description)
        self.pin_tags = QLineEdit()
        self.pin_tags.setPlaceholderText("keywords, separated, by commas")
        form.addRow("Tags / Теги", self.pin_tags)
        self.destination_url = QLineEdit()
        self.destination_url.setPlaceholderText("https://ithutir.com/relevant-page")
        form.addRow("Destination URL", self.destination_url)
        url_help = (
            "Вставте повну URL-адресу (https:// або http://) сторінки товару, "
            "статті, калькулятора чи іншої цільової сторінки. "
            "Саме на цю сторінку має переходити користувач із Pinterest. "
            "Посилання може містити UTM-мітки. "
            "Щоб зберегти адресу, натисніть «ЗБЕРЕГТИ ПІН» (Ctrl+S)."
        )
        self.destination_url.setToolTip(url_help)
        form.labelForField(self.destination_url).setToolTip(url_help)
        self.pin_board = QComboBox()
        form.addRow("Дошка / Board", self.pin_board)
        new_board = QPushButton("+ Створити дошку в каталозі")
        new_board.clicked.connect(self.create_board_for_pin)
        form.addRow(new_board)
        self.pin_status = QComboBox()
        self.pin_status.addItems(["DRAFT", "IN_REVIEW", "READY", "PUBLISHED"])
        form.addRow("Статус / Status (ручний)", self.pin_status)
        self.pin_product = QComboBox()
        form.addRow("Продукт / Product (необов'язково)", self.pin_product)
        new_product = QPushButton("+ Створити продукт у каталозі")
        new_product.clicked.connect(self.create_product_for_pin)
        form.addRow(new_product)
        self.reload_metadata_choices()
        # Metadata is committed with the design via Save pin / Ctrl+S.
        create_pin = QPushButton("Create new pin for this design")
        create_pin.clicked.connect(lambda: self.create_pin_for_design(prompt_title=True))
        form.addRow(create_pin)
        self.reload_pins()
        self.pin.currentIndexChanged.connect(self.on_pin_changed)
        self.on_pin_changed(self.pin.currentIndex())
        QTimer.singleShot(0, self.restore_last_pin)
        load = QPushButton("Load pin project")
        load.clicked.connect(self.load_pin)
        form.addRow(load)
        self.template = QComboBox()
        self.template.addItems(TEMPLATES)
        form.addRow("Template", self.template)
        apply_template = QPushButton("Apply template")
        apply_template.clicked.connect(self.apply_template)
        form.addRow(apply_template)
        add_text = QPushButton("+ Text layer")
        add_text.clicked.connect(self.add_text)
        form.addRow(add_text)
        add_image = QPushButton("IMPORT Image")
        add_image.clicked.connect(self.add_image)
        form.addRow(add_image)
        self.text = QLineEdit()
        self.text.editingFinished.connect(self.change_text)
        form.addRow("Selected text", self.text)
        self.font = QFontComboBox()
        self.font.currentFontChanged.connect(self.change_font)
        form.addRow("Font", self.font)
        self.bold_font = QCheckBox("ЖИРНИЙ / Bold")
        self.bold_font.setChecked(True)
        self.bold_font.toggled.connect(self.change_bold)
        form.addRow("Накреслення", self.bold_font)
        self.size = QSpinBox()
        self.size.setRange(8, 240)
        self.size.setValue(48)
        self.size.valueChanged.connect(self.change_size)
        form.addRow("Font size", self.size)
        self.alignment = QComboBox()
        self.alignment.addItems(("left", "center", "right"))
        self.alignment.currentTextChanged.connect(self.change_alignment)
        form.addRow("Alignment", self.alignment)
        color = QPushButton("Text color")
        color.clicked.connect(self.change_color)
        form.addRow(color)
        raise_button = QPushButton("Bring forward")
        raise_button.clicked.connect(lambda: self.shift_layer(1))
        form.addRow(raise_button)
        lower_button = QPushButton("Send backward")
        lower_button.clicked.connect(lambda: self.shift_layer(-1))
        form.addRow(lower_button)
        remove = QPushButton("Delete selected layer")
        remove.clicked.connect(self.delete_selected)
        form.addRow(remove)
        self.layers_list = QListWidget()
        self.layers_list.setMaximumHeight(130)
        self.layers_list.currentRowChanged.connect(self.select_layer_row)
        form.addRow("Layers (top first)", self.layers_list)
        self.x_position = QSpinBox()
        self.x_position.setRange(-5000, 5000)
        self.x_position.valueChanged.connect(lambda value: self.set_position("x", value))
        form.addRow("X position", self.x_position)
        self.y_position = QSpinBox()
        self.y_position.setRange(-5000, 5000)
        self.y_position.valueChanged.connect(lambda value: self.set_position("y", value))
        form.addRow("Y position", self.y_position)
        image_tools = QHBoxLayout()
        for caption, mode in (("Fit", "fit"), ("Fill", "fill"), ("Stretch", "stretch")):
            button = QPushButton(caption)
            button.clicked.connect(lambda _checked=False, m=mode: self.resize_selected_image(m))
            image_tools.addWidget(button)
        form.addRow("Image size", image_tools)
        self.zoom = QSpinBox()
        self.zoom.setRange(10, 300)
        self.zoom.setSuffix("%")
        self.zoom.setValue(100)
        self.zoom.valueChanged.connect(self.set_zoom)
        form.addRow("Zoom", self.zoom)
        preview = QPushButton("Preview at canvas size")
        preview.clicked.connect(self.preview)
        form.addRow(preview)
        self.dirty_label = QLabel("Saved / no pending changes")
        form.addRow(self.dirty_label)
        self.save_shortcut = QShortcut(QKeySequence("Ctrl+S"), self)
        self.save_shortcut.activated.connect(self.save_pin_simple)
        export = QPushButton("Export PNG + link to pin")
        export.setObjectName("Primary")
        export.clicked.connect(self.export_png)
        form.addRow(export)
        open_pin_folder = QPushButton("ВІДКРИТИ КАТАЛОГ PINTEREST_PIN")
        open_pin_folder.clicked.connect(self.open_pin_directory)
        form.addRow(open_pin_folder)
        self.canva_id = QLineEdit()
        self.canva_id.setPlaceholderText("Canva design ID (D...)")
        delete_pin_button = QPushButton("ВИДАЛИТИ ПІН")
        delete_pin_button.setObjectName("Danger")
        delete_pin_button.setStyleSheet("QPushButton { color: #DC2626; font-weight: 800; } QPushButton:disabled { color: #991B1B; }")
        delete_pin_button.clicked.connect(self.delete_current_pin)
        form.addRow(delete_pin_button)
        scroll.setWidget(left)
        splitter.addWidget(scroll)
        self.view = QGraphicsView(self.scene)
        self.view.setRenderHint(QPainter.RenderHint.Antialiasing)
        self.view.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        self.view.setMinimumWidth(250)
        self.view.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        splitter.addWidget(self.view)
        splitter.setStretchFactor(0, 1)
        splitter.setStretchFactor(1, 1)
        splitter.setSizes([600, 600])
        self.controls_scroll = scroll
        self.editor_splitter = splitter
        self.reset_scene()
        self.apply_template()
        self._canvas_pin_id = self.pin.currentData()
        self._saved_snapshot = self.snapshot()
        self.dirty = False
        self.dirty_label.setText("Saved / no pending changes")
        self._dirty_timer = QTimer(self)
        self._dirty_timer.setSingleShot(True)
        self._dirty_timer.timeout.connect(self.check_dirty)

    def request_plan(self):
        pid=self.pin.currentData()
        if pid is None or self._canvas_pin_id!=pid:
            QMessageBox.warning(self,"Контент-план","Спочатку створіть, збережіть або завантажте пін.")
            return
        self.check_dirty()
        if self.dirty or self.metadata_snapshot()!=self._metadata_snapshot:
            QMessageBox.warning(self,"Контент-план","Спочатку збережіть зміни піна.")
            return
        self.plan_requested.emit(int(pid))

    def metadata_snapshot(self):
        return (self.pin_title.text(), self.pin_description.text(),
                self.pin_tags.text(), self.destination_url.text(),
                self.pin_board.currentData(), self.pin_product.currentData(),
                self.pin_status.currentText())

    def start_new_pin(self):
        """Start an empty, unlinked draft without changing saved pins or files."""
        if self.storage is None:
            QMessageBox.warning(self, "No project", "Open a Pinterest OS project first.")
            return
        self._dirty_timer.stop()
        self.check_dirty()
        if self.dirty or self.metadata_snapshot() != self._metadata_snapshot:
            answer = QMessageBox.question(
                self, "Незбережені зміни",
                "Почати новий пін і відкинути незбережені зміни поточного? "
                "Збережений пін залишиться в бібліотеці.",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No)
            if answer != QMessageBox.StandardButton.Yes:
                return
        self._loading = True
        try:
            self._blank_draft = True
            self._canvas_pin_id = None
            self.pin.setCurrentIndex(-1)
            self.on_pin_changed(-1)
            self.canva_id.clear()
            self.template.setCurrentIndex(0)
            self.background = TEMPLATES["ITHutir Dark"]["background"]
            self.reset_scene()
            self.refresh_layers()
            self.text.clear()
            self.font.setCurrentFont(QFont("DejaVu Sans"))
            self.bold_font.setChecked(True)
            self.size.setValue(48)
            self.alignment.setCurrentText("center")
            self.x_position.setValue(0)
            self.y_position.setValue(0)
            self.zoom.setValue(100)
            self.fit()
            if self._resume_key:
                self._resume_settings.remove(self._resume_key)
                self._resume_settings.sync()
            self._saved_snapshot = self.snapshot()
            self._metadata_snapshot = self.metadata_snapshot()
            self.dirty = False
            self.dirty_label.setText("New pin — not saved")
            self.pin_title.setFocus()
        finally:
            self._loading = False

    def snapshot(self):
        return json.dumps(self.project(), ensure_ascii=False, sort_keys=True)

    def schedule_dirty_check(self, *_args):
        if not self._loading and hasattr(self, "_dirty_timer"):
            self._dirty_timer.start(75)

    def check_dirty(self):
        if not self._loading and self._saved_snapshot is not None:
            self.dirty = self.snapshot() != self._saved_snapshot
            self.dirty_label.setText("Unsaved changes" if self.dirty else
                                     "New pin — not saved" if self._blank_draft else
                                     "Saved / no pending changes")

    def mark_dirty(self, *_args):
        if not self._loading and hasattr(self, "dirty_label"):
            self.dirty = True
            self.dirty_label.setText("Unsaved changes")

    def confirm_discard(self, include_metadata=True) -> bool:
        if hasattr(self, "_dirty_timer"):
            self._dirty_timer.stop()
            self.check_dirty()
        metadata_dirty = (include_metadata and self._blank_draft
                          and self.metadata_snapshot() != self._metadata_snapshot)
        if not self.dirty and not metadata_dirty:
            return True
        return QMessageBox.question(
            self, "Unsaved design", "Discard unsaved design or draft changes?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No) == QMessageBox.StandardButton.Yes

    def delete_current_pin(self):
        """Explicitly delete the selected local pin, never its exported PNG."""
        pin_id = self.pin.currentData()
        if not self.storage or pin_id is None:
            QMessageBox.information(self, "Видалення піна", "Спочатку виберіть пін.")
            return
        record = self.storage.get("pins", pin_id)
        if not record:
            return
        answer = QMessageBox.question(
            self, "Підтвердження видалення",
            f"Видалити пін #{pin_id}: {record['title']}?\n\n"
            "Його локальний дизайн і записи календаря також буде видалено.\n"
            "Експортовані PNG-файли та Google Таблиця НЕ зміняться.\n"
            "Цю дію неможливо скасувати.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No)
        if answer != QMessageBox.StandardButton.Yes:
            return
        try:
            if not self.storage.delete_pin(int(pin_id)):
                return
            if self._canvas_pin_id == pin_id:
                self._loading = True
                self._canvas_pin_id = None
                self.reset_scene()
                self._loading = False
                self._saved_snapshot = self.snapshot()
                self.dirty = False
                self.dirty_label.setText("Пін видалено. Виберіть інший або створіть новий.")
            self.pin.blockSignals(True)
            self.reload_pins()
            self.pin.blockSignals(False)
            self.on_pin_changed(self.pin.currentIndex())
            self.pin_deleted.emit(int(pin_id))
            QMessageBox.information(self, "Пін видалено", "Локальний пін видалено.")
        except Exception as exc:
            QMessageBox.warning(self, "Помилка видалення", str(exc))

    def reload_metadata_choices(self):
        for widget, table, empty in (
            (self.pin_board, "boards", "— Без дошки —"),
            (self.pin_product, "products", "— Без продукту —"),
        ):
            old = widget.currentData()
            widget.blockSignals(True)
            widget.clear()
            widget.addItem(empty, None)
            if self.storage:
                for record in self.storage.all(table):
                    widget.addItem(record["name"], record["id"])
            index = widget.findData(old)
            widget.setCurrentIndex(index if index >= 0 else 0)
            widget.blockSignals(False)

    def create_board_for_pin(self):
        if not self.storage:
            return
        name, ok = QInputDialog.getText(self, "Нова дошка", "Назва дошки:")
        if ok and name.strip():
            try:
                board_id = self.storage.create("boards", name=name.strip())
                self.reload_metadata_choices()
                self.pin_board.setCurrentIndex(self.pin_board.findData(board_id))
            except Exception as exc:
                QMessageBox.warning(self, "Помилка створення дошки", str(exc))

    def create_product_for_pin(self):
        if not self.storage:
            return
        name, ok = QInputDialog.getText(self, "Новий продукт", "Назва продукту:")
        if ok and name.strip():
            try:
                product_id = self.storage.create("products", name=name.strip())
                self.reload_metadata_choices()
                self.pin_product.setCurrentIndex(self.pin_product.findData(product_id))
            except Exception as exc:
                QMessageBox.warning(self, "Помилка створення продукту", str(exc))

    def get_export_pin_id(self, pin_id):
        if not self.storage or pin_id is None:
            return ""
        rows = export_pin_rows_with_ids(self.storage)
        pins = self.storage.all("pins")
        return next((str(row["pin_id"]) for pin, row in zip(pins, rows)
                     if pin["id"] == pin_id), "")

    def save_destination_url(self):
        """Validate and save the full metadata as one logical operation."""
        pin_id = self.pin.currentData()
        if not self.storage or pin_id is None:
            return False
        title = self.pin_title.text().strip()
        description = self.pin_description.text().strip()
        tags = self.pin_tags.text().strip()
        url = self.destination_url.text().strip()
        if not self.validate_metadata(title, description, tags, url):
            return False
        self.storage.update(
            "pins", pin_id, title=title, description=description,
            tags=tags, destination_url=url, board_id=self.pin_board.currentData(),
            product_id=self.pin_product.currentData(),
            status=self.pin_status.currentText())
        self._metadata_snapshot = self.metadata_snapshot()
        return True

    def validate_metadata(self, title, description, tags, url):
        if not title or len(title) > 300:
            QMessageBox.warning(self, "Pin title", "Enter a title (max 300 characters).")
            return False
        if len(description) > 5000 or len(tags) > 2000:
            QMessageBox.warning(self, "Metadata too long", "Shorten description or tags.")
            return False
        if url:
            parsed = urlsplit(url)
            if parsed.scheme not in ("http", "https") or not parsed.netloc or len(url) > 4096:
                QMessageBox.warning(self, "Invalid URL", "Enter a complete http:// or https:// destination URL.")
                return False
        return True

    def remember_current_pin(self):
        if self._resume_key and self._canvas_pin_id is not None:
            self._resume_settings.setValue(self._resume_key, int(self._canvas_pin_id))
            self._resume_settings.sync()

    def restore_last_pin(self):
        if not self._resume_key or not self.storage:
            return
        pin_id = self._resume_settings.value(self._resume_key, None)
        if pin_id is None:
            return
        try:
            pin_id = int(pin_id)
        except (ValueError, TypeError):
            return
        index = self.pin.findData(pin_id)
        if index < 0 or not self.storage.get_pin_design(pin_id):
            return
        self.pin.setCurrentIndex(index)
        self.load_pin()

    def on_pin_changed(self, _index):
        pin = self.storage.get("pins", self.pin.currentData()) if self.storage and self.pin.currentData() else None
        if pin is not None and self._blank_draft:
            if not self.confirm_discard():
                blocked = self.pin.blockSignals(True)
                self.pin.setCurrentIndex(-1)
                self.pin.blockSignals(blocked)
                return
            self._blank_draft = False
        self.reload_metadata_choices()
        for widget, key in ((self.pin_board, "board_id"), (self.pin_product, "product_id")):
            index = widget.findData((pin or {}).get(key))
            widget.setCurrentIndex(index if index >= 0 else 0)
        status_index = self.pin_status.findText((pin or {}).get("status") or "DRAFT")
        self.pin_status.setCurrentIndex(status_index if status_index >= 0 else 0)
        self.export_pin_id.setText(self.get_export_pin_id(self.pin.currentData()) if pin else "")
        for widget, key in ((self.pin_title, "title"), (self.pin_description, "description"),
                            (self.pin_tags, "tags"), (self.destination_url, "destination_url")):
            widget.blockSignals(True)
            widget.setText((pin or {}).get(key) or "")
            widget.blockSignals(False)
        self._metadata_snapshot = self.metadata_snapshot()
        # Canvas remains associated with its original pin until explicitly loaded.
        if self._canvas_pin_id != self.pin.currentData() and hasattr(self, "dirty_label"):
            self.dirty_label.setText("Different pin selected — load its design before editing")

    def refresh_layers(self):
        if not hasattr(self, "layers_list"):
            return
        items = [x for x in self.scene.items() if isinstance(x, (LayerText, LayerImage))]
        self.layers_list.blockSignals(True)
        self.layers_list.clear()
        for item in items:
            name = item.toPlainText()[:35] if isinstance(item, LayerText) else Path(item.source_path).name
            self.layers_list.addItem(("Text: " if isinstance(item, LayerText) else "Image: ") + name)
            if item.isSelected():
                self.layers_list.setCurrentRow(items.index(item))
        self.layers_list.blockSignals(False)

    def select_layer_row(self, row):
        items = [x for x in self.scene.items() if isinstance(x, (LayerText, LayerImage))]
        if 0 <= row < len(items):
            self.scene.clearSelection()
            items[row].setSelected(True)

    def set_position(self, axis, value):
        item = self.selected()
        if isinstance(item, (LayerText, LayerImage)):
            if axis == "x":
                item.setX(value)
            else:
                item.setY(value)
            self.schedule_dirty_check()

    def set_zoom(self, _value):
        self.fit()

    def preview(self):
        image = self.render_image()
        from PyQt6.QtWidgets import QDialog
        dialog = QDialog(self)
        dialog.setWindowTitle(f"Pin preview — {WIDTH} × {HEIGHT}")
        dialog.resize(540, 740)
        layout = QVBoxLayout(dialog)
        display = QLabel()
        display.setAlignment(Qt.AlignmentFlag.AlignCenter)
        display.setPixmap(QPixmap.fromImage(image).scaled(
            480, 650, Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation))
        layout.addWidget(display)
        dialog.exec()

    def render_image(self):
        image = QImage(WIDTH, HEIGHT, QImage.Format.Format_ARGB32)
        image.fill(Qt.GlobalColor.transparent)
        painter = QPainter(image)
        self.scene.render(painter, QRectF(0, 0, WIDTH, HEIGHT), self.scene.sceneRect())
        painter.end()
        return image

    def reload_pins(self):
        old = self.pin.currentData()
        if self._blank_draft and old is None:
            blocked = self.pin.blockSignals(True)
            try:
                self.pin.clear()
                if self.storage:
                    for row in self.storage.all("pins"):
                        self.pin.addItem(f"#{row['id']} {row['title']}", row["id"])
                self.pin.setCurrentIndex(-1)
            finally:
                self.pin.blockSignals(blocked)
            return
        self.pin.clear()
        if self.storage:
            for row in self.storage.all("pins"):
                self.pin.addItem(f"#{row['id']} {row['title']}", row["id"])
        found = self.pin.findData(old)
        if found >= 0:
            self.pin.setCurrentIndex(found)

    def selected(self):
        return next(iter(self.scene.selectedItems()), None)

    def update_selection(self):
        item = self.selected()
        if isinstance(item, LayerText):
            highest_image = max((i.zValue() for i in self.scene.items()
                                 if isinstance(i, LayerImage)), default=-1)
            if item.zValue() <= highest_image:
                item.setZValue(max((i.zValue() for i in self.scene.items()),
                                   default=highest_image) + 1)
                self.schedule_dirty_check()
        self.refresh_layers()
        for widget, value in ((self.x_position, round(item.x()) if item else 0),
                              (self.y_position, round(item.y()) if item else 0)):
            widget.blockSignals(True)
            widget.setValue(value)
            widget.blockSignals(False)
        if not isinstance(item, LayerText):
            return
        self.text.blockSignals(True)
        self.font.blockSignals(True)
        self.size.blockSignals(True)
        self.alignment.blockSignals(True)
        self.bold_font.blockSignals(True)
        self.text.setText(item.toPlainText())
        self.font.setCurrentFont(item.font())
        self.size.setValue(item.font().pointSize())
        self.alignment.setCurrentText(item.align_value)
        self.bold_font.setChecked(item.font().bold())
        for widget in (self.text, self.font, self.size, self.alignment, self.bold_font):
            widget.blockSignals(False)

    def reset_scene(self):
        self.scene.clear()
        self.background_item = QGraphicsRectItem(0, 0, WIDTH, HEIGHT)
        self.background_item.setPen(QPen(Qt.PenStyle.NoPen))
        self.background_item.setBrush(QColor(self.background))
        self.background_item.setZValue(-10000)
        self.scene.addItem(self.background_item)

    def apply_template(self):
        template = TEMPLATES[self.template.currentText()]
        if hasattr(self, "dirty_label") and not self.confirm_discard(include_metadata=False):
            return
        self.background = template["background"]
        self._canvas_pin_id = self.pin.currentData()
        self.reset_scene()
        self.scene.addItem(LayerText("BUILD SMARTER", 90, 350, 66, template["foreground"]))
        self.scene.addItem(LayerText("ITHutir • Engineering & DIY", 90, 1070, 30, template["foreground"]))
        self.scene.addItem(LayerText("ITHUTIR", 90, 1370, 25, template["foreground"]))
        self.fit()
        self.schedule_dirty_check()

    def fit(self):
        self.view.fitInView(self.scene.sceneRect(), Qt.AspectRatioMode.KeepAspectRatio)
        self.view.scale(self.zoom.value() / 100, self.zoom.value() / 100)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        QTimer.singleShot(0, self.fit)

    def showEvent(self, event):
        super().showEvent(event)
        # QTabWidget creates the editor while hidden; fit after the tab is visible.
        QTimer.singleShot(0, self.fit)

    def add_text(self):
        item = LayerText("New text", 100, 200, 45, "#43E58A")
        item.setZValue(max((i.zValue() for i in self.scene.items()), default=0) + 1)
        self.scene.addItem(item)
        self.scene.clearSelection()
        item.setSelected(True)
        self.schedule_dirty_check()

    def search_free_images(self):
        """Open a provider's public search using the existing browser session."""
        query = self.free_image_query.text().strip()
        if not query:
            QMessageBox.warning(self, "Search images", "Enter a search phrase.")
            return
        provider = self.free_image_provider.currentText()
        urls = {
            "Unsplash": "https://unsplash.com/s/photos/",
            "Pexels": "https://www.pexels.com/search/",
            "Pixabay": "https://pixabay.com/images/search/",
        }
        base = urls.get(provider)
        if base:
            webbrowser.open(base + quote(query, safe="") + "/")

    def add_image(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "IMPORT Image", "", "Images (*.png *.jpg *.jpeg *.webp)")
        if not path:
            return
        try:
            from PyQt6.QtGui import QImageReader
            reader = QImageReader(path)
            if not reader.canRead():
                raise ValueError("Cannot decode selected image.")
            # Keep the imported layer within the 1000 x 1500 pin canvas.
            original = reader.size()
            if not original.isValid():
                raise ValueError("Invalid image dimensions.")
            target = original.scaled(WIDTH, HEIGHT, Qt.AspectRatioMode.KeepAspectRatio)
            layer = LayerImage(path, (WIDTH-target.width())//2,
                               (HEIGHT-target.height())//2,
                               target.width(), target.height())
            # Images stay behind existing text, including when imported later.
            layer.setZValue(min((i.zValue() for i in self.scene.items()
                                 if isinstance(i, LayerText)), default=1) - 1)
            self.scene.addItem(layer)
            self.scene.clearSelection()
            layer.setSelected(True)
            self.refresh_layers()
            self.mark_dirty()
            QTimer.singleShot(0, self.fit)
            QMessageBox.information(
                self, "Image imported",
                f"Imported: {Path(path).name}\n"
                f"Original: {original.width()} × {original.height()} px\n"
                f"Canvas layer: {target.width()} × {target.height()} px\n"
                "The image is selected on the canvas. Save editable project to keep it.")
        except (ValueError, OSError) as exc:
            QMessageBox.warning(self, "Image import failed", str(exc))

    def resize_selected_image(self, mode: str):
        """Resize selected image from original pixels; keep other layers intact."""
        layer = self.selected()
        if not isinstance(layer, LayerImage):
            QMessageBox.information(self, "Image size", "Select an image layer first.")
            return
        original = QPixmap(layer.source_path)
        if original.isNull():
            QMessageBox.warning(self, "Image size", "Original image file is unavailable.")
            return
        if mode == "stretch":
            resized = original.scaled(
                WIDTH, HEIGHT, Qt.AspectRatioMode.IgnoreAspectRatio,
                Qt.TransformationMode.SmoothTransformation)
        elif mode == "fit":
            resized = original.scaled(
                WIDTH, HEIGHT, Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation)
        elif mode == "fill":
            resized = original.scaled(
                WIDTH, HEIGHT, Qt.AspectRatioMode.KeepAspectRatioByExpanding,
                Qt.TransformationMode.SmoothTransformation)
            # Center-crop to pin dimensions without stretching the source.
            x = (resized.width() - WIDTH) // 2
            y = (resized.height() - HEIGHT) // 2
            resized = resized.copy(x, y, WIDTH, HEIGHT)
        else:
            raise ValueError(f"Unsupported image size mode: {mode}")
        layer.setPixmap(resized)
        layer.setPos((WIDTH - resized.width()) / 2, (HEIGHT - resized.height()) / 2)
        self.update_selection()
        self.mark_dirty()

    def change_text(self):
        item = self.selected()
        if isinstance(item, LayerText):
            item.setPlainText(self.text.text())
            self.schedule_dirty_check()

    def change_bold(self, checked):
        item = self.selected()
        if isinstance(item, LayerText):
            font = item.font()
            font.setBold(checked)
            item.setFont(font)
            self.schedule_dirty_check()

    def change_font(self, font):
        item = self.selected()
        if isinstance(item, LayerText):
            old = item.font()
            old.setFamily(font.family())
            item.setFont(old)
            self.schedule_dirty_check()

    def change_size(self, size):
        item = self.selected()
        if isinstance(item, LayerText):
            font = item.font()
            font.setPointSize(size)
            item.setFont(font)
            self.schedule_dirty_check()

    def change_alignment(self, align):
        item = self.selected()
        if isinstance(item, LayerText):
            item.set_alignment(align)
            self.schedule_dirty_check()

    def change_color(self):
        item = self.selected()
        if isinstance(item, LayerText):
            color = QColorDialog.getColor(item.defaultTextColor(), self)
            if color.isValid():
                item.setDefaultTextColor(color)
                self.schedule_dirty_check()

    def shift_layer(self, amount):
        item = self.selected()
        if item:
            item.setZValue(item.zValue() + amount)
            self.schedule_dirty_check()

    def delete_selected(self):
        item = self.selected()
        if item and item is not self.background_item:
            self.scene.removeItem(item)
            self.schedule_dirty_check()

    def project(self):
        layers = []
        for item in self.scene.items(Qt.SortOrder.AscendingOrder):
            if isinstance(item, (LayerText, LayerImage)):
                layers.append(item.to_dict())
        return {"version": 1, "width": WIDTH, "height": HEIGHT,
                "background": self.background, "layers": layers}

    def restore(self, project):
        if project.get("version") != 1 or project.get("width") != WIDTH or project.get("height") != HEIGHT:
            raise ValueError("Unsupported project format")
        layers = project.get("layers")
        if not isinstance(layers, list) or len(layers) > 200:
            raise ValueError("Invalid project layers")
        self.background = project.get("background", "#0B1110")
        self.reset_scene()
        for layer in layers:
            if layer["kind"] == "text":
                item = LayerText(layer["text"], layer["x"], layer["y"],
                                 layer["size"], layer["color"], layer.get("width", 820),
                                 layer.get("font", "DejaVu Sans"), layer.get("align", "center"))
                font = item.font()
                font.setBold(layer.get("bold", True))
                item.setFont(font)
            elif layer["kind"] == "image":
                asset_path = Path(layer["path"])
                if not asset_path.is_absolute() and self.storage is not None:
                    asset_path = self.storage.path.parent / asset_path
                item = LayerImage(str(asset_path), layer["x"], layer["y"],
                                  layer["width"], layer["height"])
            else:
                raise ValueError("Unknown layer type")
            item.setZValue(layer.get("z", 0))
            self.scene.addItem(item)
        self.fit()

    def create_pin_for_design(self, prompt_title=True):
        """Create a draft pin and attach the current canvas without discarding it."""
        if not self.storage:
            QMessageBox.warning(self, "No project", "Open a Pinterest OS project first.")
            return
        if self._canvas_pin_id is not None and self._canvas_pin_id != self.pin.currentData():
            QMessageBox.warning(self, "Different pin selected",
                                "Reselect the pin linked to this canvas before creating a new one.")
            return
        pending = (self.pin_title.text(), self.pin_description.text(),
                   self.pin_tags.text(), self.destination_url.text(),
                   self.pin_board.currentData(), self.pin_product.currentData(),
                   self.pin_status.currentText())
        title = pending[0].strip()
        if prompt_title or not title:
            title, ok = QInputDialog.getText(self, "Create pin", "Pin title:", text=title)
            title = title.strip()
            if not ok or not title:
                return
        if not self.validate_metadata(title, pending[1].strip(), pending[2].strip(), pending[3].strip()):
            return
        try:
            pin_id = self.storage.create("pins", title=title)
            self.reload_pins()
            index = self.pin.findData(pin_id)
            self._blank_draft = False
            self.pin.setCurrentIndex(index)
            self._canvas_pin_id = pin_id
            for widget, value in zip((self.pin_title, self.pin_description,
                                      self.pin_tags, self.destination_url), pending):
                widget.setText(value)
            self.pin_title.setText(title)
            for widget, value in ((self.pin_board, pending[4]), (self.pin_product, pending[5])):
                index = widget.findData(value)
                widget.setCurrentIndex(index if index >= 0 else 0)
            self.pin_status.setCurrentText(pending[6])
            if not self.save_destination_url():
                return
            self.save_pin_image(pin_id)
            self._canvas_pin_id = pin_id
            self.remember_current_pin()
            self._saved_snapshot = self.snapshot()
            self.dirty = False
            self.dirty_label.setText("Saved / no pending changes")
            self.pin_saved.emit(int(pin_id))
            QMessageBox.information(self, "Pin created",
                                    f"Draft pin #{pin_id} created and editable design saved.")
        except (OSError, ValueError) as exc:
            QMessageBox.warning(self, "Create pin failed", str(exc))

    def save_pin_simple(self):
        """Save current canvas; create a draft pin if none is linked yet."""
        if not self.storage:
            QMessageBox.warning(self, "No project", "Open a Pinterest OS project first.")
            return
        if self.pin.currentData() is None:
            self.create_pin_for_design(prompt_title=False)
            return
        self.save_project()

    def save_project(self):
        pin_id = self.pin.currentData()
        if pin_id != self._canvas_pin_id:
            QMessageBox.warning(self, "Different pin selected", "Load the selected pin first, or reselect the canvas pin.")
            return
        if not self.storage or pin_id is None:
            QMessageBox.warning(self, "Select pin",
                                "Create a pin using 'Create new pin for this design', then save.")
            return
        if not self.save_destination_url():
            return
        try:
            self.save_pin_image(pin_id)
            self._canvas_pin_id = pin_id
            self.remember_current_pin()
            self._saved_snapshot = self.snapshot()
            self.dirty = False
            self.dirty_label.setText("Saved / no pending changes")
            self.pin_saved.emit(int(pin_id))
            QMessageBox.information(self, "Saved", "Editable project saved to SQLite.")
        except (OSError, ValueError) as exc:
            QMessageBox.warning(self, "Save failed", str(exc))

    def load_pin(self):
        if not self.confirm_discard():
            return
        pin_id = self.pin.currentData()
        data = self.storage.get_pin_design(pin_id) if self.storage and pin_id else None
        if not data:
            QMessageBox.information(self, "No project", "No saved design for this pin.")
            return
        try:
            self._loading = True
            try:
                self.restore(json.loads(data["project_json"]))
            finally:
                self._loading = False
            self._canvas_pin_id = pin_id
            self.remember_current_pin()
            self._saved_snapshot = self.snapshot()
            self.dirty = False
            self.dirty_label.setText("Saved / no pending changes")
            self.canva_id.setText(data.get("canva_design_id", ""))
        except (ValueError, KeyError, TypeError) as exc:
            QMessageBox.warning(self, "Cannot load", str(exc))

    def open_canva_templates(self):
        """Use the user's existing default-browser Canva session."""
        return webbrowser.open("https://www.canva.com/templates/")

    def import_canva(self):
        """Import a user-downloaded Canva PNG/JPG as a movable image layer.

        Canva's native editable elements cannot be reconstructed from a bitmap.
        This is a local file import, not an API-based automatic synchronization.
        """
        if self._canvas_pin_id != self.pin.currentData():
            QMessageBox.warning(
                self, "Different pin selected",
                "Load the selected pin design before importing Canva artwork.")
            return
        self.open_canva_templates()
        path, _ = QFileDialog.getOpenFileName(
            self, "Import downloaded Canva design", "",
            "Canva images (*.png *.jpg *.jpeg *.webp)")
        if not path:
            return
        source = Path(path)
        if not source.is_file():
            QMessageBox.warning(self, "Import failed", "Image file not found.")
            return
        if source.stat().st_size > 50 * 1024 * 1024:
            QMessageBox.warning(self, "Import failed", "Image exceeds 50 MB.")
            return
        # Keep a project-local copy so moving/deleting Downloads does not break
        # the saved project. Do not modify the source file.
        try:
            import uuid
            from shutil import copy2
            if self.storage is None:
                raise ValueError("Open a project before importing Canva artwork.")
            asset_dir = self.storage.path.parent / "assets" / "canva_imports"
            asset_dir.mkdir(parents=True, exist_ok=True)
            dest = asset_dir / f"{uuid.uuid4().hex}{source.suffix.lower()}"
            copy2(source, dest)
            layer = LayerImage(str(dest), 0, 0, WIDTH, HEIGHT)
            self.scene.addItem(layer)
            self.scene.clearSelection()
            layer.setSelected(True)
            self.refresh_layers()
            self.schedule_dirty_check()
            QMessageBox.information(
                self, "Canva artwork imported",
                "Image added as a movable layer. Original layers were preserved. "
                "The imported image is not split into editable Canva text/shapes. "
                "Save editable project to keep this change.")
        except (OSError, ValueError) as exc:
            QMessageBox.warning(self, "Canva import failed", str(exc))

    def export_canva_svg(self):
        path, _ = QFileDialog.getSaveFileName(
            self, "Export SVG for Canva", "ithutir-canva.svg", "SVG (*.svg)")
        if not path:
            return
        try:
            project_to_svg(self.project(), path)
            self.open_canva_templates()
            QMessageBox.information(
                self, "SVG exported",
                "Canva opened in your browser. Import this SVG in Canva. Text is stored as SVG text and images as separate SVG elements. "
                "Canva may flatten or alter them; verify editability in Canva.")
        except (OSError, ValueError, KeyError) as exc:
            QMessageBox.warning(self, "SVG export failed", str(exc))

    def link_canva(self):
        pin_id = self.pin.currentData()
        if not self.storage or pin_id is None:
            QMessageBox.warning(self, "Select pin", "Select a pin first.")
            return
        try:
            self.storage.set_canva_design_id(pin_id, self.canva_id.text().strip())
            QMessageBox.information(self, "Linked", "Canva design ID linked to pin.")
        except ValueError as exc:
            QMessageBox.warning(self, "Invalid Canva ID", str(exc))

    @staticmethod
    def pin_image_filename(title, export_id):
        """Human-readable title plus the exact immutable export PIN ID."""
        normalized = unicodedata.normalize("NFKD", title.strip())
        slug = re.sub(r"[^\w-]+", "-", normalized, flags=re.UNICODE)
        slug = re.sub(r"-+", "-", slug).strip("-_")[:80].strip("-_")
        return f"{slug or 'pin'}-{export_id}.png"

    def pin_directory(self):
        """Dedicated image library alongside the existing Pinterest OS project."""
        directory = Path(__file__).resolve().parents[2] / "PINTEREST_PIN"
        directory.mkdir(parents=True, exist_ok=True)
        return directory

    def open_pin_directory(self):
        try:
            directory = self.pin_directory()
            subprocess.Popen(["xdg-open", str(directory)],
                             stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        except (OSError, ValueError) as exc:
            QMessageBox.warning(self, "Каталог PINTEREST_PIN", str(exc))

    def save_pin_image(self, pin_id):
        """Keep one up-to-date PNG for each saved local pin."""
        export_id = self.get_export_pin_id(pin_id)
        if not export_id:
            raise ValueError("PIN ID missing")
        filename = self.pin_image_filename(self.pin_title.text(), export_id)
        destination = self.pin_directory() / filename
        image = self.render_image()
        if image.width() != WIDTH or image.height() != HEIGHT:
            raise ValueError("Unexpected image dimensions")
        temporary = destination.with_name(destination.name + ".tmp.png")
        if not image.save(str(temporary), "PNG"):
            raise OSError("Cannot save PNG in PINTEREST_PIN")
        os.replace(temporary, destination)
        self.storage.save_pin_design(
            pin_id, json.dumps(self.project(), ensure_ascii=False), str(destination))
        return destination

    def export_png(self):
        pin_id = self.pin.currentData()
        if pin_id != self._canvas_pin_id:
            QMessageBox.warning(self, "Different pin selected", "Load the selected pin first.")
            return
        if not self.storage or pin_id is None:
            QMessageBox.warning(self, "Select pin", "Select a pin before exporting.")
            return
        if not self.save_destination_url():
            return
        export_id = self.get_export_pin_id(pin_id)
        if not export_id:
            QMessageBox.warning(self, "PIN ID missing", "Cannot generate the stable PIN ID.")
            return
        self.export_pin_id.setText(export_id)
        filename = self.pin_image_filename(self.pin_title.text(), export_id)
        path, _ = QFileDialog.getSaveFileName(
            self, "Export pin", str(self.pin_directory() / filename), "PNG (*.png)")
        if path and Path(path).name != filename:
            QMessageBox.warning(
                self, "PIN ID mismatch",
                "The image filename must contain the same PIN ID as Google Sheets.")
            return
        if not path:
            return
        image = self.render_image()
        if image.width() != WIDTH or image.height() != HEIGHT or not image.save(path, "PNG"):
            QMessageBox.warning(self, "Export failed", "Cannot save PNG.")
            return
        try:
            self.storage.save_pin_design(pin_id, json.dumps(self.project(), ensure_ascii=False),
                                         str(Path(path).resolve()))
            self._canvas_pin_id = pin_id
            self.remember_current_pin()
            self._saved_snapshot = self.snapshot()
            self.dirty = False
            self.dirty_label.setText("Saved / no pending changes")
        except Exception as exc:
            QMessageBox.warning(self, "Link failed", f"PNG saved but SQLite link failed: {exc}")
            return
        QMessageBox.information(self, "Exported", "PNG exported and linked to the selected pin.")
