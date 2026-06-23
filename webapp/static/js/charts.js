/**
 * Helpers partagés par les pages à graphiques (chargé via partials/_plotly.html,
 * juste après Plotly). Factorise ce qui était copié-collé dans chaque template :
 * rendu des graphiques, resize au changement d'onglet, scrollspy de la sidebar.
 */
window.KiloWatch = window.KiloWatch || {};

KiloWatch.PLOT_CONFIG = { responsive: true, displayModeBar: false };

// Markup d'erreur réutilisé par renderChart et loadCharts.
var _CHART_ERROR_HTML =
    '<div class="chart-error-msg"><i class="ti ti-alert-triangle me-1"></i>' +
    'Le graphique n\'a pas pu être affiché.</div>';

function _chartError(el) {
    KiloWatch._hideOverlay(el.id);
    el.classList.add('chart-error');
    el.setAttribute('role', 'alert');
    el.innerHTML = _CHART_ERROR_HTML;
}

/**
 * Affiche un overlay spinner dans le .chart-container parent du div id donné.
 * L'overlay est un vrai élément DOM (les pseudo-éléments sont écrasés par
 * le contexte de stacking interne de Plotly).
 */
KiloWatch._showOverlay = function(id) {
    var el = document.getElementById(id);
    if (!el) return;
    var container = el.parentElement;
    if (!container) return;
    if (container.querySelector('.chart-overlay[data-for="' + id + '"]')) return;
    var overlay = document.createElement('div');
    overlay.className = 'chart-overlay';
    overlay.setAttribute('data-for', id);
    container.appendChild(overlay);
};

/**
 * Retire l'overlay spinner du .chart-container parent du div id donné.
 */
KiloWatch._hideOverlay = function(id) {
    var el = document.getElementById(id);
    if (!el) return;
    var container = el.parentElement;
    if (!container) return;
    var overlay = container.querySelector('.chart-overlay[data-for="' + id + '"]');
    if (overlay) container.removeChild(overlay);
};

/**
 * Rend un graphique Plotly à partir du JSON sérialisé par la vue Django.
 * Affiche un message d'erreur en cas d'échec (JSON corrompu, exception Plotly…).
 * @param {string} id - id du div cible
 * @param {string} json - figure Plotly sérialisée (data + layout)
 * @param {Object} [config] - config Plotly (défaut : PLOT_CONFIG)
 */
KiloWatch.renderChart = function(id, json, config) {
    var el = document.getElementById(id);
    if (!el) return;

    KiloWatch._hideOverlay(id);

    try {
        var chart = JSON.parse(json);
        Plotly.newPlot(el, chart.data, chart.layout, config || KiloWatch.PLOT_CONFIG);
    } catch (err) {
        _chartError(el);
        if (window.console) console.error('KiloWatch.renderChart(' + id + '):', err);
    }
};

/**
 * Charge les graphiques d'une page en AJAX et les rend avec Plotly.
 * Affiche un overlay spinner sur chaque div cible pendant le fetch.
 *
 * @param {string}   url       - URL à fetcher (avec éventuels query params)
 * @param {string[]} targetIds - ids des divs à charger
 */
KiloWatch.loadCharts = function(url, targetIds) {
    targetIds.forEach(function(id) { KiloWatch._showOverlay(id); });

    fetch(url, { headers: { 'X-Requested-With': 'XMLHttpRequest' } })
        .then(function(response) {
            if (!response.ok) throw new Error('HTTP ' + response.status);
            return response.json();
        })
        .then(function(data) {
            Object.keys(data.charts).forEach(function(id) {
                var el = document.getElementById(id);
                if (!el) return;
                KiloWatch._hideOverlay(id);
                try {
                    var c = data.charts[id];
                    Plotly.newPlot(el, c.data, c.layout, KiloWatch.PLOT_CONFIG);
                } catch (err) {
                    _chartError(el);
                    if (window.console) console.error('KiloWatch.loadCharts(' + id + '):', err);
                }
            });
        })
        .catch(function(err) {
            targetIds.forEach(function(id) {
                var el = document.getElementById(id);
                if (el) _chartError(el);
            });
            if (window.console) console.error('KiloWatch.loadCharts:', err);
        });
};

document.addEventListener('DOMContentLoaded', function() {
    'use strict';

    // Les graphiques rendus dans un onglet masqué ont une largeur nulle :
    // forcer un resize quand l'onglet devient visible.
    document.querySelectorAll('button[data-bs-toggle="tab"]').forEach(function(button) {
        button.addEventListener('shown.bs.tab', function() {
            window.dispatchEvent(new Event('resize'));
        });
    });

    // Scrollspy de la sidebar « Sur cette page » via IntersectionObserver
    var nav = document.getElementById('page-nav');
    if (!nav) return;

    var navLinks = nav.querySelectorAll('.nav-link[href^="#"]');
    var sections = [];
    navLinks.forEach(function(link) {
        var section = document.querySelector(link.getAttribute('href'));
        if (section) sections.push(section);
    });

    var observer = new IntersectionObserver(function(entries) {
        entries.forEach(function(entry) {
            if (entry.isIntersecting) {
                navLinks.forEach(function(link) { link.classList.remove('active'); });
                var active = nav.querySelector('a[href="#' + entry.target.id + '"]');
                if (active) active.classList.add('active');
            }
        });
    }, { rootMargin: '-15% 0px -70% 0px' });

    sections.forEach(function(section) { observer.observe(section); });
});
