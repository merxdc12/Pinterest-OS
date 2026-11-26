from datetime import datetime, timezone
from unittest.mock import patch
import pytest
from pinterest_os import pinterest_credentials as keys

class MemoryStore:
    def __init__(self): self.data={}
    def get_password(self,s,k): return self.data.get((s,k))
    def set_password(self,s,k,v): self.data[s,k]=v
    def delete_password(self,s,k): del self.data[s,k]

def test_secure_store_roundtrip_and_isolation():
    backend=MemoryStore()
    record=dict(access_token='test-only',app_secret='test-secret',refresh_token='test-refresh',expires_at='2030-01-01T00:00:00+01:00')
    keys.save('ithutir','1645174',record,backend)
    assert keys.load('ITHutir','1645174',backend)==record
    assert keys.load('other','1645174',backend) is None
    assert keys.load('ithutir','1645175',backend) is None
    keys.delete('ithutir','1645174',backend)
    assert keys.load('ithutir','1645174',backend) is None

def test_expiration_and_validation():
    now=datetime(2026,11,26,tzinfo=timezone.utc)
    assert keys.ensure_current(dict(access_token='fake',expires_at='2026-11-27T00:00+01:00'),now)=='fake'
    with pytest.raises(ValueError,match='прострочений'):
        keys.ensure_current(dict(access_token='fake',expires_at='2026-11-25T00:00+01:00'),now)
    with pytest.raises(ValueError): keys.validated(dict(access_token='fake',expires_at='2026-11-27T12:00'))
    with pytest.raises(ValueError): keys.validated(dict(access_token='fake token'))
    with pytest.raises(ValueError): keys.identity('ithutir','../wrong')

def test_backend_failure_does_not_leak_secret():
    class Failing(MemoryStore):
        def set_password(self,s,k,v): raise RuntimeError(v)
    with pytest.raises(ValueError) as exc:
        keys.save('ithutir','1645174',dict(access_token='do-not-print'),Failing())
    assert 'do-not-print' not in str(exc.value)

def test_import_page_uses_saved_keys(tmp_path):
    from PyQt6.QtWidgets import QApplication,QLineEdit,QMessageBox
    from pinterest_os.storage import Storage
    from pinterest_os.pinterest_import_page import PinterestImportPage
    app=QApplication.instance() or QApplication([])
    storage=Storage(tmp_path/'workspace.sqlite3')
    backend=MemoryStore()
    try:
        with patch.object(keys,'backend',return_value=backend):
            page=PinterestImportPage(storage)
            assert page.token.echoMode()==QLineEdit.EchoMode.Password
            page.token.setText('test-only')
            page.app_secret.setText('test-secret')
            page.save_keys()
            assert page.token.text()=='' and page.app_secret.text()==''
            assert keys.load('ithutir','1645174')['access_token']=='test-only'
            page.load_keys()
            assert page.token.text()=='test-only'
            page.account.setText('other')
            assert page.token.text()==''
            page.account.setText('ithutir')
            with patch.object(QMessageBox,'question',return_value=QMessageBox.StandardButton.Yes):
                page.disconnect_keys()
            assert keys.load('ithutir','1645174') is None
            page.close()
    finally:
        storage.close()
