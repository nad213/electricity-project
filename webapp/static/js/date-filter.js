/**
 * Formulaire de filtre : validation des dates + mise à jour AJAX des graphiques.
 * Intercepte le submit, récupère le JSON des graphiques via fetch(), et met à
 * jour uniquement les graphiques avec Plotly.react() sans recharger la page.
 */
(function() {
    'use strict';

    document.addEventListener('DOMContentLoaded', function() {
        var form = document.getElementById('date-filter-form');
        var startDateInput = document.getElementById('start_date');
        var endDateInput = document.getElementById('end_date');
        var errorDiv = document.getElementById('date-error');

        if (!form || !startDateInput || !endDateInput || !errorDiv) {
            return;
        }

        function hideError() {
            errorDiv.style.display = 'none';
        }

        function showError(message) {
            errorDiv.innerHTML = '<i class="ti ti-alert-circle me-1"></i>' + message;
            errorDiv.style.display = 'block';
        }

        function validateDates() {
            var startDate = startDateInput.value;
            var endDate = endDateInput.value;
            if (startDate && endDate && startDate > endDate) {
                showError('La date de début doit être antérieure à la date de fin.');
                return false;
            }
            hideError();
            return true;
        }

        form.addEventListener('submit', function(e) {
            e.preventDefault();

            if (!validateDates()) {
                return;
            }

            var submitBtn = form.querySelector('button[type="submit"]');
            var originalHTML = submitBtn.innerHTML;
            submitBtn.disabled = true;
            submitBtn.innerHTML = '<span class="spinner-border spinner-border-sm me-1" role="status"></span>Chargement...';

            var params = new URLSearchParams(new FormData(form)).toString();
            var url = window.location.pathname + '?' + params;

            fetch(url, {
                headers: { 'X-Requested-With': 'XMLHttpRequest' }
            })
            .then(function(response) {
                if (!response.ok) {
                    return response.text().then(function(text) {
                        throw new Error(text || 'Erreur serveur (' + response.status + ')');
                    });
                }
                return response.json();
            })
            .then(function(data) {
                var plotConfig = { responsive: true };
                Object.keys(data.charts).forEach(function(chartId) {
                    var chartData = data.charts[chartId];
                    Plotly.react(chartId, chartData.data, chartData.layout, plotConfig);
                });
                // Mettre à jour l'URL (pour que refresh/bookmark fonctionnent)
                window.history.replaceState(null, '', url);
                // Mettre à jour les liens d'export CSV avec les nouveaux paramètres
                document.querySelectorAll('a[href*="export"]').forEach(function(link) {
                    var baseUrl = link.href.split('?')[0];
                    link.href = baseUrl + '?' + params;
                });
            })
            .catch(function(err) {
                showError(err.message || 'Erreur lors de la mise à jour des graphiques.');
            })
            .finally(function() {
                submitBtn.disabled = false;
                submitBtn.innerHTML = originalHTML;
            });
        });

        startDateInput.addEventListener('change', hideError);
        endDateInput.addEventListener('change', hideError);
    });
})();
