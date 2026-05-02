console.log('Initializing WebSocket connection...');
let ws = null;
let reconnectInterval = null;
let webhookToDelete = null;

function connectWebSocket() {
    const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
    const wsUrl = `${protocol}//${window.location.host}/ws`;
    
    console.log('Connecting to:', wsUrl);
    ws = new WebSocket(wsUrl);
    
    ws.onopen = function() {
        console.log('WebSocket Connected!');
        if (reconnectInterval) {
            clearInterval(reconnectInterval);
            reconnectInterval = null;
        }
    };
    
    ws.onerror = function(error) {
        console.error('WebSocket Error:', error);
    };
    
    ws.onclose = function(event) {
        console.log('WebSocket Disconnected:', event.code, event.reason);
        if (!reconnectInterval) {
            reconnectInterval = setInterval(() => {
                console.log('Attempting to reconnect...');
                connectWebSocket();
            }, 2000);
        }
    };
    
    ws.onmessage = function(event) {
        console.log('WebSocket message received:', event.data);
        try {
            const data = JSON.parse(event.data);
            
            if (data.type === 'new_webhook_request') {
                console.log('Received new_webhook_request event:', data);
                
                // Update the request count for the specific webhook
                const webhookCard = document.querySelector(`[data-webhook-url="${data.webhook_url}"]`);
                if (webhookCard) {
                    const totalStat = webhookCard.querySelector('.webhook-stat:last-child strong');
                    if (totalStat) {
                        const currentCount = parseInt(totalStat.textContent) || 0;
                        totalStat.textContent = currentCount + 1;
                    }
                } else {
                    // If we can't find the specific card, reload the page
                    console.log('Reloading page to show new request...');
                    location.reload();
                }
            }
        } catch (e) {
            console.error('Error parsing WebSocket message:', e);
        }
    };
}

// Initialize connection
connectWebSocket();

// Convert UTC timestamps to local time
function formatLocalTime(utcString) {
    const date = new Date(utcString);
    return date.toLocaleString(undefined, {
        month: 'short',
        day: 'numeric',
        year: 'numeric',
        hour: '2-digit',
        minute: '2-digit'
    });
}

// DOM Ready
document.addEventListener('DOMContentLoaded', function() {
    // Convert all UTC timestamps to local time
    document.querySelectorAll('.last-activity-time[data-utc]').forEach(el => {
        const utc = el.dataset.utc;
        if (utc) {
            el.textContent = formatLocalTime(utc);
        }
    });

    const createDialog = document.querySelector('.create-dialog');
    const deleteDialog = document.querySelector('.delete-dialog');
    const successAlert = document.querySelector('.success-alert');
    const warningAlert = document.querySelector('.warning-alert');
    const dangerAlert = document.querySelector('.danger-alert');
    
    // Create webhook buttons
    const createWebhookBtn = document.getElementById('create-webhook-btn');
    const emptyCreateBtn = document.getElementById('empty-create-btn');
    const cancelCreateBtn = document.querySelector('.cancel-create');
    const confirmCreateBtn = document.querySelector('.confirm-create');
    
    // Open create dialog
    function openCreateDialog() {
        createDialog.show();
        document.getElementById('webhook-name').value = '';
        document.getElementById('webhook-url-preview').style.display = 'none';
    }
    
    if (createWebhookBtn) {
        createWebhookBtn.addEventListener('click', openCreateDialog);
    }
    
    if (emptyCreateBtn) {
        emptyCreateBtn.addEventListener('click', openCreateDialog);
    }
    
    // Cancel create
    if (cancelCreateBtn) {
        cancelCreateBtn.addEventListener('click', () => {
            createDialog.hide();
        });
    }
    
    // Confirm create
    if (confirmCreateBtn) {
        confirmCreateBtn.addEventListener('click', () => {
            const name = document.getElementById('webhook-name').value.trim();
            
            if (!name) {
                alert('Please enter a webhook name');
                return;
            }
            
            confirmCreateBtn.loading = true;
            
            fetch('/add_webhook', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json'
                },
                body: JSON.stringify({ name })
            })
            .then(response => response.json())
            .then(data => {
                // Show generated URL
                document.getElementById('generated-url').textContent = data.url;
                document.getElementById('copy-generated-url').value = data.url;
                document.getElementById('webhook-url-preview').style.display = 'block';
                
                // Update success message
                document.getElementById('success-message').textContent = `Webhook "${data.name}" created successfully!`;
                
                // Close dialog and show success
                setTimeout(() => {
                    createDialog.hide();
                    successAlert.toast();
                    
                    // Reload page after a short delay
                    setTimeout(() => {
                        location.reload();
                    }, 1500);
                }, 2000);
            })
            .catch(error => {
                console.error('Error creating webhook:', error);
                alert('Failed to create webhook');
            })
            .finally(() => {
                confirmCreateBtn.loading = false;
            });
        });
    }
    
    // Delete webhook
    const deleteButtons = document.querySelectorAll('.delete-webhook-btn');
    const cancelDeleteBtn = document.querySelector('.cancel-delete');
    const confirmDeleteBtn = document.querySelector('.confirm-delete');
    
    deleteButtons.forEach(btn => {
        btn.addEventListener('click', (e) => {
            e.preventDefault();
            webhookToDelete = btn.dataset.webhookUrl;
            deleteDialog.show();
        });
    });
    
    if (cancelDeleteBtn) {
        cancelDeleteBtn.addEventListener('click', () => {
            deleteDialog.hide();
            webhookToDelete = null;
        });
    }
    
    if (confirmDeleteBtn) {
        confirmDeleteBtn.addEventListener('click', () => {
            if (!webhookToDelete) return;
            
            confirmDeleteBtn.loading = true;
            
            fetch('/delete', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json'
                },
                body: JSON.stringify({ url: webhookToDelete })
            })
            .then(response => {
                if (response.ok) {
                    const card = document.querySelector(`[data-webhook-url="${webhookToDelete}"]`);
                    if (card) {
                        card.remove();
                    }
                    deleteDialog.hide();
                    dangerAlert.toast();
                    webhookToDelete = null;
                }
            })
            .catch(error => {
                console.error('Error deleting webhook:', error);
                alert('Failed to delete webhook');
            })
            .finally(() => {
                confirmDeleteBtn.loading = false;
            });
        });
    }
    
    // Toggle webhook status
    const toggles = document.querySelectorAll('.webhook-toggle');
    toggles.forEach(toggle => {
        toggle.addEventListener('sl-change', (e) => {
            const webhookUrl = toggle.dataset.webhookUrl;
            const isActive = e.target.checked;
            
            fetch('/pause', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json'
                },
                body: JSON.stringify({ url: webhookUrl })
            })
            .then(response => response.json())
            .then(data => {
                if (data.status !== undefined) {
                    // Update badge
                    const card = document.querySelector(`[data-webhook-url="${webhookUrl}"]`);
                    if (card) {
                        const badge = card.querySelector('sl-badge');
                        if (data.status) {
                            badge.variant = 'success';
                            badge.textContent = 'ACTIVE';
                            successAlert.toast();
                        } else {
                            badge.variant = 'warning';
                            badge.textContent = 'PAUSED';
                            warningAlert.toast();
                        }
                    }
                }
            })
            .catch(error => {
                console.error('Error toggling webhook:', error);
                // Revert toggle on error
                toggle.checked = !isActive;
            });
        });
    });
    
    // Copy URL buttons
    const copyButtons = document.querySelectorAll('.copy-url-btn');
    copyButtons.forEach(btn => {
        btn.addEventListener('click', (e) => {
            e.preventDefault();
            const url = btn.dataset.url;
            
            navigator.clipboard.writeText(url).then(() => {
                btn.name = 'check';
                setTimeout(() => {
                    btn.name = 'clipboard';
                }, 2000);
            });
        });
    });
    
    // Search functionality
    const searchInput = document.querySelector('.search-input');
    if (searchInput) {
        searchInput.addEventListener('sl-input', (e) => {
            const filter = e.target.value.toLowerCase();
            const cards = document.querySelectorAll('.webhook-card');
            
            cards.forEach(card => {
                const name = card.querySelector('.webhook-name').textContent.toLowerCase();
                const path = card.querySelector('.webhook-path').textContent.toLowerCase();
                
                if (name.includes(filter) || path.includes(filter)) {
                    card.style.display = '';
                } else {
                    card.style.display = 'none';
                }
            });
        });
    }
});
