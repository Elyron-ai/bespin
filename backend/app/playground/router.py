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
