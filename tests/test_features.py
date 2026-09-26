from fastapi.testclient import TestClient
from pathlib import Path
from app.main import app
client=TestClient(app)

def _pid():
    p=Path(__file__).parents[1]/'samples'/'demo_structure.dxf'
    with p.open('rb') as f: r=client.post('/api/analyze',files={'file':('demo_structure.dxf',f,'application/dxf')})
    assert r.status_code==200
    return r.json()['project_id']

def test_active_features():
    pid=_pid()
    feats=client.get('/api/health').json()['features']
    if 'calibration' in feats: assert client.post(f'/api/projects/{pid}/calibrate',json={'pixel_distance':100,'real_distance_m':10}).status_code==200
    if 'recognition' in feats: assert client.get(f'/api/projects/{pid}/recognition').status_code==200
    if 'model3d' in feats: assert client.get(f'/api/projects/{pid}/model3d').status_code==200
    if 'takeoff' in feats: assert client.get(f'/api/projects/{pid}/takeoff').status_code==200
    if 'ifc_bim' in feats: assert client.get(f'/api/projects/{pid}/bim').status_code==200
    if 'phasing' in feats: assert client.post(f'/api/projects/{pid}/phases',json={'category_phases':{}}).status_code==200
    if 'costing' in feats: assert client.post(f'/api/projects/{pid}/cost',json={'prices':{}}).status_code==200
    if 'assistant' in feats:
        assert client.post(f'/api/projects/{pid}/assistant',json={'command':'volume beton'}).status_code==200
        assert client.get(f'/api/projects/{pid}/qa').status_code==200
