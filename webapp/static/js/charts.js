/**
 * Helpers partagés par les pages à graphiques (chargé via partials/_plotly.html,
 * juste après Plotly). Factorise ce qui était copié-collé dans chaque template :
 * rendu des graphiques, resize au changement d'onglet, scrollspy de la sidebar.
 */
window.KiloWatch = window.KiloWatch || {};

KiloWatch.PLOT_CONFIG = { responsive: true, displayModeBar: false };

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

    el.removeAttribute('aria-busy');

    try {
        var chart = JSON.parse(json);
        Plotly.newPlot(el, chart.data, chart.layout, config || KiloWatch.PLOT_CONFIG);
    } catch (err) {
        el.classList.add('chart-error');
        el.setAttribute('role', 'alert');
        el.innerHTML = '<div class="chart-error-msg"><i class="ti ti-alert-triangle me-1"></i>Le graphique n\'a pas pu être affiché.</div>';
        if (window.console) console.error('KiloWatch.renderChart(' + id + '):', err);
    }
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
    // (ne dépend pas de Bootstrap). Les sections sont déduites des ancres.
    var nav = document.getElementById('page-nav');
    if (!nav) {
        return;
    }

    var navLinks = nav.querySelectorAll('.nav-link[href^="#"]');
    var sections = [];
    navLinks.forEach(function(link) {
        var section = document.querySelector(link.getAttribute('href'));
        if (section) {
            sections.push(section);
        }
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
