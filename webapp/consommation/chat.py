"""
Chatbot service — tool-use loop against the Mistral API.

Exposes a thin set of tools that wrap services.py so the model can answer
questions about French electricity data (consumption, production, exchanges).

Stateless: the caller supplies the full message history each turn (OpenAI-style
roles: user / assistant / tool).
"""
from __future__ import annotations

import json
from datetime import date, datetime

import pandas as pd
try:
    from mistralai import Mistral
except ImportError:  # mistralai >= 2.x a déplacé Mistral sous le sous-paquet client
    from mistralai.client import Mistral
from django.conf import settings

from . import services


SYSTEM_PROMPT = """Tu es un assistant qui aide à explorer les données électriques françaises (source RTE / ODRÉ).

Règles :
- Réponds toujours en français, de manière concise.
- N'invente jamais de chiffres : utilise systématiquement les tools pour récupérer les données.
- Si l'utilisateur ne précise pas la période, appelle d'abord `get_overview` pour connaître les bornes disponibles.
- Les valeurs de consommation et de production sont en MW (puissance instantanée demi-horaire) ou MWh (énergie agrégée mensuelle/annuelle). Précise toujours l'unité.
- Pour les filières de production : nucleaire, hydraulique, eolien, solaire, gaz, charbon, fioul, bioenergies.
- Pour les pays d'échange : ech_physiques (solde total), ech_comm_angleterre, ech_comm_espagne, ech_comm_italie, ech_comm_suisse, ech_comm_allemagne_belgique. Un solde négatif = exportation, positif = importation.
- Quand tu présentes des séries de chiffres, utilise des tableaux markdown lisibles.
- Pour les questions de type « pic / record / maximum / minimum » sur une période, appelle TOUJOURS `get_peak` (pas `get_consommation`/`get_production` en raw — qui downsample et perdent le datetime exact).
- La granularité `raw` est limitée à 31 jours. Au-delà, utilise `daily` ou `get_peak`.
- Si une demande est ambiguë, pose une courte question avant d'appeler un tool."""


TOOLS = [
    {
        "name": "get_overview",
        "description": "Retourne les bornes temporelles disponibles pour chaque dataset (consommation, production, échanges) ainsi que la liste des filières et pays. À appeler en début de conversation si tu n'as pas le contexte.",
        "input_schema": {"type": "object", "properties": {}, "required": []},
    },
    {
        "name": "get_consommation",
        "description": "Consommation électrique française. Utilise `granularity` pour choisir l'agrégation. 'raw' = données demi-horaires en MW (limiter à quelques jours). 'daily' = moyenne quotidienne en MW. 'monthly' = totaux mensuels en MWh. 'annual' = totaux annuels en MWh.",
        "input_schema": {
            "type": "object",
            "properties": {
                "granularity": {"type": "string", "enum": ["raw", "daily", "monthly", "annual"]},
                "start": {"type": "string", "description": "Date de début ISO YYYY-MM-DD. Ignoré pour 'monthly' et 'annual' (renvoie tout)."},
                "end": {"type": "string", "description": "Date de fin ISO YYYY-MM-DD."},
            },
            "required": ["granularity"],
        },
    },
    {
        "name": "get_production",
        "description": "Production électrique française par filière. 'raw' = demi-horaire MW, 'daily' = moyenne quotidienne MW, 'monthly' = MWh mensuels, 'annual' = MWh annuels.",
        "input_schema": {
            "type": "object",
            "properties": {
                "filiere": {"type": "string", "enum": ["nucleaire", "hydraulique", "eolien", "solaire", "gaz", "charbon", "fioul", "bioenergies"]},
                "granularity": {"type": "string", "enum": ["raw", "daily", "monthly", "annual"]},
                "start": {"type": "string", "description": "Date début ISO. Ignoré pour 'monthly'/'annual'."},
                "end": {"type": "string", "description": "Date fin ISO."},
            },
            "required": ["filiere", "granularity"],
        },
    },
    {
        "name": "get_echanges",
        "description": "Échanges transfrontaliers d'électricité. Solde négatif = export, positif = import. Granularité 'raw' (MW demi-horaire) ou 'daily' (moyenne MW).",
        "input_schema": {
            "type": "object",
            "properties": {
                "pays": {"type": "string", "enum": ["ech_physiques", "ech_comm_angleterre", "ech_comm_espagne", "ech_comm_italie", "ech_comm_suisse", "ech_comm_allemagne_belgique"]},
                "granularity": {"type": "string", "enum": ["raw", "daily"]},
                "start": {"type": "string"},
                "end": {"type": "string"},
            },
            "required": ["pays", "granularity", "start", "end"],
        },
    },
    {
        "name": "get_dashboard",
        "description": "Photo du jour : dernière journée disponible (conso et production demi-horaires), pic de conso de l'année et historique, mix de production de l'année en cours.",
        "input_schema": {"type": "object", "properties": {}, "required": []},
    },
    {
        "name": "get_peak",
        "description": "Top-N valeurs extrêmes (max ou min) avec leur datetime exact, sur une période. À utiliser pour toute question 'pic / record / maximum / minimum' au lieu de get_consommation/get_production en granularity raw (plus précis, pas de downsampling).",
        "input_schema": {
            "type": "object",
            "properties": {
                "dataset": {"type": "string", "enum": ["consommation", "production", "echanges"]},
                "filiere": {"type": "string", "enum": ["nucleaire", "hydraulique", "eolien", "solaire", "gaz", "charbon", "fioul", "bioenergies"], "description": "Requis si dataset=production."},
                "pays": {"type": "string", "enum": ["ech_physiques", "ech_comm_angleterre", "ech_comm_espagne", "ech_comm_italie", "ech_comm_suisse", "ech_comm_allemagne_belgique"], "description": "Requis si dataset=echanges."},
                "start": {"type": "string", "description": "Date début ISO YYYY-MM-DD."},
                "end": {"type": "string", "description": "Date fin ISO YYYY-MM-DD."},
                "direction": {"type": "string", "enum": ["max", "min"], "description": "Sens du tri. Défaut 'max'."},
                "n": {"type": "integer", "description": "Nombre de résultats (1-20). Défaut 5."},
            },
            "required": ["dataset", "start", "end"],
        },
    },
]


# Mistral attend le format OpenAI : {"type": "function", "function": {name, description, parameters}}.
# On dérive cette liste des définitions ci-dessus pour garder les schémas en un seul endroit.
MISTRAL_TOOLS = [
    {
        "type": "function",
        "function": {
            "name": t["name"],
            "description": t["description"],
            "parameters": t["input_schema"],
        },
    }
    for t in TOOLS
]


# ---------- serialization helpers ---------- #

_MAX_ROWS = 150
_SAMPLE_SIZE = 30
_MAX_RAW_DAYS = 31


def _isoformat(v):
    if isinstance(v, (pd.Timestamp, datetime)):
        return v.isoformat()
    if isinstance(v, date):
        return v.isoformat()
    return v


def _df_to_payload(df: pd.DataFrame, value_col: str, unit: str, force_full: bool = False) -> dict:
    """Compact JSON for a time-series DataFrame.

    Returns full rows when `force_full` ou sous _MAX_ROWS, else stats +
    sous-échantillon de lignes. Le sous-échantillonnage jette des lignes
    entières (donc des périodes entières) : à ne JAMAIS utiliser pour des
    agrégats déjà compacts (mensuel/annuel) — passer `force_full=True`.
    """
    if df.empty:
        return {"rows_total": 0, "data": [], "unit": unit}

    series = df[value_col].astype(float)
    stats = {
        "min": float(series.min()),
        # La ligne du min/max est jointe pour que le modèle ne recolle pas une
        # stat globale sur la mauvaise période quand on sous-échantillonne.
        "min_row": {k: _isoformat(v) for k, v in df.loc[series.idxmin()].items()},
        "max": float(series.max()),
        "max_row": {k: _isoformat(v) for k, v in df.loc[series.idxmax()].items()},
        "mean": float(series.mean()),
        "sum": float(series.sum()),
        "count": int(series.count()),
    }
    payload = {"unit": unit, "rows_total": len(df), "stats": stats}

    if force_full or len(df) <= _MAX_ROWS:
        payload["data"] = [
            {k: _isoformat(v) for k, v in r.items()} for r in df.to_dict(orient="records")
        ]
    else:
        step = max(1, len(df) // _SAMPLE_SIZE)
        sample = df.iloc[::step].head(_SAMPLE_SIZE)
        payload["sample"] = [
            {k: _isoformat(v) for k, v in r.items()} for r in sample.to_dict(orient="records")
        ]
        payload["note"] = f"Dataset trop volumineux ({len(df)} lignes) — sample équiréparti de {len(sample)} points fourni, plus stats globales."
    return payload


# ---------- tool dispatch ---------- #

def _parse_dates(args: dict, default_days: int | None = None) -> tuple[date, date] | tuple[None, None]:
    start = args.get("start")
    end = args.get("end")
    if not start and not end:
        return None, None
    start_d = date.fromisoformat(start) if start else None
    end_d = date.fromisoformat(end) if end else None
    return start_d, end_d


def _tool_get_overview() -> dict:
    cons_min, cons_max = services.get_date_range()
    prod_min, prod_max = services.get_production_date_range()
    ech_min, ech_max = services.get_echanges_date_range()
    return {
        "consommation": {"start": cons_min.isoformat(), "end": cons_max.isoformat()},
        "production": {"start": prod_min.isoformat(), "end": prod_max.isoformat()},
        "echanges": {"start": ech_min.isoformat(), "end": ech_max.isoformat()},
        "filieres": list(services.get_production_filieres().keys()),
        "pays": list(services.get_echanges_pays().keys()),
    }


def _tool_get_consommation(args: dict) -> dict:
    g = args["granularity"]
    if g == "annual":
        df = services.get_annual_data()
        return _df_to_payload(df.rename(columns={"yearly_consumption": "value"}), "value", "MWh", force_full=True)
    if g == "monthly":
        df = services.get_monthly_data()
        return _df_to_payload(df.rename(columns={"monthly_consumption": "value"}), "value", "MWh", force_full=True)

    start, end = _parse_dates(args)
    if not start or not end:
        return {"error": "start et end sont requis pour granularity raw/daily"}
    if g == "raw" and (end - start).days > _MAX_RAW_DAYS:
        return {"error": f"Période trop longue pour granularity=raw ({(end - start).days} jours > {_MAX_RAW_DAYS}). Utilise granularity='daily' pour agréger, ou le tool 'get_peak' pour les extrêmes."}
    df = services.get_puissance_data(start, end)
    if df.empty:
        return {"rows_total": 0, "data": [], "unit": "MW"}
    df = df[["date_heure", "consommation"]].rename(columns={"consommation": "value"})

    if g == "daily":
        df["date"] = pd.to_datetime(df["date_heure"]).dt.date
        df = df.groupby("date", as_index=False)["value"].mean()
    return _df_to_payload(df, "value", "MW")


def _tool_get_production(args: dict) -> dict:
    filiere = args["filiere"]
    g = args["granularity"]
    if g == "annual":
        df = services.get_production_annual_data()
        col = f"{filiere}_yearly_mwh"
        if col not in df.columns:
            return {"error": f"colonne {col} absente"}
        return _df_to_payload(df[["year", col]].rename(columns={col: "value"}), "value", "MWh", force_full=True)
    if g == "monthly":
        df = services.get_production_monthly_data()
        col = f"{filiere}_mwh"
        if col not in df.columns:
            return {"error": f"colonne {col} absente"}
        return _df_to_payload(
            df[["year_month", col]].rename(columns={col: "value"}),
            "value",
            "MWh",
            force_full=True,
        )

    start, end = _parse_dates(args)
    if not start or not end:
        return {"error": "start et end sont requis pour granularity raw/daily"}
    if g == "raw" and (end - start).days > _MAX_RAW_DAYS:
        return {"error": f"Période trop longue pour granularity=raw ({(end - start).days} jours > {_MAX_RAW_DAYS}). Utilise granularity='daily' pour agréger, ou le tool 'get_peak' pour les extrêmes."}
    df = services.get_production_data(start, end, filiere=filiere)
    if df.empty:
        return {"rows_total": 0, "data": [], "unit": "MW"}
    df = df[["date_heure", "production"]].rename(columns={"production": "value"})
    if g == "daily":
        df["date"] = pd.to_datetime(df["date_heure"]).dt.date
        df = df.groupby("date", as_index=False)["value"].mean()
    return _df_to_payload(df, "value", "MW")


def _tool_get_echanges(args: dict) -> dict:
    pays = args["pays"]
    g = args["granularity"]
    start, end = _parse_dates(args)
    if not start or not end:
        return {"error": "start et end sont requis"}
    if g == "raw" and (end - start).days > _MAX_RAW_DAYS:
        return {"error": f"Période trop longue pour granularity=raw ({(end - start).days} jours > {_MAX_RAW_DAYS}). Utilise granularity='daily' pour agréger, ou le tool 'get_peak' pour les extrêmes."}
    df = services.get_echanges_data(start, end, pays=pays)
    if df.empty:
        return {"rows_total": 0, "data": [], "unit": "MW"}
    df = df[["date_heure", "echange"]].rename(columns={"echange": "value"})
    if g == "daily":
        df["date"] = pd.to_datetime(df["date_heure"]).dt.date
        df = df.groupby("date", as_index=False)["value"].mean()
    return _df_to_payload(df, "value", "MW")


def _tool_get_dashboard() -> dict:
    d = services.get_dashboard_data()
    if d is None:
        return {"error": "données dashboard indisponibles"}
    conso_ts = d["conso_ts"][["date_heure", "consommation"]]
    return {
        "dashboard_date": d["dashboard_date"].isoformat(),
        "peak_year": {"value_mw": d["peak_year_value"], "datetime": d["peak_year_datetime"].isoformat()},
        "peak_all_history": {"value_mw": d["peak_all_value"], "datetime": d["peak_all_datetime"].isoformat()},
        "conso_today": _df_to_payload(
            conso_ts.rename(columns={"consommation": "value"}), "value", "MW"
        ),
        "production_mix_year_mwh": {k: round(v, 0) for k, v in d["production_mix_year"].items()},
    }


def _tool_get_peak(args: dict) -> dict:
    dataset = args["dataset"]
    direction = args.get("direction", "max")
    n = args.get("n", 5)
    start, end = _parse_dates(args)
    if not start or not end:
        return {"error": "start et end sont requis"}

    if dataset == "consommation":
        df = services.get_consommation_peaks(start, end, n=n, direction=direction)
    elif dataset == "production":
        filiere = args.get("filiere")
        if not filiere:
            return {"error": "filiere requise pour dataset=production"}
        df = services.get_production_peaks(filiere, start, end, n=n, direction=direction)
    elif dataset == "echanges":
        pays = args.get("pays")
        if not pays:
            return {"error": "pays requis pour dataset=echanges"}
        df = services.get_echanges_peaks(pays, start, end, n=n, direction=direction)
    else:
        return {"error": f"dataset {dataset} inconnu"}

    if df.empty:
        return {"rows_total": 0, "rows": [], "unit": "MW"}
    return {
        "unit": "MW",
        "direction": direction,
        "rows_total": len(df),
        "rows": [
            {"date_heure": _isoformat(r["date_heure"]), "value": float(r["value"])}
            for r in df.to_dict(orient="records")
        ],
    }


_DISPATCH = {
    "get_overview": lambda args: _tool_get_overview(),
    "get_consommation": _tool_get_consommation,
    "get_production": _tool_get_production,
    "get_echanges": _tool_get_echanges,
    "get_dashboard": lambda args: _tool_get_dashboard(),
    "get_peak": _tool_get_peak,
}


def _run_tool(name: str, args: dict) -> str:
    try:
        result = _DISPATCH[name](args)
    except KeyError:
        result = {"error": f"tool {name} inconnu"}
    except ValueError as e:
        result = {"error": str(e)}
    except Exception as e:  # noqa: BLE001
        result = {"error": f"{type(e).__name__}: {e}"}
    return json.dumps(result, default=str, ensure_ascii=False)


# ---------- main loop ---------- #


def _content_to_text(content) -> str:
    """Mistral renvoie content soit en str, soit en liste de chunks selon le SDK."""
    if content is None:
        return ""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = []
        for chunk in content:
            if isinstance(chunk, str):
                parts.append(chunk)
            elif isinstance(chunk, dict):
                parts.append(chunk.get("text", ""))
            else:
                parts.append(getattr(chunk, "text", "") or "")
        return "".join(parts)
    return str(content)


class ChatService:
    def __init__(self):
        if not settings.MISTRAL_API_KEY:
            raise RuntimeError("MISTRAL_API_KEY non configurée")
        self.client = Mistral(api_key=settings.MISTRAL_API_KEY)
        self.model = settings.CHAT_MODEL
        self.max_turns = settings.CHAT_MAX_TURNS

    def run(self, messages: list[dict]) -> dict:
        """Run the tool-use loop until the model produces a final text answer.

        `messages` is the OpenAI/Mistral-format history: [{role, content, ...}, ...]
        (without the system message — il est ajouté à chaque appel).
        Returns {"reply": str, "messages": updated_history, "usage": {...}}.
        """
        if len(messages) > self.max_turns * 2:
            return {"error": f"Conversation trop longue (>{self.max_turns} tours)"}

        history = list(messages)
        usage_totals = {"input": 0, "output": 0}

        for _ in range(10):  # hard cap on tool-use iterations
            resp = self.client.chat.complete(
                model=self.model,
                max_tokens=2048,
                messages=[{"role": "system", "content": SYSTEM_PROMPT}] + history,
                tools=MISTRAL_TOOLS,
                tool_choice="auto",
            )
            usage = resp.usage
            usage_totals["input"] += getattr(usage, "prompt_tokens", 0) or 0
            usage_totals["output"] += getattr(usage, "completion_tokens", 0) or 0

            msg = resp.choices[0].message
            tool_calls = msg.tool_calls or []

            if not tool_calls:
                text = _content_to_text(msg.content)
                history.append({"role": "assistant", "content": text})
                return {"reply": text, "messages": history, "usage": usage_totals}

            # On stocke des dicts JSON-sérialisables (l'historique fait l'aller-retour
            # avec le frontend) — pas les objets SDK.
            history.append({
                "role": "assistant",
                "content": _content_to_text(msg.content),
                "tool_calls": [
                    {
                        "id": tc.id,
                        "type": "function",
                        "function": {
                            "name": tc.function.name,
                            "arguments": tc.function.arguments,
                        },
                    }
                    for tc in tool_calls
                ],
            })

            for tc in tool_calls:
                raw_args = tc.function.arguments
                try:
                    args = json.loads(raw_args) if isinstance(raw_args, str) else (raw_args or {})
                except json.JSONDecodeError:
                    args = {}
                result_json = _run_tool(tc.function.name, args)
                history.append({
                    "role": "tool",
                    "name": tc.function.name,
                    "tool_call_id": tc.id,
                    "content": result_json,
                })

        return {"error": "Trop d'itérations tool-use", "messages": history, "usage": usage_totals}
