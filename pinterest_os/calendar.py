"""Local publishing calendar. Planning is not automatic Pinterest posting."""
from __future__ import annotations

from datetime import datetime
import webbrowser
from .calendar_logic import filter_entries, is_overdue
from . import content_plan as plan


from PyQt6.QtCore import QDate, Qt, QLocale
from PyQt6.QtGui import QColor, QFont, QTextCharFormat
from PyQt6.QtWidgets import (
    QCalendarWidget, QComboBox, QDateTimeEdit, QDialog, QDialogButtonBox,
    QFormLayout, QHBoxLayout, QLabel, QMessageBox, QPushButton, QLineEdit, QCheckBox, QTextEdit,
    QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget,
)

STATUS = ("PLANNED", "READY", "PUBLISHED", "CANCELLED")
STATUS_UK = {"PLANNED":"Заплановано", "READY":"Готово", "PUBLISHED":"Опубліковано", "CANCELLED":"Скасовано"}
VIEW_UK = {"Month":"Місяць","Week":"Тиждень","Day":"День","List":"Список"}
KIND_UK = {"PIN":"Пін","CAROUSEL":"Карусель"}

def status_caption(status):
    return STATUS_UK.get(status,status)

QA_UK = {
    "Pin title": "Назва піна",
    "Pin description": "Опис піна",
    "Destination URL": "Цільове посилання (URL)",
    "Assigned board": "Призначена дошка",
    "Exported PNG asset": "Експортоване PNG-зображення",
    "PNG file does not exist at saved path": "PNG-файл відсутній за збереженим шляхом",
    "Destination URL must be HTTP(S) with a hostname": "Цільове посилання має містити HTTP(S) та назву домену",
    "Pin PNG must be 1000 × 1500": "PNG піна має бути розміром 1000 × 1500",
    "Invalid or missing PNG": "Некоректне або відсутнє PNG-зображення",
    "Carousel title": "Назва каруселі",
    "Carousel description": "Опис каруселі",
    "Title exceeds 100 characters": "Назва перевищує 100 символів",
    "Description exceeds 500 characters": "Опис перевищує 500 символів",
    "Exact duplicate creative and destination on this board": "Точний дублікат дизайну та посилання на цій дошці",
    "Valid destination URL": "Коректне цільове посилання (URL)",
    "ITHutir UTM required or invalid": "UTM для ITHutir відсутня або некоректна",
    "UTM URL does not match registered destination or campaign": "UTM-посилання не відповідає зареєстрованій адресі чи кампанії",
    "Invalid UTM registry data": "Некоректні дані реєстру UTM",
    "External destination / partner rules not reviewed": "Зовнішнє посилання або правила партнера не перевірено",
    "Affiliate disclosure must appear in description": "В описі має бути розкриття партнерства",
    "Content Factory: approve and export this slot before manual publication.": "Фабрика контенту: погодьте та експортуйте слот перед ручною публікацією.",
    "Select a board": "Виберіть дошку",
    "Enter a valid HTTP(S) destination URL": "Введіть коректне цільове посилання HTTP(S)",
    "This pin already has a pending plan; edit that entry": "Цей пін уже має активний план. Відредагуйте його.",
    "This carousel is already planned/published for this board": "Карусель уже запланована або опублікована на цій дошці",
    "Only pending unpublished entries can be moved": "Перенести можна лише активні неопубліковані записи",
}

def qa_caption(message):
    if message.startswith("Not ready: "):
        return "Не готово: " + "; ".join(qa_caption(x) for x in message[11:].split("; "))
    return QA_UK.get(message,message)



class ScheduleDialog(QDialog):
    def __init__(self, storage, selected: QDate, entry=None, parent=None, kind='PIN', content_id=None):
        super().__init__(parent)
        self.storage, self.entry = storage, entry
        self.kind = entry['kind'] if entry else kind
        self.setWindowTitle("Редагувати контент-план" if entry else "Запланувати публікацію")
        self.resize(690, 570)
        layout = QVBoxLayout(self)
        form = QFormLayout()
        layout.addLayout(form)
        self.pin = QComboBox()
        records = storage.all("pins") if self.kind == 'PIN' else storage.list_carousels()
        for row in records:
            if self.kind == 'CAROUSEL' or row['status'] != 'PUBLISHED':
                self.pin.addItem(row['title'],row['id'])
        form.addRow("Тип контенту", QLabel("Пін" if self.kind=='PIN' else "Карусель"))
        form.addRow("Вибрати з бібліотеки", self.pin)
        self.board = QComboBox()
        self.board.addItem("— Вибрати дошку —",None)
        for board in storage.all('boards'):
            self.board.addItem(board['name'],board['id'])
        form.addRow("Дошка Pinterest",self.board)
        self.when = QDateTimeEdit()
        self.when.setCalendarPopup(True)
        self.when.setDisplayFormat("yyyy-MM-dd HH:mm")
        self.when.setDate(selected)
        from PyQt6.QtCore import QTime
        self.when.setTime(QTime(12,0))
        form.addRow("Дата / час (локальні)",self.when)
        self.url=QLineEdit()
        self.url.setPlaceholderText("https://ithutir.com/...")
        self.url.setToolTip("Повна адреса сторінки товару чи статті. UTM додається лише до HTTPS ithutir.com.")
        form.addRow("Цільове посилання (URL) товару",self.url)
        self.description=QTextEdit()
        self.description.setMaximumHeight(76)
        self.description.setReadOnly(self.kind=='PIN')
        form.addRow("Опис (для піна — з бібліотеки)",self.description)
        self.utm=QCheckBox("Додати UTM Pinterest (pint)")
        self.utm.setChecked(True)
        form.addRow(self.utm)
        self.campaign=QLineEdit("pinterest")
        self.campaign.setToolTip("Назва кампанії: латиниця, цифри, дефіс або підкреслення.")
        form.addRow("Назва UTM-кампанії",self.campaign)
        self.external=QCheckBox("Перевірено зовнішнє посилання та правила партнера")
        self.affiliate=QCheckBox("Партнерське посилання / affiliate")
        self.disclosure=QLineEdit()
        self.disclosure.setPlaceholderText("Текст розкриття партнерства, який є в описі")
        form.addRow(self.external)
        form.addRow(self.affiliate)
        form.addRow("Розкриття партнерства (Disclosure)",self.disclosure)
        self.state=QComboBox()
        for status in ("PLANNED","READY"):
            self.state.addItem(status_caption(status),status)
            self.state.setItemData(self.state.count()-1,status,Qt.ItemDataRole.ToolTipRole)
        form.addRow("Статус (готово — після перевірки)",self.state)
        note=QLabel("План локальний. Публікація в Pinterest — вручну. Статус «Готово» вимагає перевірки URL, дошки, зображень, UTM та розкриття партнерства.")
        note.setWordWrap(True)
        layout.addWidget(note)
        self.pin.currentIndexChanged.connect(self.load_source)
        self.url.textChanged.connect(self.update_url)
        self.load_source()
        if content_id is not None:
            self.pin.setCurrentIndex(self.pin.findData(content_id))
        if entry:
            self.pin.setCurrentIndex(self.pin.findData(entry['pin_id'] if self.kind=='PIN' else entry['carousel_id']))
            self.pin.setEnabled(False)
            self.board.setCurrentIndex(max(0,self.board.findData(entry['board_id'])))
            self.url.setText(entry['original_url'])
            self.description.setPlainText(entry['description'])
            self.when.setDate(QDate.fromString(entry['scheduled_at'][:10],'yyyy-MM-dd'))
            self.when.setTime(QTime.fromString(entry['scheduled_at'][11:16],'HH:mm'))
            self.campaign.setText(entry['campaign'] or 'pinterest')
            self.utm.setChecked(bool(entry['tracking_id']) or (entry['details_id'] is None and plan.owned(entry['original_url'])))
            self.external.setChecked(bool(entry['external_review']))
            self.affiliate.setChecked(bool(entry['affiliate']))
            self.disclosure.setText(entry['disclosure'] or '')
            self.state.setCurrentIndex(max(0,self.state.findData(entry['status'])))
        buttons=QDialogButtonBox(QDialogButtonBox.StandardButton.Save|QDialogButtonBox.StandardButton.Cancel)
        buttons.button(QDialogButtonBox.StandardButton.Save).setText("ДОДАТИ В КОНТЕНТ-ПЛАН" if not entry else "ЗБЕРЕГТИ ЗМІНИ")
        buttons.button(QDialogButtonBox.StandardButton.Cancel).setText("Скасувати")
        buttons.accepted.connect(self.save)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def update_url(self,*_):
        local=plan.owned(self.url.text().strip())
        self.utm.setEnabled(local)
        if not local: self.utm.setChecked(False)
        elif not self.entry: self.utm.setChecked(True)
        self.external.setEnabled(not local)

    def load_source(self,*_):
        if self.kind=='PIN':
            pin=self.storage.get('pins',self.pin.currentData())
            if pin:
                self.board.setCurrentIndex(max(0,self.board.findData(pin['board_id'])))
                self.url.setText(pin['destination_url'])
                self.description.setPlainText(pin['description'])
        self.update_url()

    def save(self):
        content=self.pin.currentData()
        if content is None:
            QMessageBox.warning(self,"Контент-план","Спочатку створіть або виберіть контент.")
            return
        when=self.when.dateTime().toString("yyyy-MM-ddTHH:mm")
        entry_id=self.entry['id'] if self.entry else None
        collisions=plan.conflicts(self.storage,when,self.board.currentData(),entry_id)
        if collisions:
            if QMessageBox.question(self,"Конфлікт розкладу",
                "На цю дошку вже заплановано публікацію в той самий час. Продовжити?",
                QMessageBox.StandardButton.Yes|QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No)!=QMessageBox.StandardButton.Yes:
                return
        try:
            if self.state.currentData()=='CANCELLED' and self.entry:
                plan.remove(self.storage,entry_id)
            else:
                plan.save(self.storage,self.kind,content,when,self.board.currentData(),self.url.text(),
                          self.description.toPlainText(),self.campaign.text(),self.utm.isChecked(),
                          self.external.isChecked(),self.affiliate.isChecked(),self.disclosure.text(),
                          self.state.currentData(),entry_id)
        except (ValueError,OSError) as exc:
            QMessageBox.warning(self,"Не вдалося зберегти",qa_caption(str(exc)))
            return
        self.accept()


class ScheduleGrid(QTableWidget):
    """Drag a schedule row onto a day column to reschedule its date."""
    def __init__(self, on_move, parent=None):
        super().__init__(parent)
        self.on_move = on_move
        self.day_columns = []
        self.setDragEnabled(True)
        self.setAcceptDrops(True)
        self.setDragDropMode(QTableWidget.DragDropMode.DragDrop)
        self.setDefaultDropAction(Qt.DropAction.MoveAction)

    def dropEvent(self, event):
        if not event.source() is self:
            event.ignore()
            return
        source_row = self.currentRow()
        source_item = self.item(source_row, 0) if source_row >= 0 else None
        target = self.indexAt(event.position().toPoint())
        if source_item is None or not target.isValid():
            event.ignore()
            return
        schedule_id = source_item.data(Qt.ItemDataRole.UserRole)
        if not schedule_id or target.column() >= len(self.day_columns):
            event.ignore()
            return
        day = self.day_columns[target.column()]
        if day and self.on_move(int(schedule_id), day):
            event.acceptProposedAction()
        else:
            event.ignore()


class CalendarPage(QWidget):
    COLORS = {
        "PLANNED": "#E5B64A",
        "READY": "#43E58A",
        "PUBLISHED": "#4C9BE8",
        "CANCELLED": "#E26B72",
    }

    def __init__(self, storage, parent=None):
        super().__init__(parent)
        self.storage = storage
        self._marked = set()
        outer = QVBoxLayout(self)
        controls = QHBoxLayout()
        self.prev = QPushButton("◀ Назад")
        self.prev.clicked.connect(lambda: self.move_period(-1))
        controls.addWidget(self.prev)
        self.today = QPushButton("Сьогодні")
        self.today.clicked.connect(self.go_today)
        controls.addWidget(self.today)
        self.next = QPushButton("Далі ▶")
        self.next.clicked.connect(lambda: self.move_period(1))
        controls.addWidget(self.next)
        self.view = QComboBox()
        for name, caption in VIEW_UK.items():
            self.view.addItem(caption,name)
        self.view.currentTextChanged.connect(self.refresh)
        controls.addWidget(self.view)
        self.board = QComboBox()
        self.board.currentIndexChanged.connect(self.refresh)
        controls.addWidget(QLabel("Дошка:"))
        controls.addWidget(self.board)
        self.status_filter = QComboBox()
        self.status_filter.addItem("Усі статуси", "ALL")
        for state in STATUS:
            self.status_filter.addItem(status_caption(state), state)
            self.status_filter.setItemData(self.status_filter.count()-1,state,Qt.ItemDataRole.ToolTipRole)
        self.status_filter.currentIndexChanged.connect(self.refresh)
        controls.addWidget(self.status_filter)
        self.kind_filter = QComboBox()
        self.kind_filter.addItem("Увесь контент", "ALL")
        self.kind_filter.addItem("Піни", "PIN")
        self.kind_filter.addItem("Каруселі", "CAROUSEL")
        self.kind_filter.currentIndexChanged.connect(self.refresh)
        controls.addWidget(self.kind_filter)
        self.overdue_filter = QComboBox()
        self.overdue_filter.addItem("Усі дати", False)
        self.overdue_filter.addItem("Лише прострочені", True)
        self.overdue_filter.currentIndexChanged.connect(self.refresh)
        controls.addWidget(self.overdue_filter)
        controls.addStretch()
        add = QPushButton("+ Запланувати пін")
        add.setObjectName("Primary")
        add.clicked.connect(self.add_schedule)
        controls.addWidget(add)
        carousel = QPushButton("+ Запланувати карусель")
        carousel.setObjectName("Primary")
        carousel.clicked.connect(lambda: self.add_schedule(kind="CAROUSEL"))
        controls.addWidget(carousel)
        outer.addLayout(controls)

        self.calendar = QCalendarWidget()
        self.calendar.setLocale(QLocale(QLocale.Language.Ukrainian,QLocale.Country.Ukraine))
        self.calendar.setGridVisible(True)
        self.calendar.selectionChanged.connect(self.refresh)
        self.calendar.currentPageChanged.connect(lambda year, month: self.refresh())
        outer.addWidget(self.calendar, 2)
        self.heading = QLabel()
        outer.addWidget(self.heading)
        self.grid = ScheduleGrid(self.move_entry)
        self.grid.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.grid.setSelectionMode(QTableWidget.SelectionMode.SingleSelection)
        self.grid.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.grid.verticalHeader().setVisible(False)
        self.grid.horizontalHeader().setStretchLastSection(True)
        self.grid.doubleClicked.connect(lambda index: self.edit_selected())
        outer.addWidget(self.grid, 1)
        actions = QHBoxLayout()
        edit = QPushButton("РЕДАГУВАТИ")
        edit.clicked.connect(self.edit_selected)
        actions.addWidget(edit)
        self.reschedule_button=QPushButton("ПЕРЕНЕСТИ ПУБЛІКАЦІЮ")
        self.reschedule_button.setObjectName("Primary")
        self.reschedule_button.setToolTip("Змінити дату або час, зберігши дошку, URL, UTM та статус.")
        self.reschedule_button.clicked.connect(self.reschedule_selected)
        actions.addWidget(self.reschedule_button)
        self.cancel_button=QPushButton("СКАСУВАТИ ПУБЛІКАЦІЮ")
        self.cancel_button.setStyleSheet("QPushButton:enabled { color: #E5B64A; font-weight: bold; }")
        self.cancel_button.setToolTip("Прибрати з черги, зберігши запис зі статусом «Скасовано» (CANCELLED).")
        self.cancel_button.clicked.connect(self.remove_selected)
        actions.addWidget(self.cancel_button)
        self.delete_button=QPushButton("ВИДАЛИТИ З КОНТЕНТ-ПЛАНУ")
        self.delete_button.setStyleSheet("QPushButton:enabled { color: #EF4444; font-weight: bold; }")
        self.delete_button.setToolTip("Видалити лише запис планування. Пін, карусель, PNG та UTM-реєстр залишаються.")
        self.delete_button.clicked.connect(self.delete_selected)
        actions.addWidget(self.delete_button)
        ready = QPushButton("ПЕРЕВІРИТИ ГОТОВНІСТЬ")
        ready.clicked.connect(self.show_publishing_checklist)
        actions.addWidget(ready)
        actions.addStretch()
        outer.addLayout(actions)
        self.grid.itemSelectionChanged.connect(self.update_action_buttons)
        self.refresh()

    def reload_boards(self):
        selected = self.board.currentData()
        self.board.blockSignals(True)
        self.board.clear()
        self.board.addItem("Усі дошки", None)
        for board in self.storage.all("boards"):
            self.board.addItem(board["name"], board["id"])
        index = self.board.findData(selected)
        self.board.setCurrentIndex(max(index, 0))
        self.board.blockSignals(False)

    def move_period(self, delta: int):
        selected = self.calendar.selectedDate()
        mode = self.view.currentData()
        new_date = selected.addMonths(delta) if mode in ("Month","List") else selected.addDays(delta * (7 if mode == "Week" else 1))
        self.calendar.setSelectedDate(new_date)

    def go_today(self):
        self.calendar.setSelectedDate(QDate.currentDate())
        self.calendar.showToday()

    def selected_entry(self, notify=True):
        selected=self.grid.selectionModel().selectedRows()
        row=selected[0].row() if selected else -1
        item=self.grid.item(row,0) if row>=0 else None
        entry_id=item.data(Qt.ItemDataRole.UserRole) if item else None
        entry=plan.get_entry(self.storage,int(entry_id)) if entry_id else None
        if entry is None and notify:
            QMessageBox.information(self,"Контент-план","Виберіть пін або карусель у таблиці.")
        return entry

    def update_action_buttons(self):
        entry=self.selected_entry(notify=False)
        pending=bool(entry and entry['status'] in ('PLANNED','READY') and entry['pin_status']!='PUBLISHED')
        deletable=bool(entry and entry['status'] in ('PLANNED','READY','CANCELLED')
                       and plan.factory_slot_for_entry(self.storage,entry['id']) is None)
        self.reschedule_button.setEnabled(pending)
        self.cancel_button.setEnabled(pending)
        self.delete_button.setEnabled(deletable)

    def refresh_after_action(self):
        self.refresh()
        window=self.window()
        if hasattr(window,'publishing_page'):
            window.publishing_page.refresh()
        if hasattr(window,'content_factory_page'):
            window.content_factory_page.reload()

    def reschedule_selected(self):
        entry=self.selected_entry()
        if not entry or entry['status'] not in ('PLANNED','READY'):
            return
        dialog=QDialog(self)
        dialog.setWindowTitle("Перенести публікацію")
        layout=QFormLayout(dialog)
        layout.addRow("Контент",QLabel(entry['title']))
        when=QDateTimeEdit()
        when.setCalendarPopup(True)
        when.setDisplayFormat("yyyy-MM-dd HH:mm")
        from PyQt6.QtCore import QDateTime
        when.setDateTime(QDateTime.fromString(entry['scheduled_at'],"yyyy-MM-ddTHH:mm"))
        layout.addRow("Нова дата / час",when)
        buttons=QDialogButtonBox(QDialogButtonBox.StandardButton.Save|QDialogButtonBox.StandardButton.Cancel)
        buttons.button(QDialogButtonBox.StandardButton.Save).setText("ПЕРЕНЕСТИ")
        buttons.button(QDialogButtonBox.StandardButton.Cancel).setText("Скасувати")
        layout.addRow(buttons)
        def apply():
            proposed=when.dateTime().toString("yyyy-MM-ddTHH:mm")
            if proposed!=entry['scheduled_at'] and self.reschedule_entry(entry,proposed):
                dialog.accept()
            elif proposed==entry['scheduled_at']:
                dialog.reject()
        buttons.accepted.connect(apply)
        buttons.rejected.connect(dialog.reject)
        dialog.exec()

    def reschedule_entry(self,entry,proposed):
        conflicts=plan.conflicts(self.storage,proposed,entry['board_id'],entry['id'])
        if conflicts and QMessageBox.question(
            self,"Конфлікт розкладу","На цю дошку вже заплановано публікацію в цей час. Продовжити?",
            QMessageBox.StandardButton.Yes|QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No)!=QMessageBox.StandardButton.Yes:
            return False
        try:
            plan.move(self.storage,entry['id'],proposed)
        except (ValueError,OSError) as exc:
            QMessageBox.warning(self,"Контент-план",qa_caption(str(exc)))
            return False
        self.calendar.setSelectedDate(QDate.fromString(proposed[:10],"yyyy-MM-dd"))
        self.refresh_after_action()
        return True

    def add_schedule(self, checked=False, kind="PIN", content_id=None):
        if ScheduleDialog(self.storage, self.calendar.selectedDate(), parent=self,kind=kind,content_id=content_id).exec():
            self.refresh()

    def edit_selected(self):
        entry = self.selected_entry()
        if entry and entry['status'] in ('PUBLISHED','CANCELLED'):
            QMessageBox.information(self,"Контент-план","Завершений запис не редагується.")
            return
        if entry and ScheduleDialog(self.storage, self.calendar.selectedDate(), entry, self).exec():
            self.refresh()

    def remove_selected(self):
        entry=self.selected_entry()
        if not entry:
            return
        extra=("\nСлот Фабрики контенту повернеться на погодження."
               if plan.factory_slot_for_entry(self.storage,entry['id']) is not None else "")
        answer=QMessageBox.question(self,"Скасувати публікацію?",
            f"{entry['title']} — {entry['scheduled_at']}\n\n"
            "Запис залишиться в історії зі статусом «Скасовано» (CANCELLED). Контент не видаляється."
            "\nДія локальна: Pinterest не змінюється."+extra,
            QMessageBox.StandardButton.Yes|QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No)
        if answer!=QMessageBox.StandardButton.Yes:
            return
        try:
            plan.remove(self.storage,entry['id'])
        except (ValueError,OSError) as exc:
            QMessageBox.warning(self,"Контент-план",qa_caption(str(exc)))
        self.refresh_after_action()

    def delete_selected(self):
        entry=self.selected_entry()
        if not entry:
            return
        answer=QMessageBox.question(self,"Видалити запис з контент-плану?",
            f"{entry['title']} — {entry['scheduled_at']}\n\n"
            "Буде остаточно видалено лише локальний запис планування. "
            "Пін, карусель, зображення та UTM-реєстр залишаться. "
            "Дія не впливає на Pinterest.",
            QMessageBox.StandardButton.Yes|QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No)
        if answer!=QMessageBox.StandardButton.Yes:
            return
        try:
            plan.delete_entry(self.storage,entry['id'])
        except (ValueError,OSError) as exc:
            QMessageBox.warning(self,"Контент-план",qa_caption(str(exc)))
        self.refresh_after_action()

    def show_publishing_checklist(self):
        entry = self.selected_entry()
        if not entry:
            return
        missing = plan.issues(self.storage,entry)
        if missing:
            QMessageBox.information(
                self, "Перевірка готовності публікації",
                "Перед відкриттям Pinterest виправте:\n• " + "\n• ".join(qa_caption(x) for x in missing))
            return
        answer = QMessageBox.question(
            self, "Перевірка готовності публікації",
            "Метадані, дошка та шлях до PNG перевірені.\n"
            "Перевірте зображення та контент, після чого опублікуйте вручну.\n"
            "Відкрити Pinterest у браузері? (Без автоматичної публікації.)",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No)
        if answer == QMessageBox.StandardButton.Yes:
            webbrowser.open("https://www.pinterest.com/")

    def move_entry(self, entry_id: int, day: str) -> bool:
        entry = plan.get_entry(self.storage,entry_id)
        if not entry:
            return False
        if entry["scheduled_at"][:10] == day:
            return False
        answer = QMessageBox.question(
            self, "Перенести публікацію",
            f"Перенести публікацію на {day}? Час залишиться {entry['scheduled_at'][11:16]}."
        )
        if answer != QMessageBox.StandardButton.Yes:
            return False
        proposed = day + entry["scheduled_at"][10:]
        return self.reschedule_entry(entry,proposed)

    def refresh(self, *_):
        self.reload_boards()
        selected = self.calendar.selectedDate()
        mode = self.view.currentData()
        if mode == "Month":
            start = QDate(selected.year(), selected.month(), 1)
            end = start.addMonths(1).addDays(-1)
            self.calendar.show()
        elif mode == "Week":
            start = selected.addDays(1 - selected.dayOfWeek())
            end = start.addDays(6)
            self.calendar.hide()
        elif mode == "List":
            start = QDate(selected.year(),selected.month(),1)
            end = start.addMonths(1).addDays(-1)
            self.calendar.hide()
        else:
            start = selected
            end = selected
            self.calendar.hide()
        start_iso = start.toString("yyyy-MM-dd")
        end_iso = end.toString("yyyy-MM-dd")
        entries = plan.entries(self.storage,start_iso,end_iso,self.board.currentData())
        entries = [r for r in entries if self.kind_filter.currentData() in ("ALL",r["kind"])]
        entries = filter_entries(entries, self.status_filter.currentData(),
                                 self.overdue_filter.currentData(), datetime.now())
        summary = {state: sum(row["status"] == state for row in entries) for state in STATUS}
        overdue_count = sum(is_overdue(row, datetime.now()) for row in entries)
        counts = "  |  ".join(f"{status_caption(key)}: {value}" for key, value in summary.items())
        self.heading.setText(
            f"{VIEW_UK[mode]}: {start_iso} — {end_iso}  |  Записів: {len(entries)}  |  Прострочено: {overdue_count}  |  {counts}")
        if mode == "Week":
            days = [start.addDays(i).toString("yyyy-MM-dd") for i in range(7)]
        elif mode == "Day":
            days = [start_iso]
        else:
            days = [start.addDays(i).toString("yyyy-MM-dd") for i in range(start.daysTo(end) + 1)]
        # A compact list in Month mode; Week/Day use date columns as drop targets.
        if mode in ("Month","List"):
            headers = ["Дата", "Час", "Контент", "Дошка", "Статус", "Тип", "URL / UTM"]
            self.grid.day_columns = []
        else:
            headers = days
            self.grid.day_columns = days
        self.grid.clearContents()
        self.grid.setColumnCount(len(headers))
        self.grid.setHorizontalHeaderLabels(headers)
        self.grid.setRowCount(len(entries))
        for i, entry in enumerate(entries):
            if mode in ("Month","List"):
                values = [entry["scheduled_at"][:10], entry["scheduled_at"][11:16],
                          entry["title"], entry["board_name"] or "Без дошки", status_caption(entry["status"]),
                          "Пін" if entry["kind"]=="PIN" else "Карусель",entry["destination_url"]]
                for j, value in enumerate(values):
                    item = QTableWidgetItem(str(value))
                    item.setData(Qt.ItemDataRole.UserRole, entry["id"])
                    if j==6: item.setToolTip(str(value))
                    if j == 4:
                        item.setToolTip(entry["status"])
                        item.setForeground(QColor(
                            "#E26B72" if is_overdue(entry, datetime.now())
                            else self.COLORS[entry["status"]]))
                    self.grid.setItem(i, j, item)
            else:
                target = days.index(entry["scheduled_at"][:10])
                # Each row has a pin in its scheduled day and empty drop targets elsewhere.
                for j in range(len(days)):
                    item = QTableWidgetItem(
                        f"{entry['scheduled_at'][11:16]}  {KIND_UK[entry['kind']]} {entry['title']} [{status_caption(entry['status'])}]"
                        if j == target else "Перетягніть сюди"
                    )
                    item.setData(Qt.ItemDataRole.UserRole, entry["id"])
                    if j == target:
                        item.setToolTip(entry["status"])
                        item.setForeground(QColor(self.COLORS[entry["status"]]))
                    self.grid.setItem(i, j, item)
        self.grid.resizeColumnsToContents()
        if mode in ("Month","List"):
            self.grid.setColumnWidth(6, min(340,self.grid.columnWidth(6)))
        self.update_markers()
        self.update_action_buttons()

    def update_markers(self):
        # Highlight days with entries in the displayed month, respecting the board filter.
        shown = self.calendar.yearShown(), self.calendar.monthShown()
        first = QDate(shown[0], shown[1], 1)
        last = first.addMonths(1).addDays(-1)
        rows = filter_entries(plan.entries(self.storage,
            first.toString("yyyy-MM-dd"), last.toString("yyyy-MM-dd"), self.board.currentData()
        ), self.status_filter.currentData(), self.overdue_filter.currentData(), datetime.now())
        rows = [r for r in rows if self.kind_filter.currentData() in ("ALL",r["kind"])]
        by_day = {}
        for row in rows:
            by_day.setdefault(row["scheduled_at"][:10], []).append(row["status"])
        for old in self._marked:
            self.calendar.setDateTextFormat(old, QTextCharFormat())
        self._marked.clear()
        for day, statuses in by_day.items():
            qdate = QDate.fromString(day, "yyyy-MM-dd")
            fmt = QTextCharFormat()
            fmt.setFontWeight(QFont.Weight.Bold)
            fmt.setForeground(QColor(self.COLORS[statuses[0]]))
            self.calendar.setDateTextFormat(qdate, fmt)
            self._marked.add(qdate)
