"""Read-only import with optional Linux Secret Service credential storage."""
from PyQt6.QtCore import QThread, pyqtSignal
from PyQt6.QtWidgets import (QWidget,QVBoxLayout,QLabel,QLineEdit,QPushButton,QPlainTextEdit,
                             QFileDialog,QMessageBox,QCheckBox)
import webbrowser
from . import pinterest_import as engine
from . import pinterest_credentials as credentials

class FetchWorker(QThread):
    result=pyqtSignal(object)
    failed=pyqtSignal(str)
    def __init__(self,token,username,parent=None):
        super().__init__(parent)
        self.token,self.username=token,username
    def run(self):
        try: self.result.emit(engine.fetch_snapshot(self.token,self.username))
        except Exception as exc: self.failed.emit(str(exc) if isinstance(exc,ValueError) else 'Помилка API. Імпорт не виконано.')
        finally: self.token=''

class PinterestImportPage(QWidget):
    imported=pyqtSignal()
    def __init__(self,storage,parent=None):
        super().__init__(parent)
        self.storage=storage
        self.snapshot=None
        self.worker=None
        self.generation=0
        layout=QVBoxLayout(self)
        note=QLabel("Імпорт власних опублікованих пінів. Лише читання Pinterest; наявні локальні записи не перезаписуються. API: власні публічні дошки, без repin і ad-only.")
        note.setWordWrap(True);layout.addWidget(note)
        self.account=QLineEdit()
        self.account.setPlaceholderText("Username профілю Pinterest (без @)")
        self.account.setText("ithutir")
        layout.addWidget(QLabel("Профіль Pinterest"));layout.addWidget(self.account)
        self.app_id=QLineEdit("1645174")
        layout.addWidget(QLabel("App ID (ідентифікатор додатка)"));layout.addWidget(self.app_id)
        self.app_secret=QLineEdit()
        self.app_secret.setEchoMode(QLineEdit.EchoMode.Password)
        self.app_secret.setPlaceholderText("Необов’язково для Trial")
        layout.addWidget(QLabel("App Secret (секретний ключ)"));layout.addWidget(self.app_secret)
        self.token=QLineEdit()
        self.token.setEchoMode(QLineEdit.EchoMode.Password)
        self.token.setPlaceholderText("Вставте маркер доступу")
        layout.addWidget(QLabel("Access Token (pins:read, boards:read, user_accounts:read)"));layout.addWidget(self.token)
        self.refresh_token=QLineEdit()
        self.refresh_token.setEchoMode(QLineEdit.EchoMode.Password)
        self.refresh_token.setPlaceholderText("Необов’язково; лише повноцінний OAuth")
        layout.addWidget(QLabel("Refresh Token (маркер оновлення)"));layout.addWidget(self.refresh_token)
        self.expiry=QLineEdit()
        self.expiry.setPlaceholderText("YYYY-MM-DDTHH:MM+01:00 — якщо відомо")
        layout.addWidget(QLabel("Термін дії Access Token (із часовим поясом)"));layout.addWidget(self.expiry)
        layout.addWidget(QLabel("Середовище: Production (Trial — обмежений доступ)"))
        self.credential_status=QLabel("Ключі не завантажено. Збереження — лише Linux Keyring.")
        self.credential_status.setWordWrap(True)
        layout.addWidget(self.credential_status)
        self.save_keys_button=self.button(layout,"ЗБЕРЕГТИ КЛЮЧІ API",self.save_keys)
        self.load_keys_button=self.button(layout,"ЗАВАНТАЖИТИ КЛЮЧІ З KEYRING",self.load_keys)
        self.check_button=self.button(layout,"ПЕРЕВІРИТИ ПІДКЛЮЧЕННЯ",self.fetch)
        self.rotate_button=self.button(layout,"ОНОВИТИ ACCESS TOKEN (ВРУЧНУ)",self.open_token_page)
        self.disconnect_button=self.button(layout,"ВІДКЛЮЧИТИ PINTEREST (ЛОКАЛЬНО)",self.disconnect_keys)
        self.button(layout,"ВІДКРИТИ PINTEREST DEVELOPERS",lambda:webbrowser.open("https://developers.pinterest.com/"))
        self.fetch_button=self.button(layout,"ОТРИМАТИ ДОШКИ ТА ПІНИ (API)",self.fetch)
        self.button(layout,"ЗАПИТАТИ АРХІВ PINTEREST",lambda:webbrowser.open("https://help.pinterest.com/en/article/download-your-pinterest-data"))
        self.file_button=self.button(layout,"ВІДКРИТИ JSON / ZIP ІМПОРТУ",self.load)
        self.preview=QPlainTextEdit()
        self.preview.setReadOnly(True);self.preview.setMinimumHeight(180)
        layout.addWidget(self.preview)
        self.confirm=QCheckBox("Підтверджую: це наші власні опубліковані піни, дошки та права на контент.")
        layout.addWidget(self.confirm)
        self.apply_button=self.button(layout,"ІМПОРТУВАТИ ПЕРЕВІРЕНІ ЗАПИСИ",self.apply)
        self.apply_button.setEnabled(False)
        self.confirm.toggled.connect(self.update_controls)
        self.account.textChanged.connect(self.identity_changed)
        self.app_id.textChanged.connect(self.identity_changed)
        layout.addStretch()
    def button(self,layout,title,handler):
        button=QPushButton(title);button.clicked.connect(handler);layout.addWidget(button);return button
    def key_record(self):
        return {"access_token":self.token.text(),"app_secret":self.app_secret.text(),
                "refresh_token":self.refresh_token.text(),"expires_at":self.expiry.text()}

    def clear_keys(self):
        for field in (self.token,self.app_secret,self.refresh_token,self.expiry):
            field.clear()

    def identity_changed(self,*_):
        self.generation+=1
        self.clear_keys()
        self.credential_status.setText("Ідентифікатор змінено. Завантажте відповідні ключі.")
        self.reset_preview()

    def save_keys(self):
        try:
            credentials.save(self.account.text(),self.app_id.text(),self.key_record())
        except ValueError as exc:
            self.credential_status.setText(str(exc));return
        self.clear_keys()
        self.credential_status.setText("Ключі збережено у Linux Keyring. Поля очищено; для запиту ключ завантажиться автоматично.")

    def load_keys(self):
        try:
            record=credentials.load(self.account.text(),self.app_id.text())
        except ValueError as exc:
            self.credential_status.setText(str(exc));return
        if not record:
            self.credential_status.setText("Для цього профілю та App ID ключі не збережено.");return
        self.token.setText(record["access_token"])
        self.app_secret.setText(record["app_secret"])
        self.refresh_token.setText(record["refresh_token"])
        self.expiry.setText(record["expires_at"])
        self.credential_status.setText("Ключі завантажено у захищені поля. Термін дії перевіряється перед запитом.")

    def open_token_page(self):
        try: credentials.identity(self.account.text(),self.app_id.text())
        except ValueError as exc:
            self.credential_status.setText(str(exc));return
        webbrowser.open("https://developers.pinterest.com/apps/"+self.app_id.text().strip()+"/")
        self.credential_status.setText("Створіть новий маркер Limited Production, вставте його, оновіть дату дії та збережіть. Для OAuth-оновлення потрібен окремий потік авторизації.")

    def disconnect_keys(self):
        if QMessageBox.question(self,"Відключити Pinterest?",
            "Видалити локально збережені ключі для цього профілю та App ID? Дозвіл Pinterest і імпортовані піни не зміняться.",
            QMessageBox.StandardButton.Yes|QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No)!=QMessageBox.StandardButton.Yes:
            return
        try: credentials.delete(self.account.text(),self.app_id.text())
        except ValueError as exc:
            self.credential_status.setText(str(exc));return
        self.clear_keys()
        self.reset_preview()
        self.credential_status.setText("Локальні ключі видалено з Linux Keyring.")

    def update_controls(self,*_):
        busy=bool(self.worker and self.worker.isRunning())
        self.apply_button.setEnabled(self.snapshot is not None and self.confirm.isChecked() and not busy)
        self.fetch_button.setEnabled(not busy);self.file_button.setEnabled(not busy)
        for control in (self.save_keys_button,self.load_keys_button,self.check_button,self.rotate_button,
                        self.disconnect_button,self.account,self.app_id,self.token,self.app_secret,
                        self.refresh_token,self.expiry):
            control.setEnabled(not busy)
    def reset_preview(self,*_):
        self.snapshot=None
        self.confirm.setChecked(False)
        self.preview.clear()
        self.update_controls()
    def set_storage(self,storage):
        self.generation+=1
        self.storage=storage
        self.clear_keys()
        self.reset_preview()
    def fetch(self):
        if self.worker and self.worker.isRunning(): return
        try:
            username=engine._account(self.account.text())
            record=self.key_record() if self.token.text().strip() else credentials.load(username,self.app_id.text())
            if not record: raise ValueError("Введіть або збережіть Access Token, отриманий у Pinterest Developers.")
            token=credentials.ensure_current(record)
        except ValueError as exc:
            QMessageBox.warning(self,"Pinterest",str(exc));return
        self.reset_preview()
        self.preview.setPlainText("Отримання даних Pinterest API…")
        generation=self.generation
        worker=FetchWorker(token,username,self)
        self.worker=worker
        worker.result.connect(lambda snapshot:self.received(snapshot,generation))
        worker.failed.connect(lambda msg:self.failed(msg,generation))
        worker.finished.connect(self.update_controls)
        worker.start();self.update_controls()
    def received(self,snapshot,generation):
        if generation!=self.generation: return
        self.show_snapshot(snapshot)
    def failed(self,msg,generation):
        if generation==self.generation: self.preview.setPlainText(msg)
    def load(self):
        path,_=QFileDialog.getOpenFileName(self,"Відкрити імпорт Pinterest","","JSON / ZIP (*.json *.zip)")
        if not path:return
        self.reset_preview()
        try:self.show_snapshot(engine.read_manifest(path))
        except Exception as exc: self.preview.setPlainText(str(exc))
    def show_snapshot(self,snapshot):
        try:
            plan=engine.prepare(self.storage,snapshot,self.account.text())
        except Exception as exc:
            self.preview.setPlainText(str(exc));return
        self.snapshot=snapshot
        self.preview.setPlainText("\n".join([
            "Профіль: "+plan['account'],"Джерело: "+plan['source'],
            f"Дошок: {len(plan['boards'])} | Нових пінів: {len(plan['pins'])} | Відомих ID: {plan['skipped']} | Конфліктів назв: {len(plan['conflicts'])}",
            "Зображення: зберігається URL джерела, не локальний PNG. Архів: підтвердження користувачем, не API.",
            *["+ "+p['title']+" | "+p['id'] for p in plan['pins'][:200]],
            *["КОНФЛІКТ (пропущено): "+t for t in plan['conflicts'][:200]]
        ]))
        self.update_controls()
    def apply(self):
        if self.snapshot is None or not self.confirm.isChecked():return
        try:
            from .workspace import backup_database
            from uuid import uuid4
            path=self.storage.path
            dest=path.parent.parent/(path.parent.name+'.pre-pinterest-import-'+uuid4().hex[:8]+'.sqlite3') if (path.parent/'manifest.json').is_file() else path.with_name(path.name+'.pre-pinterest-import-'+uuid4().hex[:8]+'.sqlite3')
            backup_database(self.storage.conn,dest)
            result=engine.apply(self.storage,self.snapshot,self.account.text())
        except Exception as exc:
            QMessageBox.warning(self,"Імпорт не виконано",str(exc));return
        self.reset_preview()
        self.preview.setPlainText(f"Імпортовано нових пінів: {len(result['pins'])}. Пропущено відомих ID: {result['skipped']}. Конфліктів: {len(result['conflicts'])}. Резервна копія створена.")
        self.imported.emit()
