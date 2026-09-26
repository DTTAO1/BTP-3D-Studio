from pathlib import Path
import json,re

def test_product_manifest():
    p=json.loads((Path(__file__).resolve().parents[1]/'product.json').read_text(encoding='utf-8'))
    assert p['version'] and p['features']

def test_ui_accessibility_basics():
    h=(Path(__file__).resolve().parents[1]/'app/static/index.html').read_text(encoding='utf-8')
    assert 'viewport' in h and '@media' in h
    assert 'Importer un plan' in h and 'Métrés du projet' in h
    assert h.count('<button') >= 8

def test_ui_information_architecture():
    h=(Path(__file__).resolve().parents[1]/'app/static/index.html').read_text(encoding='utf-8')
    for term in ['Projet','Ouvrages','Propriétés','Actions rapides','Plan 2D','Maquette 3D']:
        assert term in h
