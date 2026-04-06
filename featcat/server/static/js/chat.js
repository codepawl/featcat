/* featcat AI Chat */

const messages = document.getElementById('messages');
const chatInput = document.getElementById('chat-input');
const sendBtn = document.getElementById('send-btn');

/* --- Initialization --- */

document.addEventListener('DOMContentLoaded', () => {
    addMessage('Welcome to featcat AI Chat! Ask anything about your features.', 'ai');
    chatInput.focus();
});

chatInput.addEventListener('keydown', (e) => {
    if (e.key === 'Enter' && !e.shiftKey) {
        e.preventDefault();
        sendMessage();
    }
});

/* --- Core Functions --- */

function addMessage(text, role) {
    const div = document.createElement('div');
    div.className = `message ${role}`;
    div.textContent = text;
    messages.appendChild(div);
    scrollToBottom();
    return div;
}

function scrollToBottom() {
    messages.scrollTop = messages.scrollHeight;
}

function setLoading(loading) {
    sendBtn.disabled = loading;
    chatInput.disabled = loading;
}

function sendMessage() {
    const text = chatInput.value.trim();
    if (!text) return;

    chatInput.value = '';
    setLoading(true);
    addMessage(text, 'user');

    if (text.startsWith('discover: ') || text.startsWith('/discover ')) {
        const useCase = text.replace(/^(discover: |\/discover )/, '');
        handleDiscover(useCase);
    } else {
        handleStream(text);
    }
}

function handleStream(query) {
    const bubble = addMessage('', 'ai');

    featcat.ai.stream(
        query,
        function onToken(content) {
            bubble.textContent += content;
            scrollToBottom();
        },
        function onDone(data) {
            if (data && data.results && data.results.length > 0) {
                bubble.innerHTML = formatResults(data);
            }
            setLoading(false);
            chatInput.focus();
            scrollToBottom();
        },
        function onError(err) {
            bubble.innerHTML = '<span style="color:var(--danger)">Error: ' + escapeHtml(err.message) + '</span>';
            setLoading(false);
            chatInput.focus();
            scrollToBottom();
        }
    );
}

function handleDiscover(useCase) {
    const bubble = addMessage('Analyzing catalog...', 'ai');

    featcat.ai.discover(useCase)
        .then(data => {
            bubble.innerHTML = formatDiscoverResults(data);
            scrollToBottom();
        })
        .catch(err => {
            bubble.innerHTML = '<span style="color:var(--danger)">Error: ' + escapeHtml(err.message) + '</span>';
            scrollToBottom();
        })
        .finally(() => {
            setLoading(false);
            chatInput.focus();
        });
}

/* --- Formatting Helpers --- */

function formatResults(data) {
    let html = '<table style="width:100%;border-collapse:collapse;font-size:0.85rem">';
    html += '<tr style="border-bottom:1px solid var(--border)">';
    html += '<th style="text-align:left;padding:6px 8px">Feature</th>';
    html += '<th style="text-align:left;padding:6px 8px">Score</th>';
    html += '<th style="text-align:left;padding:6px 8px">Reason</th>';
    html += '</tr>';

    data.results.forEach(r => {
        const score = typeof r.score === 'number' ? Math.round(r.score * 100) + '%' : r.score || '-';
        html += '<tr style="border-bottom:1px solid var(--border)">';
        html += '<td style="padding:6px 8px;font-weight:500">' + escapeHtml(r.name || r.feature || '') + '</td>';
        html += '<td style="padding:6px 8px">' + escapeHtml(String(score)) + '</td>';
        html += '<td style="padding:6px 8px">' + escapeHtml(r.reason || '') + '</td>';
        html += '</tr>';
    });

    html += '</table>';

    if (data.answer) {
        html += '<div style="margin-top:8px">' + escapeHtml(data.answer) + '</div>';
    }

    return html;
}

function formatDiscoverResults(data) {
    let html = '';

    if (data.features && data.features.length > 0) {
        html += '<strong>Relevant Features:</strong>';
        html += '<table style="width:100%;border-collapse:collapse;font-size:0.85rem;margin:8px 0">';
        html += '<tr style="border-bottom:1px solid var(--border)">';
        html += '<th style="text-align:left;padding:6px 8px">Name</th>';
        html += '<th style="text-align:left;padding:6px 8px">Relevance</th>';
        html += '<th style="text-align:left;padding:6px 8px">Reason</th>';
        html += '</tr>';
        data.features.forEach(f => {
            const rel = typeof f.relevance === 'number' ? Math.round(f.relevance * 100) + '%' : f.relevance || '-';
            html += '<tr style="border-bottom:1px solid var(--border)">';
            html += '<td style="padding:6px 8px;font-weight:500">' + escapeHtml(f.name || '') + '</td>';
            html += '<td style="padding:6px 8px">' + escapeHtml(String(rel)) + '</td>';
            html += '<td style="padding:6px 8px">' + escapeHtml(f.reason || '') + '</td>';
            html += '</tr>';
        });
        html += '</table>';
    }

    if (data.suggestions && data.suggestions.length > 0) {
        html += '<strong>Suggestions:</strong>';
        html += '<table style="width:100%;border-collapse:collapse;font-size:0.85rem;margin:8px 0">';
        html += '<tr style="border-bottom:1px solid var(--border)">';
        html += '<th style="text-align:left;padding:6px 8px">Name</th>';
        html += '<th style="text-align:left;padding:6px 8px">Source</th>';
        html += '<th style="text-align:left;padding:6px 8px">Reason</th>';
        html += '</tr>';
        data.suggestions.forEach(s => {
            html += '<tr style="border-bottom:1px solid var(--border)">';
            html += '<td style="padding:6px 8px;font-weight:500">' + escapeHtml(s.name || '') + '</td>';
            html += '<td style="padding:6px 8px">' + escapeHtml(s.source || '') + '</td>';
            html += '<td style="padding:6px 8px">' + escapeHtml(s.reason || '') + '</td>';
            html += '</tr>';
        });
        html += '</table>';
    }

    if (data.summary) {
        html += '<div style="margin-top:8px"><strong>Summary:</strong> ' + escapeHtml(data.summary) + '</div>';
    }

    if (!html) {
        html = 'No discovery results found.';
    }

    return html;
}

function prefill(text) {
    chatInput.value = text;
    chatInput.focus();
}

function escapeHtml(str) {
    const div = document.createElement('div');
    div.textContent = str;
    return div.innerHTML;
}
