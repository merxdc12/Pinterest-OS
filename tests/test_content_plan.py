"""Local unified content plan regression tests. No network or live workspace."""
from datetime import datetime
from urllib.parse import urlsplit, parse_qs
from unittest.mock import patch
import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
import pytest
from PyQt6.QtCore import QDate
from PyQt6.QtGui import QImage, QColor
from PyQt6.QtWidgets import QApplication, QMessageBox
from pinterest_os.storage import Storage
from pinterest_os import content_plan as plan
from pinterest_os.calendar import CalendarPage, ScheduleDialog
from pinterest_os.publishing import PublishingPage

@pytest.fixture
def workspace(tmp_path):
    app=QApplication.instance() or QApplication([])
    db=Storage(tmp_path/'plan.sqlite3')
    a=db.create('boards',name='Electronics')
    b=db.create('boards',name='Linux')
    pins=[]
    for i,color in enumerate(('#123456','#abcdef','#123456')):
        pid=db.create('pins',title=f'Pin {i}',description='An engineering guide',
                      destination_url='https://ithutir.com/guide',board_id=a)
        path=tmp_path/f'pin{i}.png'
        img=QImage(1000,1500,QImage.Format.Format_RGB32)
        img.fill(QColor(color))
        assert img.save(str(path))
        db.save_pin_design(pid,'{"version":1}',str(path))
        pins.append(pid)
    carousel=db.create_carousel('Carousel')
    db.set_carousel_slides(carousel,pins[:2])
    try: yield app,db,a,b,pins,carousel
    finally: db.close()

def test_pin_and_carousel_plan_and_tracking(workspace):
    app,db,a,b,pins,carousel=workspace
    url='https://ithutir.com/product?x=1'
    pid=plan.save(db,'PIN',pins[0],'2026-11-25T10:00',b,url,status='READY')
    cid=plan.save(db,'CAROUSEL',carousel,'2026-11-25T11:00',a,url,
                  description='Carousel guide',status='READY')
    assert pid>0 and cid<0
    assert len(plan.entries(db,'2026-11-01','2026-11-30'))==2
    assert plan.entries(db,'2026-11-01','2026-11-30',b)[0]['id']==pid
    assert db.get('pins',pins[0])['board_id']==a
    assert db.get('pins',pins[0])['destination_url']=='https://ithutir.com/guide'
    first,second=plan.get_entry(db,pid),plan.get_entry(db,cid)
    assert first['tracking_code']!=second['tracking_code']
    query=parse_qs(urlsplit(first['destination_url']).query)
    assert query['x']==['1'] and query['utm_source']==['pint']
    assert query['utm_content']==[first['tracking_code']]
    plan.move(db,cid,'2026-11-26T11:00')
    assert plan.get_entry(db,cid)['scheduled_at']=='2026-11-26T11:00'
    assert len(plan.queue(db,datetime(2026,11,25,10,30)))==1
    plan.confirm(db,cid)
    assert plan.get_entry(db,cid)['status']=='PUBLISHED'
    assert db.get('pins',pins[1])['status']=='DRAFT'
    plan.confirm(db,pid)
    assert db.get('pins',pins[0])['status']=='PUBLISHED'
    with pytest.raises(ValueError): plan.confirm(db,pid)

def test_external_url_untouched_and_disclosure_gate(workspace):
    app,db,a,b,pins,carousel=workspace
    url='https://partner.example/item?tag=abc'
    with pytest.raises(ValueError,match='UTM'):
        plan.save(db,'CAROUSEL',carousel,'2026-11-25T10:00',a,url)
    with pytest.raises(ValueError,match='reviewed'):
        plan.save(db,'CAROUSEL',carousel,'2026-11-25T10:00',a,url,'Guide',
                  add_utm=False,status='READY')
    assert plan.entries(db,'2026-11-01','2026-11-30')==[]
    with pytest.raises(ValueError,match='disclosure'):
        plan.save(db,'CAROUSEL',carousel,'2026-11-25T10:00',a,url,'Guide',
                  add_utm=False,external_review=True,affiliate=True,disclosure='Affiliate link',status='READY')
    cid=plan.save(db,'CAROUSEL',carousel,'2026-11-25T10:00',a,url,'Guide. Affiliate link.',
                  add_utm=False,external_review=True,affiliate=True,disclosure='Affiliate link',status='READY')
    assert plan.get_entry(db,cid)['destination_url']==url

def test_duplicate_and_readiness_and_cancel(workspace):
    app,db,a,b,pins,carousel=workspace
    url='https://ithutir.com/guide'
    pid=plan.save(db,'PIN',pins[0],'2026-11-25T10:00',a,url,status='READY')
    with pytest.raises(ValueError,match='duplicate'):
        plan.save(db,'PIN',pins[2],'2026-11-25T11:00',a,url,status='READY')
    assert len(plan.entries(db,'2026-11-01','2026-11-30'))==1
    before=plan.get_entry(db,pid)['tracking_code']
    plan.save(db,'PIN',pins[0],'2026-11-26T10:00',b,url,entry_id=pid,status='READY')
    assert plan.get_entry(db,pid)['tracking_code']==before
    plan.remove(db,pid)
    assert plan.get_entry(db,pid)['status']=='CANCELLED'
    assert db.get('pins',pins[0])
    assert not plan.queue(db,datetime(2026,11,27))

def test_legacy_calendar_stays_and_carousel_ui(workspace):
    app,db,a,b,pins,carousel=workspace
    legacy=db.create_schedule(pins[0],'2026-11-25T10:00')
    assert plan.get_entry(db,legacy)['details_id'] is None
    dialog=ScheduleDialog(db,QDate(2026,11,25),kind='CAROUSEL',content_id=carousel)
    dialog.board.setCurrentIndex(dialog.board.findData(b))
    dialog.url.setText('https://ithutir.com/guide')
    dialog.description.setPlainText('Carousel guide')
    dialog.state.setCurrentIndex(dialog.state.findData('READY'))
    dialog.save()
    assert dialog.result()==1
    page=CalendarPage(db)
    page.calendar.setSelectedDate(QDate(2026,11,25))
    page.view.setCurrentIndex(page.view.findData('List'))
    assert page.grid.rowCount()==2
    page.kind_filter.setCurrentIndex(page.kind_filter.findData('CAROUSEL'))
    assert page.grid.rowCount()==1
    assert page.grid.item(0,5).text()=='Карусель'
    queue=PublishingPage(db)
    # Queue uses local clock; verify row rendering with an explicit due date.
    with patch('pinterest_os.publishing.plan.queue',return_value=plan.queue(db,datetime(2026,11,26))):
        queue.refresh()
    assert queue.table.rowCount()==2
    queue.close()
    page.close()



def test_existing_workspace_backup_and_restart(tmp_path):
    import sqlite3
    path=tmp_path/'old.sqlite3'
    db=Storage(path)
    pin=db.create('pins',title='Preserve me')
    sid=db.create_schedule(pin,'2026-12-01T10:00')
    # Simulate a pre-plan schema in the temporary test database only.
    with db.conn:
        db.conn.execute('DROP TABLE plan_details')
        db.conn.execute('DROP TABLE carousel_schedule')
    db.close()
    migrated=Storage(path)
    try:
        backup=migrated.content_plan_backup
        assert backup and backup.is_file()
        with sqlite3.connect(backup) as old:
            assert old.execute('SELECT title FROM pins WHERE id=?',(pin,)).fetchone()[0]=='Preserve me'
            assert old.execute("SELECT 1 FROM sqlite_master WHERE name='plan_details'").fetchone() is None
        assert plan.get_entry(migrated,sid)['title']=='Preserve me'
    finally:
        migrated.close()
    reopened=Storage(path)
    try:
        assert reopened.content_plan_backup is None
        assert plan.get_entry(reopened,sid)['title']=='Preserve me'
    finally:
        reopened.close()


def test_tracking_export_and_tamper_gate(workspace):
    from pinterest_os.sheets_exchange import export_tracking_rows
    app, db, a, b, pins, carousel = workspace
    url = "https://ithutir.com/guide"
    pid = plan.save(db, "PIN", pins[0], "2026-11-25T10:00", a, url, status="READY")
    row = plan.get_entry(db, pid)
    records = export_tracking_rows(db)
    assert len(records) == 1
    assert records[0]["tracking_code"] == row["tracking_code"]
    assert records[0]["utm_source"] == "pint"
    assert records[0]["original_url"] == url
    assert records[0]["local_status"] == "READY"
    with db.conn:
        db.conn.execute("UPDATE pin_tracking SET marketing_url=? WHERE id=?",
                        (row["marketing_url"].replace("utm_source=pint", "utm_source=tik"), row["tracking_id"]))
    assert any("UTM" in x for x in plan.issues(db, plan.get_entry(db, pid)))
    with pytest.raises(ValueError, match="UTM"):
        plan.confirm(db, pid)


def test_reschedule_cancel_delete_preserve_library_and_tracking(workspace):
    app,db,a,b,pins,carousel=workspace
    url='https://ithutir.com/guide'
    pid=plan.save(db,'PIN',pins[0],'2026-11-25T10:00',a,url,status='READY')
    cid=plan.save(db,'CAROUSEL',carousel,'2026-11-25T11:00',b,url,'Guide',status='READY')
    for entry_id in (pid,cid):
        before=plan.get_entry(db,entry_id)
        page=CalendarPage(db)
        page.calendar.setSelectedDate(QDate(2026,11,25))
        assert page.reschedule_entry(before,'2026-11-26T15:45')
        after=plan.get_entry(db,entry_id)
        assert after['scheduled_at']=='2026-11-26T15:45'
        assert {k:v for k,v in before.items() if k!='scheduled_at'}=={k:v for k,v in after.items() if k!='scheduled_at'}
        page.close()
        plan.remove(db,entry_id)
        assert plan.get_entry(db,entry_id)['status']=='CANCELLED'
        assert not any(r['id']==entry_id for r in plan.queue(db,datetime(2026,11,27)))
        plan.delete_entry(db,entry_id)
        assert plan.get_entry(db,entry_id) is None
        assert db.conn.execute('SELECT 1 FROM pin_tracking WHERE id=?',(before['tracking_id'],)).fetchone()
    assert db.get('pins',pins[0])
    assert db.get_pin_design(pins[0])
    assert len(db.carousel_slides(carousel))==2
    assert not plan.entries(db,'2026-11-01','2026-11-30')


def test_delete_pending_and_protect_published(workspace):
    app,db,a,b,pins,carousel=workspace
    url='https://ithutir.com/guide'
    pid=plan.save(db,'PIN',pins[0],'2026-11-25T10:00',a,url)
    plan.delete_entry(db,pid)
    assert plan.get_entry(db,pid) is None
    cid=plan.save(db,'CAROUSEL',carousel,'2026-11-25T11:00',a,url,'Guide',status='READY')
    plan.confirm(db,cid)
    with pytest.raises(ValueError): plan.delete_entry(db,cid)
    with pytest.raises(ValueError): plan.remove(db,cid)
    assert plan.get_entry(db,cid)['status']=='PUBLISHED'


def test_action_buttons_and_confirmation(workspace):
    app,db,a,b,pins,carousel=workspace
    pid=plan.save(db,'PIN',pins[0],'2026-11-25T10:00',a,'https://ithutir.com/guide')
    page=CalendarPage(db)
    page.calendar.setSelectedDate(QDate(2026,11,25))
    page.grid.clearSelection()
    assert not page.cancel_button.isEnabled()
    page.grid.selectRow(0)
    assert page.cancel_button.isEnabled() and page.delete_button.isEnabled() and page.reschedule_button.isEnabled()
    with patch.object(QMessageBox,'question',return_value=QMessageBox.StandardButton.No):
        page.delete_button.click()
    assert plan.get_entry(db,pid)['status']=='PLANNED'
    with patch.object(QMessageBox,'question',return_value=QMessageBox.StandardButton.Yes):
        page.cancel_button.click()
    assert plan.get_entry(db,pid)['status']=='CANCELLED'
    page.grid.selectRow(0)
    assert not page.cancel_button.isEnabled() and not page.reschedule_button.isEnabled()
    assert page.delete_button.isEnabled()
    with patch.object(QMessageBox,'question',return_value=QMessageBox.StandardButton.Yes):
        page.delete_button.click()
    assert plan.get_entry(db,pid) is None
    assert page.grid.rowCount()==0
    assert db.get('pins',pins[0])
    page.close()


def test_ukrainian_labels_preserve_internal_status(workspace):
    from PyQt6.QtWidgets import QPushButton, QDialogButtonBox
    from pinterest_os.i18n_uk import apply_language
    app,db,a,b,pins,carousel=workspace
    pid=plan.save(db,'PIN',pins[0],'2026-11-25T10:00',a,'https://ithutir.com/guide',status='READY')
    page=CalendarPage(db)
    page.calendar.setSelectedDate(QDate(2026,11,25))
    apply_language(page,'uk')
    assert page.today.text()=='Сьогодні'
    assert page.board.itemText(0)=='Усі дошки'
    assert {'РЕДАГУВАТИ','ПЕРЕВІРИТИ ГОТОВНІСТЬ'} <= {w.text() for w in page.findChildren(QPushButton)}
    page.status_filter.setCurrentIndex(page.status_filter.findData('READY'))
    assert page.status_filter.currentText()=='Готово'
    assert page.grid.rowCount()==1 and page.grid.item(0,4).text()=='Готово'
    assert page.grid.item(0,4).toolTip()=='READY'
    assert plan.get_entry(db,pid)['status']=='READY'
    dialog=ScheduleDialog(db,QDate(2026,11,25),entry=plan.get_entry(db,pid))
    assert dialog.state.currentText()=='Готово' and dialog.state.currentData()=='READY'
    buttons=QDialogButtonBox(QDialogButtonBox.StandardButton.Yes|QDialogButtonBox.StandardButton.No)
    assert buttons.button(QDialogButtonBox.StandardButton.Yes).text().replace('&','')=='Так'
    apply_language(page,'en')
    page.close()
