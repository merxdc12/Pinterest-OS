"""Manual-only publishing queue and explicit local confirmation."""
from __future__ import annotations

import webbrowser
from pathlib import Path

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QApplication, QComboBox, QFileDialog, QHBoxLayout, QLabel, QMessageBox, QPushButton, QTableWidget,
    QTableWidgetItem, QVBoxLayout, QWidget,
)

from . import content_plan as plan
from .calendar import status_caption, qa_caption
from .carousel_logic import validate_slides, export_carousel


class PublishingPage(QWidget):
    def __init__(self, storage, parent=None):
        super().__init__(parent)
        self.storage = storage
        layout = QVBoxLayout(self)
        layout.addWidget(QLabel("Черга ручної публікації — без Pinterest API та автоматичного завантаження"))
        self.table = QTableWidget()
        self.table.setColumnCount(7)
        self.table.setHorizontalHeaderLabels(["Дата / час", "Контент", "Дошка", "Статус", "QA", "Тип", "URL / UTM"])
        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QTableWidget.SelectionMode.SingleSelection)
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        layout.addWidget(self.table)
        buttons = QHBoxLayout()
        for title, handler in (
            ("Оновити", self.refresh),
            ("Перевірити вибране", self.review_selected),
            ("Копіювати дані публікації", self.copy_selected_details),
            ("Відкрити Pinterest", lambda: webbrowser.open("https://www.pinterest.com/")),
            ("Підтвердити публікацію", self.confirm_published),
        ):
            button = QPushButton(title)
            button.clicked.connect(handler)
            buttons.addWidget(button)
        export_selected=QPushButton("Експорт запланованої каруселі ZIP")
        export_selected.clicked.connect(self.export_planned_carousel)
        buttons.addWidget(export_selected)
        layout.addLayout(buttons)
        carousel_controls = QHBoxLayout()
        carousel_controls.addWidget(QLabel("Карусель (ручна підготовка):"))
        self.carousel_picker = QComboBox()
        carousel_controls.addWidget(self.carousel_picker)
        export_button = QPushButton("Експортувати карусель ZIP")
        export_button.clicked.connect(self.export_selected_carousel)
        carousel_controls.addWidget(export_button)
        layout.addLayout(carousel_controls)
        self.refresh()

    def refresh(self):
        current = self.carousel_picker.currentData()
        self.carousel_picker.clear()
        for carousel in self.storage.list_carousels():
            self.carousel_picker.addItem(carousel["title"], carousel["id"])
        index = self.carousel_picker.findData(current)
        if index >= 0:
            self.carousel_picker.setCurrentIndex(index)
        rows = plan.queue(self.storage)
        self.table.setRowCount(len(rows))
        for i, row in enumerate(rows):
            issues = plan.issues(self.storage,row)
            values = [row["scheduled_at"], row["title"], row["board_name"] or "Без дошки",
                      status_caption(row["status"]), "Готово" if not issues else f"Зауважень: {len(issues)}",
                      "Пін" if row["kind"]=="PIN" else "Карусель",row["destination_url"]]
            for j, value in enumerate(values):
                cell = QTableWidgetItem(str(value))
                cell.setData(Qt.ItemDataRole.UserRole, row["id"])
                if j==6: cell.setToolTip(str(value))
                if j==3: cell.setToolTip(row["status"])
                self.table.setItem(i, j, cell)
        self.table.resizeColumnsToContents()
        self.table.setColumnWidth(6,min(340,self.table.columnWidth(6)))

    def export_selected_carousel(self):
        carousel_id = self.carousel_picker.currentData()
        if carousel_id is None:
            QMessageBox.information(self, "Немає каруселі", "Спочатку створіть карусель у вкладці ПІН.")
            return
        slides = self.storage.carousel_slides(carousel_id)
        issues = validate_slides(slides)
        if issues:
            QMessageBox.warning(self, "Карусель не готова", "\n".join(qa_caption(x) for x in issues))
            return
        destination, _ = QFileDialog.getSaveFileName(
            self, "Експорт каруселі для ручної публікації", "carousel.zip", "ZIP archive (*.zip)")
        if not destination:
            return
        try:
            export_carousel(slides, Path(destination), self.carousel_picker.currentText())
        except (OSError, ValueError) as exc:
            QMessageBox.warning(self, "Помилка експорту", qa_caption(str(exc)))
            return
        QMessageBox.information(self, "Експортовано",
            "Файли каруселі підготовлено. Публікація в Pinterest не виконувалась і не перевірялась.")

    def selected_id(self):
        row = self.table.currentRow()
        item = self.table.item(row, 0) if row >= 0 else None
        if item is None:
            QMessageBox.information(self, "Виберіть публікацію", "Спочатку виберіть запис у черзі.")
            return None
        return int(item.data(Qt.ItemDataRole.UserRole))

    def entry(self):
        entry_id=self.selected_id()
        if entry_id is None: return None
        row=plan.get_entry(self.storage,entry_id)
        if not row:
            QMessageBox.warning(self,"Запис відсутній","Запис контент-плану більше не існує.")
            self.refresh()
        return row

    def review_selected(self):
        row=self.entry()
        if not row: return
        issues=plan.issues(self.storage,row)
        text=("Потрібно виправити:\n• "+"\n• ".join(qa_caption(x) for x in issues)) if issues else (
            "Локальну перевірку пройдено. Перед публікацією перевірте дизайн, URL, дошку та правила партнера.")
        QMessageBox.information(self,"Перевірка готовності",text)

    def copy_selected_details(self):
        row=self.entry()
        if not row: return
        problems=plan.issues(self.storage,row)
        if problems:
            QMessageBox.warning(self,"Не готово","\n".join(qa_caption(x) for x in problems))
            return
        details="\n".join(["Title: "+row["title"],"Description: "+row["description"],
            "Destination: "+row["destination_url"],"Board: "+(row["board_name"] or "Unassigned")])
        if row["kind"]=="PIN":
            from .content_factory import ContentFactory
            factory=ContentFactory(self.storage)
            slots=factory.rows('SELECT id FROM campaign_slots WHERE pin_id=?',(row['pin_id'],))
            if slots:
                details+="\nAlt text: "+factory.copy(slots[0]['id'])['alt_text']
        else:
            details+="\nSlides: "+str(len(self.storage.carousel_slides(row['carousel_id'])))
        QApplication.clipboard().setText(details)
        QMessageBox.information(self,"Скопійовано","Дані публікації скопійовано для ручного вставлення.")

    def export_planned_carousel(self):
        row=self.entry()
        if not row: return
        if row['kind']!='CAROUSEL':
            QMessageBox.warning(self,"Carousel","Виберіть заплановану карусель.")
            return
        problems=plan.issues(self.storage,row)
        if problems:
            QMessageBox.warning(self,"Не готово","\n".join(qa_caption(x) for x in problems))
            return
        destination,_=QFileDialog.getSaveFileName(self,"Експорт каруселі","carousel.zip","ZIP (*.zip)")
        if not destination: return
        try:
            export_carousel(self.storage.carousel_slides(row['carousel_id']),Path(destination),row['title'])
            from zipfile import ZipFile
            import json
            with ZipFile(destination,'a') as archive:
                archive.writestr('publication.json',json.dumps({k:row[k] for k in
                    ('title','description','board_name','original_url','destination_url','tracking_code','scheduled_at')},
                    ensure_ascii=False,indent=2))
        except (OSError,ValueError) as exc:
            QMessageBox.warning(self,"Помилка експорту",qa_caption(str(exc)))
            return
        QMessageBox.information(self,"Експортовано","ZIP підготовлено локально; у Pinterest нічого не опубліковано.")

    def confirm_published(self):
        row=self.entry()
        if not row: return
        problems=plan.issues(self.storage,row)
        if problems:
            QMessageBox.warning(self,"Не готово","\n".join(qa_caption(x) for x in problems))
            return
        answer=QMessageBox.question(self,"Підтвердити ручну публікацію",
            "Підтверджуйте лише після фактичної публікації у Pinterest. "
            "Це локальний статус, не перевірка Pinterest API. Продовжити?",
            QMessageBox.StandardButton.Yes|QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No)
        if answer!=QMessageBox.StandardButton.Yes: return
        try:
            plan.confirm(self.storage,row['id'])
        except (ValueError,OSError) as exc:
            QMessageBox.warning(self,"Не вдалося оновити статус",qa_caption(str(exc)))
            return
        self.refresh()
        window=self.window()
        if hasattr(window,"calendar_page"): window.calendar_page.refresh()
        if hasattr(window,"refresh") and hasattr(window,"tables"): window.refresh("pins")
