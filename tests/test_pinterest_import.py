import json
from zipfile import ZipFile
import pytest
from pinterest_os.storage import Storage
from pinterest_os import pinterest_import as importer

@pytest.fixture
def db(tmp_path):
    s=Storage(tmp_path/'test.sqlite3')
    try: yield s
    finally: s.close()

def snapshot():
    return {'account':'ithutir','source':'API_READ','boards':[{'id':'100','name':'Linux'}],
        'pins':[{'id':'987654321012345678','board_id':'100','title':'Own pin',
        'description':'Original copy','link':'https://ithutir.com/tool?utm_source=pint',
        'media_type':'image','media_url':'https://i.pinimg.com/originals/test.jpg','created_at':'2026-01-01'}]}

def test_import_idempotence_and_local_board_reuse(db):
    local=db.create('boards',name='Linux')
    assert len(importer.apply(db,snapshot(),'ithutir')['pins'])==1
    row=db.all('pins')[0]
    assert row['board_id']==local and row['status']=='PUBLISHED'
    assert row['destination_url']==snapshot()['pins'][0]['link']
    assert importer.apply(db,snapshot(),'ithutir')['skipped']==1
    assert len(db.all('pins'))==1 and len(db.all('boards'))==1
    assert db.conn.execute('SELECT remote_id,source FROM pinterest_remote_pins').fetchone()==('987654321012345678','API_READ')
    assert not db.conn.execute('SELECT 1 FROM pin_schedule').fetchone()

def test_conflict_is_not_overwritten(db):
    pid=db.create('pins',title='Own pin',description='Local design')
    plan=importer.apply(db,snapshot(),'ithutir')
    assert plan['conflicts']==['Own pin']
    assert db.get('pins',pid)['description']=='Local design'
    assert len(db.all('pins'))==1

def test_archive_requires_known_manifest(tmp_path):
    file=tmp_path/'download.zip'
    with ZipFile(file,'w') as z:z.writestr('pins.json','[]')
    with pytest.raises(ValueError,match='Невідомий формат'): importer.read_manifest(file)
    data=snapshot();data['format']='ITHutir Pinterest Import v1'
    with ZipFile(file,'w') as z:z.writestr('ithutir_pinterest_import.json',json.dumps(data))
    assert importer.read_manifest(file)['source']=='USER_ARCHIVE'

def test_api_filters_and_account_mismatch():
    calls=[]
    def get(token,endpoint,query=None):
        calls.append((endpoint,dict(query or {})))
        if endpoint=='user_account':return {'username':'ithutir'}
        if endpoint=='boards':return {'items':[{'id':'100','name':'Linux','privacy':'PUBLIC','owner':{'username':'ithutir'}},
                {'id':'101','name':'Secret','privacy':'SECRET','owner':{'username':'ithutir'}}]}
        assert query['pin_filter']=='exclude_repins'
        if 'bookmark' not in query:
            return {'items':[{'id':'1','board_id':'100','title':'Good','media':{'media_type':'image','images':{'originals':{'width':1000,'url':'https://i.pinimg.com/test.jpg'}}}},
                             {'id':'2','board_id':'100','parent_pin_id':'4'},{'id':'3','board_id':'101'}],
                    'bookmark':'next'}
        return {'items':[{'id':'4','board_id':'100','is_removable':True},{'id':'5','board_id':'100','is_owner':False}]}
    with pytest.raises(ValueError,match='іншому акаунту'):importer.fetch_snapshot('test','different',get)
    result=importer.fetch_snapshot('test','ithutir',get)
    assert [p['id'] for p in result['pins']]==['1']
    assert result['pins'][0]['media_url']=='https://i.pinimg.com/test.jpg'
    assert result['boards'][0]['id']=='100'

def test_bad_id_rolls_back(db):
    data=snapshot();data['pins'].append(dict(data['pins'][0],id=123))
    with pytest.raises(ValueError):importer.apply(db,data,'ithutir')
    assert not db.all('pins') and not db.all('boards')
