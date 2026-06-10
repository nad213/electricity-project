"""
API publique ElecFlow (v1) — Django Ninja.

Expose en JSON, en lecture seule, les données déjà servies par les pages de
visualisation. Les endpoints réutilisent directement `services.py` (DuckDB →
Parquet/S3) : ici on ne fait que valider les paramètres et sérialiser.

Accès protégé par clé d'API (en-tête `Authorization: Bearer <clé>`, cf.
`api_auth.py`) et limité en débit par clé (throttling). Données publiques mais
accès tracé/révocable.

Documentation interactive (Swagger) : /api/v1/docs
"""
import os
from datetime import date, datetime
from typing import Optional

import pandas as pd
from ninja import NinjaAPI, Schema
from ninja.errors import HttpError
from ninja.throttling import AuthRateThrottle

from . import services
from .api_auth import get_api_auth


# ========== Rate limiting (throttling) ==========
# Les endpoints sont coûteux (lecture Parquet + DuckDB à chaque appel) :
# sans plafond, une boucle de requêtes suffit à saturer le service.
# `AuthRateThrottle` compte PAR CLÉ d'API (str(request.auth)) : la requête est
# toujours authentifiée puisqu'une clé valide est requise. Deux fenêtres :
#   - "burst"     : coupe les boucles serrées (rafale courte)
#   - "sustained" : plafonne le volume total sur la durée
# Les seuils sont ajustables sans redéploiement via variables d'environnement.
# NB : le compteur vit dans le cache Django (LocMemCache par défaut, donc par
# process) — la limite effective est multipliée par le nombre de workers
# Gunicorn. Pour un comptage exact en multi-worker, brancher un cache partagé
# (Redis) ; ce throttling « approximatif » protège déjà l'essentiel.
class BurstRateThrottle(AuthRateThrottle):
    scope = "burst"


class SustainedRateThrottle(AuthRateThrottle):
    scope = "sustained"


# Seuils de débit (par clé), exposés comme constantes pour que la page /api/
# puisse afficher les limites réelles sans dupliquer les valeurs par défaut.
THROTTLE_BURST = os.getenv("API_THROTTLE_BURST", "1/2s")
THROTTLE_SUSTAINED = os.getenv("API_THROTTLE_SUSTAINED", "5/min")

api = NinjaAPI(
    title="ElecFlow API",
    version="1.0.0",
    description=(
        "API publique de données de l'application. "
        "Données en lecture seule. Les courbes de puissance sont en MW, "
        "l'énergie agrégée en GWh. "
        "Accès par clé d'API : en-tête `Authorization: Bearer <clé>`."
    ),
    docs_url="/docs",
    auth=get_api_auth(),
    throttle=[
        BurstRateThrottle(THROTTLE_BURST),
        SustainedRateThrottle(THROTTLE_SUSTAINED),
    ],
)

# Les courbes infra-journalières (pas de 15/30 min) génèrent ~35 000 points par
# an et par série : on borne la plage pour éviter des réponses démesurées (pic
# RAM DuckDB + DataFrame + sérialisation sur petite instance). Ajustable sans
# redéploiement via `API_MAX_RANGE_DAYS`. Les endpoints « énergie » ne renvoient
# qu'une ligne par mois → cap bien plus large.
MAX_RANGE_DAYS = int(os.getenv("API_MAX_RANGE_DAYS", "366"))
MAX_RANGE_DAYS_ENERGIE = 366 * 10


# ========== Helpers ==========
def _parse_date(value: str, name: str) -> date:
    try:
        return datetime.strptime(value, "%Y-%m-%d").date()
    except (ValueError, TypeError):
        raise HttpError(400, f"{name} doit être au format AAAA-MM-JJ")


def _validate_range(start: date, end: date, max_days: int = MAX_RANGE_DAYS) -> None:
    if start > end:
        raise HttpError(400, "debut doit être antérieure ou égale à fin")
    if (end - start).days > max_days:
        raise HttpError(400, f"La plage demandée ne peut excéder {max_days} jours")


def _records(df: pd.DataFrame) -> list[dict]:
    """DataFrame → liste de dicts JSON-safe (NaN/NaT → null)."""
    return df.where(pd.notnull(df), None).to_dict(orient="records")


def _gwh(value) -> Optional[float]:
    """MWh → GWh, arrondi à 1 décimale, None-safe."""
    if value is None or pd.isna(value):
        return None
    return round(value / 1000.0, 1)


def _energie_mois(df: pd.DataFrame) -> list[dict]:
    """[mois, energie_mwh] → [{mois, energie_gwh}]."""
    return [{"mois": r["mois"], "energie_gwh": _gwh(r["energie_mwh"])}
            for r in _records(df)]


# ========== Schémas ==========
class DateRange(Schema):
    min: date
    max: date


class MetaOut(Schema):
    consommation: DateRange
    production: DateRange
    echanges: DateRange
    filieres: dict[str, str]
    pays: dict[str, str]


# --- Courbes : série de puissance (MW), pas de 15/30 min ---
class CourbeConsoRow(Schema):
    date_heure: datetime
    consommation: Optional[float] = None
    source: Optional[str] = None


class CourbeConsoOut(Schema):
    count: int
    debut: date
    fin: date
    unite: str = "MW"
    data: list[CourbeConsoRow]


class CourbeProdRow(Schema):
    date_heure: datetime
    production: Optional[float] = None
    source: Optional[str] = None


class CourbeProdOut(Schema):
    count: int
    debut: date
    fin: date
    filiere: str
    unite: str = "MW"
    data: list[CourbeProdRow]


class EchangeRow(Schema):
    date_heure: datetime
    echange: Optional[float] = None
    source: Optional[str] = None


class EchangeOut(Schema):
    count: int
    debut: date
    fin: date
    pays: str
    unite: str = "MW"
    note: str = "Signe positif = import vers la France, négatif = export."
    data: list[EchangeRow]


# --- Énergie : intégrale de la puissance, agrégée par mois (GWh) ---
class EnergieMoisRow(Schema):
    mois: str
    energie_gwh: Optional[float] = None


class EnergieConsoOut(Schema):
    debut: date
    fin: date
    unite: str = "GWh"
    data: list[EnergieMoisRow]


class EnergieProdOut(Schema):
    debut: date
    fin: date
    filiere: str
    unite: str = "GWh"
    data: list[EnergieMoisRow]


class EnergieEchangeMoisRow(Schema):
    mois: str
    import_gwh: Optional[float] = None
    export_gwh: Optional[float] = None


class EnergieEchangeOut(Schema):
    debut: date
    fin: date
    pays: str
    unite: str = "GWh"
    note: str = "import = flux entrant vers la France, export = flux sortant."
    data: list[EnergieEchangeMoisRow]


# --- Parc ---
class ParcRow(Schema):
    date: str
    filiere: str
    parc_mw: Optional[float] = None


class ParcOut(Schema):
    count: int
    unite: str = "MW"
    data: list[ParcRow]


# ========== Endpoints ==========
@api.get("/meta", response=MetaOut, tags=["meta"], summary="Métadonnées")
def meta(request):
    """Plages de dates disponibles et listes de référence (filières, pays).

    La liste `pays` inclut la clé `total` (somme des frontières commerciales),
    acceptée par `echange` et `energie_echange`.
    """
    c_min, c_max = services.get_date_range()
    p_min, p_max = services.get_production_date_range()
    e_min, e_max = services.get_echanges_date_range()
    return {
        "consommation": {"min": c_min, "max": c_max},
        "production": {"min": p_min, "max": p_max},
        "echanges": {"min": e_min, "max": e_max},
        "filieres": services.get_production_filieres(),
        "pays": {"total": "Total (somme des frontières commerciales)",
                 **services.get_echanges_pays()},
    }


# ---------- Courbes (puissance, MW) ----------
@api.get("/courbe_conso", response=CourbeConsoOut, tags=["courbes"],
         summary="Courbe de consommation (puissance)")
def courbe_conso(request, debut: str, fin: str):
    """Courbe de consommation (MW) sur une plage de dates."""
    s = _parse_date(debut, "debut")
    e = _parse_date(fin, "fin")
    _validate_range(s, e)
    df = services.get_puissance_data(s, e)
    return {"count": len(df), "debut": s, "fin": e, "data": _records(df)}


@api.get("/courbe_prod", response=CourbeProdOut, tags=["courbes"],
         summary="Courbe de production par filière")
def courbe_prod(request, debut: str, fin: str, filiere: str = "nucleaire"):
    """Courbe de production (MW) d'une filière. Filières : voir `/meta`."""
    s = _parse_date(debut, "debut")
    e = _parse_date(fin, "fin")
    _validate_range(s, e)
    try:
        df = services.get_production_data(s, e, filiere)
    except ValueError as ex:
        raise HttpError(400, str(ex))
    return {"count": len(df), "debut": s, "fin": e, "filiere": filiere,
            "data": _records(df)}


@api.get("/echange", response=EchangeOut, tags=["courbes"],
         summary="Courbe d'échanges transfrontaliers")
def echange(request, debut: str, fin: str, pays: str = "total"):
    """Courbe de flux d'échange (MW). `pays` : `total`, `ech_physiques` ou une
    frontière commerciale (voir `/meta`)."""
    s = _parse_date(debut, "debut")
    e = _parse_date(fin, "fin")
    _validate_range(s, e)
    try:
        df = services.get_echanges_data(s, e, pays)
    except ValueError as ex:
        raise HttpError(400, str(ex))
    return {"count": len(df), "debut": s, "fin": e, "pays": pays,
            "data": _records(df)}


# ---------- Énergie (GWh, par mois) ----------
@api.get("/energie_conso", response=EnergieConsoOut, tags=["énergie"],
         summary="Énergie consommée par mois")
def energie_conso(request, debut: str, fin: str):
    """Énergie consommée (GWh), un total par mois sur la plage."""
    s = _parse_date(debut, "debut")
    e = _parse_date(fin, "fin")
    _validate_range(s, e, MAX_RANGE_DAYS_ENERGIE)
    df = services.get_consommation_energie_mensuelle(s, e)
    return {"debut": s, "fin": e, "data": _energie_mois(df)}


@api.get("/energie_prod", response=EnergieProdOut, tags=["énergie"],
         summary="Énergie produite par mois")
def energie_prod(request, debut: str, fin: str, filiere: str = "nucleaire"):
    """Énergie produite (GWh) d'une filière, un total par mois. Filières : `/meta`."""
    s = _parse_date(debut, "debut")
    e = _parse_date(fin, "fin")
    _validate_range(s, e, MAX_RANGE_DAYS_ENERGIE)
    try:
        df = services.get_production_energie_mensuelle(s, e, filiere)
    except ValueError as ex:
        raise HttpError(400, str(ex))
    return {"debut": s, "fin": e, "filiere": filiere, "data": _energie_mois(df)}


@api.get("/energie_echange", response=EnergieEchangeOut, tags=["énergie"],
         summary="Énergie échangée (import/export) par mois")
def energie_echange(request, debut: str, fin: str, pays: str = "total"):
    """Énergie importée/exportée (GWh) par mois. `pays` : `total` ou une
    frontière commerciale (voir `/meta`)."""
    s = _parse_date(debut, "debut")
    e = _parse_date(fin, "fin")
    _validate_range(s, e, MAX_RANGE_DAYS_ENERGIE)
    try:
        df = services.get_echanges_energie_mensuelle(s, e, pays)
    except ValueError as ex:
        raise HttpError(400, str(ex))
    data = [{"mois": r["mois"],
             "import_gwh": _gwh(r["import_mwh"]),
             "export_gwh": _gwh(r["export_mwh"])}
            for r in _records(df)]
    return {"debut": s, "fin": e, "pays": pays, "data": data}


# ---------- Parc ----------
@api.get("/parc", response=ParcOut, tags=["parc"],
         summary="Parc installé (éolien/solaire)")
def parc(request):
    """Parc installé mensuel (MW) pour l'éolien (terrestre/mer) et le solaire."""
    df = services.get_parc_installe_data()
    return {"count": len(df), "data": _records(df)}
