/**
 * Validation du formulaire de filtre par dates.
 * Empêche la soumission si la date de début est postérieure à la date de fin.
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

        function validateDates(e) {
            var startDate = startDateInput.value;
            var endDate = endDateInput.value;

            if (startDate && endDate && startDate > endDate) {
                e.preventDefault();
                errorDiv.style.display = 'block';
            } else {
                hideError();
            }
        }

        form.addEventListener('submit', validateDates);
        startDateInput.addEventListener('change', hideError);
        endDateInput.addEventListener('change', hideError);
    });
})();
