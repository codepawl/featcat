/* featcat AI Chat */

const messages = document.getElementById('messages');
const chatInput = document.getElementById('chat-input');
const sendBtn = document.getElementById('send-btn');

/* --- Initialization --- */

document.addEventListener('DOMContentLoaded', () => {
    addMessage('ai', 'Welcome to featcat AI Chat! Ask anything about your features.');
    chatInput.focus();
});

chatInput.addEventListener('keydown', (e) => {
    if (e.key === 'Enter' && !e.shiftKey) {
        e.preventDefault();
        doSend();
    }
});

if (sendBtn) {
    sendBtn.addEventListener('click', doSend);
}

document.querySelectorAll('[data-query]').forEach(btn => {
    btn.addEventListener('click', () => {
        chatInput.value = btn.dataset.query;
        doSend();
    });
});

function doSend() {
    const query = chatInput.value;
    if (!query || !query.trim()) return;
    chatInput.value = '';
    setLoading(true);
    sendMessage(query.trim());
}

/* --- Message DOM --- */

function addMessage(role, content) {
    const wrapper = document.createElement('div');
    wrapper.className = `msg msg-${role}`;
    wrapper.innerHTML =
        '<div class="msg-avatar">' + (role === 'user' ? 'You' : 'AI') + '</div>' +
        '<div class="msg-body"><div class="msg-content"></div></div>';
    messages.appendChild(wrapper);
    scrollToBottom();

    const contentEl = wrapper.querySelector('.msg-content');
    if (content) {
        contentEl.textContent = content;
    }
    return contentEl;
}

function addThinkingBlock(parentEl) {
    const details = document.createElement('details');
    details.className = 'thinking-block';
    details.innerHTML =
        '<summary>' +
        '<span class="thinking-indicator"></span>' +
        'Reasoning...' +
        '</summary>' +
        '<div class="thinking-content"></div>';
    parentEl.appendChild(details);
    return details.querySelector('.thinking-content');
}

function scrollToBottom() {
    messages.scrollTop = messages.scrollHeight;
}

function setLoading(loading) {
    if (sendBtn) sendBtn.disabled = loading;
    if (chatInput) chatInput.disabled = loading;
}

/* --- Send & Route --- */

function sendMessage(query) {
    // Route slash commands
    if (query.startsWith('/discover ') || query.startsWith('discover: ')) {
        const useCase = query.replace(/^(\/discover |discover: )/, '');
        return handleDiscover(useCase);
    }
    if (query.startsWith('/monitor')) return handleMonitor();
    if (query.startsWith('/stats')) return handleStats();

    // Default: streaming AI query
    addMessage('user', query);
    handleStream(query);
}

/* --- Streaming Handler --- */

function handleStream(query) {
    const contentEl = addMessage('ai', '');
    let thinkingEl = null;
    let answerBuffer = '';
    let answerEl = null;
    let gotEvents = false;

    const source = featcat.ai.stream(query, {
        onThinkingStart() {
            gotEvents = true;
            thinkingEl = addThinkingBlock(contentEl);
            scrollToBottom();
        },
        onThinking(text) {
            gotEvents = true;
            if (thinkingEl) {
                thinkingEl.textContent += text;
                scrollToBottom();
            }
        },
        onThinkingEnd() {
            if (thinkingEl) {
                const details = thinkingEl.closest('details');
                details.querySelector('summary').innerHTML =
                    '<span class="thinking-indicator done"></span>' +
                    'Thought for a moment';
            }
            thinkingEl = null;
            scrollToBottom();
        },
        onToken(text) {
            gotEvents = true;
            answerBuffer += text;
            if (!answerEl) {
                answerEl = document.createElement('div');
                answerEl.className = 'answer';
                contentEl.appendChild(answerEl);
            }
            // Live markdown render
            try {
                answerEl.innerHTML = marked.parse(answerBuffer);
            } catch (e) {
                answerEl.textContent = answerBuffer;
            }
            scrollToBottom();
        },
        onResult(data) {
            gotEvents = true;
            const resultEl = document.createElement('div');
            resultEl.className = 'answer';
            contentEl.appendChild(resultEl);
            formatSearchResults(resultEl, data);
            scrollToBottom();
        },
        onError(err) {
            console.error('SSE error:', err);
            if (source) source.close();
            // Only fallback if we haven't received any useful events yet
            if (!gotEvents) {
                fallbackAsk(query, contentEl);
            } else {
                // Had partial data, just finish up
                finishStream(contentEl, answerBuffer, answerEl);
            }
        },
        onDone() {
            finishStream(contentEl, answerBuffer, answerEl);
        }
    });
}

function finishStream(contentEl, answerBuffer, answerEl) {
    // Final render of answer with markdown
    if (answerBuffer.trim() && answerEl) {
        renderAnswer(answerEl, answerBuffer.trim());
    }
    // If nothing was rendered at all, show a message
    if (!contentEl.querySelector('.answer') && !contentEl.querySelector('.thinking-block') && !contentEl.textContent.trim()) {
        contentEl.textContent = 'No response received.';
    }
    setLoading(false);
    chatInput.focus();
    scrollToBottom();
}

/* --- Rendering --- */

function renderAnswer(el, text) {
    // Try to parse as JSON search results
    try {
        const data = JSON.parse(text);
        if (data.results || data.existing_features || data.new_feature_suggestions) {
            formatSearchResults(el, data);
            return;
        }
    } catch (e) { /* not JSON, render as markdown */ }

    try {
        el.innerHTML = marked.parse(text);
    } catch (e) {
        el.textContent = text;
    }
}

function formatSearchResults(el, data) {
    var html = '';

    if (data.results && data.results.length > 0) {
        html += '<div class="results-table"><table>';
        html += '<thead><tr><th>Feature</th><th>Score</th><th>Reason</th></tr></thead><tbody>';
        data.results.forEach(function(r) {
            var score = typeof r.score === 'number' ?
                (r.score > 1 ? r.score + '%' : Math.round(r.score * 100) + '%') : (r.score || '-');
            html += '<tr>' +
                '<td><code>' + escapeHtml(r.feature || r.name || '') + '</code></td>' +
                '<td class="score">' + escapeHtml(String(score)) + '</td>' +
                '<td>' + escapeHtml(r.reason || '') + '</td>' +
                '</tr>';
        });
        html += '</tbody></table></div>';
    } else if (data.results && data.results.length === 0) {
        html += '<p class="no-results">No matching features found.</p>';
    }

    if (data.interpretation) {
        html += '<p class="interpretation">' + escapeHtml(data.interpretation) + '</p>';
    }
    if (data.follow_up) {
        html += '<p class="follow-up">Try: ' + escapeHtml(data.follow_up) + '</p>';
    }
    if (data.summary) {
        try { html += '<div class="summary">' + marked.parse(data.summary) + '</div>'; }
        catch (e) { html += '<div class="summary">' + escapeHtml(data.summary) + '</div>'; }
    }

    // Existing features (discovery)
    if (data.existing_features && data.existing_features.length > 0) {
        html += '<h4>Relevant features</h4><div class="results-table"><table>';
        html += '<thead><tr><th>Name</th><th>Relevance</th><th>Reason</th></tr></thead><tbody>';
        data.existing_features.forEach(function(f) {
            var rel = typeof f.relevance === 'number' ? Math.round(f.relevance * 100) + '%' : (f.relevance || '-');
            html += '<tr>' +
                '<td><code>' + escapeHtml(f.name || '') + '</code></td>' +
                '<td class="score">' + escapeHtml(String(rel)) + '</td>' +
                '<td>' + escapeHtml(f.reason || '') + '</td>' +
                '</tr>';
        });
        html += '</tbody></table></div>';
    }

    // New feature suggestions (discovery)
    if (data.new_feature_suggestions && data.new_feature_suggestions.length > 0) {
        html += '<h4>Suggested new features</h4><div class="suggestions">';
        data.new_feature_suggestions.forEach(function(s) {
            html += '<div class="suggestion-card">' +
                '<strong>' + escapeHtml(s.name || '') + '</strong>' +
                '<span class="source">from ' + escapeHtml(s.source || '') + '</span>' +
                '<p>' + escapeHtml(s.reason || '') + '</p>' +
                (s.column_expression ? '<code>' + escapeHtml(s.column_expression) + '</code>' : '') +
                '</div>';
        });
        html += '</div>';
    }

    el.innerHTML = html || '<p class="no-results">No results.</p>';
}

/* --- Fallback (non-streaming) --- */

async function fallbackAsk(query, el) {
    try {
        const res = await fetch('/api/ai/ask', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ query: query })
        });
        const data = await res.json();
        if (!res.ok) {
            el.innerHTML = '<div class="answer error">Error: ' + escapeHtml(data.detail || 'Request failed') + '</div>';
            return;
        }
        var div = document.createElement('div');
        div.className = 'answer';
        el.appendChild(div);
        formatSearchResults(div, data);
    } catch (err) {
        el.innerHTML = '<div class="answer error">Failed to get response: ' + escapeHtml(err.message) + '</div>';
    } finally {
        setLoading(false);
        chatInput.focus();
    }
}

/* --- Slash Commands --- */

async function handleDiscover(useCase) {
    addMessage('user', '/discover ' + useCase);
    var el = addMessage('ai', '');
    el.innerHTML = '<span class="loading">Analyzing catalog</span>';
    try {
        var data = await featcat.ai.discover(useCase);
        formatSearchResults(el, data);
    } catch (err) {
        el.innerHTML = '<div class="error">Discovery failed: ' + escapeHtml(err.message) + '</div>';
    } finally {
        setLoading(false);
        chatInput.focus();
        scrollToBottom();
    }
}

async function handleMonitor() {
    addMessage('user', '/monitor');
    var el = addMessage('ai', '');
    el.innerHTML = '<span class="loading">Running drift check</span>';
    try {
        var res = await fetch('/api/monitor/check');
        var data = await res.json();
        var html = '<p><strong>' + (data.healthy || 0) + '</strong> healthy, <strong>' + (data.warnings || 0) + '</strong> warnings, <strong>' + (data.critical || 0) + '</strong> critical</p>';
        if (data.details && data.details.length > 0) {
            html += '<div class="results-table"><table><thead><tr><th>Feature</th><th>Severity</th><th>PSI</th></tr></thead><tbody>';
            data.details.forEach(function(d) {
                html += '<tr><td>' + escapeHtml(d.feature || '') + '</td><td><span class="badge badge-' + (d.severity || '') + '">' + escapeHtml(d.severity || '') + '</span></td><td>' + (d.psi || '-') + '</td></tr>';
            });
            html += '</tbody></table></div>';
        }
        el.innerHTML = html;
    } catch (err) {
        el.innerHTML = '<div class="error">Monitor check failed: ' + escapeHtml(err.message) + '</div>';
    } finally {
        setLoading(false);
        chatInput.focus();
        scrollToBottom();
    }
}

async function handleStats() {
    addMessage('user', '/stats');
    var el = addMessage('ai', '');
    try {
        var s = await featcat.stats();
        el.innerHTML =
            '<div class="stats-grid">' +
            '<div class="stat"><span class="stat-value">' + (s.total_features || s.features || 0) + '</span><span class="stat-label">Features</span></div>' +
            '<div class="stat"><span class="stat-value">' + (s.sources || 0) + '</span><span class="stat-label">Sources</span></div>' +
            '<div class="stat"><span class="stat-value">' + (s.coverage ? Math.round(s.coverage) : 0) + '%</span><span class="stat-label">Doc coverage</span></div>' +
            '<div class="stat"><span class="stat-value">' + (s.documented || 0) + '/' + (s.total_features || s.features || 0) + '</span><span class="stat-label">Documented</span></div>' +
            '</div>';
    } catch (err) {
        el.innerHTML = '<div class="error">Stats failed: ' + escapeHtml(err.message) + '</div>';
    } finally {
        setLoading(false);
        chatInput.focus();
        scrollToBottom();
    }
}

/* --- Utilities --- */

function prefill(text) {
    chatInput.value = text;
    chatInput.focus();
}

function escapeHtml(str) {
    var div = document.createElement('div');
    div.textContent = str;
    return div.innerHTML;
}
