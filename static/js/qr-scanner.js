// QR Code scanner initialization
let html5QrcodeScanner = null;

// Function to show alerts
function showAlert(message, type = 'info') {
    const resultsDiv = document.getElementById('qr-reader-results');
    if (!resultsDiv) return;

    const alertDiv = document.createElement('div');
    alertDiv.className = `alert alert-${type} alert-dismissible fade show`;
    alertDiv.role = 'alert';
    alertDiv.innerHTML = `
        ${message}
        <button type="button" class="btn-close" data-bs-dismiss="alert" aria-label="Close"></button>
    `;
    
    resultsDiv.innerHTML = '';
    resultsDiv.appendChild(alertDiv);

    // Auto dismiss after 5 seconds
    setTimeout(() => {
        alertDiv.classList.remove('show');
        setTimeout(() => alertDiv.remove(), 300);
    }, 5000);
}

// Initialize the scanner when the page loads
document.addEventListener('DOMContentLoaded', function() {
    const startButton = document.getElementById('startButton');
    const stopButton = document.getElementById('stopButton');

    if (!startButton || !stopButton) {
        console.error('Scanner buttons not found');
        return;
    }

    // Configure the scanner
    const isMobile = /iPhone|iPad|iPod|Android/i.test(navigator.userAgent);
    
    html5QrcodeScanner = new Html5QrcodeScanner(
        "qr-reader",
        {
            fps: 10,
            qrbox: { width: 250, height: 250 },
            aspectRatio: isMobile ? 1.0 : 1.777778,
            videoConstraints: {
                facingMode: isMobile ? "environment" : "user",
                width: { min: 640, ideal: 1280, max: 1920 },
                height: { min: 480, ideal: 720, max: 1080 }
            },
            showTorchButtonIfSupported: true,
            showZoomSliderIfSupported: true,
            defaultZoom: 1
        },
        false // Don't start scanning automatically
    );

    // Add button event listeners
    startButton.addEventListener('click', startScanner);
    stopButton.addEventListener('click', stopScanner);
});

function startScanner() {
    if (!html5QrcodeScanner) {
        showAlert('Scanner not initialized properly. Please refresh the page.', 'danger');
        return;
    }

    // Update button states
    const startButton = document.getElementById('startButton');
    const stopButton = document.getElementById('stopButton');
    
    startButton.disabled = true;
    startButton.innerHTML = '<span class="spinner-border spinner-border-sm me-2"></span>Starting Camera...';
    stopButton.disabled = false;

    // Clear any previous messages
    showAlert('Starting camera... Please wait.', 'info');

    // Add camera selection handler for desktop/laptop
    if (!/iPhone|iPad|iPod|Android/i.test(navigator.userAgent)) {
        setTimeout(() => {
            const cameraSelectElement = document.querySelector('#qr-reader__dashboard_section_csr select');
            if (cameraSelectElement) {
                cameraSelectElement.addEventListener('change', () => {
                    showAlert('Switching camera...', 'info');
                });
            }
        }, 1000);
    }

    // Clear any previous results
    const resultsDiv = document.getElementById('qr-reader-results');
    if (resultsDiv) resultsDiv.innerHTML = '';

    // Start scanning (single render call)
    try {
        html5QrcodeScanner.render(onScanSuccess, onScanError);
    } catch (err) {
        handleScannerError(err);
        return;
    }

    // Show startup message
    showAlert('Scanner starting... Please allow camera access if prompted.', 'info');

    startButton.innerHTML = '<i class="fas fa-camera"></i> Camera Active';
    showAlert('Point the camera at a QR code to scan.', 'info');
}

function handleScannerError(err) {
    console.error(`QR Code Scanner failed to start: ${err}`);
    const startButton = document.getElementById('startButton');
    startButton.disabled = false;
    startButton.innerHTML = '<i class="fas fa-camera"></i> Start Scanner';
    
    if (err.name === 'NotAllowedError') {
        showAlert('Camera access was denied. Please allow camera access and try again.', 'danger');
    } else if (err.name === 'NotFoundError') {
        showAlert('No camera found. Please make sure your device has a working camera.', 'danger');
    } else if (err.name === 'NotReadableError') {
        showAlert('Camera is in use by another application. Please close other apps using the camera.', 'danger');
    } else {
        showAlert('Error starting scanner: ' + err.message, 'danger');
    }
}

function stopScanner() {
    if (!html5QrcodeScanner) {
        return;
    }

    html5QrcodeScanner.clear().then(() => {
        // Update button states
        const startButton = document.getElementById('startButton');
        const stopButton = document.getElementById('stopButton');
        
        startButton.disabled = false;
        startButton.innerHTML = '<i class="fas fa-camera"></i> Start Scanner';
        stopButton.disabled = true;

        showAlert('Scanner stopped', 'info');
    }).catch((err) => {
        console.error('Error stopping scanner:', err);
        showAlert('Error stopping scanner. Please refresh the page.', 'danger');
    });
}

function onScanSuccess(decodedText) {
    console.log('QR code scanned:', decodedText);
    try {
        const data = JSON.parse(decodedText);
        
        // Validate required fields
        if (!data.student_id || !data.name) {
            throw new Error('Invalid QR code data: Missing required fields');
        }

        // Stop scanning and update UI
        stopScanner();
        showAlert(`Successfully scanned QR code for ${data.name}`, 'success');
        
        // Mark attendance
        markAttendance(data.student_id);
    } catch (error) {
        console.error('Error parsing QR code:', error);
        showAlert('Invalid QR code format. Please try scanning again.', 'danger');
    }
}

// Handle scanning errors
function onScanError(error) {
    // Only show errors that aren't normal scanning process messages
    if (error !== 'No QR code found') {
        console.error('Scan error:', error);
        showAlert(`Scanner error: ${error}`, 'danger');
    }
}

function markAttendance(studentId) {
    // Get current time to determine meal type
    const now = new Date();
    const hour = now.getHours();
    const mealType = hour < 15 ? 'lunch' : 'dinner';  // Before 3 PM is lunch, after is dinner

    // Show loading state
    showAlert(`Marking ${mealType} attendance...`, 'info');

    // Get CSRF token
    const csrfToken = document.querySelector('meta[name="csrf-token"]')?.getAttribute('content');
    if (!csrfToken) {
        showAlert('CSRF token not found. Please refresh the page.', 'danger');
        return;
    }

    // Send attendance request
    fetch('/mark-attendance', {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json',
            'X-CSRFToken': csrfToken
        },
        body: JSON.stringify({
            student_id: studentId,
            meal_type: mealType,
            method: 'qr'
        })
    })
    .then(response => {
        if (!response.ok) {
            throw new Error(`HTTP error! status: ${response.status}`);
        }
        return response.json();
    })
    .then(data => {
        if (data.success) {
            showAlert(`✅ Attendance marked successfully for ${mealType}!`, 'success');
            // Automatically reload after 2 seconds to update the attendance list
            setTimeout(() => window.location.reload(), 2000);
        } else {
            throw new Error(data.error || 'Failed to mark attendance');
        }
    })
    .catch(error => {
        console.error('Error:', error);
        showAlert(`❌ ${error.message || 'Error marking attendance'}`, 'danger');
        
        // Re-enable scanner after error
        startScanner();
    });
}

