document.addEventListener('DOMContentLoaded', function() {
    // Initialize event listeners
    initializeEventListeners();
});

function initializeEventListeners() {
    // Initialize delete buttons
    const deleteButtons = document.querySelectorAll('.delete-attendance');
    deleteButtons.forEach(button => {
        button.addEventListener('click', function(e) {
            e.preventDefault();
            const attendanceId = this.getAttribute('data-id');
            if (confirm('Are you sure you want to delete this attendance record?')) {
                deleteAttendance(attendanceId, this);
            }
        });
    });

    // Refresh button
    const refreshButton = document.getElementById('refreshAttendance');
    if (refreshButton) {
        refreshButton.addEventListener('click', handleRefresh);
    }

    // Apply Filters button
    const applyFiltersBtn = document.getElementById('applyFilters');
    if (applyFiltersBtn) {
        applyFiltersBtn.addEventListener('click', handleFilterApply);
    }

    // Toggle custom date inputs based on selection
    const dateFilter = document.getElementById('dateFilter');
    const customRange = document.getElementById('customRangeInputs');
    if (dateFilter && customRange) {
        const toggleCustom = () => {
            customRange.style.display = dateFilter.value === 'custom' ? 'flex' : 'none';
        };
        dateFilter.addEventListener('change', toggleCustom);
        // Initialize on load
        toggleCustom();

        // Prefill from query params if present
        try {
            const url = new URL(window.location.href);
            const start = url.searchParams.get('startDate');
            const end = url.searchParams.get('endDate');
            if (start) document.getElementById('startDate').value = start;
            if (end) document.getElementById('endDate').value = end;
        } catch {}
    }

    // Edit buttons
    const editButtons = document.querySelectorAll('.edit-attendance');
    editButtons.forEach(button => {
        button.addEventListener('click', function(e) {
            e.preventDefault();
            const id = this.getAttribute('data-id');
            const date = this.getAttribute('data-date');
            const meal = this.getAttribute('data-meal');

            // Populate modal fields
            document.getElementById('editAttendanceId').value = id;
            document.getElementById('editAttendanceDate').value = date;
            document.getElementById('editAttendanceMeal').value = meal;
            const warn = document.getElementById('editAttendanceWarning');
            if (warn) { warn.classList.add('d-none'); warn.textContent = ''; }

            // Show modal
            const modalEl = document.getElementById('editAttendanceModal');
            if (modalEl) {
                const modal = new bootstrap.Modal(modalEl, { backdrop: false, keyboard: true });
                modal.show();
            }
        });
    });

    // Save changes
    const saveBtn = document.getElementById('saveAttendanceChanges');
    if (saveBtn) {
        saveBtn.addEventListener('click', handleAttendanceSave);
    }

    // Copy scan URL
    const copyBtn = document.getElementById('copyScanUrlBtn');
    if (copyBtn) {
        copyBtn.addEventListener('click', async () => {
            const input = document.getElementById('sessionScanUrl');
            if (!input || !input.value) return;
            try {
                await navigator.clipboard.writeText(input.value);
                const original = copyBtn.innerHTML;
                copyBtn.innerHTML = '<i class="fas fa-check me-1"></i>Copied';
                setTimeout(() => copyBtn.innerHTML = original, 1500);
            } catch (e) {
                // Fallback
                input.select();
                document.execCommand('copy');
            }
        });
    }
}

function handleRefresh() {
    const button = document.getElementById('refreshAttendance');
    showButtonLoading(button, 'Refreshing...');
    window.location.reload();
}

function handleFilterApply() {
    const button = document.getElementById('applyFilters');
    showButtonLoading(button, 'Applying...');
    // Build query parameters and navigate so server returns filtered data
    try {
        const params = new URLSearchParams();
        const dateFilter = document.getElementById('dateFilter')?.value || 'today';
        params.set('dateRange', dateFilter);

        if (dateFilter === 'custom') {
            const start = document.getElementById('startDate')?.value;
            const end = document.getElementById('endDate')?.value;
            if (!start || !end) {
                hideButtonLoading(button, '<i class="fas fa-check me-1"></i> Apply Filters');
                alert('Please select both start and end dates for custom range');
                return;
            }
            params.set('startDate', start);
            params.set('endDate', end);
        }

        const mealType = document.getElementById('mealFilter')?.value || 'all';
        params.set('mealType', mealType);

        const sort = document.getElementById('sortFilter')?.value || 'recent';
        params.set('sort', sort);

        // Navigate to attendance with filters
        window.location.href = `/attendance?${params.toString()}`;
    } catch (e) {
        console.error('Failed to apply filters:', e);
        hideButtonLoading(button, '<i class="fas fa-check me-1"></i> Apply Filters');
    }
}

function showButtonLoading(button, text) {
    button.originalContent = button.innerHTML;
    button.innerHTML = `<span class="spinner-border spinner-border-sm me-1" role="status" aria-hidden="true"></span> ${text}`;
    button.disabled = true;
}

function hideButtonLoading(button, content) {
    button.innerHTML = content || button.originalContent;
    button.disabled = false;
}

function applyFilters() {
    try {
        const tbody = document.querySelector('table tbody');
        if (!tbody) return;

        // Get all data rows (excluding the no-results message)
        let rows = Array.from(tbody.querySelectorAll('tr:not([id="noResults"])'));
        if (rows.length === 0) return;

        // Apply meal type filter
        rows = filterByMealType(rows);

        // Sort the filtered rows
        rows = sortRows(rows);

        // Update the table
        updateTableRows(tbody, rows);
        
        // Check if table is empty
        checkTableEmpty();
    } catch (error) {
        console.error('Error applying filters:', error);
        showNotification('error', '<i class="fas fa-exclamation-circle me-1"></i> Error applying filters');
    }
}

function filterByMealType(rows) {
    const mealFilter = document.getElementById('mealFilter');
    if (!mealFilter || mealFilter.value === 'all') return rows;

    return rows.filter(row => {
        const mealBadge = row.querySelector('td:nth-child(3) .badge');
        if (!mealBadge) return false;
        
        const mealType = mealBadge.textContent.trim().toLowerCase();
        return mealType.includes(mealFilter.value.toLowerCase());
    });
}

function sortRows(rows) {
    const sortFilter = document.getElementById('sortFilter');
    if (!sortFilter) return rows;

    return rows.sort((a, b) => {
        switch (sortFilter.value) {
            case 'name':
                return compareNames(a, b);
            case 'recent':
                return compareTimes(a, b);
            case 'mealType':
                return compareMealTypes(a, b);
            default:
                return 0;
        }
    });
}

function compareNames(rowA, rowB) {
    const nameA = rowA.querySelector('td:nth-child(2) .fw-bold')?.textContent.trim() || '';
    const nameB = rowB.querySelector('td:nth-child(2) .fw-bold')?.textContent.trim() || '';
    return nameA.localeCompare(nameB);
}

function compareTimes(rowA, rowB) {
    const timeA = rowA.querySelector('td:nth-child(1)')?.textContent.trim() || '';
    const timeB = rowB.querySelector('td:nth-child(1)')?.textContent.trim() || '';
    // Parse times in 12-hour format
    const [timeADate, timeBDate] = [timeA, timeB].map(time => {
        const [rawTime, meridian] = time.split(' ');
        const [hours, minutes] = rawTime.split(':').map(Number);
        const date = new Date();
        date.setHours(meridian === 'PM' && hours !== 12 ? hours + 12 : hours);
        date.setMinutes(minutes);
        return date;
    });
    return timeBDate - timeADate; // Most recent first
}

function compareMealTypes(rowA, rowB) {
    const mealA = rowA.querySelector('td:nth-child(3) .badge')?.textContent.trim() || '';
    const mealB = rowB.querySelector('td:nth-child(3) .badge')?.textContent.trim() || '';
    return mealA.localeCompare(mealB);
}

function updateTableRows(tbody, filteredRows) {
    // Clear existing rows
    const existingRows = tbody.querySelectorAll('tr:not([id="noResults"])');
    existingRows.forEach(row => row.remove());

    // Show no results message or append filtered rows
    if (filteredRows.length === 0) {
        showNoResultsMessage(tbody);
    } else {
        // Remove any existing no-results message
        const noResults = tbody.querySelector('#noResults');
        if (noResults) noResults.remove();
        
        // Append filtered rows
        filteredRows.forEach(row => tbody.appendChild(row));
    }
}

function showNoResultsMessage(tbody) {
    // Clear existing content
    tbody.innerHTML = '';
    
    // Add no results message
    const noResultsRow = document.createElement('tr');
    noResultsRow.id = 'noResults';
    noResultsRow.innerHTML = `
        <td colspan="5" class="text-center py-4">
            <div class="text-muted">
                <i class="fas fa-filter fa-3x mb-3"></i>
                <p class="mb-0">No attendance records match the selected filters</p>
            </div>
        </td>
    `;
    tbody.appendChild(noResultsRow);
}

function checkTableEmpty() {
    const tbody = document.querySelector('table tbody');
    if (!tbody) return;
    
    const rows = tbody.querySelectorAll('tr:not([id="noResults"])');
    if (rows.length === 0) {
        showEmptyTableMessage(tbody);
    }
}

function showEmptyTableMessage(tbody) {
    // Clear existing content
    tbody.innerHTML = '';
    
    // Add empty message
    const emptyRow = document.createElement('tr');
    emptyRow.id = 'noResults';
    emptyRow.innerHTML = `
        <td colspan="5" class="text-center py-4">
            <div class="text-muted">
                <i class="fas fa-inbox fa-3x mb-3"></i>
                <p class="mb-0">No attendance records found</p>
            </div>
        </td>
    `;
    tbody.appendChild(emptyRow);
}

function deleteAttendance(attendanceId, button) {
    // Show loading state
    const row = button.closest('tr');
    button.disabled = true;
    button.innerHTML = '<span class="spinner-border spinner-border-sm" role="status" aria-hidden="true"></span>';

    // Get CSRF token from meta tag
    const csrfToken = document.querySelector('meta[name="csrf-token"]').getAttribute('content');

    fetch(`/delete-attendance/${attendanceId}`, {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json',
            'X-CSRFToken': csrfToken
        },
        credentials: 'same-origin'
    })
    .then(response => {
        if (!response.ok) {
            throw new Error('Network response was not ok');
        }
        return response.json();
    })
    .then(data => {
        if (data.success) {
            // Fade out and remove the row
            row.style.transition = 'opacity 0.5s ease';
            row.style.opacity = '0';
            setTimeout(() => {
                row.remove();
                checkTableEmpty();
            }, 500);
            
            showNotification('success', data.message || 'Record deleted successfully');
        } else {
            throw new Error(data.message || 'Failed to delete record');
        }
    })
    .catch(error => {
        console.error('Error:', error);
        button.disabled = false;
        button.innerHTML = '<i class="fas fa-trash-alt"></i>';
        showNotification('error', '<i class="fas fa-exclamation-circle me-1"></i> Failed to delete record');
    });
}

// Notification system
function showNotification(type, message) {
    // Remove existing notifications
    const existingNotifications = document.querySelectorAll('.floating-notification');
    existingNotifications.forEach(notification => notification.remove());

    // Create new notification
    const notification = document.createElement('div');
    notification.className = `floating-notification alert alert-${type === 'success' ? 'success' : 'danger'} alert-dismissible fade show`;
    notification.innerHTML = `
        ${message}
        <button type="button" class="btn-close" data-bs-dismiss="alert" aria-label="Close"></button>
    `;

    // Add to document
    document.body.appendChild(notification);

    // Show with animation
    setTimeout(() => notification.classList.add('show'), 100);

    // Auto dismiss after 5 seconds
    setTimeout(() => {
        notification.classList.remove('show');
        setTimeout(() => notification.remove(), 500);
    }, 5000);
}

async function handleAttendanceSave() {
    const saveBtn = document.getElementById('saveAttendanceChanges');
    const id = document.getElementById('editAttendanceId').value;
    const date = document.getElementById('editAttendanceDate').value;
    const meal = document.getElementById('editAttendanceMeal').value;
    const warn = document.getElementById('editAttendanceWarning');

    if (!id || !date || !meal) return;

    showButtonLoading(saveBtn, 'Saving...');

    const csrfToken = document.querySelector('meta[name="csrf-token"]').getAttribute('content');

    try {
        const res = await fetch(`/update-attendance/${id}`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'X-CSRFToken': csrfToken
            },
            credentials: 'same-origin',
            body: JSON.stringify({ date: date, meal_type: meal })
        });

        const data = await res.json();
        if (!res.ok || !data.success) {
            throw new Error(data.message || 'Failed to update');
        }

        // Close modal and refresh to reflect changes
        const modalEl = document.getElementById('editAttendanceModal');
        if (modalEl) {
            const modal = bootstrap.Modal.getInstance(modalEl) || new bootstrap.Modal(modalEl);
            modal.hide();
        }
        showNotification('success', data.message || 'Updated successfully');
        setTimeout(() => window.location.reload(), 600);
    } catch (e) {
        if (warn) {
            warn.textContent = e.message;
            warn.classList.remove('d-none');
        }
        hideButtonLoading(saveBtn);
    }
}