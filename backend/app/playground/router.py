"""Playground UI for interacting with the Cofounder API."""
import os

from fastapi import APIRouter, HTTPException, status
from fastapi.responses import HTMLResponse

router = APIRouter(tags=["playground"])

# Environment variable to enable/disable Playground UI
PLAYGROUND_UI_ENABLED = os.getenv("PLAYGROUND_UI_ENABLED", "0") == "1"
DEV_CONSOLE_ENABLED = os.getenv("DEV_CONSOLE_ENABLED", "0") == "1"
DEV_CONSOLE_KEY = os.getenv("DEV_CONSOLE_KEY", "dev-console-secret")


PLAYGROUND_HTML = """<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <title>Bespin Playground</title>
    <style>
        * { box-sizing: border-box; margin: 0; padding: 0; }
        body {
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
            background: #f5f5f5;
            height: 100vh;
            display: flex;
            flex-direction: column;
        }
        .header {
            background: #1a1a2e;
            color: white;
            padding: 12px 20px;
            display: flex;
            justify-content: space-between;
            align-items: center;
        }
        .header h1 { font-size: 18px; font-weight: 600; }
        .header a { color: #88c8ff; text-decoration: none; font-size: 13px; }
        .header a:hover { text-decoration: underline; }
        .main { display: flex; flex: 1; overflow: hidden; }
        .sidebar {
            width: 280px;
            background: white;
            border-right: 1px solid #ddd;
            display: flex;
            flex-direction: column;
            overflow: hidden;
        }
        .sidebar-section { padding: 15px; border-bottom: 1px solid #eee; }
        .sidebar-section h3 { font-size: 12px; color: #666; margin-bottom: 10px; text-transform: uppercase; }
        .sidebar-section input, .sidebar-section select {
            width: 100%;
            padding: 8px;
            margin-bottom: 8px;
            border: 1px solid #ddd;
            border-radius: 4px;
            font-size: 13px;
        }
        .sidebar-section button {
            width: 100%;
            padding: 8px;
            background: #0066cc;
            color: white;
            border: none;
            border-radius: 4px;
            cursor: pointer;
            font-size: 13px;
        }
        .sidebar-section button:hover { background: #0052a3; }
        .conversations-list {
            flex: 1;
            overflow-y: auto;
            padding: 10px;
        }
        .conv-item {
            padding: 10px;
            border-radius: 4px;
            cursor: pointer;
            margin-bottom: 5px;
            font-size: 13px;
            white-space: nowrap;
            overflow: hidden;
            text-overflow: ellipsis;
        }
        .conv-item:hover { background: #f0f0f0; }
        .conv-item.active { background: #e3f2fd; }
        .chat-area { flex: 1; display: flex; flex-direction: column; }
        .messages {
            flex: 1;
            overflow-y: auto;
            padding: 20px;
            background: #fafafa;
        }
        .message {
            margin-bottom: 15px;
            max-width: 80%;
        }
        .message.user { margin-left: auto; }
        .message-content {
            padding: 12px 16px;
            border-radius: 12px;
            font-size: 14px;
            line-height: 1.5;
        }
        .message.user .message-content {
            background: #0066cc;
            color: white;
            border-bottom-right-radius: 4px;
        }
        .message.assistant .message-content {
            background: white;
            border: 1px solid #ddd;
            border-bottom-left-radius: 4px;
        }
        .message-cards { margin-top: 10px; }
        .card {
            background: #f8f9fa;
            border: 1px solid #e9ecef;
            border-radius: 8px;
            padding: 12px;
            margin-top: 8px;
            font-size: 12px;
        }
        .card-type {
            font-weight: 600;
            color: #0066cc;
            margin-bottom: 8px;
            text-transform: uppercase;
            font-size: 11px;
        }
        .card pre {
            background: #f0f0f0;
            padding: 8px;
            border-radius: 4px;
            overflow-x: auto;
            font-size: 11px;
            white-space: pre-wrap;
        }
        .input-area {
            padding: 15px;
            background: white;
            border-top: 1px solid #ddd;
        }
        .quick-buttons { margin-bottom: 10px; display: flex; gap: 8px; flex-wrap: wrap; }
        .quick-btn {
            padding: 6px 12px;
            background: #f0f0f0;
            border: 1px solid #ddd;
            border-radius: 20px;
            cursor: pointer;
            font-size: 12px;
        }
        .quick-btn:hover { background: #e0e0e0; }
        .input-row { display: flex; gap: 10px; }
        .input-row input {
            flex: 1;
            padding: 12px;
            border: 1px solid #ddd;
            border-radius: 8px;
            font-size: 14px;
        }
        .input-row button {
            padding: 12px 24px;
            background: #0066cc;
            color: white;
            border: none;
            border-radius: 8px;
            cursor: pointer;
            font-size: 14px;
            font-weight: 500;
        }
        .input-row button:hover { background: #0052a3; }
        .input-row button:disabled { background: #ccc; cursor: not-allowed; }
        .status { font-size: 11px; color: #666; margin-top: 5px; }
        .status.error { color: #cc0000; }
        .status.success { color: #00aa00; }
        .empty-state {
            display: flex;
            align-items: center;
            justify-content: center;
            height: 100%;
            color: #999;
            font-size: 14px;
        }
    </style>
</head>
<body>
    <div class="header">
        <h1>Bespin Playground</h1>
        <div>
            <a href="#" id="console-link" style="display: none;">Dev Console</a>
        </div>
    </div>
    <div class="main">
        <div class="sidebar">
            <div class="sidebar-section">
                <h3>Configuration</h3>
                <input type="text" id="tenant-id" placeholder="Tenant ID">
                <input type="text" id="api-key" placeholder="API Key">
                <input type="text" id="user-id" placeholder="User ID">
                <button onclick="saveConfig()">Save & Connect</button>
                <div class="status" id="config-status"></div>
            </div>
            <div class="sidebar-section">
                <h3>Usage (Today)</h3>
                <div id="usage-panel" style="font-size: 12px; line-height: 1.8;">
                    <div class="empty-state" style="font-size: 11px; padding: 10px 0;">Configure credentials above</div>
                </div>
                <button onclick="loadUsage()" style="margin-top: 8px;">Refresh Usage</button>
            </div>
            <div class="sidebar-section">
                <h3>Billing / Credits</h3>
                <div id="billing-panel" style="font-size: 12px; line-height: 1.6;">
                    <div class="empty-state" style="font-size: 11px; padding: 10px 0;">Configure credentials above</div>
                </div>
                <button onclick="loadBillingUsage()" style="margin-top: 8px;">Refresh Billing</button>
            </div>
            <div class="sidebar-section">
                <h3>Conversations</h3>
                <button onclick="loadConversations()">Refresh</button>
            </div>
            <div class="conversations-list" id="conversations-list">
                <div class="empty-state">Configure credentials above</div>
            </div>
        </div>
        <div class="chat-area">
            <div class="messages" id="messages">
                <div class="empty-state">Select or start a conversation</div>
            </div>
            <div class="input-area">
                <div class="quick-buttons">
                    <button class="quick-btn" onclick="sendQuickMessage('today\\'s brief')">Today's Brief</button>
                    <button class="quick-btn" onclick="sendQuickMessage('kpis')">KPIs</button>
                    <button class="quick-btn" onclick="sendQuickMessage('outbox')">Outbox</button>
                    <button class="quick-btn" onclick="sendQuickMessage('help')">Help</button>
                </div>
                <div class="input-row">
                    <input type="text" id="message-input" placeholder="Type a message..." onkeypress="handleKeyPress(event)">
                    <button id="send-btn" onclick="sendMessage()">Send</button>
                </div>
            </div>
        </div>
    </div>

    <script>
        let currentConversationId = null;

        // Load saved config on page load
        document.addEventListener('DOMContentLoaded', () => {
            const tenantId = localStorage.getItem('playground_tenant_id');
            const apiKey = localStorage.getItem('playground_api_key');
            const userId = localStorage.getItem('playground_user_id');

            if (tenantId) document.getElementById('tenant-id').value = tenantId;
            if (apiKey) document.getElementById('api-key').value = apiKey;
            if (userId) document.getElementById('user-id').value = userId;

            // Show console link if enabled
            const consoleLink = document.getElementById('console-link');
            if (consoleLink && window.DEV_CONSOLE_ENABLED) {
                consoleLink.style.display = 'inline';
                consoleLink.href = '/console?key=' + window.DEV_CONSOLE_KEY;
            }

            if (tenantId && apiKey && userId) {
                loadConversations();
                loadUsage();
                loadBillingUsage();
            }
        });

        // Inject server-side config
        window.DEV_CONSOLE_ENABLED = {DEV_CONSOLE_ENABLED};
        window.DEV_CONSOLE_KEY = '{DEV_CONSOLE_KEY}';

        function getHeaders() {
            return {
                'Content-Type': 'application/json',
                'X-Tenant-ID': document.getElementById('tenant-id').value,
                'X-API-Key': document.getElementById('api-key').value,
                'X-User-ID': document.getElementById('user-id').value
            };
        }

        function setStatus(elementId, message, type) {
            const el = document.getElementById(elementId);
            el.textContent = message;
            el.className = 'status ' + (type || '');
        }

        function saveConfig() {
            const tenantId = document.getElementById('tenant-id').value;
            const apiKey = document.getElementById('api-key').value;
            const userId = document.getElementById('user-id').value;

            if (!tenantId || !apiKey || !userId) {
                setStatus('config-status', 'All fields required', 'error');
                return;
            }

            localStorage.setItem('playground_tenant_id', tenantId);
            localStorage.setItem('playground_api_key', apiKey);
            localStorage.setItem('playground_user_id', userId);

            setStatus('config-status', 'Saved! Loading...', 'success');
            loadConversations();
            loadUsage();
            loadBillingUsage();
        }

        async function loadConversations() {
            const listEl = document.getElementById('conversations-list');
            try {
                const response = await fetch('/v1/conversations', { headers: getHeaders() });
                if (!response.ok) {
                    const err = await response.json();
                    setStatus('config-status', err.detail || 'Error loading', 'error');
                    return;
                }

                const data = await response.json();
                setStatus('config-status', 'Connected', 'success');

                if (data.items.length === 0) {
                    listEl.innerHTML = '<div class="empty-state">No conversations yet</div>';
                    return;
                }

                listEl.innerHTML = data.items.map(conv => `
                    <div class="conv-item ${conv.conversation_id === currentConversationId ? 'active' : ''}"
                         onclick="selectConversation('${conv.conversation_id}')">
                        ${conv.title || 'Untitled'}
                    </div>
                `).join('');
            } catch (e) {
                setStatus('config-status', 'Network error', 'error');
            }
        }

        async function loadUsage() {
            const usagePanel = document.getElementById('usage-panel');
            try {
                const response = await fetch('/v1/usage/daily', { headers: getHeaders() });
                if (!response.ok) {
                    usagePanel.innerHTML = '<div style="color: #cc0000; font-size: 11px;">Error loading usage</div>';
                    return;
                }

                const data = await response.json();
                const limits = data.limits;

                // Map activity types to human-readable labels
                const labels = {
                    'assistant_query': 'Chat',
                    'tool_invocation': 'Tools',
                    'daily_brief_generated': 'Briefs',
                    'notification_enqueued': 'Notifs'
                };

                const limitFields = {
                    'assistant_query': 'assistant_query_daily_limit',
                    'tool_invocation': 'tool_invocation_daily_limit',
                    'daily_brief_generated': 'daily_brief_generated_daily_limit',
                    'notification_enqueued': 'notification_enqueued_daily_limit'
                };

                let html = '';
                for (const item of data.usage) {
                    const label = labels[item.activity_type] || item.activity_type;
                    const limit = limits[limitFields[item.activity_type]] || 0;
                    const pct = limit > 0 ? (item.units / limit) * 100 : 0;

                    let color = '#333';
                    let warning = '';
                    if (pct >= 100) {
                        color = '#cc0000';
                        warning = ' (LIMIT)';
                    } else if (pct >= 80) {
                        color = '#cc6600';
                        warning = ' (!)';
                    }

                    html += `<div style="color: ${color}">${label}: ${item.units}/${limit}${warning}</div>`;
                }

                usagePanel.innerHTML = html || '<div>No usage data</div>';
            } catch (e) {
                usagePanel.innerHTML = '<div style="color: #cc0000; font-size: 11px;">Network error</div>';
            }
        }

        async function loadBillingUsage() {
            const billingPanel = document.getElementById('billing-panel');
            try {
                const response = await fetch('/v1/billing/usage', { headers: getHeaders() });
                if (!response.ok) {
                    billingPanel.innerHTML = '<div style="color: #cc0000; font-size: 11px;">Error loading billing</div>';
                    return;
                }

                const data = await response.json();
                const credits = data.credits;

                // Calculate usage percentage
                const pct = credits.included > 0 ? (credits.used / credits.included) * 100 : 0;
                let creditsColor = '#333';
                let creditsWarning = '';
                if (pct >= 100) {
                    creditsColor = '#cc0000';
                    creditsWarning = ' (OVER)';
                } else if (pct >= 80) {
                    creditsColor = '#cc6600';
                    creditsWarning = ' (!)';
                }

                let html = `
                    <div style="margin-bottom: 8px;">
                        <strong>Plan:</strong> ${data.plan.name}
                    </div>
                    <div style="color: ${creditsColor}; font-weight: 600;">
                        Credits: ${credits.used.toFixed(1)} / ${credits.included}${creditsWarning}
                    </div>
                    <div style="color: #666; font-size: 11px;">
                        Remaining: ${credits.remaining.toFixed(1)}
                    </div>
                `;

                if (credits.overage_credits > 0) {
                    html += `<div style="color: #cc0000; font-size: 11px;">
                        Overage: ${credits.overage_credits.toFixed(1)} (~$${credits.estimated_overage_cost.toFixed(2)})
                    </div>`;
                }

                html += `<div style="color: #666; font-size: 11px; margin-top: 4px;">
                    Est. List Cost: $${credits.estimated_list_cost.toFixed(4)}
                </div>`;

                // Breakdown table
                if (data.breakdown && data.breakdown.length > 0) {
                    html += `<div style="margin-top: 10px; font-size: 11px;">
                        <strong>Breakdown:</strong>
                        <table style="width: 100%; margin-top: 4px; border-collapse: collapse; font-size: 10px;">
                            <tr style="background: #f0f0f0;">
                                <th style="text-align: left; padding: 2px 4px;">Event</th>
                                <th style="text-align: right; padding: 2px 4px;">Units</th>
                                <th style="text-align: right; padding: 2px 4px;">Credits</th>
                            </tr>
                    `;
                    for (const item of data.breakdown) {
                        html += `<tr>
                            <td style="padding: 2px 4px;">${item.event_key.replace('_', ' ')}</td>
                            <td style="text-align: right; padding: 2px 4px;">${item.raw_units}</td>
                            <td style="text-align: right; padding: 2px 4px;">${item.credits.toFixed(1)}</td>
                        </tr>`;
                    }
                    html += '</table></div>';
                }

                billingPanel.innerHTML = html;
            } catch (e) {
                billingPanel.innerHTML = '<div style="color: #cc0000; font-size: 11px;">Network error</div>';
            }
        }

        async function selectConversation(conversationId) {
            currentConversationId = conversationId;

            // Update active state
            document.querySelectorAll('.conv-item').forEach(el => {
                el.classList.toggle('active', el.onclick.toString().includes(conversationId));
            });

            // Load messages
            try {
                const response = await fetch(`/v1/conversations/${conversationId}`, { headers: getHeaders() });
                if (!response.ok) return;

                const data = await response.json();
                renderMessages(data.messages);
            } catch (e) {
                console.error('Error loading conversation:', e);
            }
        }

        function renderMessages(messages) {
            const container = document.getElementById('messages');

            if (messages.length === 0) {
                container.innerHTML = '<div class="empty-state">No messages yet</div>';
                return;
            }

            container.innerHTML = messages.map(msg => `
                <div class="message ${msg.role}">
                    <div class="message-content">
                        ${escapeHtml(msg.content).replace(/\\n/g, '<br>')}
                    </div>
                    ${msg.cards && msg.cards.length > 0 ? `
                        <div class="message-cards">
                            ${msg.cards.map(card => `
                                <div class="card">
                                    <div class="card-type">${card.type}</div>
                                    <pre>${JSON.stringify(card, null, 2)}</pre>
                                </div>
                            `).join('')}
                        </div>
                    ` : ''}
                </div>
            `).join('');

            container.scrollTop = container.scrollHeight;
        }

        function escapeHtml(text) {
            const div = document.createElement('div');
            div.textContent = text;
            return div.innerHTML;
        }

        function handleKeyPress(event) {
            if (event.key === 'Enter') {
                sendMessage();
            }
        }

        function sendQuickMessage(msg) {
            document.getElementById('message-input').value = msg;
            sendMessage();
        }

        async function sendMessage() {
            const input = document.getElementById('message-input');
            const message = input.value.trim();
            if (!message) return;

            const sendBtn = document.getElementById('send-btn');
            sendBtn.disabled = true;
            input.disabled = true;

            try {
                const body = { message };
                if (currentConversationId) {
                    body.conversation_id = currentConversationId;
                }

                const response = await fetch('/v1/cofounder/chat', {
                    method: 'POST',
                    headers: getHeaders(),
                    body: JSON.stringify(body)
                });

                if (!response.ok) {
                    const err = await response.json();
                    alert('Error: ' + (err.detail || 'Unknown error'));
                    return;
                }

                const data = await response.json();

                // If this was a new conversation, update the current ID and reload list
                if (!currentConversationId || currentConversationId !== data.conversation_id) {
                    currentConversationId = data.conversation_id;
                    loadConversations();
                }

                // Reload conversation to show all messages
                await selectConversation(currentConversationId);

                // Refresh usage panels
                loadUsage();
                loadBillingUsage();

                input.value = '';
            } catch (e) {
                console.error('Error sending message:', e);
                alert('Network error');
            } finally {
                sendBtn.disabled = false;
                input.disabled = false;
                input.focus();
            }
        }
    </script>
</body>
</html>
"""


@router.get("/ui", response_class=HTMLResponse)
def playground_ui() -> str:
    """Serve the Playground UI.

    Enabled via PLAYGROUND_UI_ENABLED=1 environment variable.
    """
    if not PLAYGROUND_UI_ENABLED:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Playground UI is disabled. Set PLAYGROUND_UI_ENABLED=1 to enable.",
        )

    # Inject server-side config
    html = PLAYGROUND_HTML.replace(
        "{DEV_CONSOLE_ENABLED}",
        "true" if DEV_CONSOLE_ENABLED else "false"
    ).replace(
        "{DEV_CONSOLE_KEY}",
        DEV_CONSOLE_KEY if DEV_CONSOLE_ENABLED else ""
    )

    return html


# Core Business OS UI
CORE_OS_HTML = """<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <title>Bespin - Core Business OS</title>
    <style>
        * { box-sizing: border-box; margin: 0; padding: 0; }
        body {
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
            background: #f5f5f5;
            min-height: 100vh;
        }
        .header {
            background: #1a1a2e;
            color: white;
            padding: 12px 20px;
            display: flex;
            justify-content: space-between;
            align-items: center;
        }
        .header h1 { font-size: 18px; font-weight: 600; }
        .header-links a { color: #88c8ff; text-decoration: none; font-size: 13px; margin-left: 15px; }
        .header-links a:hover { text-decoration: underline; }
        .main { display: flex; min-height: calc(100vh - 50px); }
        .sidebar {
            width: 200px;
            background: white;
            border-right: 1px solid #ddd;
            padding: 15px 0;
        }
        .sidebar a {
            display: block;
            padding: 10px 20px;
            color: #333;
            text-decoration: none;
            font-size: 14px;
        }
        .sidebar a:hover { background: #f0f0f0; }
        .sidebar a.active { background: #e3f2fd; color: #0066cc; font-weight: 500; }
        .sidebar hr { border: none; border-top: 1px solid #eee; margin: 10px 0; }
        .content { flex: 1; padding: 20px; overflow-y: auto; }
        .config-bar {
            background: white;
            padding: 10px 20px;
            border-bottom: 1px solid #ddd;
            display: flex;
            gap: 10px;
            align-items: center;
            font-size: 13px;
        }
        .config-bar input {
            padding: 6px 10px;
            border: 1px solid #ddd;
            border-radius: 4px;
            font-size: 13px;
            width: 200px;
        }
        .config-bar button {
            padding: 6px 14px;
            background: #0066cc;
            color: white;
            border: none;
            border-radius: 4px;
            cursor: pointer;
        }
        .config-bar button:hover { background: #0052a3; }
        .config-status { font-size: 12px; color: #666; }
        .config-status.error { color: #cc0000; }
        .config-status.success { color: #00aa00; }
        .card {
            background: white;
            border-radius: 8px;
            box-shadow: 0 1px 3px rgba(0,0,0,0.1);
            padding: 20px;
            margin-bottom: 20px;
        }
        .card h2 { font-size: 16px; margin-bottom: 15px; color: #333; }
        .btn {
            padding: 8px 16px;
            background: #0066cc;
            color: white;
            border: none;
            border-radius: 4px;
            cursor: pointer;
            font-size: 13px;
        }
        .btn:hover { background: #0052a3; }
        .btn-secondary { background: #666; }
        .btn-secondary:hover { background: #555; }
        .btn-danger { background: #cc0000; }
        .btn-danger:hover { background: #aa0000; }
        .btn-success { background: #00aa00; }
        .btn-success:hover { background: #008800; }
        table { width: 100%; border-collapse: collapse; font-size: 13px; }
        th, td { text-align: left; padding: 10px; border-bottom: 1px solid #eee; }
        th { background: #f8f9fa; font-weight: 600; }
        tr:hover { background: #f8f9fa; }
        .status-badge {
            display: inline-block;
            padding: 2px 8px;
            border-radius: 12px;
            font-size: 11px;
            font-weight: 500;
        }
        .status-proposed { background: #fff3cd; color: #856404; }
        .status-approved { background: #d4edda; color: #155724; }
        .status-rejected { background: #f8d7da; color: #721c24; }
        .status-executed { background: #cce5ff; color: #004085; }
        .status-cancelled { background: #e2e3e5; color: #383d41; }
        .status-todo { background: #e2e3e5; color: #383d41; }
        .status-doing { background: #fff3cd; color: #856404; }
        .status-done { background: #d4edda; color: #155724; }
        .status-active { background: #d4edda; color: #155724; }
        .status-superseded { background: #e2e3e5; color: #383d41; }
        .priority-high { color: #cc0000; font-weight: 500; }
        .priority-medium { color: #cc6600; }
        .priority-low { color: #666; }
        .form-group { margin-bottom: 15px; }
        .form-group label { display: block; margin-bottom: 5px; font-size: 13px; font-weight: 500; }
        .form-group input, .form-group select, .form-group textarea {
            width: 100%;
            padding: 8px;
            border: 1px solid #ddd;
            border-radius: 4px;
            font-size: 13px;
        }
        .form-group textarea { min-height: 80px; resize: vertical; }
        .form-row { display: flex; gap: 15px; }
        .form-row .form-group { flex: 1; }
        .modal {
            display: none;
            position: fixed;
            top: 0; left: 0; right: 0; bottom: 0;
            background: rgba(0,0,0,0.5);
            z-index: 1000;
            justify-content: center;
            align-items: center;
        }
        .modal.active { display: flex; }
        .modal-content {
            background: white;
            border-radius: 8px;
            padding: 20px;
            max-width: 600px;
            width: 90%;
            max-height: 80vh;
            overflow-y: auto;
        }
        .modal-header { display: flex; justify-content: space-between; margin-bottom: 15px; }
        .modal-header h3 { font-size: 16px; }
        .modal-close { cursor: pointer; font-size: 20px; color: #666; }
        .detail-section { margin-bottom: 20px; }
        .detail-section h4 { font-size: 13px; color: #666; margin-bottom: 8px; text-transform: uppercase; }
        .detail-value { font-size: 14px; color: #333; white-space: pre-wrap; }
        .search-box {
            display: flex;
            gap: 10px;
            margin-bottom: 20px;
        }
        .search-box input { flex: 1; padding: 10px; border: 1px solid #ddd; border-radius: 4px; font-size: 14px; }
        .tabs { display: flex; border-bottom: 1px solid #ddd; margin-bottom: 15px; }
        .tab { padding: 10px 20px; cursor: pointer; font-size: 14px; color: #666; border-bottom: 2px solid transparent; }
        .tab:hover { color: #333; }
        .tab.active { color: #0066cc; border-bottom-color: #0066cc; }
        .empty-state { text-align: center; color: #999; padding: 40px; font-size: 14px; }
        .action-buttons { display: flex; gap: 8px; }
        pre { background: #f0f0f0; padding: 10px; border-radius: 4px; overflow-x: auto; font-size: 12px; }
        .diagnostics-panel {
            position: fixed;
            bottom: 0;
            right: 0;
            width: 400px;
            max-height: 300px;
            background: white;
            border: 1px solid #ddd;
            border-radius: 8px 0 0 0;
            box-shadow: 0 -2px 10px rgba(0,0,0,0.1);
            z-index: 100;
            display: flex;
            flex-direction: column;
        }
        .diagnostics-header {
            padding: 8px 12px;
            background: #f8f9fa;
            border-bottom: 1px solid #eee;
            display: flex;
            justify-content: space-between;
            align-items: center;
            font-size: 12px;
            font-weight: 600;
        }
        .diagnostics-toggle {
            cursor: pointer;
            color: #666;
            font-size: 14px;
        }
        .diagnostics-body {
            flex: 1;
            overflow-y: auto;
            padding: 10px;
            font-family: monospace;
            font-size: 11px;
            white-space: pre-wrap;
            word-break: break-all;
        }
        .diagnostics-body.error { color: #cc0000; background: #fff5f5; }
        .diagnostics-body.success { color: #006600; background: #f5fff5; }
        .checkbox-row { display: flex; align-items: center; gap: 8px; margin-bottom: 10px; }
        .checkbox-row input[type="checkbox"] { width: auto; margin: 0; }
    </style>
</head>
<body>
    <div class="header">
        <h1>Core Business OS</h1>
        <div class="header-links">
            <a href="/ui">Chat</a>
            <a href="#" id="console-link" style="display: none;">Console</a>
        </div>
    </div>
    <div class="config-bar">
        <input type="text" id="tenant-id" placeholder="Tenant ID">
        <input type="text" id="api-key" placeholder="API Key">
        <input type="text" id="user-id" placeholder="User ID">
        <button onclick="saveConfig()">Connect</button>
        <span class="config-status" id="config-status"></span>
        <span style="margin-left: auto; font-size: 12px; color: #666;" id="user-role"></span>
    </div>
    <div class="main">
        <div class="sidebar">
            <a href="#" data-section="today" class="active">Today</a>
            <hr>
            <a href="#" data-section="actions">Actions</a>
            <a href="#" data-section="tasks">Tasks</a>
            <a href="#" data-section="decisions">Decisions</a>
            <a href="#" data-section="meetings">Meetings</a>
            <a href="#" data-section="memory">Memory</a>
            <hr>
            <a href="#" data-section="timeline">Timeline</a>
            <a href="#" data-section="billing">Billing</a>
            <a href="#" data-section="search">Search</a>
        </div>
        <div class="content" id="content">
            <div class="empty-state">Configure credentials to connect</div>
        </div>
    </div>

    <!-- Create/Edit Modal -->
    <div class="modal" id="modal">
        <div class="modal-content">
            <div class="modal-header">
                <h3 id="modal-title">Create</h3>
                <span class="modal-close" onclick="closeModal()">&times;</span>
            </div>
            <div id="modal-body"></div>
        </div>
    </div>

    <!-- Diagnostics Panel -->
    <div class="diagnostics-panel" id="diagnostics-panel">
        <div class="diagnostics-header">
            <span>Last API Response</span>
            <span class="diagnostics-toggle" onclick="toggleDiagnostics()">_</span>
        </div>
        <div class="diagnostics-body" id="diagnostics-body">No API calls yet</div>
    </div>

    <script>
        let currentSection = 'today';
        let userRole = 'member';
        let diagnosticsMinimized = false;
        let lastApiResponse = null;
        let actionsCreatedByMeFilter = false;

        window.DEV_CONSOLE_ENABLED = {DEV_CONSOLE_ENABLED};
        window.DEV_CONSOLE_KEY = '{DEV_CONSOLE_KEY}';

        // Diagnostics panel functions
        function toggleDiagnostics() {
            diagnosticsMinimized = !diagnosticsMinimized;
            const panel = document.getElementById('diagnostics-panel');
            const body = document.getElementById('diagnostics-body');
            const toggle = document.querySelector('.diagnostics-toggle');
            if (diagnosticsMinimized) {
                body.style.display = 'none';
                panel.style.maxHeight = '35px';
                toggle.textContent = '+';
            } else {
                body.style.display = 'block';
                panel.style.maxHeight = '300px';
                toggle.textContent = '_';
            }
        }

        function updateDiagnostics(response, data, isError = false) {
            const body = document.getElementById('diagnostics-body');
            const timestamp = new Date().toLocaleTimeString();
            let content = `[${timestamp}] ${response.status} ${response.statusText}\nURL: ${response.url}\n\n`;
            content += JSON.stringify(data, null, 2);
            body.textContent = content;
            body.className = 'diagnostics-body ' + (isError ? 'error' : 'success');
            lastApiResponse = { response, data, isError };
        }

        // Wrapper for fetch that logs to diagnostics
        async function apiFetch(url, options = {}) {
            try {
                const res = await fetch(url, options);
                const data = await res.json();
                updateDiagnostics(res, data, !res.ok);
                return { res, data, ok: res.ok };
            } catch (e) {
                updateDiagnostics({ status: 0, statusText: 'Network Error', url }, { error: e.message }, true);
                throw e;
            }
        }

        document.addEventListener('DOMContentLoaded', () => {
            // Load saved config
            ['tenant-id', 'api-key', 'user-id'].forEach(id => {
                const val = localStorage.getItem('playground_' + id.replace('-', '_'));
                if (val) document.getElementById(id).value = val;
            });

            // Console link
            if (window.DEV_CONSOLE_ENABLED) {
                const link = document.getElementById('console-link');
                link.style.display = 'inline';
                link.href = '/console?key=' + window.DEV_CONSOLE_KEY;
            }

            // Navigation
            document.querySelectorAll('.sidebar a').forEach(a => {
                a.addEventListener('click', e => {
                    e.preventDefault();
                    document.querySelectorAll('.sidebar a').forEach(el => el.classList.remove('active'));
                    a.classList.add('active');
                    currentSection = a.dataset.section;
                    loadSection(currentSection);
                });
            });

            if (document.getElementById('tenant-id').value) {
                saveConfig();
            }
        });

        function getHeaders() {
            return {
                'Content-Type': 'application/json',
                'X-Tenant-ID': document.getElementById('tenant-id').value,
                'X-API-Key': document.getElementById('api-key').value,
                'X-User-ID': document.getElementById('user-id').value
            };
        }

        function setStatus(msg, type) {
            const el = document.getElementById('config-status');
            el.textContent = msg;
            el.className = 'config-status ' + (type || '');
        }

        async function saveConfig() {
            ['tenant-id', 'api-key', 'user-id'].forEach(id => {
                localStorage.setItem('playground_' + id.replace('-', '_'), document.getElementById(id).value);
            });

            // Test connection and get user role via /v1/me endpoint
            try {
                const meRes = await fetch('/v1/me', { headers: getHeaders() });
                if (!meRes.ok) throw new Error('Auth failed');
                const meData = await meRes.json();
                setStatus('Connected', 'success');

                // Set user role from /v1/me response
                userRole = meData.role;
                document.getElementById('user-role').textContent = 'Role: ' + userRole + ' | ' + meData.email;

                loadSection(currentSection);
            } catch (e) {
                setStatus('Connection failed: ' + e.message, 'error');
            }
        }

        function loadSection(section) {
            const content = document.getElementById('content');
            switch(section) {
                case 'today': loadToday(); break;
                case 'actions': loadActions(); break;
                case 'tasks': loadTasks(); break;
                case 'decisions': loadDecisions(); break;
                case 'meetings': loadMeetings(); break;
                case 'memory': loadMemory(); break;
                case 'timeline': loadTimeline(); break;
                case 'billing': loadBilling(); break;
                case 'search': loadSearch(); break;
            }
        }

        async function loadToday() {
            const content = document.getElementById('content');
            content.innerHTML = '<div class="empty-state">Loading...</div>';

            try {
                const [actionsRes, tasksRes] = await Promise.all([
                    fetch('/v1/actions?status=proposed&limit=5', { headers: getHeaders() }),
                    fetch('/v1/tasks?status=todo&limit=5', { headers: getHeaders() })
                ]);

                const actions = actionsRes.ok ? (await actionsRes.json()).items : [];
                const tasks = tasksRes.ok ? (await tasksRes.json()).items : [];

                content.innerHTML = `
                    <div class="card">
                        <h2>Open Actions (${actions.length})</h2>
                        ${actions.length ? `<table>
                            <tr><th>Title</th><th>Type</th><th>Status</th></tr>
                            ${actions.map(a => `<tr>
                                <td><a href="#" onclick="viewAction('${a.action_id}')">${escapeHtml(a.title)}</a></td>
                                <td>${a.action_type}</td>
                                <td><span class="status-badge status-${a.status}">${a.status}</span></td>
                            </tr>`).join('')}
                        </table>` : '<p style="color:#999">No open actions</p>'}
                    </div>
                    <div class="card">
                        <h2>Tasks Due Soon (${tasks.length})</h2>
                        ${tasks.length ? `<table>
                            <tr><th>Title</th><th>Priority</th><th>Due</th></tr>
                            ${tasks.map(t => `<tr>
                                <td><a href="#" onclick="viewTask('${t.task_id}')">${escapeHtml(t.title)}</a></td>
                                <td class="priority-${t.priority}">${t.priority}</td>
                                <td>${t.due_date || '-'}</td>
                            </tr>`).join('')}
                        </table>` : '<p style="color:#999">No pending tasks</p>'}
                    </div>
                `;
            } catch (e) {
                content.innerHTML = '<div class="empty-state">Error loading data</div>';
            }
        }

        let actionsStatusFilter = 'all';
        let tasksStatusFilter = 'todo';
        let tasksAssignedToMeFilter = false;
        let tasksCreatedByMeFilter = false;

        async function loadActions() {
            const content = document.getElementById('content');
            content.innerHTML = '<div class="empty-state">Loading...</div>';

            try {
                let url = '/v1/actions?status=' + actionsStatusFilter + '&limit=50';
                if (actionsCreatedByMeFilter) {
                    url += '&created_by_user_id=' + encodeURIComponent(document.getElementById('user-id').value);
                }
                const { res, data, ok } = await apiFetch(url, { headers: getHeaders() });
                if (!ok) throw new Error(data.detail || 'Failed to load actions');

                const isAdmin = userRole === 'admin';
                const currentUserId = document.getElementById('user-id').value;

                content.innerHTML = `
                    <div class="card">
                        <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:15px;">
                            <h2>Actions (${data.total})</h2>
                            <div style="display:flex;gap:10px;align-items:center;">
                                <label style="font-size:12px;display:flex;align-items:center;gap:5px;">
                                    <input type="checkbox" id="created-by-me-filter" onchange="toggleCreatedByMeFilter()" ${actionsCreatedByMeFilter?'checked':''}>
                                    Created by me
                                </label>
                                <select id="action-status-filter" onchange="changeActionsFilter()" style="padding:6px;border:1px solid #ddd;border-radius:4px;">
                                    <option value="all" ${actionsStatusFilter==='all'?'selected':''}>All</option>
                                    <option value="proposed" ${actionsStatusFilter==='proposed'?'selected':''}>Proposed</option>
                                    <option value="approved" ${actionsStatusFilter==='approved'?'selected':''}>Approved</option>
                                    <option value="rejected" ${actionsStatusFilter==='rejected'?'selected':''}>Rejected</option>
                                    <option value="executed" ${actionsStatusFilter==='executed'?'selected':''}>Executed</option>
                                    <option value="cancelled" ${actionsStatusFilter==='cancelled'?'selected':''}>Cancelled</option>
                                </select>
                                <button class="btn" onclick="showCreateAction()">+ New Action</button>
                            </div>
                        </div>
                        ${data.items.length ? `<table>
                            <tr><th>Created</th><th>Status</th><th>Title</th><th>Type</th><th>Creator</th><th>Assigned</th><th>Actions</th></tr>
                            ${data.items.map(a => `<tr>
                                <td>${a.created_at.split('T')[0]}</td>
                                <td><span class="status-badge status-${a.status}">${a.status}</span></td>
                                <td><a href="#" onclick="viewActionDetail('${a.action_id}')">${escapeHtml(a.title)}</a></td>
                                <td>${a.action_type}</td>
                                <td>${a.created_by_user_id.substring(0,8)}...</td>
                                <td>${a.assigned_to_user_id ? a.assigned_to_user_id.substring(0,8)+'...' : '-'}</td>
                                <td class="action-buttons">
                                    ${a.status === 'proposed' && isAdmin ? `
                                        <button class="btn btn-success" onclick="showApproveDialog('${a.action_id}')" style="padding:4px 8px;font-size:11px;">Approve</button>
                                        <button class="btn btn-danger" onclick="showRejectDialog('${a.action_id}')" style="padding:4px 8px;font-size:11px;">Reject</button>
                                    ` : ''}
                                    ${a.status === 'proposed' && (isAdmin || a.created_by_user_id === currentUserId) ? `
                                        <button class="btn btn-secondary" onclick="cancelAction('${a.action_id}')" style="padding:4px 8px;font-size:11px;">Cancel</button>
                                    ` : ''}
                                    ${a.status === 'approved' && isAdmin ? `
                                        <button class="btn" onclick="showExecuteDialog('${a.action_id}')" style="padding:4px 8px;font-size:11px;">Execute</button>
                                    ` : ''}
                                </td>
                            </tr>`).join('')}
                        </table>` : '<div class="empty-state">No actions found</div>'}
                    </div>
                `;
            } catch (e) {
                content.innerHTML = '<div class="empty-state">Error loading actions: ' + escapeHtml(e.message) + '</div>';
            }
        }

        function changeActionsFilter() {
            actionsStatusFilter = document.getElementById('action-status-filter').value;
            loadActions();
        }

        function toggleCreatedByMeFilter() {
            actionsCreatedByMeFilter = document.getElementById('created-by-me-filter').checked;
            loadActions();
        }

        async function loadTasks() {
            const content = document.getElementById('content');
            content.innerHTML = '<div class="empty-state">Loading...</div>';

            try {
                let url = '/v1/tasks?status=' + tasksStatusFilter + '&limit=50';
                if (tasksAssignedToMeFilter) {
                    url += '&assigned_to_user_id=' + encodeURIComponent(document.getElementById('user-id').value);
                }
                if (tasksCreatedByMeFilter) {
                    url += '&created_by_user_id=' + encodeURIComponent(document.getElementById('user-id').value);
                }
                const { res, data, ok } = await apiFetch(url, { headers: getHeaders() });
                if (!ok) throw new Error(data.detail || 'Failed to load tasks');

                const currentUserId = document.getElementById('user-id').value;
                const isAdmin = userRole === 'admin';

                content.innerHTML = `
                    <div class="card">
                        <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:15px;">
                            <h2>Tasks (${data.total})</h2>
                            <div style="display:flex;gap:10px;align-items:center;">
                                <label style="font-size:12px;display:flex;align-items:center;gap:5px;">
                                    <input type="checkbox" id="tasks-assigned-to-me" onchange="toggleTasksAssignedToMe()" ${tasksAssignedToMeFilter?'checked':''}>
                                    Assigned to me
                                </label>
                                <label style="font-size:12px;display:flex;align-items:center;gap:5px;">
                                    <input type="checkbox" id="tasks-created-by-me" onchange="toggleTasksCreatedByMe()" ${tasksCreatedByMeFilter?'checked':''}>
                                    Created by me
                                </label>
                                <select id="tasks-status-filter" onchange="changeTasksFilter()" style="padding:6px;border:1px solid #ddd;border-radius:4px;">
                                    <option value="all" ${tasksStatusFilter==='all'?'selected':''}>All</option>
                                    <option value="todo" ${tasksStatusFilter==='todo'?'selected':''}>Todo</option>
                                    <option value="doing" ${tasksStatusFilter==='doing'?'selected':''}>Doing</option>
                                    <option value="done" ${tasksStatusFilter==='done'?'selected':''}>Done</option>
                                </select>
                                <button class="btn" onclick="showCreateTask()">+ New Task</button>
                            </div>
                        </div>
                        ${data.items.length ? `<table>
                            <tr><th>Due</th><th>Status</th><th>Priority</th><th>Title</th><th>Assigned</th><th>ID</th><th>Updated</th><th>Actions</th></tr>
                            ${data.items.map(t => `<tr>
                                <td>${t.due_date || '-'}</td>
                                <td><span class="status-badge status-${t.status}">${t.status}</span></td>
                                <td class="priority-${t.priority}">${t.priority}</td>
                                <td><a href="#" onclick="viewTaskDetail('${t.task_id}')">${escapeHtml(t.title)}</a></td>
                                <td>${t.assigned_to_user_id ? t.assigned_to_user_id.substring(0,8)+'...' : '-'}</td>
                                <td>${t.task_id.substring(0,8)}...</td>
                                <td>${t.updated_at.split('T')[0]}</td>
                                <td class="action-buttons">
                                    ${t.status !== 'done' ? `<button class="btn btn-success" onclick="completeTask('${t.task_id}')" style="padding:4px 8px;font-size:11px;">Complete</button>` : ''}
                                </td>
                            </tr>`).join('')}
                        </table>` : '<div class="empty-state">No tasks found</div>'}
                    </div>
                `;
            } catch (e) {
                content.innerHTML = '<div class="empty-state">Error loading tasks: ' + escapeHtml(e.message) + '</div>';
            }
        }

        function changeTasksFilter() {
            tasksStatusFilter = document.getElementById('tasks-status-filter').value;
            loadTasks();
        }

        function toggleTasksAssignedToMe() {
            tasksAssignedToMeFilter = document.getElementById('tasks-assigned-to-me').checked;
            loadTasks();
        }

        function toggleTasksCreatedByMe() {
            tasksCreatedByMeFilter = document.getElementById('tasks-created-by-me').checked;
            loadTasks();
        }

        async function loadDecisions() {
            const content = document.getElementById('content');
            content.innerHTML = '<div class="empty-state">Loading...</div>';

            try {
                const res = await fetch('/v1/decisions?limit=50', { headers: getHeaders() });
                if (!res.ok) throw new Error();
                const data = await res.json();

                content.innerHTML = `
                    <div class="card">
                        <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:15px;">
                            <h2>Decisions (${data.total})</h2>
                            <button class="btn" onclick="showCreateDecision()">+ New Decision</button>
                        </div>
                        ${data.items.length ? `<table>
                            <tr><th>Title</th><th>Date</th><th>Status</th></tr>
                            ${data.items.map(d => `<tr>
                                <td><a href="#" onclick="viewDecision('${d.decision_id}')">${escapeHtml(d.title)}</a></td>
                                <td>${d.decision_date}</td>
                                <td><span class="status-badge status-${d.status}">${d.status}</span></td>
                            </tr>`).join('')}
                        </table>` : '<div class="empty-state">No decisions yet</div>'}
                    </div>
                `;
            } catch (e) {
                content.innerHTML = '<div class="empty-state">Error loading decisions</div>';
            }
        }

        async function loadMeetings() {
            const content = document.getElementById('content');
            content.innerHTML = '<div class="empty-state">Loading...</div>';

            try {
                const res = await fetch('/v1/meetings?limit=50', { headers: getHeaders() });
                if (!res.ok) throw new Error();
                const data = await res.json();

                content.innerHTML = `
                    <div class="card">
                        <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:15px;">
                            <h2>Meeting Notes (${data.total})</h2>
                            <button class="btn" onclick="showCreateMeeting()">+ New Meeting Note</button>
                        </div>
                        ${data.items.length ? `<table>
                            <tr><th>Title</th><th>Date</th></tr>
                            ${data.items.map(m => `<tr>
                                <td><a href="#" onclick="viewMeeting('${m.meeting_id}')">${escapeHtml(m.title)}</a></td>
                                <td>${m.meeting_date}</td>
                            </tr>`).join('')}
                        </table>` : '<div class="empty-state">No meeting notes yet</div>'}
                    </div>
                `;
            } catch (e) {
                content.innerHTML = '<div class="empty-state">Error loading meetings</div>';
            }
        }

        async function loadMemory() {
            const content = document.getElementById('content');
            content.innerHTML = '<div class="empty-state">Loading...</div>';

            try {
                const res = await fetch('/v1/memory/facts?status=active&limit=50', { headers: getHeaders() });
                if (!res.ok) throw new Error();
                const data = await res.json();

                content.innerHTML = `
                    <div class="card">
                        <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:15px;">
                            <h2>Memory Facts (${data.total})</h2>
                            <button class="btn" onclick="showCreateFact()">+ New Fact</button>
                        </div>
                        ${data.items.length ? `<table>
                            <tr><th>Key</th><th>Category</th><th>Value</th><th>Status</th></tr>
                            ${data.items.map(f => `<tr>
                                <td><a href="#" onclick="viewFact('${f.fact_id}')">${escapeHtml(f.fact_key)}</a></td>
                                <td>${f.category}</td>
                                <td>${escapeHtml(f.fact_value.substring(0, 50))}${f.fact_value.length > 50 ? '...' : ''}</td>
                                <td><span class="status-badge status-${f.status}">${f.status}</span></td>
                            </tr>`).join('')}
                        </table>` : '<div class="empty-state">No memory facts yet</div>'}
                    </div>
                `;
            } catch (e) {
                content.innerHTML = '<div class="empty-state">Error loading memory</div>';
            }
        }

        async function loadTimeline() {
            const content = document.getElementById('content');
            content.innerHTML = '<div class="empty-state">Loading...</div>';

            try {
                const res = await fetch('/v1/timeline?limit=50', { headers: getHeaders() });
                if (!res.ok) throw new Error();
                const data = await res.json();

                content.innerHTML = `
                    <div class="card">
                        <h2>Timeline (${data.total})</h2>
                        ${data.items.length ? `<table>
                            <tr><th>Event</th><th>Entity</th><th>Summary</th><th>Time</th></tr>
                            ${data.items.map(e => `<tr>
                                <td>${e.event_type}</td>
                                <td>${e.entity_type}/${e.entity_id.substring(0, 8)}...</td>
                                <td>${escapeHtml(e.summary)}</td>
                                <td>${e.created_at.split('T')[0]}</td>
                            </tr>`).join('')}
                        </table>` : '<div class="empty-state">No timeline events yet</div>'}
                    </div>
                `;
            } catch (e) {
                content.innerHTML = '<div class="empty-state">Error loading timeline</div>';
            }
        }

        async function loadBilling() {
            const content = document.getElementById('content');
            content.innerHTML = '<div class="empty-state">Loading...</div>';

            try {
                const { res, data, ok } = await apiFetch('/v1/billing/usage', { headers: getHeaders() });
                if (!ok) throw new Error(data.detail || 'Failed to load billing data');

                const credits = data.credits;
                const plan = data.plan;

                // Filter breakdown to show action_* events prominently
                const actionEvents = data.breakdown.filter(b => b.event_key.startsWith('action_'));
                const otherEvents = data.breakdown.filter(b => !b.event_key.startsWith('action_'));

                content.innerHTML = `
                    <div class="card">
                        <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:15px;">
                            <h2>Billing Usage</h2>
                            <button class="btn btn-secondary" onclick="loadBilling()">Refresh</button>
                        </div>
                        <div style="margin-bottom:15px;font-size:13px;color:#666;">
                            <strong>Plan:</strong> ${plan.name} |
                            <strong>Period:</strong> ${data.period_start} to ${data.period_end}
                        </div>
                        <div style="display:flex;gap:30px;margin-bottom:20px;">
                            <div>
                                <div style="font-size:24px;font-weight:bold;">${credits.included}</div>
                                <div style="font-size:12px;color:#666;">Included Credits</div>
                            </div>
                            <div>
                                <div style="font-size:24px;font-weight:bold;color:#0066cc;">${credits.used.toFixed(2)}</div>
                                <div style="font-size:12px;color:#666;">Credits Used</div>
                            </div>
                            <div>
                                <div style="font-size:24px;font-weight:bold;color:#00aa00;">${credits.remaining.toFixed(2)}</div>
                                <div style="font-size:12px;color:#666;">Remaining</div>
                            </div>
                            ${credits.overage_credits > 0 ? `<div>
                                <div style="font-size:24px;font-weight:bold;color:#cc0000;">${credits.overage_credits.toFixed(2)}</div>
                                <div style="font-size:12px;color:#666;">Overage (~$${credits.estimated_overage_cost.toFixed(2)})</div>
                            </div>` : ''}
                        </div>

                        ${actionEvents.length ? `
                            <h3 style="font-size:14px;margin-bottom:10px;">Action Center Usage</h3>
                            <table style="margin-bottom:20px;">
                                <tr><th>Event Type</th><th>Raw Units</th><th>Credits</th><th>Est. Cost</th></tr>
                                ${actionEvents.map(b => `<tr>
                                    <td>${b.event_key}</td>
                                    <td>${b.raw_units}</td>
                                    <td>${b.credits.toFixed(2)}</td>
                                    <td>$${b.list_cost_estimate.toFixed(4)}</td>
                                </tr>`).join('')}
                            </table>
                        ` : ''}

                        <h3 style="font-size:14px;margin-bottom:10px;">All Usage Breakdown</h3>
                        ${data.breakdown.length ? `<table>
                            <tr><th>Event Type</th><th>Raw Units</th><th>Credits</th><th>Est. Cost</th></tr>
                            ${data.breakdown.map(b => `<tr>
                                <td>${b.event_key}</td>
                                <td>${b.raw_units}</td>
                                <td>${b.credits.toFixed(2)}</td>
                                <td>$${b.list_cost_estimate.toFixed(4)}</td>
                            </tr>`).join('')}
                        </table>` : '<div class="empty-state">No usage yet</div>'}
                    </div>
                `;
            } catch (e) {
                content.innerHTML = '<div class="empty-state">Error loading billing data: ' + escapeHtml(e.message) + '</div>';
            }
        }

        async function loadSearch() {
            const content = document.getElementById('content');
            content.innerHTML = `
                <div class="card">
                    <h2>Global Search</h2>
                    <div class="search-box">
                        <input type="text" id="search-input" placeholder="Search across all entities..." onkeypress="if(event.key==='Enter')doSearch()">
                        <button class="btn" onclick="doSearch()">Search</button>
                    </div>
                    <div id="search-results"></div>
                </div>
            `;
        }

        async function doSearch() {
            const q = document.getElementById('search-input').value.trim();
            if (!q) return;

            const results = document.getElementById('search-results');
            results.innerHTML = '<div class="empty-state">Searching...</div>';

            try {
                const res = await fetch('/v1/search?q=' + encodeURIComponent(q), { headers: getHeaders() });
                if (!res.ok) throw new Error();
                const data = await res.json();

                results.innerHTML = data.results.length ? `<table>
                    <tr><th>Type</th><th>Title</th><th>Snippet</th></tr>
                    ${data.results.map(r => `<tr>
                        <td>${r.entity_type}</td>
                        <td><a href="#" onclick="viewRecord('${r.entity_type}', '${r.entity_id}')">${escapeHtml(r.title)}</a></td>
                        <td>${escapeHtml(r.snippet || '')}</td>
                    </tr>`).join('')}
                </table>` : '<div class="empty-state">No results found</div>';
            } catch (e) {
                results.innerHTML = '<div class="empty-state">Search failed</div>';
            }
        }

        // Modal functions
        function openModal(title, body) {
            document.getElementById('modal-title').textContent = title;
            document.getElementById('modal-body').innerHTML = body;
            document.getElementById('modal').classList.add('active');
        }

        function closeModal() {
            document.getElementById('modal').classList.remove('active');
        }

        // Create forms
        function showCreateAction() {
            openModal('Create Action', `
                <div class="form-group"><label>Title *</label><input type="text" id="action-title" placeholder="Action title (required)"></div>
                <div class="form-group"><label>Description</label><textarea id="action-description" placeholder="Optional description"></textarea></div>
                <div class="form-row">
                    <div class="form-group"><label>Action Type *</label><input type="text" id="action-type" value="general" placeholder="e.g., outreach, update, create"></div>
                    <div class="form-group"><label>Source</label><select id="action-source"><option value="user">user</option><option value="agent">agent</option><option value="system">system</option></select></div>
                </div>
                <div class="form-row">
                    <div class="form-group"><label>Assigned To User ID</label><input type="text" id="action-assigned" placeholder="Optional user ID"></div>
                    <div class="form-group"><label>Source Ref</label><input type="text" id="action-source-ref" placeholder="Optional reference"></div>
                </div>
                <div class="form-group">
                    <label>Payload (JSON)</label>
                    <textarea id="action-payload" style="font-family:monospace;min-height:100px;" placeholder='{"key": "value"}'>{}</textarea>
                    <div id="action-payload-error" style="color:#cc0000;font-size:11px;display:none;"></div>
                </div>
                <button class="btn" onclick="createAction()">Create Action</button>
            `);
        }

        async function createAction() {
            const title = document.getElementById('action-title').value.trim();
            const actionType = document.getElementById('action-type').value.trim();
            const payloadText = document.getElementById('action-payload').value.trim();
            const payloadError = document.getElementById('action-payload-error');

            if (!title) {
                alert('Title is required');
                return;
            }
            if (!actionType) {
                alert('Action type is required');
                return;
            }

            let payload = {};
            try {
                payload = JSON.parse(payloadText || '{}');
                payloadError.style.display = 'none';
            } catch (e) {
                payloadError.textContent = 'Invalid JSON: ' + e.message;
                payloadError.style.display = 'block';
                return;
            }

            const body = {
                title: title,
                description: document.getElementById('action-description').value || null,
                action_type: actionType,
                source: document.getElementById('action-source').value,
                source_ref: document.getElementById('action-source-ref').value || null,
                assigned_to_user_id: document.getElementById('action-assigned').value || null,
                payload: payload
            };

            try {
                const { res, data, ok } = await apiFetch('/v1/actions', {
                    method: 'POST',
                    headers: getHeaders(),
                    body: JSON.stringify(body)
                });
                if (!ok) {
                    throw new Error(typeof data.detail === 'string' ? data.detail : JSON.stringify(data.detail));
                }
                closeModal();
                loadActions();
                // Open the newly created action in detail view
                setTimeout(() => viewActionDetail(data.action_id), 100);
            } catch (e) {
                alert('Error: ' + e.message);
            }
        }

        function showCreateTask() {
            openModal('Create Task', `
                <div class="form-group"><label>Title *</label><input type="text" id="task-title" placeholder="Task title (required)"></div>
                <div class="form-group"><label>Description</label><textarea id="task-description" placeholder="Optional description"></textarea></div>
                <div class="form-row">
                    <div class="form-group"><label>Priority</label><select id="task-priority"><option value="low">Low</option><option value="medium" selected>Medium</option><option value="high">High</option></select></div>
                    <div class="form-group"><label>Due Date</label><input type="date" id="task-due"></div>
                </div>
                <div class="form-group"><label>Assigned To User ID</label><input type="text" id="task-assigned" placeholder="Optional user ID"></div>
                <div class="form-row">
                    <div class="form-group"><label>Linked Entity Type</label><input type="text" id="task-linked-type" placeholder="e.g. action, decision"></div>
                    <div class="form-group"><label>Linked Entity ID</label><input type="text" id="task-linked-id" placeholder="Optional entity ID"></div>
                </div>
                <button class="btn" onclick="createTask()">Create Task</button>
            `);
        }

        async function createTask() {
            const title = document.getElementById('task-title').value.trim();
            if (!title) {
                alert('Title is required');
                return;
            }

            const body = {
                title: title,
                description: document.getElementById('task-description').value || null,
                priority: document.getElementById('task-priority').value,
                due_date: document.getElementById('task-due').value || null,
                assigned_to_user_id: document.getElementById('task-assigned').value || null,
                linked_entity_type: document.getElementById('task-linked-type').value || null,
                linked_entity_id: document.getElementById('task-linked-id').value || null
            };
            try {
                const { res, data, ok } = await apiFetch('/v1/tasks', { method: 'POST', headers: getHeaders(), body: JSON.stringify(body) });
                if (!ok) {
                    throw new Error(typeof data.detail === 'string' ? data.detail : JSON.stringify(data.detail));
                }
                closeModal();
                loadTasks();
                // Open the newly created task in detail view
                setTimeout(() => viewTaskDetail(data.task_id), 100);
            } catch (e) { alert('Error: ' + e.message); }
        }

        function showCreateDecision() {
            openModal('Create Decision', `
                <div class="form-group"><label>Title</label><input type="text" id="decision-title"></div>
                <div class="form-group"><label>Date</label><input type="date" id="decision-date" value="${new Date().toISOString().split('T')[0]}"></div>
                <div class="form-group"><label>Context</label><textarea id="decision-context"></textarea></div>
                <div class="form-group"><label>Decision</label><textarea id="decision-text"></textarea></div>
                <div class="form-group"><label>Rationale</label><textarea id="decision-rationale"></textarea></div>
                <button class="btn" onclick="createDecision()">Create</button>
            `);
        }

        async function createDecision() {
            const body = {
                title: document.getElementById('decision-title').value,
                decision_date: document.getElementById('decision-date').value,
                context: document.getElementById('decision-context').value,
                decision: document.getElementById('decision-text').value,
                rationale: document.getElementById('decision-rationale').value
            };
            try {
                const res = await fetch('/v1/decisions', { method: 'POST', headers: getHeaders(), body: JSON.stringify(body) });
                if (!res.ok) throw new Error((await res.json()).detail);
                closeModal();
                loadDecisions();
            } catch (e) { alert('Error: ' + e.message); }
        }

        function showCreateMeeting() {
            openModal('Create Meeting Note', `
                <div class="form-group"><label>Title</label><input type="text" id="meeting-title"></div>
                <div class="form-group"><label>Date</label><input type="date" id="meeting-date" value="${new Date().toISOString().split('T')[0]}"></div>
                <div class="form-group"><label>Notes</label><textarea id="meeting-notes" style="min-height:150px;"></textarea></div>
                <button class="btn" onclick="createMeeting()">Create</button>
            `);
        }

        async function createMeeting() {
            const body = {
                title: document.getElementById('meeting-title').value,
                meeting_date: document.getElementById('meeting-date').value,
                notes: document.getElementById('meeting-notes').value
            };
            try {
                const res = await fetch('/v1/meetings', { method: 'POST', headers: getHeaders(), body: JSON.stringify(body) });
                if (!res.ok) throw new Error((await res.json()).detail);
                closeModal();
                loadMeetings();
            } catch (e) { alert('Error: ' + e.message); }
        }

        function showCreateFact() {
            openModal('Create Memory Fact', `
                <div class="form-row">
                    <div class="form-group"><label>Category</label><select id="fact-category">
                        <option value="icp">ICP</option><option value="positioning">Positioning</option><option value="pricing">Pricing</option>
                        <option value="goals">Goals</option><option value="constraints">Constraints</option><option value="brand">Brand</option><option value="other">Other</option>
                    </select></div>
                    <div class="form-group"><label>Key</label><input type="text" id="fact-key" placeholder="e.g. ICP.primary"></div>
                </div>
                <div class="form-group"><label>Value</label><textarea id="fact-value" style="min-height:100px;"></textarea></div>
                <button class="btn" onclick="createFact()">Create</button>
            `);
        }

        async function createFact() {
            const body = {
                category: document.getElementById('fact-category').value,
                fact_key: document.getElementById('fact-key').value,
                fact_value: document.getElementById('fact-value').value
            };
            try {
                const res = await fetch('/v1/memory/facts', { method: 'POST', headers: getHeaders(), body: JSON.stringify(body) });
                if (!res.ok) throw new Error((await res.json()).detail);
                closeModal();
                loadMemory();
            } catch (e) { alert('Error: ' + e.message); }
        }

        // Action operations - Dialog versions with comment/form inputs
        function showApproveDialog(id) {
            openModal('Approve Action', `
                <p style="margin-bottom:15px;">Approve this action?</p>
                <div class="form-group">
                    <label>Comment (optional)</label>
                    <textarea id="approve-comment" placeholder="Add an optional comment for the approval"></textarea>
                </div>
                <div style="display:flex;gap:10px;">
                    <button class="btn btn-success" onclick="doApproveAction('${id}')">Approve</button>
                    <button class="btn btn-secondary" onclick="closeModal()">Cancel</button>
                </div>
            `);
        }

        async function doApproveAction(id) {
            const comment = document.getElementById('approve-comment').value || null;
            try {
                const { res, data, ok } = await apiFetch('/v1/actions/' + id + '/approve', {
                    method: 'POST',
                    headers: getHeaders(),
                    body: JSON.stringify({ comment: comment })
                });
                if (!ok) {
                    throw new Error(typeof data.detail === 'string' ? data.detail : JSON.stringify(data.detail));
                }
                closeModal();
                loadActions();
            } catch (e) {
                alert('Error: ' + e.message);
            }
        }

        function showRejectDialog(id) {
            openModal('Reject Action', `
                <p style="margin-bottom:15px;">Reject this action?</p>
                <div class="form-group">
                    <label>Comment (optional)</label>
                    <textarea id="reject-comment" placeholder="Add an optional comment for the rejection"></textarea>
                </div>
                <div style="display:flex;gap:10px;">
                    <button class="btn btn-danger" onclick="doRejectAction('${id}')">Reject</button>
                    <button class="btn btn-secondary" onclick="closeModal()">Cancel</button>
                </div>
            `);
        }

        async function doRejectAction(id) {
            const comment = document.getElementById('reject-comment').value || null;
            try {
                const { res, data, ok } = await apiFetch('/v1/actions/' + id + '/reject', {
                    method: 'POST',
                    headers: getHeaders(),
                    body: JSON.stringify({ comment: comment })
                });
                if (!ok) {
                    throw new Error(typeof data.detail === 'string' ? data.detail : JSON.stringify(data.detail));
                }
                closeModal();
                loadActions();
            } catch (e) {
                alert('Error: ' + e.message);
            }
        }

        function showExecuteDialog(id) {
            openModal('Execute Action', `
                <p style="margin-bottom:15px;">Execute this action</p>
                <div class="form-group">
                    <label>Execution Status *</label>
                    <select id="execute-status">
                        <option value="succeeded" selected>succeeded</option>
                        <option value="failed">failed</option>
                        <option value="skipped">skipped</option>
                    </select>
                </div>
                <div class="form-group">
                    <label>Result (JSON)</label>
                    <textarea id="execute-result" style="font-family:monospace;min-height:100px;" placeholder='{"key": "value"}'>{}</textarea>
                    <div id="execute-result-error" style="color:#cc0000;font-size:11px;display:none;"></div>
                </div>
                <div style="display:flex;gap:10px;">
                    <button class="btn" onclick="doExecuteAction('${id}')">Execute</button>
                    <button class="btn btn-secondary" onclick="closeModal()">Cancel</button>
                </div>
            `);
        }

        async function doExecuteAction(id) {
            const execStatus = document.getElementById('execute-status').value;
            const resultText = document.getElementById('execute-result').value.trim();
            const resultError = document.getElementById('execute-result-error');

            let result = {};
            try {
                result = JSON.parse(resultText || '{}');
                resultError.style.display = 'none';
            } catch (e) {
                resultError.textContent = 'Invalid JSON: ' + e.message;
                resultError.style.display = 'block';
                return;
            }

            try {
                const { res, data, ok } = await apiFetch('/v1/actions/' + id + '/execute', {
                    method: 'POST',
                    headers: getHeaders(),
                    body: JSON.stringify({ execution_status: execStatus, result: result })
                });
                if (!ok) {
                    throw new Error(typeof data.detail === 'string' ? data.detail : JSON.stringify(data.detail));
                }
                closeModal();
                loadActions();
            } catch (e) {
                alert('Error: ' + e.message);
            }
        }

        async function cancelAction(id) {
            if (!confirm('Cancel this action?')) return;
            try {
                const { res, data, ok } = await apiFetch('/v1/actions/' + id + '/cancel', {
                    method: 'POST',
                    headers: getHeaders(),
                    body: '{}'
                });
                if (!ok) {
                    throw new Error(typeof data.detail === 'string' ? data.detail : JSON.stringify(data.detail));
                }
                loadActions();
            } catch (e) {
                alert('Error: ' + e.message);
            }
        }

        // Legacy function names for backwards compatibility with detail view buttons
        function approveAction(id) { showApproveDialog(id); }
        function rejectAction(id) { showRejectDialog(id); }
        function executeAction(id) { showExecuteDialog(id); }

        async function viewActionDetail(id) {
            try {
                const { res, data: a, ok } = await apiFetch('/v1/actions/' + id, { headers: getHeaders() });
                if (!ok) throw new Error(a.detail || 'Failed to load action');

                const isAdmin = userRole === 'admin';
                const currentUserId = document.getElementById('user-id').value;
                const canCancel = a.status === 'proposed' && (isAdmin || a.created_by_user_id === currentUserId);

                let body = `
                    <div class="detail-section">
                        <h4>Action Details</h4>
                        <p><strong>ID:</strong> ${a.action_id}</p>
                        <p><strong>Title:</strong> ${escapeHtml(a.title)}</p>
                        <p><strong>Status:</strong> <span class="status-badge status-${a.status}">${a.status}</span></p>
                        <p><strong>Type:</strong> ${a.action_type}</p>
                        <p><strong>Source:</strong> ${a.source}${a.source_ref ? ' (ref: ' + escapeHtml(a.source_ref) + ')' : ''}</p>
                        <p><strong>Description:</strong> ${escapeHtml(a.description || '-')}</p>
                        <p><strong>Created By:</strong> ${a.created_by_user_id}</p>
                        <p><strong>Assigned To:</strong> ${a.assigned_to_user_id || '-'}</p>
                        <p><strong>Created:</strong> ${a.created_at}</p>
                        <p><strong>Updated:</strong> ${a.updated_at}</p>
                    </div>
                    <div class="detail-section">
                        <h4>Payload</h4>
                        <pre>${JSON.stringify(a.payload, null, 2)}</pre>
                    </div>
                `;

                if (a.review) {
                    body += `
                        <div class="detail-section" style="border-top:1px solid #eee;padding-top:15px;">
                            <h4>Review</h4>
                            <p><strong>Decision:</strong> <span class="status-badge status-${a.review.decision}">${a.review.decision}</span></p>
                            <p><strong>Reviewer:</strong> ${a.review.reviewer_user_id}</p>
                            <p><strong>Comment:</strong> ${escapeHtml(a.review.comment || '-')}</p>
                            <p><strong>Time:</strong> ${a.review.created_at}</p>
                        </div>
                    `;
                } else if (a.status === 'proposed') {
                    body += `
                        <div class="detail-section" style="border-top:1px solid #eee;padding-top:15px;">
                            <h4>Review</h4>
                            <p style="color:#999;">Pending review</p>
                        </div>
                    `;
                }

                if (a.execution) {
                    body += `
                        <div class="detail-section" style="border-top:1px solid #eee;padding-top:15px;">
                            <h4>Execution</h4>
                            <p><strong>Execution ID:</strong> ${a.execution.execution_id}</p>
                            <p><strong>Status:</strong> <span class="status-badge status-${a.execution.execution_status === 'succeeded' ? 'done' : a.execution.execution_status === 'failed' ? 'rejected' : 'cancelled'}">${a.execution.execution_status}</span></p>
                            <p><strong>Executed By:</strong> ${a.execution.executed_by_user_id}</p>
                            <p><strong>Time:</strong> ${a.execution.created_at}</p>
                            <p><strong>Result:</strong></p>
                            <pre>${JSON.stringify(a.execution.result, null, 2)}</pre>
                        </div>
                    `;
                } else if (a.status === 'approved') {
                    body += `
                        <div class="detail-section" style="border-top:1px solid #eee;padding-top:15px;">
                            <h4>Execution</h4>
                            <p style="color:#999;">Pending execution</p>
                        </div>
                    `;
                }

                // Add action buttons based on status
                body += '<div style="margin-top:20px;display:flex;gap:10px;">';
                if (a.status === 'proposed' && isAdmin) {
                    body += `<button class="btn btn-success" onclick="closeModal();showApproveDialog('${a.action_id}')">Approve</button>`;
                    body += `<button class="btn btn-danger" onclick="closeModal();showRejectDialog('${a.action_id}')">Reject</button>`;
                }
                if (canCancel) {
                    body += `<button class="btn btn-secondary" onclick="closeModal();cancelAction('${a.action_id}')">Cancel</button>`;
                }
                if (a.status === 'approved' && isAdmin) {
                    body += `<button class="btn" onclick="closeModal();showExecuteDialog('${a.action_id}')">Execute</button>`;
                }
                body += '</div>';

                openModal('Action: ' + escapeHtml(a.title), body);
            } catch (e) {
                alert('Error loading action details: ' + e.message);
            }
        }

        async function viewTaskDetail(id) {
            try {
                const { res, data: t, ok } = await apiFetch('/v1/tasks/' + id, { headers: getHeaders() });
                if (!ok) throw new Error(t.detail || 'Failed to load task');

                const isAdmin = userRole === 'admin';
                const currentUserId = document.getElementById('user-id').value;
                const isCreator = t.created_by_user_id === currentUserId;
                const isAssignee = t.assigned_to_user_id === currentUserId;
                const canEdit = isAdmin || isCreator || isAssignee;
                const canComplete = (isAdmin || isCreator || isAssignee) && t.status !== 'done';

                let body = `
                    <div class="detail-section">
                        <h4>Task Details</h4>
                        <p><strong>ID:</strong> ${t.task_id}</p>
                        <p><strong>Title:</strong> ${escapeHtml(t.title)}</p>
                        <p><strong>Status:</strong> <span class="status-badge status-${t.status}">${t.status}</span></p>
                        <p><strong>Priority:</strong> <span class="priority-${t.priority}">${t.priority}</span></p>
                        <p><strong>Due Date:</strong> ${t.due_date || '-'}</p>
                        <p><strong>Description:</strong> ${escapeHtml(t.description || '-')}</p>
                        <p><strong>Created By:</strong> ${t.created_by_user_id}</p>
                        <p><strong>Assigned To:</strong> ${t.assigned_to_user_id || '-'}</p>
                        ${t.linked_entity_type ? `<p><strong>Linked:</strong> ${t.linked_entity_type}/${t.linked_entity_id || '-'}</p>` : ''}
                        <p><strong>Created:</strong> ${t.created_at}</p>
                        <p><strong>Updated:</strong> ${t.updated_at}</p>
                    </div>
                `;

                if (canEdit) {
                    body += `
                        <div class="detail-section" style="border-top:1px solid #eee;padding-top:15px;">
                            <h4>Edit Task</h4>
                            <div class="form-group"><label>Title</label><input type="text" id="edit-task-title" value="${escapeHtml(t.title)}"></div>
                            <div class="form-group"><label>Description</label><textarea id="edit-task-description">${escapeHtml(t.description || '')}</textarea></div>
                            <div class="form-row">
                                <div class="form-group"><label>Priority</label><select id="edit-task-priority">
                                    <option value="low" ${t.priority==='low'?'selected':''}>Low</option>
                                    <option value="medium" ${t.priority==='medium'?'selected':''}>Medium</option>
                                    <option value="high" ${t.priority==='high'?'selected':''}>High</option>
                                </select></div>
                                <div class="form-group"><label>Status</label><select id="edit-task-status">
                                    <option value="todo" ${t.status==='todo'?'selected':''}>Todo</option>
                                    <option value="doing" ${t.status==='doing'?'selected':''}>Doing</option>
                                    <option value="done" ${t.status==='done'?'selected':''}>Done</option>
                                </select></div>
                            </div>
                            <div class="form-row">
                                <div class="form-group"><label>Due Date</label><input type="date" id="edit-task-due" value="${t.due_date || ''}"></div>
                                <div class="form-group"><label>Assigned To</label><input type="text" id="edit-task-assigned" value="${t.assigned_to_user_id || ''}"></div>
                            </div>
                        </div>
                    `;
                }

                body += '<div style="margin-top:20px;display:flex;gap:10px;">';
                if (canEdit) {
                    body += `<button class="btn" onclick="saveTaskChanges('${t.task_id}')">Save Changes</button>`;
                }
                if (canComplete) {
                    body += `<button class="btn btn-success" onclick="closeModal();completeTask('${t.task_id}')">Complete</button>`;
                }
                body += '</div>';

                openModal('Task: ' + escapeHtml(t.title), body);
            } catch (e) {
                alert('Error loading task details: ' + e.message);
            }
        }

        async function saveTaskChanges(id) {
            const body = {
                title: document.getElementById('edit-task-title').value,
                description: document.getElementById('edit-task-description').value || null,
                priority: document.getElementById('edit-task-priority').value,
                status: document.getElementById('edit-task-status').value,
                due_date: document.getElementById('edit-task-due').value || null,
                assigned_to_user_id: document.getElementById('edit-task-assigned').value || null
            };

            try {
                const { res, data, ok } = await apiFetch('/v1/tasks/' + id, {
                    method: 'PATCH',
                    headers: getHeaders(),
                    body: JSON.stringify(body)
                });
                if (!ok) {
                    throw new Error(typeof data.detail === 'string' ? data.detail : JSON.stringify(data.detail));
                }
                closeModal();
                loadTasks();
            } catch (e) {
                alert('Error: ' + e.message);
            }
        }

        async function completeTask(id) {
            try {
                const { res, data, ok } = await apiFetch('/v1/tasks/' + id + '/complete', { method: 'POST', headers: getHeaders() });
                if (!ok) throw new Error(typeof data.detail === 'string' ? data.detail : JSON.stringify(data.detail));
                loadTasks();
            } catch (e) { alert('Error: ' + e.message); }
        }

        // View record details
        async function viewRecord(type, id) {
            try {
                const res = await fetch('/v1/records/' + type + '/' + id, { headers: getHeaders() });
                if (!res.ok) throw new Error();
                const data = await res.json();

                let body = `<div class="detail-section"><h4>Entity</h4><pre>${JSON.stringify(data.entity, null, 2)}</pre></div>`;
                if (data.evidence.length) {
                    body += `<div class="detail-section"><h4>Evidence (${data.evidence.length})</h4><pre>${JSON.stringify(data.evidence, null, 2)}</pre></div>`;
                }
                if (data.timeline.length) {
                    body += `<div class="detail-section"><h4>Timeline (${data.timeline.length})</h4><pre>${JSON.stringify(data.timeline, null, 2)}</pre></div>`;
                }

                openModal(type.charAt(0).toUpperCase() + type.slice(1) + ' Details', body);
            } catch (e) { alert('Error loading record'); }
        }

        function viewAction(id) { viewActionDetail(id); }
        function viewTask(id) { viewTaskDetail(id); }
        function viewDecision(id) { viewRecord('decision', id); }
        function viewMeeting(id) { viewRecord('meeting', id); }
        function viewFact(id) { viewRecord('memory_fact', id); }

        function escapeHtml(text) {
            const div = document.createElement('div');
            div.textContent = text;
            return div.innerHTML;
        }
    </script>
</body>
</html>
"""


@router.get("/app", response_class=HTMLResponse)
def core_os_ui() -> str:
    """Serve the Core Business OS UI.

    Enabled via PLAYGROUND_UI_ENABLED=1 environment variable.
    """
    if not PLAYGROUND_UI_ENABLED:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Core OS UI is disabled. Set PLAYGROUND_UI_ENABLED=1 to enable.",
        )

    html = CORE_OS_HTML.replace(
        "{DEV_CONSOLE_ENABLED}",
        "true" if DEV_CONSOLE_ENABLED else "false"
    ).replace(
        "{DEV_CONSOLE_KEY}",
        DEV_CONSOLE_KEY if DEV_CONSOLE_ENABLED else ""
    )

    return html
