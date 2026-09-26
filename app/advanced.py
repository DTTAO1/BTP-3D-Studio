from __future__ import annotations
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
from pathlib import Path
from typing import Any
import json, math, re

router=APIRouter(prefix='/api')

class CalibrationPayload(BaseModel):
    pixel_distance: float = Field(gt=0)
    real_distance_m: float = Field(gt=0)

class PhasePayload(BaseModel):
    category_phases: dict[str,int] = Field(default_factory=dict)

class CostPayload(BaseModel):
    prices: dict[str,float] = Field(default_factory=dict)

class AssistantPayload(BaseModel):
    command: str

def _features():
    return set(json.loads((Path(__file__).resolve().parent.parent/'product.json').read_text(encoding='utf-8'))['features'])

def _require(name):
    if name not in _features(): raise HTTPException(404, 'Fonction disponible dans une version ultérieure')

def _project(root, pid):
    if not pid.isalnum(): raise HTTPException(400,'Projet invalide')
    p=root/'workspace'/pid/'analysis.json'
    if not p.exists(): raise HTTPException(404,'Projet introuvable')
    return p, json.loads(p.read_text(encoding='utf-8'))

@router.post('/projects/{pid}/calibrate')
def calibrate(pid:str, payload:CalibrationPayload):
    _require('calibration')
    from .main import ROOT
    p,d=_project(ROOT,pid)
    factor=payload.real_distance_m/payload.pixel_distance
    d.setdefault('settings',{})['unit_to_m']=factor
    d['settings']['calibration']={'method':'two_points','pixel_distance':payload.pixel_distance,'real_distance_m':payload.real_distance_m,'factor_m_per_unit':factor}
    p.write_text(json.dumps(d,ensure_ascii=False,indent=2),encoding='utf-8')
    return {'ok':True,'factor_m_per_unit':factor,'settings':d['settings']}

@router.get('/projects/{pid}/recognition')
def recognition(pid:str):
    _require('recognition')
    from .main import ROOT
    _,d=_project(ROOT,pid)
    rows=[]
    for e in (d.get('preview') or {}).get('entities',[]):
        cat=e.get('cat','other'); layer=e.get('layer','')
        confidence=0.96 if cat!='other' else 0.25
        reason='nom du calque + règle BTP' if cat!='other' else 'aucune règle fiable'
        rows.append({'layer':layer,'category':cat,'confidence':confidence,'reason':reason})
    by={}
    for r in rows:
        key=(r['layer'],r['category']); by.setdefault(key,[]).append(r['confidence'])
    out=[{'layer':k[0],'category':k[1],'confidence':round(sum(v)/len(v),3)} for k,v in by.items()]
    return {'items':out,'recognized_ratio': round(sum(1 for x in rows if x['category']!='other')/max(1,len(rows)),3)}

@router.get('/projects/{pid}/model3d')
def model3d(pid:str):
    _require('model3d')
    from .main import ROOT
    _,d=_project(ROOT,pid)
    defs=(d.get('settings') or {}).get('category_defaults') or {}
    prim=[]
    for e in (d.get('preview') or {}).get('entities',[]):
        cat=e.get('cat','other')
        if cat=='other': continue
        h=float((defs.get(cat) or {}).get('height') or (0.25 if cat in {'foundation','slab','fill'} else 2.8))
        prim.append({'type':e.get('type'),'category':cat,'height':h,'geometry':e})
    return {'primitives':prim,'count':len(prim),'coordinate_system':'local-metric'}

@router.get('/projects/{pid}/takeoff')
def takeoff(pid:str):
    _require('takeoff')
    from .main import ROOT
    _,d=_project(ROOT,pid)
    q=d.get('quantities') or []
    total_v=sum(float(x.get('volume_m3') or 0) for x in q)
    total_s=sum(float(x.get('surface_m2') or x.get('area_m2') or 0) for x in q)
    total_l=sum(float(x.get('length_m') or 0) for x in q)
    checks=[]
    for x in q:
        checks.append({'category':x.get('category'),'status':'ok' if x.get('count',0)>0 else 'review','count':x.get('count',0)})
    return {'totals':{'length_m':round(total_l,3),'surface_m2':round(total_s,3),'volume_m3':round(total_v,3)},'checks':checks,'families':q}

@router.get('/projects/{pid}/bim')
def bim(pid:str):
    _require('ifc_bim')
    from .main import ROOT
    _,d=_project(ROOT,pid)
    mapping={'wall':'IfcWall','slab':'IfcSlab','beam':'IfcBeam','column':'IfcColumn','foundation':'IfcFooting','opening':'IfcOpeningElement','fill':'IfcBuildingElementProxy'}
    entities=[]
    for q in d.get('quantities') or []:
        entities.append({'category':q.get('category'),'ifc_class':mapping.get(q.get('category'),'IfcBuildingElementProxy'),'material':q.get('material'),'quantity':q})
    return {'schema':'IFC4','entities':entities,'levels':['Niveau 0']}

@router.post('/projects/{pid}/phases')
def phases(pid:str, payload:PhasePayload):
    _require('phasing')
    from .main import ROOT
    p,d=_project(ROOT,pid)
    default={'foundation':1,'fill':2,'slab':3,'column':4,'wall':5,'beam':6,'opening':7,'other':8}
    default.update({k:int(v) for k,v in payload.category_phases.items() if 1<=int(v)<=99})
    d.setdefault('settings',{})['phases']=default
    p.write_text(json.dumps(d,ensure_ascii=False,indent=2),encoding='utf-8')
    return {'phases':default,'sequence':[{'phase':n,'categories':[k for k,v in default.items() if v==n]} for n in sorted(set(default.values()))]}

@router.post('/projects/{pid}/cost')
def cost(pid:str, payload:CostPayload):
    _require('costing')
    from .main import ROOT
    _,d=_project(ROOT,pid)
    default={'foundation':185.0,'slab':145.0,'column':620.0,'beam':530.0,'wall':92.0,'fill':48.0,'opening':180.0,'other':0.0}
    default.update({k:float(v) for k,v in payload.prices.items() if float(v)>=0})
    rows=[]; total=0.0
    for q in d.get('quantities') or []:
        cat=q.get('category','other'); price=default.get(cat,0)
        qty=float(q.get('volume_m3') or q.get('surface_m2') or q.get('area_m2') or q.get('length_m') or q.get('count') or 0)
        amount=qty*price; total+=amount
        rows.append({'category':cat,'quantity':round(qty,3),'unit_price':price,'amount':round(amount,2)})
    return {'currency':'EUR','rows':rows,'total':round(total,2),'note':'Estimation paramétrique à valider avec la base de prix entreprise.'}

@router.post('/projects/{pid}/assistant')
def assistant(pid:str, payload:AssistantPayload):
    _require('assistant')
    from .main import ROOT
    _,d=_project(ROOT,pid)
    cmd=payload.command.strip().lower()
    q=d.get('quantities') or []
    if any(w in cmd for w in ['béton','beton','volume']):
        val=sum(float(x.get('volume_m3') or 0) for x in q if x.get('category') in {'foundation','slab','column','beam'})
        ans=f'Volume béton pré-métré : {val:.2f} m³.'
    elif any(w in cmd for w in ['mur','maçonnerie','maconnerie']):
        val=sum(float(x.get('surface_m2') or 0) for x in q if x.get('category')=='wall')
        ans=f'Surface de murs pré-métrée : {val:.2f} m².'
    elif 'alerte' in cmd or 'contrôle' in cmd or 'controle' in cmd:
        n=sum(int(x.get('count') or 0) for x in q if x.get('category')=='other')
        ans=f'Contrôle qualité : {n} élément(s) non classé(s) à vérifier.'
    else:
        ans='Commande comprise. Je peux résumer les volumes béton, surfaces de murs et alertes de classification.'
    return {'answer':ans,'mode':'local-rule-assistant','command':payload.command}

@router.get('/projects/{pid}/qa')
def qa(pid:str):
    _require('assistant')
    from .main import ROOT
    _,d=_project(ROOT,pid)
    ents=(d.get('preview') or {}).get('entities',[])
    other=sum(1 for e in ents if e.get('cat')=='other')
    ratio=1-other/max(1,len(ents))
    unit=(d.get('settings') or {}).get('unit_to_m')
    score=100
    issues=[]
    if not unit: score-=25; issues.append('Échelle/unité non validée')
    if ratio<.75: score-=20; issues.append('Taux de classification faible')
    if not d.get('quantities'): score-=20; issues.append('Aucun métré exploitable')
    return {'score':max(0,score),'classification_ratio':round(ratio,3),'issues':issues,'status':'ready' if score>=80 else 'review'}
