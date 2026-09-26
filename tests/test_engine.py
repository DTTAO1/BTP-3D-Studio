from pathlib import Path
from app.engine import analyze, classify_layer


def test_classification_and_override():
    assert classify_layer('MUR_AGGLOS')[0] == 'wall'
    assert classify_layer('SEMELLE_BETON')[0] == 'foundation'
    assert classify_layer('XXX')[0] == 'other'
    assert classify_layer('XXX', {'XXX': 'slab'})[0] == 'slab'


def test_demo_dxf_and_recalculation():
    p = Path(__file__).parents[1] / 'samples' / 'demo_structure.dxf'
    r = analyze(p)
    assert r.kind == 'DXF'
    assert r.summary['entities'] > 0
    assert any(x['category'] == 'wall' for x in r.quantities)
    r2 = analyze(p, category_defaults={'wall': {'height': 3.2}})
    wall = next(x for x in r2.quantities if x['category'] == 'wall')
    assert wall['surface_m2'] > 0
    assert r2.settings['category_defaults']['wall']['height'] == 3.2
