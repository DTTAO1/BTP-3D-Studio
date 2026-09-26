from __future__ import annotations

from collections import Counter
from copy import deepcopy
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any
import json
import math
import re

try:
    import ezdxf
except Exception:  # pragma: no cover
    ezdxf = None

try:
    import fitz
except Exception:  # pragma: no cover
    fitz = None


CATEGORY_META = {
    "foundation": {"label": "Fondations / longrines", "material": "Béton fondation", "width": 0.50, "height": 0.25},
    "slab": {"label": "Dallages / dalles", "material": "Béton superstructure", "thickness": 0.15},
    "column": {"label": "Poteaux / raidisseurs", "material": "Béton armé", "width": 0.20, "depth": 0.20, "height": 2.80},
    "beam": {"label": "Poutres / linteaux / chaînages", "material": "Béton armé", "width": 0.20, "height": 0.40},
    "wall": {"label": "Murs / maçonnerie", "material": "Maçonnerie", "thickness": 0.20, "height": 2.80},
    "fill": {"label": "Remblais", "material": "Remblai grave", "thickness": 0.30},
    "opening": {"label": "Ouvertures", "material": "Ouverture", "height": 2.10, "width": 0.90},
    "other": {"label": "Non classé", "material": "Non classé"},
}

LAYER_RULES = [
    (r"semelle|fondation|radier|longrine", "foundation"),
    (r"dallage|dalle|plancher", "slab"),
    (r"poteau|raidisseur", "column"),
    (r"poutre|linteau|chainage|cha[iî]nage", "beam"),
    (r"mur|voile|agglo|parpaing|moellon", "wall"),
    (r"remblai|grave", "fill"),
    (r"ouverture|porte|fen[eê]tre", "opening"),
]

DXF_UNITS = {
    0: ("unité non définie", None),
    1: ("pouce", 0.0254),
    2: ("pied", 0.3048),
    4: ("mm", 0.001),
    5: ("cm", 0.01),
    6: ("m", 1.0),
    7: ("km", 1000.0),
}


def merged_defaults(overrides: dict[str, Any] | None = None) -> dict[str, Any]:
    out = deepcopy(CATEGORY_META)
    if not overrides:
        return out
    for cat, vals in overrides.items():
        if cat not in out or not isinstance(vals, dict):
            continue
        for key, value in vals.items():
            if key in {"label", "material"}:
                out[cat][key] = str(value)
            elif key in {"width", "height", "depth", "thickness"}:
                try:
                    v = float(value)
                except (TypeError, ValueError):
                    continue
                if 0 < v < 100:
                    out[cat][key] = v
    return out


def classify_layer(name: str, layer_map: dict[str, str] | None = None) -> tuple[str, str, str]:
    if layer_map and name in layer_map and layer_map[name] in CATEGORY_META:
        cat = layer_map[name]
        meta = CATEGORY_META[cat]
        return cat, meta["label"], meta["material"]
    n = (name or "").lower()
    for rx, cat in LAYER_RULES:
        if re.search(rx, n):
            meta = CATEGORY_META[cat]
            return cat, meta["label"], meta["material"]
    meta = CATEGORY_META["other"]
    return "other", meta["label"], meta["material"]


@dataclass
class AnalysisResult:
    file: str
    kind: str
    summary: dict[str, Any]
    preview: dict[str, Any]
    quantities: list[dict[str, Any]]
    warnings: list[str]
    settings: dict[str, Any]


def _polyline_length(points: list[tuple[float, float]], closed: bool = False) -> float:
    total = sum(math.hypot(b[0] - a[0], b[1] - a[1]) for a, b in zip(points, points[1:]))
    if closed and len(points) > 2:
        total += math.hypot(points[0][0] - points[-1][0], points[0][1] - points[-1][1])
    return total


def _polygon_area(points: list[tuple[float, float]]) -> float:
    if len(points) < 3:
        return 0.0
    return abs(sum(a[0] * b[1] - b[0] * a[1] for a, b in zip(points, points[1:] + points[:1]))) / 2.0


def _quantity_record(
    cat: str,
    count: int,
    length_units: float,
    area_units2: float,
    factor_m: float | None,
    defaults: dict[str, Any],
) -> dict[str, Any]:
    meta = defaults[cat]
    rec: dict[str, Any] = {
        "category": cat,
        "label": meta["label"],
        "material": meta["material"],
        "count": count,
        "linear_drawing_units": round(length_units, 3),
        "area_drawing_units2": round(area_units2, 3),
    }
    if factor_m:
        length_m = length_units * factor_m
        area_m2 = area_units2 * factor_m * factor_m
        rec["length_m"] = round(length_m, 3)
        rec["area_m2"] = round(area_m2, 3)
        if cat == "foundation":
            rec["volume_m3"] = round(length_m * meta.get("width", 0.50) * meta.get("height", 0.25), 3)
        elif cat == "wall":
            rec["surface_m2"] = round(length_m * meta.get("height", 2.80), 3)
            rec["volume_m3"] = round(length_m * meta.get("height", 2.80) * meta.get("thickness", 0.20), 3)
        elif cat == "beam":
            rec["volume_m3"] = round(length_m * meta.get("width", 0.20) * meta.get("height", 0.40), 3)
        elif cat == "column":
            rec["volume_m3"] = round(count * meta.get("width", 0.20) * meta.get("depth", 0.20) * meta.get("height", 2.80), 3)
        elif cat == "slab":
            rec["volume_m3"] = round(area_m2 * meta.get("thickness", 0.15), 3)
        elif cat == "fill":
            rec["volume_m3"] = round(area_m2 * meta.get("thickness", 0.30), 3)
    return rec


def analyze_dxf(
    path: Path,
    *,
    unit_to_m_override: float | None = None,
    layer_map: dict[str, str] | None = None,
    category_defaults: dict[str, Any] | None = None,
) -> AnalysisResult:
    if ezdxf is None:
        raise RuntimeError("ezdxf non disponible")
    doc = ezdxf.readfile(path)
    msp = doc.modelspace()
    defaults = merged_defaults(category_defaults)
    types: Counter[str] = Counter()
    layers: Counter[str] = Counter()
    cat_lengths: Counter[str] = Counter()
    cat_areas: Counter[str] = Counter()
    cat_counts: Counter[str] = Counter()
    points: list[tuple[float, float]] = []
    entities: list[dict[str, Any]] = []

    insunits = int(doc.header.get("$INSUNITS", 0) or 0)
    unit_name, detected_factor_m = DXF_UNITS.get(insunits, (f"code {insunits}", None))
    factor_m = unit_to_m_override if unit_to_m_override and unit_to_m_override > 0 else detected_factor_m
    if unit_to_m_override and unit_to_m_override > 0:
        unit_name = f"calibrée ({unit_to_m_override:g} m/unité)"

    def add_pt(x: float, y: float) -> None:
        if math.isfinite(x) and math.isfinite(y):
            points.append((float(x), float(y)))

    for e in msp:
        t = e.dxftype()
        types[t] += 1
        layer = getattr(e.dxf, "layer", "0")
        layers[layer] += 1
        cat, _, _ = classify_layer(layer, layer_map)
        cat_counts[cat] += 1
        length = 0.0
        area = 0.0
        geom = None
        try:
            if t == "LINE":
                a = e.dxf.start
                b = e.dxf.end
                add_pt(a.x, a.y)
                add_pt(b.x, b.y)
                length = math.hypot(b.x - a.x, b.y - a.y)
                geom = {"type": "line", "a": [a.x, a.y], "b": [b.x, b.y], "cat": cat, "layer": layer}
            elif t in ("LWPOLYLINE", "POLYLINE"):
                if t == "LWPOLYLINE":
                    arr = [(float(p[0]), float(p[1])) for p in e.get_points("xy")]
                    closed = bool(e.closed)
                else:
                    arr = [(float(v.dxf.location.x), float(v.dxf.location.y)) for v in e.vertices]
                    closed = bool(e.is_closed)
                for p in arr:
                    add_pt(*p)
                length = _polyline_length(arr, closed)
                if closed:
                    area = _polygon_area(arr)
                geom = {"type": "polyline", "points": arr, "closed": closed, "cat": cat, "layer": layer}
            elif t == "CIRCLE":
                c = e.dxf.center
                r = float(e.dxf.radius)
                add_pt(c.x - r, c.y - r)
                add_pt(c.x + r, c.y + r)
                length = 2 * math.pi * r
                area = math.pi * r * r
                geom = {"type": "circle", "c": [c.x, c.y], "r": r, "cat": cat, "layer": layer}
            elif t == "ARC":
                c = e.dxf.center
                r = float(e.dxf.radius)
                add_pt(c.x - r, c.y - r)
                add_pt(c.x + r, c.y + r)
                span = (float(e.dxf.end_angle) - float(e.dxf.start_angle)) % 360
                length = 2 * math.pi * r * span / 360
            elif t in ("TEXT", "MTEXT"):
                try:
                    pos = e.dxf.insert
                    add_pt(pos.x, pos.y)
                except Exception:
                    pass
        except Exception:
            pass
        if length:
            cat_lengths[cat] += length
        if area:
            cat_areas[cat] += area
        if geom and len(entities) < 12000:
            entities.append(geom)

    if points:
        xs = [p[0] for p in points]
        ys = [p[1] for p in points]
        bbox = [min(xs), min(ys), max(xs), max(ys)]
    else:
        bbox = [0, 0, 1, 1]

    categories = sorted(set(cat_counts) | set(cat_lengths) | set(cat_areas))
    quantities = [_quantity_record(cat, cat_counts[cat], cat_lengths[cat], cat_areas[cat], factor_m, defaults) for cat in categories]
    warnings: list[str] = []
    if all(classify_layer(k, layer_map)[0] == "other" for k in layers):
        warnings.append("Aucun calque métier reconnu : utilisez le mapping des calques pour classer le plan.")
    if factor_m is None:
        warnings.append("Unité DXF non définie : renseignez l'échelle pour obtenir les métrés en mètres.")

    layer_categories = {layer: classify_layer(layer, layer_map)[0] for layer in layers}
    settings = {
        "unit": unit_name,
        "unit_to_m": factor_m,
        "detected_unit_to_m": detected_factor_m,
        "category_defaults": defaults,
        "layer_map": layer_categories,
    }
    return AnalysisResult(
        path.name,
        "DXF",
        {
            "entities": sum(types.values()),
            "entity_types": dict(types),
            "layers": dict(layers),
            "bbox": bbox,
            "dxf_version": doc.dxfversion,
            "drawing_unit": unit_name,
            "unit_to_m": factor_m,
        },
        {"bbox": bbox, "entities": entities, "source": "dxf"},
        quantities,
        warnings,
        settings,
    )


def analyze_pdf(
    path: Path,
    *,
    unit_to_m_override: float | None = None,
    category_defaults: dict[str, Any] | None = None,
) -> AnalysisResult:
    if fitz is None:
        raise RuntimeError("PyMuPDF non disponible")
    defaults = merged_defaults(category_defaults)
    doc = fitz.open(path)
    pages = []
    total_drawings = 0
    total_text = 0
    preview_entities: list[dict[str, Any]] = []
    preview_bbox = [0.0, 0.0, 1.0, 1.0]

    for i, p in enumerate(doc):
        drawings = p.get_drawings()
        text = p.get_text("text")
        total_drawings += len(drawings)
        total_text += len(text.strip())
        pages.append({
            "page": i + 1,
            "width_pt": round(p.rect.width, 1),
            "height_pt": round(p.rect.height, 1),
            "vector_paths": len(drawings),
            "text_chars": len(text.strip()),
        })
        if i == 0:
            preview_bbox = [0.0, 0.0, float(p.rect.width), float(p.rect.height)]
            for d in drawings[:3500]:
                for item in d.get("items", []):
                    op = item[0]
                    try:
                        if op == "l":
                            a, b = item[1], item[2]
                            preview_entities.append({"type": "line", "a": [a.x, a.y], "b": [b.x, b.y], "cat": "other", "layer": "PDF"})
                        elif op == "re":
                            r = item[1]
                            preview_entities.append({
                                "type": "polyline",
                                "points": [[r.x0, r.y0], [r.x1, r.y0], [r.x1, r.y1], [r.x0, r.y1]],
                                "closed": True,
                                "cat": "other",
                                "layer": "PDF",
                            })
                    except Exception:
                        continue
                    if len(preview_entities) >= 12000:
                        break
                if len(preview_entities) >= 12000:
                    break

    vector = total_drawings > 10
    warnings: list[str] = []
    if not vector:
        warnings.append("PDF probablement raster/scanné : une vectorisation ou une lecture vision sera nécessaire.")
    else:
        warnings.append("PDF vectoriel détecté : aperçu disponible. La classification automatique reste limitée sans calques CAO.")
    if unit_to_m_override is None:
        warnings.append("Renseignez l'échelle PDF si vous souhaitez convertir les unités de dessin en mètres.")

    return AnalysisResult(
        path.name,
        "PDF",
        {
            "pages": len(doc),
            "page_details": pages,
            "vector_paths": total_drawings,
            "text_chars": total_text,
            "pdf_mode": "vectoriel" if vector else "raster/mixte",
            "drawing_unit": "points PDF",
            "unit_to_m": unit_to_m_override,
        },
        {"bbox": preview_bbox, "entities": preview_entities, "source": "pdf", "y_down": True},
        [],
        warnings,
        {"unit": "points PDF", "unit_to_m": unit_to_m_override, "detected_unit_to_m": None, "category_defaults": defaults, "layer_map": {"PDF": "other"}},
    )


def analyze(
    path: Path,
    *,
    unit_to_m_override: float | None = None,
    layer_map: dict[str, str] | None = None,
    category_defaults: dict[str, Any] | None = None,
) -> AnalysisResult:
    suffix = path.suffix.lower()
    if suffix == ".dxf":
        return analyze_dxf(path, unit_to_m_override=unit_to_m_override, layer_map=layer_map, category_defaults=category_defaults)
    if suffix == ".pdf":
        return analyze_pdf(path, unit_to_m_override=unit_to_m_override, category_defaults=category_defaults)
    if suffix == ".dwg":
        return AnalysisResult(
            path.name,
            "DWG",
            {"status": "conversion_required"},
            {"bbox": [0, 0, 1, 1], "entities": [], "source": "dwg"},
            [],
            ["DWG : conversion locale vers DXF requise (LibreDWG/ODA). Le fichier est conservé dans le projet."],
            {"unit": "inconnue", "unit_to_m": unit_to_m_override, "detected_unit_to_m": None, "category_defaults": merged_defaults(category_defaults), "layer_map": {}},
        )
    raise ValueError(f"Format non pris en charge: {suffix}")


def write_result(result: AnalysisResult, out: Path) -> None:
    out.write_text(json.dumps(asdict(result), ensure_ascii=False, indent=2), encoding="utf-8")
