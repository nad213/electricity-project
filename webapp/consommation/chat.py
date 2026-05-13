"""
Chatbot service — tool-use loop against the Anthropic API.

Exposes a thin set of tools that wrap services.py so the model can answer
questions about French electricity data (consumption, production, exchanges).

Stateless: the caller supplies the full message history each turn.
"""
from __future__ import annotations

import json
from datetime import date, datetime

import pandas as pd
from anthropic import Anthropic
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
]


# ---------- serialization helpers ---------- #

_MAX_ROWS = 150
_SAMPLE_SIZE = 30


def _isoformat(v):
    if isinstance(v, (pd.Timestamp, datetime)):
        return v.isoformat()
    if isinstance(v, date):
        return v.isoformat()
    return v


def _df_to_payload(df: pd.DataFrame, value_col: str, unit: str) -> dict:
    """Compact JSON for a time-series DataFrame.

    Returns full rows under _MAX_ROWS, else stats + downsampled sample.
    """
    if df.empty:
        return {"rows_total": 0, "data": [], "unit": unit}

    series = df[value_col].astype(float)
    stats = {
        "min": float(series.min()),
        "max": float(series.max()),
        "mean": float(series.mean()),
        "sum": float(series.sum()),
        "count": int(series.count()),
    }
    payload = {"unit": unit, "rows_total": len(df), "stats": stats}

    if len(df) <= _MAX_ROWS:
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
        return _df_to_payload(df.rename(columns={"yearly_consumption": "value"}), "value", "MWh")
    if g == "monthly":
        df = services.get_monthly_data()
        return _df_to_payload(df.rename(columns={"monthly_consumption": "value"}), "value", "MWh")

    start, end = _parse_dates(args)
    if not start or not end:
        return {"error": "start et end sont requis pour granularity raw/daily"}
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
        return _df_to_payload(df[["year", col]].rename(columns={col: "value"}), "value", "MWh")
    if g == "monthly":
        df = services.get_production_monthly_data()
        col = f"{filiere}_mwh"
        if col not in df.columns:
            return {"error": f"colonne {col} absente"}
        return _df_to_payload(
            df[["year_month", col]].rename(columns={col: "value"}),
            "value",
            "MWh",
        )

    start, end = _parse_dates(args)
    if not start or not end:
        return {"error": "start et end sont requis pour granularity raw/daily"}
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


_DISPATCH = {
    "get_overview": lambda args: _tool_get_overview(),
    "get_consommation": _tool_get_consommation,
    "get_production": _tool_get_production,
    "get_echanges": _tool_get_echanges,
    "get_dashboard": lambda args: _tool_get_dashboard(),
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


class ChatService:
    def __init__(self):
        if not settings.ANTHROPIC_API_KEY:
            raise RuntimeError("ANTHROPIC_API_KEY non configurée")
        self.client = Anthropic(api_key=settings.ANTHROPIC_API_KEY)
        self.model = settings.CHAT_MODEL
        self.max_turns = settings.CHAT_MAX_TURNS

    def run(self, messages: list[dict]) -> dict:
        """Run the tool-use loop until the model produces a final text answer.

        `messages` is the Anthropic-format history: [{role, content}, ...].
        Returns {"reply": str, "messages": updated_history, "usage": {...}}.
        """
        if len(messages) > self.max_turns * 2:
            return {"error": f"Conversation trop longue (>{self.max_turns} tours)"}

        history = list(messages)
        usage_totals = {"input": 0, "output": 0, "cache_read": 0, "cache_create": 0}

        for _ in range(10):  # hard cap on tool-use iterations
            resp = self.client.messages.create(
                model=self.model,
                max_tokens=2048,
                system=SYSTEM_PROMPT,
                tools=TOOLS,
                messages=history,
            )
            usage_totals["input"] += resp.usage.input_tokens
            usage_totals["output"] += resp.usage.output_tokens
            usage_totals["cache_read"] += getattr(resp.usage, "cache_read_input_tokens", 0) or 0
            usage_totals["cache_create"] += getattr(resp.usage, "cache_creation_input_tokens", 0) or 0

            assistant_content = [block.model_dump() for block in resp.content]
            history.append({"role": "assistant", "content": assistant_content})

            if resp.stop_reason != "tool_use":
                text = "".join(b.text for b in resp.content if b.type == "text")
                return {"reply": text, "messages": history, "usage": usage_totals}

            tool_results = []
            for block in resp.content:
                if block.type == "tool_use":
                    result_json = _run_tool(block.name, block.input or {})
                    tool_results.append({
                        "type": "tool_result",
                        "tool_use_id": block.id,
                        "content": result_json,
                    })
            history.append({"role": "user", "content": tool_results})

        return {"error": "Trop d'itérations tool-use", "messages": history, "usage": usage_totals}
