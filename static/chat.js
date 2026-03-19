const API_BASE = window.location.origin;
let token = null;
let ws = null;
let conversationId = null;
let currentBubble = null;
let heartbeatTimer = null;

async function login() {
    const username = document.getElementById('username').value;
    const password = document.getElementById('password').value;
    try {
        const res = await fetch(`${API_BASE}/api/v1/admin/auth/login`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ username, password }),
        });
        const data = await res.json();
        if (data.success && data.data) {
            token = data.data.access_token;
            document.getElementById('loginBtn').style.display = 'none';
            document.getElementById('username').style.display = 'none';
            document.getElementById('password').style.display = 'none';
            document.getElementById('userInfo').style.display = 'inline';
            document.getElementById('userInfo').textContent = username;
            document.getElementById('sendBtn').disabled = false;
            connectWS();
        } else {
            alert(data.error || 'Login failed');
        }
    } catch (e) {
        alert('Login error: ' + e.message);
    }
}

function connectWS() {
    if (ws) ws.close();
    const proto = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
    ws = new WebSocket(`${proto}//${window.location.host}/api/v1/chat/ws/${token}`);

    ws.onopen = () => {
        heartbeatTimer = setInterval(() => {
            if (ws.readyState === WebSocket.OPEN) {
                ws.send(JSON.stringify({ type: 'ping' }));
            }
        }, 30000);
    };

    ws.onmessage = (event) => {
        const msg = JSON.parse(event.data);
        handleServerMessage(msg);
    };

    ws.onclose = () => {
        clearInterval(heartbeatTimer);
        setTimeout(() => { if (token) connectWS(); }, 3000);
    };

    ws.onerror = () => {};
}

function handleServerMessage(msg) {
    if (msg.conversation_id) {
        conversationId = msg.conversation_id;
    }

    switch (msg.type) {
        case 'token':
            if (!currentBubble) {
                currentBubble = addMessage('assistant', '');
                document.getElementById('cancelBtn').style.display = 'inline-block';
                document.getElementById('sendBtn').style.display = 'none';
            }
            currentBubble.querySelector('.bubble').textContent += msg.data.content;
            scrollToBottom();
            break;
        case 'message_end':
            if (msg.data.sources && msg.data.sources.length > 0 && currentBubble) {
                const srcDiv = document.createElement('div');
                srcDiv.className = 'sources';
                srcDiv.innerHTML = 'Sources: ' + msg.data.sources
                    .map(s => `<span>${s.title || 'Unknown'} (${(s.score * 100).toFixed(0)}%)</span>`)
                    .join('');
                currentBubble.appendChild(srcDiv);
            }
            currentBubble = null;
            document.getElementById('cancelBtn').style.display = 'none';
            document.getElementById('sendBtn').style.display = 'inline-block';
            break;
        case 'intent':
            if (currentBubble) {
                const tag = document.createElement('div');
                tag.className = 'intent-tag';
                tag.textContent = `${msg.data.label} (${(msg.data.confidence * 100).toFixed(0)}%)`;
                currentBubble.appendChild(tag);
            }
            break;
        case 'error':
            addMessage('assistant', msg.data.content || 'An error occurred');
            currentBubble = null;
            document.getElementById('cancelBtn').style.display = 'none';
            document.getElementById('sendBtn').style.display = 'inline-block';
            break;
        case 'ticket':
            if (currentBubble) {
                const ticketInfo = document.createElement('div');
                ticketInfo.className = 'intent-tag';
                ticketInfo.textContent = `Ticket: ${msg.data.ticket_id}`;
                currentBubble.appendChild(ticketInfo);
            }
            break;
        case 'pong':
            break;
    }
}

function sendMessage() {
    const input = document.getElementById('messageInput');
    const content = input.value.trim();
    if (!content || !ws || ws.readyState !== WebSocket.OPEN) return;

    addMessage('user', content);
    ws.send(JSON.stringify({
        type: 'message',
        conversation_id: conversationId,
        content: content,
        timestamp: Math.floor(Date.now() / 1000),
    }));
    input.value = '';
}

function cancelGeneration() {
    if (ws && ws.readyState === WebSocket.OPEN) {
        ws.send(JSON.stringify({ type: 'cancel' }));
    }
}

function addMessage(role, content) {
    const container = document.getElementById('messages');
    const div = document.createElement('div');
    div.className = `message ${role}`;
    div.innerHTML = `
        <div class="role">${role === 'user' ? 'You' : 'AskFlow'}</div>
        <div class="bubble">${escapeHtml(content)}</div>
    `;
    container.appendChild(div);
    scrollToBottom();
    return div;
}

function escapeHtml(text) {
    const el = document.createElement('div');
    el.textContent = text;
    return el.innerHTML;
}

function scrollToBottom() {
    const container = document.getElementById('messages');
    container.scrollTop = container.scrollHeight;
}
