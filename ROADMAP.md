# Roadmap technique — BTP 3D Studio

## Principe

Le produit est volontairement découpé en couches :

1. **Ingestion** : PDF / DXF / DWG / IFC / images ;
2. **Normalisation géométrique** : unités, origine, niveaux, calques ;
3. **Compréhension BTP** : familles d'ouvrages + matériaux ;
4. **Modèle canonique** : objets bâtiment indépendants de Blender/FreeCAD ;
5. **Sorties** : 3D, IFC, métrés, Excel, rapports ;
6. **Connecteurs** : Blender, IfcOpenShell, LibreDWG, OpenDroneMap.

Cette séparation permet de remplacer un moteur sans casser l'interface ni les métrés.

## v0.3 prioritaire

- calibration interactive PDF par deux points ;
- éditeur de mapping `calque → ouvrage` ;
- dimensions d'ouvrages éditables ;
- sauvegarde d'un profil entreprise ;
- génération d'un modèle 3D canonique (murs, dalles, semelles, longrines, poteaux, poutres) ;
- export IFC minimal testable ;
- validation visuelle avant export.

## v0.4

- lecture DWG automatisée si LibreDWG disponible ;
- niveaux / étages ;
- ouvertures portes/fenêtres ;
- détection d'intersections et nettoyage géométrique ;
- export GLB/Blender ;
- journal de provenance de chaque quantité.

## v0.5

- base de prix matériaux / main d'œuvre ;
- déboursé sec ;
- variantes ;
- import catalogue fournisseur ;
- comparaison prévisionnel / relevé chantier ;
- photogrammétrie / OpenDroneMap.
