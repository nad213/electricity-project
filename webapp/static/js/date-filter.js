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

            // Overlay spinner uniquement sur les graphiques dynamiques (pas data-chart-static)
            var chartIds = [];
            document.querySelectorAll('.chart-container > [id]:not([data-chart-static])').forEach(function(el) {
                chartIds.push(el.id);
                if (window.ElecStat) ElecStat._showOverlay(el.id);
            });

            var params = new URLSearchParams(new FormData(form)).toString();
            var url = window.location.pathname + '?_dynamic_only=1&' + params;

            // Double requestAnimationFrame : garantit que le navigateur peigne
            // l'overlay avant le fetch. Sans ça, si le serveur répond vite
            // (local + cache Parquet), l'overlay est retiré avant le prochain
            // paint et n'est jamais visible.
            requestAnimationFrame(function() {
                requestAnimationFrame(function() {
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
                        var plotConfig = (window.ElecStat && ElecStat.PLOT_CONFIG) || { responsive: true, displayModeBar: false };
                        Object.keys(data.charts).forEach(function(chartId) {
                            if (window.ElecStat) ElecStat._hideOverlay(chartId);
                            var el = document.getElementById(chartId);
                            if (el) {
                                el.classList.remove('chart-error');
                                el.removeAttribute('role');
                            }
                            var chartData = data.charts[chartId];
                            Plotly.react(chartId, chartData.data, chartData.layout, plotConfig);
                        });
                        window.history.replaceState(null, '', window.location.pathname + '?' + params);
                        document.querySelectorAll('a[href*="export"]:not([data-static-export])').forEach(function(link) {
                            var baseUrl = link.href.split('?')[0];
                            link.href = baseUrl + '?' + params;
                        });
                    })
                    .catch(function(err) {
                        if (window.ElecStat) chartIds.forEach(function(id) { ElecStat._hideOverlay(id); });
                        showError(err.message || 'Erreur lors de la mise à jour des graphiques.');
                    })
                    .finally(function() {
                        submitBtn.disabled = false;
                        submitBtn.innerHTML = originalHTML;
                    });
                });
            });
        });

        startDateInput.addEventListener('change', hideError);
        endDateInput.addEventListener('change', hideError);

        // Presets de période : remplissent les dates (calées sur la dernière
        // donnée disponible, pas sur la date du jour) puis soumettent le
        // formulaire, ce qui déclenche la mise à jour AJAX ci-dessus.
        form.querySelectorAll('.date-preset').forEach(function(btn) {
            btn.addEventListener('click', function() {
                var days = parseInt(btn.dataset.days, 10);
                var maxDate = endDateInput.max;
                if (!days || !maxDate) {
                    return;
                }
                var start = new Date(maxDate + 'T00:00:00Z');
                start.setUTCDate(start.getUTCDate() - (days - 1));
                var startStr = start.toISOString().slice(0, 10);
                if (startDateInput.min && startStr < startDateInput.min) {
                    startStr = startDateInput.min;
                }
                startDateInput.value = startStr;
                endDateInput.value = maxDate;
                hideError();
                form.requestSubmit();
            });
        });
    });
})();
