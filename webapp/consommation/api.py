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
# `AuthRateThrottle` compte PAR CLÉ d'API (str(request.auth)) quand la requête
# est authentifiée, et retombe sur l'IP sinon (dev-open). Deux fenêtres :
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


api = NinjaAPI(
    title="ElecFlow API",
    version="1.0.0",
    description=(
        "API publique de données électriques françaises (source : ODRE). "
        "Données en lecture seule. Les puissances sont en MW. "
        "Accès par clé d'API : en-tête `Authorization: Bearer <clé>`."
    ),
    docs_url="/docs",
    auth=get_api_auth(),
    throttle=[
        BurstRateThrottle(os.getenv("API_THROTTLE_BURST", "10/s")),
        SustainedRateThrottle(os.getenv("API_THROTTLE_SUSTAINED", "60/min")),
    ],
)

# Les données infra-journalières (pas de 15/30 min) génèrent ~35 000 points par
# an et par série : on borne la plage pour éviter des réponses démesurées.
MAX_RANGE_DAYS = 366


# ========== Helpers ==========
def _parse_date(value: str, name: str) -> date:
    try:
        return datetime.strptime(value, "%Y-%m-%d").date()
    except (ValueError, TypeError):
        raise HttpError(400, f"{name} doit être au format AAAA-MM-JJ")


def _validate_range(start: date, end: date) -> None:
    if start > end:
        raise HttpError(400, "start_date doit être antérieure ou égale à end_date")
    if (end - start).days > MAX_RANGE_DAYS:
        raise HttpError(400, f"La plage demandée ne peut excéder {MAX_RANGE_DAYS} jours")


def _records(df: pd.DataFrame) -> list[dict]:
    """DataFrame → liste de dicts JSON-safe (NaN/NaT → null)."""
    return df.where(pd.notnull(df), None).to_dict(orient="records")


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


class ConsommationRow(Schema):
    date_heure: datetime
    consommation: Optional[float] = None
    source: Optional[str] = None


class ConsommationOut(Schema):
    count: int
    start_date: date
    end_date: date
    unit: str = "MW"
    data: list[ConsommationRow]


class ProductionRow(Schema):
    date_heure: datetime
    production: Optional[float] = None
    source: Optional[str] = None


class ProductionOut(Schema):
    count: int
    start_date: date
    end_date: date
    filiere: str
    unit: str = "MW"
    data: list[ProductionRow]


class EchangeRow(Schema):
    date_heure: datetime
    echange: Optional[float] = None
    source: Optional[str] = None


class EchangesOut(Schema):
    count: int
    start_date: date
    end_date: date
    pays: str
    unit: str = "MW"
    note: str = "Signe positif = import vers la France, négatif = export."
    data: list[EchangeRow]


class ParcRow(Schema):
    date: str
    filiere: str
    parc_mw: Optional[float] = None


class ParcOut(Schema):
    count: int
    unit: str = "MW"
    data: list[ParcRow]


# ========== Endpoints ==========
@api.get("/meta", response=MetaOut, tags=["meta"], summary="Métadonnées")
def meta(request):
    """Plages de dates disponibles et listes de référence (filières, pays)."""
    c_min, c_max = services.get_date_range()
    p_min, p_max = services.get_production_date_range()
    e_min, e_max = services.get_echanges_date_range()
    return {
        "consommation": {"min": c_min, "max": c_max},
        "production": {"min": p_min, "max": p_max},
        "echanges": {"min": e_min, "max": e_max},
        "filieres": services.get_production_filieres(),
        "pays": services.get_echanges_pays(),
    }


@api.get("/consommation", response=ConsommationOut, tags=["données"],
         summary="Consommation (puissance)")
def consommation(request, start_date: str, end_date: str):
    """Courbe de consommation (MW) sur une plage de dates."""
    s = _parse_date(start_date, "start_date")
    e = _parse_date(end_date, "end_date")
    _validate_range(s, e)
    df = services.get_puissance_data(s, e)
    return {"count": len(df), "start_date": s, "end_date": e, "data": _records(df)}


@api.get("/production", response=ProductionOut, tags=["données"],
         summary="Production par filière")
def production(request, start_date: str, end_date: str, filiere: str = "nucleaire"):
    """Production (MW) d'une filière sur une plage de dates.

    Filières disponibles : voir `/meta`.
    """
    s = _parse_date(start_date, "start_date")
    e = _parse_date(end_date, "end_date")
    _validate_range(s, e)
    try:
        df = services.get_production_data(s, e, filiere)
    except ValueError as ex:
        raise HttpError(400, str(ex))
    return {"count": len(df), "start_date": s, "end_date": e,
            "filiere": filiere, "data": _records(df)}


@api.get("/echanges", response=EchangesOut, tags=["données"],
         summary="Échanges transfrontaliers")
def echanges(request, start_date: str, end_date: str, pays: str = "ech_physiques"):
    """Flux d'échange (MW) pour un pays/frontière sur une plage de dates.

    Pays disponibles : voir `/meta`.
    """
    s = _parse_date(start_date, "start_date")
    e = _parse_date(end_date, "end_date")
    _validate_range(s, e)
    try:
        df = services.get_echanges_data(s, e, pays)
    except ValueError as ex:
        raise HttpError(400, str(ex))
    return {"count": len(df), "start_date": s, "end_date": e,
            "pays": pays, "data": _records(df)}


@api.get("/parc-installe", response=ParcOut, tags=["données"],
         summary="Parc installé (éolien/solaire)")
def parc_installe(request):
    """Parc installé mensuel (MW) pour l'éolien (terrestre/mer) et le solaire."""
    df = services.get_parc_installe_data()
    return {"count": len(df), "data": _records(df)}
