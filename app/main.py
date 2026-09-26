from __future__ import annotations
from pathlib import Path
import importlib.util, json, shutil, uuid
from typing import Any
from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.responses import FileResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
from .engine import analyze, write_result, CATEGORY_META
from .exporter import export_csv, export_ifc, export_obj, export_report_html, export_xlsx
from .advanced import router as advanced_router
ROOT=Path(__file__).resolve().parent.parent; DATA=ROOT/'workspace'; DATA.mkdir(exist_ok=True); MAX_UPLOAD=150*1024*1024
PRODUCT=json.loads((ROOT/'product.json').read_text(encoding='utf-8'))
app=FastAPI(title='BTP 3D Studio',version=PRODUCT['version']); app.mount('/static',StaticFiles(directory=ROOT/'app'/'static'),name='static'); app.include_router(advanced_router)
class ConfigurePayload(BaseModel):
    unit_to_m: float|None=Field(default=None,gt=0,lt=100000); layer_map:dict[str,str]=Field(default_factory=dict); category_defaults:dict[str,dict[str,Any]]=Field(default_factory=dict)
@app.get('/',response_class=HTMLResponse)
def index(): return (ROOT/'app'/'static'/'index.html').read_text(encoding='utf-8')
@app.get('/api/health')
def health():
    return {'ok':True,'version':PRODUCT['version'],'release':PRODUCT['release'],'features':PRODUCT['features'],'feature_labels':PRODUCT['feature_labels'],'connectors':{'PDF / PyMuPDF':bool(importlib.util.find_spec('fitz')),'DXF / ezdxf':bool(importlib.util.find_spec('ezdxf')),'Excel / openpyxl':bool(importlib.util.find_spec('openpyxl')),'IFC / IfcOpenShell':bool(importlib.util.find_spec('ifcopenshell')),'Blender CLI':shutil.which('blender') is not None,'LibreDWG dwg2dxf':shutil.which('dwg2dxf') is not None,'ODM / Docker':shutil.which('docker') is not None}}
@app.post('/api/analyze')
async def api_analyze(file:UploadFile=File(...)):
    filename=Path(file.filename or 'plan').name; suffix=Path(filename).suffix.lower()
    if suffix not in {'.pdf','.dxf','.dwg'}: raise HTTPException(400,'Formats acceptés: PDF, DXF, DWG')
    pid=uuid.uuid4().hex[:10]; pdir=DATA/pid; pdir.mkdir(); path=pdir/filename; size=0
    with path.open('wb') as f:
        while chunk:=await file.read(1024*1024):
            size+=len(chunk)
            if size>MAX_UPLOAD: f.close(); path.unlink(missing_ok=True); raise HTTPException(413,'Fichier trop volumineux (limite 150 Mo)')
            f.write(chunk)
    try: result=analyze(path)
    except Exception as exc: raise HTTPException(422,str(exc)) from exc
    write_result(result,pdir/'analysis.json'); (pdir/'source.json').write_text(json.dumps({'source_name':filename},ensure_ascii=False),encoding='utf-8'); payload=json.loads((pdir/'analysis.json').read_text(encoding='utf-8')); payload['project_id']=pid; return payload
def _load_project(project_id:str):
    if not project_id.isalnum(): raise HTTPException(400,'Identifiant de projet invalide')
    pdir=DATA/project_id; path=pdir/'analysis.json'
    if not path.exists(): raise HTTPException(404,'Projet introuvable')
    return pdir,json.loads(path.read_text(encoding='utf-8'))
def _source_path(pdir:Path):
    meta=pdir/'source.json'
    if meta.exists():
        name=json.loads(meta.read_text(encoding='utf-8')).get('source_name')
        if name and (pdir/name).exists(): return pdir/name
    c=[x for x in pdir.iterdir() if x.suffix.lower() in {'.dxf','.pdf','.dwg'}]
    if not c: raise HTTPException(404,'Fichier source introuvable')
    return c[0]
@app.get('/api/projects/{project_id}/analysis')
def project_analysis(project_id:str): _,d=_load_project(project_id); d['project_id']=project_id; return d
@app.post('/api/projects/{project_id}/configure')
def project_configure(project_id:str,payload:ConfigurePayload):
    pdir,current=_load_project(project_id); source=_source_path(pdir); old=current.get('settings',{}); unit=payload.unit_to_m if payload.unit_to_m is not None else old.get('unit_to_m'); lm=dict(old.get('layer_map',{})); lm.update({l:c for l,c in payload.layer_map.items() if c in CATEGORY_META}); defs=dict(old.get('category_defaults',{}));
    for cat,vals in payload.category_defaults.items():
        if cat in CATEGORY_META and isinstance(vals,dict): defs.setdefault(cat,{}).update(vals)
    result=analyze(source,unit_to_m_override=unit,layer_map=lm,category_defaults=defs); write_result(result,pdir/'analysis.json'); d=json.loads((pdir/'analysis.json').read_text(encoding='utf-8')); d['project_id']=project_id; return d
@app.get('/api/projects/{project_id}/export.xlsx')
def ex1(project_id:str): p,d=_load_project(project_id); out=p/'metres_BTP3D.xlsx'; export_xlsx(d,out); return FileResponse(out,filename=f'BTP3D_{project_id}_metres.xlsx')
@app.get('/api/projects/{project_id}/export.csv')
def ex2(project_id:str): p,d=_load_project(project_id); out=p/'metres_BTP3D.csv'; export_csv(d,out); return FileResponse(out,filename=f'BTP3D_{project_id}_metres.csv')
@app.get('/api/projects/{project_id}/export.obj')
def ex3(project_id:str): p,d=_load_project(project_id); out=p/'modele_BTP3D.obj'; export_obj(d,out); return FileResponse(out,filename=f'BTP3D_{project_id}_modele.obj')
@app.get('/api/projects/{project_id}/export.ifc')
def ex4(project_id:str): p,d=_load_project(project_id); out=p/'modele_BTP3D.ifc'; export_ifc(d,out); return FileResponse(out,filename=f'BTP3D_{project_id}_modele.ifc')
@app.get('/api/projects/{project_id}/report.html')
def ex5(project_id:str): p,d=_load_project(project_id); out=p/'rapport_BTP3D.html'; export_report_html(d,out); return FileResponse(out,filename=f'BTP3D_{project_id}_rapport.html')
@app.get('/api/projects/{project_id}/analysis.json')
def ex6(project_id:str): p,_=_load_project(project_id); return FileResponse(p/'analysis.json',filename=f'BTP3D_{project_id}_analysis.json')
