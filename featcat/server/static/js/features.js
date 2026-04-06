/* featcat Feature Browser */

let allFeatures = [];
let filteredFeatures = [];
let currentPage = 1;
let pageSize = 25;
let sortCol = 'name';
let sortDir = 'asc';
let selectedFeature = null;

let searchTimeout = null;

document.addEventListener('DOMContentLoaded', async () => {
    await loadFeatures();
    await loadSources();
    bindEvents();
});

async function loadFeatures(params = {}) {
    try {
        const data = await featcat.features.list(params);
        allFeatures = Array.isArray(data) ? data : (data.features || data.items || []);
        filteredFeatures = [...allFeatures];
        sortFeatures();
        renderTable();
        updateResultCount();
    } catch (err) {
        showToast('Failed to load features: ' + err.message, 'error');
    }
}

async function loadSources() {
    try {
        const data = await featcat.sources.list();
        const sources = Array.isArray(data) ? data : (data.sources || data.items || []);
        const select = document.getElementById('source-filter');
        sources.forEach(src => {
            const opt = document.createElement('option');
            const name = typeof src === 'string' ? src : (src.name || src.id || '');
            opt.value = name;
            opt.textContent = name;
            select.appendChild(opt);
        });
    } catch (err) {
        // Sources may not be available; ignore silently
    }
}

function bindEvents() {
    // Search with debounce
    document.getElementById('search-input').addEventListener('input', (e) => {
        clearTimeout(searchTimeout);
        searchTimeout = setTimeout(() => {
            const query = e.target.value.trim().toLowerCase();
            if (query === '') {
                filteredFeatures = [...allFeatures];
            } else {
                filteredFeatures = allFeatures.filter(f => {
                    const name = (f.name || '').toLowerCase();
                    const colName = (f.column_name || '').toLowerCase();
                    const tags = Array.isArray(f.tags) ? f.tags.join(' ').toLowerCase() : '';
                    return name.includes(query) || colName.includes(query) || tags.includes(query);
                });
            }
            currentPage = 1;
            sortFeatures();
            renderTable();
            updateResultCount();
        }, 300);
    });

    // Source filter
    document.getElementById('source-filter').addEventListener('change', async (e) => {
        const value = e.target.value;
        if (value === '') {
            filteredFeatures = [...allFeatures];
            sortFeatures();
            renderTable();
            updateResultCount();
        } else {
            try {
                const data = await featcat.features.list({ source: value });
                const features = Array.isArray(data) ? data : (data.features || data.items || []);
                filteredFeatures = features;
                currentPage = 1;
                sortFeatures();
                renderTable();
                updateResultCount();
            } catch (err) {
                showToast('Failed to filter by source: ' + err.message, 'error');
            }
        }
    });

    // Column sort
    document.querySelectorAll('#feature-table thead th[data-col]').forEach(th => {
        th.addEventListener('click', () => {
            const col = th.getAttribute('data-col');
            if (col === 'tags') return; // Tags not sortable
            if (sortCol === col) {
                sortDir = sortDir === 'asc' ? 'desc' : 'asc';
            } else {
                sortCol = col;
                sortDir = 'asc';
            }
            // Update header classes
            document.querySelectorAll('#feature-table thead th').forEach(h => h.classList.remove('sorted'));
            th.classList.add('sorted');
            th.querySelector('.sort-icon').innerHTML = sortDir === 'asc' ? '&#x25B2;' : '&#x25BC;';
            sortFeatures();
            renderTable();
        });
    });

    // Add modal open
    document.getElementById('add-source-btn').addEventListener('click', () => {
        document.getElementById('add-modal').classList.add('active');
    });

    // Add modal cancel
    document.getElementById('modal-cancel').addEventListener('click', () => {
        closeModal();
    });

    // Add modal overlay click
    document.getElementById('add-modal').addEventListener('click', (e) => {
        if (e.target === e.currentTarget) {
            closeModal();
        }
    });

    // Add modal submit
    document.getElementById('modal-submit').addEventListener('click', handleAddSource);
}

function sortFeatures() {
    filteredFeatures.sort((a, b) => {
        let valA, valB;
        if (sortCol === 'source') {
            valA = extractSource(a.name || '');
            valB = extractSource(b.name || '');
        } else if (sortCol === 'has_doc') {
            valA = a.has_doc ? 1 : 0;
            valB = b.has_doc ? 1 : 0;
        } else {
            valA = a[sortCol] || '';
            valB = b[sortCol] || '';
        }
        if (typeof valA === 'string') valA = valA.toLowerCase();
        if (typeof valB === 'string') valB = valB.toLowerCase();
        if (valA < valB) return sortDir === 'asc' ? -1 : 1;
        if (valA > valB) return sortDir === 'asc' ? 1 : -1;
        return 0;
    });
}

function extractSource(name) {
    const idx = name.indexOf('.');
    return idx > -1 ? name.substring(0, idx) : '';
}

function renderTable() {
    const tbody = document.querySelector('#feature-table tbody');
    const start = (currentPage - 1) * pageSize;
    const pageFeatures = filteredFeatures.slice(start, start + pageSize);

    if (pageFeatures.length === 0) {
        tbody.innerHTML = '<tr><td colspan="6" style="text-align:center;padding:40px;color:var(--text-secondary)">No features found</td></tr>';
        renderPagination();
        return;
    }

    tbody.innerHTML = pageFeatures.map(f => {
        const name = f.name || '';
        const source = f.source || extractSource(name);
        const dtype = f.dtype || f.data_type || '';
        const tags = Array.isArray(f.tags) ? f.tags : [];
        const hasDoc = f.has_doc || f.documented || false;
        const owner = f.owner || '';
        const isSelected = selectedFeature && selectedFeature.name === name;

        const tagPills = tags.map(t => `<span class="pill">${escapeHtml(t)}</span>`).join('');
        const docIcon = hasDoc
            ? '<span style="color:var(--success)" title="Documented">&#x2713;</span>'
            : '<span style="color:var(--text-secondary)" title="No docs">&#x2717;</span>';

        return `<tr data-name="${escapeHtml(name)}" class="${isSelected ? 'selected' : ''}" style="cursor:pointer">
            <td><strong style="color:var(--accent)">${escapeHtml(name)}</strong></td>
            <td>${escapeHtml(source)}</td>
            <td>${escapeHtml(dtype)}</td>
            <td>${tagPills}</td>
            <td>${docIcon}</td>
            <td>${escapeHtml(owner)}</td>
        </tr>`;
    }).join('');

    // Row click handlers
    tbody.querySelectorAll('tr[data-name]').forEach(row => {
        row.addEventListener('click', () => {
            const name = row.getAttribute('data-name');
            const feature = filteredFeatures.find(f => f.name === name);
            if (feature) {
                selectFeature(feature);
                // Update selected class
                tbody.querySelectorAll('tr').forEach(r => r.classList.remove('selected'));
                row.classList.add('selected');
            }
        });
    });

    renderPagination();
}

function renderPagination() {
    const container = document.getElementById('pagination');
    const totalPages = Math.max(1, Math.ceil(filteredFeatures.length / pageSize));

    if (totalPages <= 1) {
        container.innerHTML = '';
        return;
    }

    let html = '';
    html += `<button ${currentPage === 1 ? 'disabled' : ''} data-page="${currentPage - 1}">&laquo; Prev</button>`;

    const maxButtons = 7;
    let startPage = Math.max(1, currentPage - Math.floor(maxButtons / 2));
    let endPage = Math.min(totalPages, startPage + maxButtons - 1);
    if (endPage - startPage < maxButtons - 1) {
        startPage = Math.max(1, endPage - maxButtons + 1);
    }

    for (let i = startPage; i <= endPage; i++) {
        html += `<button class="${i === currentPage ? 'active' : ''}" data-page="${i}">${i}</button>`;
    }

    html += `<button ${currentPage === totalPages ? 'disabled' : ''} data-page="${currentPage + 1}">Next &raquo;</button>`;

    container.innerHTML = html;

    container.querySelectorAll('button[data-page]').forEach(btn => {
        btn.addEventListener('click', () => {
            const page = parseInt(btn.getAttribute('data-page'));
            if (page >= 1 && page <= totalPages) {
                currentPage = page;
                renderTable();
                window.scrollTo({ top: 0, behavior: 'smooth' });
            }
        });
    });
}

async function selectFeature(feature) {
    selectedFeature = feature;
    const panel = document.getElementById('detail-panel');
    const content = document.getElementById('detail-content');
    panel.classList.add('active');

    const name = feature.name || '';
    const dtype = feature.dtype || feature.data_type || '';
    const source = feature.source || extractSource(name);
    const createdAt = feature.created_at ? timeAgo(feature.created_at) : 'N/A';
    const tags = Array.isArray(feature.tags) ? feature.tags : [];

    const stats = feature.stats || feature.statistics || {};
    const mean = stats.mean != null ? Number(stats.mean).toFixed(4) : 'N/A';
    const std = stats.std != null ? Number(stats.std).toFixed(4) : 'N/A';
    const min = stats.min != null ? Number(stats.min).toFixed(4) : 'N/A';
    const max = stats.max != null ? Number(stats.max).toFixed(4) : 'N/A';
    const nullRatio = stats.null_ratio != null ? (Number(stats.null_ratio) * 100).toFixed(1) + '%' : 'N/A';

    const tagPills = tags.map(t => `<span class="pill">${escapeHtml(t)}</span>`).join('') || '<span class="text-secondary">No tags</span>';

    let docHtml = '<p class="text-secondary">Loading documentation...</p>';

    content.innerHTML = `
        <div style="display:flex;justify-content:space-between;align-items:flex-start;margin-bottom:16px">
            <div>
                <h2 style="margin:0 0 4px;color:var(--accent)">${escapeHtml(name)}</h2>
                <span class="text-secondary">${escapeHtml(dtype)} &middot; ${escapeHtml(source)} &middot; Created ${createdAt}</span>
            </div>
            <button class="btn btn-secondary btn-sm" onclick="closeDetailPanel()" title="Close">&times;</button>
        </div>
        <div class="stat-grid mb-2">
            <div class="stat-item"><div class="label">Mean</div><div class="value">${mean}</div></div>
            <div class="stat-item"><div class="label">Std</div><div class="value">${std}</div></div>
            <div class="stat-item"><div class="label">Min</div><div class="value">${min}</div></div>
            <div class="stat-item"><div class="label">Max</div><div class="value">${max}</div></div>
            <div class="stat-item"><div class="label">Null Ratio</div><div class="value">${nullRatio}</div></div>
        </div>
        <div id="detail-docs" class="mb-2">${docHtml}</div>
        <div class="mb-2">${tagPills}</div>
        <div style="display:flex;gap:8px">
            <button class="btn btn-primary btn-sm" id="btn-generate-doc">Generate Doc</button>
            <a href="/monitoring" class="btn btn-secondary btn-sm" style="text-decoration:none">Check Drift</a>
        </div>
    `;

    // Bind generate doc button
    document.getElementById('btn-generate-doc').addEventListener('click', () => generateDoc(name));

    // Fetch documentation
    try {
        const doc = await featcat.docs.get(name);
        const docsDiv = document.getElementById('detail-docs');
        if (doc && (doc.short_description || doc.long_description)) {
            let html = '';
            if (doc.short_description) {
                html += `<p style="margin:0 0 8px"><strong>${escapeHtml(doc.short_description)}</strong></p>`;
            }
            if (doc.long_description) {
                html += `<p style="margin:0;color:var(--text-secondary)">${escapeHtml(doc.long_description)}</p>`;
            }
            docsDiv.innerHTML = html;
        } else {
            docsDiv.innerHTML = '<p class="text-secondary">No documentation</p>';
        }
    } catch (err) {
        const docsDiv = document.getElementById('detail-docs');
        if (docsDiv) {
            docsDiv.innerHTML = '<p class="text-secondary">No documentation</p>';
        }
    }
}

async function generateDoc(featureName) {
    const btn = document.getElementById('btn-generate-doc');
    if (!btn) return;
    const originalText = btn.textContent;
    btn.textContent = 'Generating...';
    btn.disabled = true;

    try {
        await featcat.docs.generate({ feature_name: featureName });
        showToast('Documentation generated successfully', 'success');
        // Refresh the detail panel to show new docs
        if (selectedFeature && selectedFeature.name === featureName) {
            await selectFeature(selectedFeature);
        }
    } catch (err) {
        showToast('Failed to generate docs: ' + err.message, 'error');
    } finally {
        if (btn) {
            btn.textContent = originalText;
            btn.disabled = false;
        }
    }
}

function closeDetailPanel() {
    selectedFeature = null;
    document.getElementById('detail-panel').classList.remove('active');
    document.querySelectorAll('#feature-table tbody tr').forEach(r => r.classList.remove('selected'));
}

function updateResultCount() {
    const el = document.getElementById('result-count');
    const total = allFeatures.length;
    const showing = filteredFeatures.length;
    if (showing === total) {
        el.textContent = `${total} feature${total !== 1 ? 's' : ''}`;
    } else {
        el.textContent = `${showing} of ${total} features`;
    }
}

async function handleAddSource() {
    const path = document.getElementById('modal-path').value.trim();
    const name = document.getElementById('modal-name').value.trim();
    const description = document.getElementById('modal-description').value.trim();
    const owner = document.getElementById('modal-owner').value.trim();
    const tagsStr = document.getElementById('modal-tags').value.trim();

    if (!path) {
        showToast('Path is required', 'error');
        return;
    }

    const submitBtn = document.getElementById('modal-submit');
    submitBtn.textContent = 'Adding...';
    submitBtn.disabled = true;

    try {
        const payload = { path };
        if (name) payload.name = name;
        if (description) payload.description = description;
        if (owner) payload.owner = owner;
        if (tagsStr) payload.tags = tagsStr.split(',').map(t => t.trim()).filter(Boolean);

        const result = await featcat.sources.add(payload);
        const sourceName = name || (result && result.name) || path.split('/').pop();

        showToast('Source added, scanning...', 'success');
        await featcat.sources.scan(sourceName);
        showToast('Scan complete', 'success');

        closeModal();
        await loadFeatures();
        await loadSources();
    } catch (err) {
        showToast('Failed to add source: ' + err.message, 'error');
    } finally {
        submitBtn.textContent = 'Add';
        submitBtn.disabled = false;
    }
}

function closeModal() {
    document.getElementById('add-modal').classList.remove('active');
    document.getElementById('modal-path').value = '';
    document.getElementById('modal-name').value = '';
    document.getElementById('modal-description').value = '';
    document.getElementById('modal-owner').value = '';
    document.getElementById('modal-tags').value = '';
}

function escapeHtml(str) {
    const div = document.createElement('div');
    div.textContent = str;
    return div.innerHTML;
}
