console.log('Initializing WebSocket connection...');
let ws = null;
let reconnectInterval = null;
let currentRequestData = null;

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
                
                const webhookId = document.body.dataset.webhookId;
                const receivedId = String(data.webhook_id);
                console.log('Current webhook ID:', webhookId, 'Received webhook ID:', receivedId);
                
                if (receivedId === webhookId) {
                    console.log('New request for current webhook, adding to list...');
                    addNewRequestToList(data);
                } else {
                    console.log('Request is for a different webhook, ignoring...');
                }
            }
        } catch (e) {
            console.error('Error parsing WebSocket message:', e);
        }
    };
}

function addNewRequestToList(data) {
    const requestList = document.getElementById('request-list');
    const emptyState = requestList.querySelector('.empty-state');
    
    // Remove empty state if present
    if (emptyState) {
        emptyState.remove();
    }
    
    // Format timestamp - convert UTC to local time
    const timestamp = new Date(data.timestamp + (data.timestamp.endsWith('Z') ? '' : 'Z'));
    const timeStr = timestamp.toLocaleString(undefined, {
        month: 'short',
        day: 'numeric',
        hour: '2-digit',
        minute: '2-digit',
        second: '2-digit',
        hour12: false
    });
    
    // Create new request item
    const newItem = document.createElement('div');
    newItem.className = 'request-item';
    newItem.setAttribute('data-request-id', data.request_id);
    newItem.setAttribute('data-status', '200');
    newItem.onclick = function() { showRequest(data.request_id); };
    
    const bodySize = data.body_length || '--';
    
    newItem.innerHTML = `
        <div class="request-header">
            <sl-badge variant="primary" size="small">POST</sl-badge>
            <sl-badge variant="success" size="small" class="status-badge">200 OK</sl-badge>
            <span class="request-time">${timeStr}</span>
        </div>
        <div class="request-path">/${data.webhook_url}</div>
        <div class="request-meta">
            <span class="meta-item">
                <sl-icon name="hdd"></sl-icon>
                ${bodySize} bytes
            </span>
            <sl-icon-button name="trash" label="Delete" class="delete-request-btn" onclick="event.stopPropagation(); deleteRequest(${data.request_id})"></sl-icon-button>
        </div>
    `;
    
    // Insert at the top of the list
    requestList.insertBefore(newItem, requestList.firstChild);
    
    // Update request count in sidebar header
    const countSpan = document.querySelector('.sidebar-title span');
    if (countSpan) {
        const currentCount = parseInt(countSpan.textContent.match(/\d+/)?.[0] || '0');
        countSpan.textContent = `REQUESTS (${currentCount + 1})`;
    }
    
    // Update delete dialog count
    const deleteCount = document.getElementById('delete-count');
    if (deleteCount) {
        deleteCount.textContent = parseInt(deleteCount.textContent || '0') + 1;
    }
    
    // Flash animation
    newItem.style.backgroundColor = '#e0f2fe';
    setTimeout(() => {
        newItem.style.transition = 'background-color 0.5s';
        newItem.style.backgroundColor = '';
    }, 100);
}

// Initialize connection
connectWebSocket();

// Convert UTC timestamps to local time
function formatLocalDateTime(utcString) {
    const date = new Date(utcString);
    return date.toLocaleString(undefined, {
        month: 'short',
        day: 'numeric',
        hour: '2-digit',
        minute: '2-digit',
        second: '2-digit',
        hour12: false
    });
}

function formatLocalTime(utcString) {
    const date = new Date(utcString);
    return date.toLocaleTimeString(undefined, {
        hour: '2-digit',
        minute: '2-digit',
        second: '2-digit',
        hour12: false
    });
}

function convertTimestampsToLocal() {
    // Convert request-time elements (date + time)
    document.querySelectorAll('.request-time[data-utc]').forEach(el => {
        const utc = el.dataset.utc;
        if (utc) {
            el.textContent = formatLocalDateTime(utc);
        }
    });
    
    // Convert meta-time elements (time only)
    document.querySelectorAll('.meta-time[data-utc]').forEach(el => {
        const utc = el.dataset.utc;
        if (utc) {
            el.textContent = formatLocalTime(utc);
        }
    });
}

// Convert timestamps on page load
document.addEventListener('DOMContentLoaded', convertTimestampsToLocal);

// Load more requests
function loadMoreRequests() {
    const loadMoreBtn = document.getElementById('load-more-btn');
    if (!loadMoreBtn) return;
    
    const webhookUrl = loadMoreBtn.dataset.webhookUrl;
    const offset = parseInt(loadMoreBtn.dataset.offset) || 0;
    const total = parseInt(loadMoreBtn.dataset.total) || 0;
    
    loadMoreBtn.loading = true;
    
    fetch(`/api/webhook/${webhookUrl}/requests?offset=${offset}&limit=100`)
        .then(response => response.json())
        .then(data => {
            const requestList = document.getElementById('request-list');
            const loadMoreContainer = document.getElementById('load-more-container');
            
            // Add new request items before the load more button
            data.requests.forEach(req => {
                const newItem = document.createElement('div');
                newItem.className = 'request-item';
                newItem.setAttribute('data-request-id', req.id);
                newItem.setAttribute('data-status', '200');
                newItem.onclick = function() { showRequest(req.id); };
                
                const dateTimeStr = req.timestamp ? formatLocalDateTime(req.timestamp) : 'Unknown';
                
                newItem.innerHTML = `
                    <div class="request-header">
                        <sl-badge variant="primary" size="small">POST</sl-badge>
                        <sl-badge variant="success" size="small" class="status-badge">200 OK</sl-badge>
                        <span class="request-time">${dateTimeStr}</span>
                    </div>
                    <div class="request-path">/${webhookUrl}</div>
                    <div class="request-meta">
                        <span class="meta-item">
                            <sl-icon name="hdd"></sl-icon>
                            ${req.body_length} bytes
                        </span>
                        <sl-icon-button name="trash" label="Delete" class="delete-request-btn" onclick="event.stopPropagation(); deleteRequest(${req.id})"></sl-icon-button>
                    </div>
                `;
                
                requestList.insertBefore(newItem, loadMoreContainer);
            });
            
            // Update offset and remaining count
            const newOffset = offset + data.requests.length;
            const remaining = total - newOffset;
            
            if (data.has_more && remaining > 0) {
                loadMoreBtn.dataset.offset = newOffset;
                loadMoreBtn.innerHTML = `
                    <sl-icon slot="prefix" name="arrow-down-circle"></sl-icon>
                    Load More (${remaining} remaining)
                `;
            } else {
                // Remove load more button if no more requests
                loadMoreContainer.remove();
            }
            
            // Update sidebar count
            const countSpan = document.querySelector('.sidebar-title span');
            if (countSpan) {
                countSpan.textContent = `REQUESTS (${newOffset}/${total})`;
            }
        })
        .catch(error => {
            console.error('Error loading more requests:', error);
        })
        .finally(() => {
            loadMoreBtn.loading = false;
        });
}

// Initialize load more button
document.addEventListener('DOMContentLoaded', function() {
    const loadMoreBtn = document.getElementById('load-more-btn');
    if (loadMoreBtn) {
        loadMoreBtn.addEventListener('click', loadMoreRequests);
    }
});

// Show request details
function showRequest(requestId) {
    // Remove active class from all items
    document.querySelectorAll('.request-item').forEach(item => {
        item.classList.remove('active');
    });
    
    // Add active class to clicked item
    const clickedItem = document.querySelector(`[data-request-id="${requestId}"]`);
    if (clickedItem) {
        clickedItem.classList.add('active');
    }
    
    fetch(`/webhook/request/${requestId}`)
        .then(response => response.json())
        .then(data => {
            currentRequestData = data;
            updateRequestDetails(data);
        })
        .catch(error => {
            console.error('Error fetching request:', error);
        });
}

function updateRequestDetails(data) {
    console.log('Updating request details:', data);
    
    // Update stats bar
    document.getElementById('status-code').textContent = '200 OK';
    
    // Convert timestamp to local time
    let displayTimestamp = data.timestamp || 'N/A';
    if (data.timestamp) {
        const date = new Date(data.timestamp);
        displayTimestamp = date.toLocaleString(undefined, {
            month: 'short',
            day: 'numeric',
            year: 'numeric',
            hour: '2-digit',
            minute: '2-digit',
            second: '2-digit',
            hour12: false
        });
    }
    document.getElementById('timestamp').textContent = displayTimestamp;
    document.getElementById('response-time').textContent = '245ms';
    document.getElementById('size').textContent = `${data.body.length} bytes`;
    
    // Update Body tab
    updateBodyTab(data.body);
    
    // Update Headers tab
    updateHeadersTab(data.headers);
    
    // Update Query Params tab
    updateQueryParamsTab(data.query_params);
}

function updateQueryParamsTab(queryParams) {
    const queryTable = document.getElementById('query-table');
    if (!queryTable) return;
    
    const tbody = queryTable.querySelector('tbody');
    const queryCount = document.getElementById('query-count');
    
    const params = queryParams || {};
    const paramEntries = Object.entries(params);
    
    if (queryCount) {
        queryCount.textContent = paramEntries.length;
    }
    
    tbody.innerHTML = '';
    
    if (paramEntries.length === 0) {
        tbody.innerHTML = '<tr><td colspan="2" class="empty-message">No query parameters</td></tr>';
        return;
    }
    
    paramEntries.forEach(([key, value]) => {
        const row = document.createElement('tr');
        row.innerHTML = `
            <td>${escapeHtml(key)}</td>
            <td>${escapeHtml(value)}</td>
        `;
        tbody.appendChild(row);
    });
}

function updateBodyTab(body) {
    const bodyContent = document.getElementById('body-content');
    const bodyContentText = document.getElementById('body-content-text');
    const codeElement = bodyContent.querySelector('code') || bodyContent;
    
    try {
        const parsed = JSON.parse(body);
        const formatted = JSON.stringify(parsed, null, 2);
        codeElement.textContent = formatted;
        if (bodyContentText) {
            bodyContentText.textContent = formatted;
        }
        
        // Apply syntax highlighting
        highlightJSON(codeElement);
    } catch (e) {
        codeElement.textContent = body;
        if (bodyContentText) {
            bodyContentText.textContent = body;
        }
    }
}

function updateHeadersTab(headers) {
    console.log('Updating headers tab:', headers);
    
    const headersTable = document.getElementById('headers-table');
    if (!headersTable) {
        console.error('Headers table not found');
        return;
    }
    
    const tbody = headersTable.querySelector('tbody');
    const headersCount = document.getElementById('headers-count');
    const headersContentText = document.getElementById('headers-content-text');
    
    tbody.innerHTML = '';
    
    const headerEntries = Object.entries(headers || {});
    if (headersCount) {
        headersCount.textContent = headerEntries.length;
    }
    
    // Update hidden text element for copy button
    if (headersContentText) {
        headersContentText.textContent = JSON.stringify(headers, null, 2);
    }
    
    if (headerEntries.length === 0) {
        tbody.innerHTML = '<tr><td colspan="2" class="empty-message">No headers</td></tr>';
        return;
    }
    
    headerEntries.forEach(([key, value]) => {
        const row = document.createElement('tr');
        row.innerHTML = `
            <td>${escapeHtml(key)}</td>
            <td>${escapeHtml(value)}</td>
        `;
        tbody.appendChild(row);
    });
    
    console.log('Headers table updated with', headerEntries.length, 'entries');
}

function highlightJSON(element) {
    let html = element.textContent;
    
    // Highlight keys
    html = html.replace(/"([^"]+)":/g, '<span class="json-key">"$1"</span>:');
    
    // Highlight strings
    html = html.replace(/: "([^"]*)"/g, ': <span class="json-string">"$1"</span>');
    
    // Highlight numbers
    html = html.replace(/: (\d+\.?\d*)/g, ': <span class="json-number">$1</span>');
    
    // Highlight booleans
    html = html.replace(/: (true|false)/g, ': <span class="json-boolean">$1</span>');
    
    // Highlight null
    html = html.replace(/: (null)/g, ': <span class="json-null">$1</span>');
    
    element.innerHTML = html;
}

function escapeHtml(text) {
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
}

// Delete single request
function deleteRequest(requestId) {
    if (!confirm('Delete this request?')) return;
    
    fetch('/delete_request', {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json'
        },
        body: JSON.stringify({ id: requestId })
    })
    .then(response => {
        if (response.ok) {
            const item = document.querySelector(`[data-request-id="${requestId}"]`);
            if (item) {
                item.remove();
                
                // Update counts
                const countSpan = document.querySelector('.sidebar-title span');
                if (countSpan) {
                    const currentCount = parseInt(countSpan.textContent.match(/\d+/)?.[0] || '1');
                    countSpan.textContent = `REQUESTS (${Math.max(0, currentCount - 1)})`;
                }
                const deleteCount = document.getElementById('delete-count');
                if (deleteCount) {
                    deleteCount.textContent = Math.max(0, parseInt(deleteCount.textContent || '1') - 1);
                }
            }
            
            // Clear details if this was the active request
            if (item && item.classList.contains('active')) {
                document.getElementById('body-content').innerHTML = '<code>Select a request to view details</code>';
            }
        }
    })
    .catch(error => {
        console.error('Error deleting request:', error);
    });
}

// Filter functionality
const statusFilter = document.getElementById('status-filter');
const dateFilter = document.getElementById('date-filter');

function applyFilters() {
    const statusValue = statusFilter?.value;
    const dateValue = dateFilter?.value;
    const items = document.querySelectorAll('.request-item');
    
    console.log('Applying filters - Status:', statusValue, 'Date:', dateValue);
    
    items.forEach(item => {
        let showItem = true;
        
        // Status filter
        if (statusValue) {
            const itemStatus = item.getAttribute('data-status');
            console.log('Item status:', itemStatus, 'Filter:', statusValue);
            if (itemStatus !== statusValue) {
                showItem = false;
            }
        }
        
        // Date filter
        if (dateValue && showItem) {
            const timeText = item.querySelector('.request-time')?.textContent;
            const now = new Date();
            
            // Parse the timestamp
            if (timeText && timeText !== 'Just now') {
                // This is a simplified date filter
                // In production, you'd want to parse the actual timestamp properly
                const today = now.toDateString();
                
                switch(dateValue) {
                    case 'today':
                        // Show only today's requests
                        if (!timeText.includes(now.toLocaleDateString('en-US', { month: 'short', day: 'numeric' }))) {
                            showItem = false;
                        }
                        break;
                    case 'yesterday':
                        const yesterday = new Date(now);
                        yesterday.setDate(yesterday.getDate() - 1);
                        if (!timeText.includes(yesterday.toLocaleDateString('en-US', { month: 'short', day: 'numeric' }))) {
                            showItem = false;
                        }
                        break;
                    case 'week':
                    case 'month':
                        // For week and month, show all for now
                        // In production, you'd parse and compare actual dates
                        break;
                }
            }
        }
        
        item.style.display = showItem ? '' : 'none';
    });
}

if (statusFilter) {
    statusFilter.addEventListener('sl-change', (e) => {
        console.log('Status filter changed:', e.target.value);
        applyFilters();
    });
    
    statusFilter.addEventListener('sl-clear', () => {
        console.log('Status filter cleared');
        applyFilters();
    });
}

if (dateFilter) {
    dateFilter.addEventListener('sl-change', (e) => {
        console.log('Date filter changed:', e.target.value);
        applyFilters();
    });
    
    dateFilter.addEventListener('sl-clear', () => {
        console.log('Date filter cleared');
        applyFilters();
    });
}

// Delete all functionality
document.addEventListener('DOMContentLoaded', function() {
    const deleteAllBtn = document.querySelector('.delete-all-btn');
    const deleteAllDialog = document.querySelector('.delete-all-dialog');
    const cancelBtn = document.querySelector('.dialog-cancel-btn');
    const confirmBtn = document.querySelector('.dialog-confirm-btn');
    
    if (deleteAllBtn) {
        deleteAllBtn.addEventListener('click', () => {
            deleteAllDialog.show();
        });
    }
    
    if (cancelBtn) {
        cancelBtn.addEventListener('click', () => {
            deleteAllDialog.hide();
        });
    }
    
    if (confirmBtn) {
        confirmBtn.addEventListener('click', () => {
            const path = window.location.pathname;
            const pathParts = path.split('/');
            const webhookId = pathParts[pathParts.length - 1];
            
            fetch('/webhooks/delete_all', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json'
                },
                body: JSON.stringify({ webhook_id: webhookId })
            })
            .then(response => response.json())
            .then(data => {
                if (data.message) {
                    location.reload();
                }
            })
            .catch(error => {
                console.error('Error deleting all requests:', error);
            })
            .finally(() => {
                deleteAllDialog.hide();
            });
        });
    }
    
    // Copy cURL button - now copies selected request's data
    const copyCurlBtn = document.getElementById('copy-curl-btn');
    if (copyCurlBtn) {
        copyCurlBtn.addEventListener('click', () => {
            let url = window.location.origin + '/' + document.querySelector('.endpoint-url').textContent.replace('/', '');
            
            if (!currentRequestData) {
                // No request selected - generate sample curl
                const curl = `curl -X POST "${url}" -H "Content-Type: application/json" -d '{"test": "data"}'`;
                navigator.clipboard.writeText(curl).then(() => {
                    copyCurlBtn.innerHTML = '<sl-icon slot="prefix" name="check"></sl-icon>Copied!';
                    setTimeout(() => {
                        copyCurlBtn.innerHTML = '<sl-icon slot="prefix" name="terminal"></sl-icon>Copy cURL';
                    }, 2000);
                });
                return;
            }
            
            // Add query params to URL
            if (currentRequestData.query_params && Object.keys(currentRequestData.query_params).length > 0) {
                const params = new URLSearchParams(currentRequestData.query_params).toString();
                url += '?' + params;
            }
            
            // Build curl with actual headers and body
            let curl = `curl -X POST "${url}"`;
            
            // Add headers
            if (currentRequestData.headers) {
                Object.entries(currentRequestData.headers).forEach(([key, value]) => {
                    // Skip some internal headers
                    if (!['host', 'content-length', 'accept-encoding'].includes(key.toLowerCase())) {
                        curl += ` \\\n  -H "${key}: ${value}"`;
                    }
                });
            }
            
            // Add body
            if (currentRequestData.body) {
                const escapedBody = currentRequestData.body.replace(/'/g, "'\\''");
                curl += ` \\\n  -d '${escapedBody}'`;
            }
            
            navigator.clipboard.writeText(curl).then(() => {
                copyCurlBtn.innerHTML = '<sl-icon slot="prefix" name="check"></sl-icon>Copied!';
                setTimeout(() => {
                    copyCurlBtn.innerHTML = '<sl-icon slot="prefix" name="terminal"></sl-icon>Copy cURL';
                }, 2000);
            });
        });
    }
    
    // Format buttons
    const formatJsonBtn = document.getElementById('format-json');
    const formatRawBtn = document.getElementById('format-raw');
    
    if (formatJsonBtn && formatRawBtn) {
        formatJsonBtn.addEventListener('click', () => {
            if (currentRequestData) {
                const bodyContent = document.getElementById('body-content');
                const bodyContentText = document.getElementById('body-content-text');
                const codeElement = bodyContent.querySelector('code') || bodyContent;
                
                try {
                    const parsed = JSON.parse(currentRequestData.body);
                    const formatted = JSON.stringify(parsed, null, 2);
                    codeElement.textContent = formatted;
                    if (bodyContentText) {
                        bodyContentText.textContent = formatted;
                    }
                    highlightJSON(codeElement);
                } catch (e) {
                    console.error('Failed to format JSON:', e);
                }
            }
        });
        
        formatRawBtn.addEventListener('click', () => {
            if (currentRequestData) {
                const bodyContent = document.getElementById('body-content');
                const bodyContentText = document.getElementById('body-content-text');
                const codeElement = bodyContent.querySelector('code') || bodyContent;
                codeElement.textContent = currentRequestData.body;
                if (bodyContentText) {
                    bodyContentText.textContent = currentRequestData.body;
                }
            }
        });
    }
});
