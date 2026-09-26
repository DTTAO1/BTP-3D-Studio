from fastapi.testclient import TestClient
from app.main import app
from pathlib import Path

client = TestClient(app)


def test_health():
    r = client.get('/api/health')
    assert r.status_code == 200
    assert r.json()['version'] == '2.0.0'


def test_analyze_configure_and_exports():
    p = Path(__file__).parents[1] / 'samples' / 'demo_structure.dxf'
    with p.open('rb') as f:
        r = client.post('/api/analyze', files={'file': ('demo_structure.dxf', f, 'application/dxf')})
    assert r.status_code == 200
    data = r.json(); pid = data['project_id']
    c = client.post(f'/api/projects/{pid}/configure', json={'unit_to_m': 1.0, 'category_defaults': {'wall': {'height': 3.0}}})
    assert c.status_code == 200
    assert c.json()['settings']['category_defaults']['wall']['height'] == 3.0
    for endpoint in ['export.xlsx', 'export.csv', 'export.obj', 'export.ifc', 'report.html', 'analysis.json']:
        x = client.get(f'/api/projects/{pid}/{endpoint}')
        assert x.status_code == 200
        assert len(x.content) > 20
