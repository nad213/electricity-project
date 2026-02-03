"""
Constantes centralisées pour l'application ElecFlow.

Ce fichier regroupe toutes les couleurs, configurations de graphiques,
et mappings utilisés dans l'application pour éviter la redondance.
"""
from functools import lru_cache


# ========== Palette de couleurs ==========

class Colors:
    """Palette de couleurs principales pour les graphiques"""
    PRIMARY = '#22D3EE'      # Cyan
    SECONDARY = '#FBBF24'    # Amber
    ACCENT = '#FBBF24'       # Amber
    SUCCESS = '#10B981'      # Emerald


class ProductionColors:
    """Couleurs par filière de production"""
    NUCLEAIRE = '#F59E0B'      # Amber
    HYDRAULIQUE = '#06B6D4'    # Cyan
    EOLIEN = '#10B981'         # Emerald
    SOLAIRE = '#FBBF24'        # Yellow
    GAZ = '#EF4444'            # Red
    CHARBON = '#6B7280'        # Gray
    FIOUL = '#A78BFA'          # Violet
    BIOENERGIES = '#34D399'    # Teal


class ChartConfig:
    """Configuration par défaut des graphiques Plotly"""
    GRID_COLOR = '#334155'
    BACKGROUND_COLOR = 'rgba(0,0,0,0)'
    PAPER_COLOR = 'rgba(0,0,0,0)'
    TEXT_COLOR = '#94A3B8'
    AXIS_COLOR = '#475569'
    LINE_CHART_HEIGHT = 450
    BAR_CHART_HEIGHT = 400
    MARGIN_WITH_LEGEND = dict(l=50, r=20, t=20, b=60)
    MARGIN_NO_LEGEND = dict(l=50, r=20, t=20, b=40)
    MARGIN_DEFAULT = dict(l=50, r=20, t=20, b=40)


# ========== Filières de production ==========

FILIERES = {
    'nucleaire': 'Nucléaire',
    'hydraulique': 'Hydraulique',
    'eolien': 'Éolien',
    'solaire': 'Solaire',
    'gaz': 'Gaz',
    'charbon': 'Charbon',
    'fioul': 'Fioul',
    'bioenergies': 'Bioénergies',
}

FILIERE_COLORS = {
    'nucleaire': ProductionColors.NUCLEAIRE,
    'hydraulique': ProductionColors.HYDRAULIQUE,
    'eolien': ProductionColors.EOLIEN,
    'solaire': ProductionColors.SOLAIRE,
    'gaz': ProductionColors.GAZ,
    'charbon': ProductionColors.CHARBON,
    'fioul': ProductionColors.FIOUL,
    'bioenergies': ProductionColors.BIOENERGIES,
}


# ========== Pays d'échange ==========

PAYS_ECHANGES = {
    'ech_physiques': 'Échanges physiques (total)',
    'ech_comm_angleterre': 'Angleterre',
    'ech_comm_espagne': 'Espagne',
    'ech_comm_italie': 'Italie',
    'ech_comm_suisse': 'Suisse',
    'ech_comm_allemagne_belgique': 'Allemagne / Belgique',
}


# ========== Traduction des sources ==========

SOURCE_LABELS = {
    'Consolidated Data': 'Données Consolidées',
    'Real-Time Data': 'Temps Réel',
}


# ========== Fonctions utilitaires ==========

@lru_cache(maxsize=1)
def get_production_colors_and_labels():
    """
    Génère les dictionnaires colors et labels pour les graphiques empilés.
    Utilise @lru_cache pour éviter de recalculer à chaque appel.

    Returns:
        tuple: (colors_dict, labels_dict)
    """
    colors = {}
    labels = {}

    for filiere, label in FILIERES.items():
        color = FILIERE_COLORS[filiere]

        # Suffixes pour les colonnes annuelles et mensuelles
        yearly_key = f'{filiere}_yearly_mwh'
        monthly_key = f'{filiere}_mwh'

        colors[yearly_key] = color
        colors[monthly_key] = color
        labels[yearly_key] = label
        labels[monthly_key] = label

    return colors, labels


def get_filiere_columns(period='annual'):
    """
    Retourne la liste des colonnes de filières selon la période.

    Args:
        period: 'annual' ou 'monthly'

    Returns:
        list: Liste des noms de colonnes
    """
    suffix = '_yearly_mwh' if period == 'annual' else '_mwh'
    return [f'{filiere}{suffix}' for filiere in FILIERES.keys()]
