/* featcat Monitoring Page */

let driftChart = null;
let currentRange = 7;
let autoRefreshTimer = null;
let lastCheckData = null;

// --- Initialization ---

document.addEventListener('DOMContentLoaded', () => {
    loadMonitoring();
    startAutoRefresh();
    document.addEventListener('visibilitychange', handleVisibility);
});

// --- Data Loading ---

async function loadMonitoring() {
    try {
        document.getElementById('error-banner').classList.add('hidden');
        const data = await featcat.monitor.check();
        lastCheckData = data;
        renderSummary(data);
        renderTable(data.details || []);
        renderChart(data.details || []);
        document.getElementById('last-check').textContent = 'Last check: just now';
    } catch (err) {
        console.error('Monitor check failed:', err);
        document.getElementById('error-banner').classList.remove('hidden');
        showToast('Failed to load monitoring data', 'error');
    }
}

// --- Summary Cards ---

function renderSummary(data) {
    const checked = data.checked || 0;

    const healthyCount = data.healthy || 0;
    const warningCount = data.warnings || 0;
    const criticalCount = data.critical || 0;

    const pct = (v) => checked > 0 ? Math.round((v / checked) * 100) : 0;

    setCardValue('card-healthy', healthyCount, `${pct(healthyCount)}%`, 'success');
    setCardValue('card-warning', warningCount, `${pct(warningCount)}%`, 'warning');
    setCardValue('card-critical', criticalCount, `${pct(criticalCount)}%`, 'danger');
}

function setCardValue(cardId, count, pctText, cls) {
    const card = document.getElementById(cardId);
    const valueEl = card.querySelector('.value');
    valueEl.classList.remove('skeleton', 'skeleton-text');
    valueEl.className = `value ${cls}`;
    valueEl.innerHTML = `${count} <span style="font-size:0.9rem;font-weight:400;color:var(--text-secondary)">${pctText}</span>`;
}

// --- Monitoring Table ---

function renderTable(details) {
    const tbody = document.getElementById('monitor-tbody');

    if (!details || details.length === 0) {
        tbody.innerHTML = '<tr><td colspan="5" style="text-align:center;padding:24px;color:var(--text-secondary)">No features checked yet</td></tr>';
        return;
    }

    const severityOrder = { critical: 0, warning: 1, healthy: 2 };
    const sorted = [...details].sort((a, b) => {
        const sa = severityOrder[a.severity] !== undefined ? severityOrder[a.severity] : 3;
        const sb = severityOrder[b.severity] !== undefined ? severityOrder[b.severity] : 3;
        return sa - sb;
    });

    tbody.innerHTML = sorted.map((item, idx) => {
        const sevClass = item.severity === 'critical' ? 'danger'
            : item.severity === 'warning' ? 'warning'
            : 'success';
        const sevLabel = item.severity || 'healthy';
        const issues = item.issues || [];
        const issueType = issues.length > 0 ? issues[0].message : '-';
        const psi = item.psi !== undefined && item.psi !== null ? Number(item.psi).toFixed(4) : '-';
        const delta = item.delta !== undefined && item.delta !== null ? Number(item.delta).toFixed(4) : '-';

        return `<tr class="monitor-row" data-idx="${idx}" onclick="toggleRow(this, ${idx})" style="cursor:pointer">
            <td>${escapeHtml(item.feature)}</td>
            <td><span class="badge ${sevClass}">${sevLabel}</span></td>
            <td>${escapeHtml(issueType)}</td>
            <td>${psi}</td>
            <td>${delta}</td>
        </tr>
        <tr class="monitor-detail hidden" id="detail-${idx}">
            <td colspan="5" style="padding:12px 20px;background:var(--bg-surface)">
                ${renderDetailContent(item)}
            </td>
        </tr>`;
    }).join('');
}

function renderDetailContent(item) {
    const issues = item.issues || [];
    let html = '<div style="font-size:0.85rem">';

    if (issues.length > 0) {
        html += '<strong>Issues:</strong><ul style="margin:4px 0 8px 16px;padding:0">';
        issues.forEach(iss => {
            html += `<li>${escapeHtml(iss.message)}</li>`;
        });
        html += '</ul>';
    } else {
        html += '<p style="color:var(--text-secondary)">No issues detected</p>';
    }

    if (item.analysis) {
        html += `<strong>AI Analysis:</strong><p style="margin:4px 0 0">${escapeHtml(item.analysis)}</p>`;
    }

    html += '</div>';
    return html;
}

function toggleRow(rowEl, idx) {
    const detailRow = document.getElementById(`detail-${idx}`);
    if (detailRow) {
        detailRow.classList.toggle('hidden');
        rowEl.classList.toggle('selected');
    }
}

function escapeHtml(str) {
    if (!str) return '';
    const div = document.createElement('div');
    div.textContent = str;
    return div.innerHTML;
}

// --- Drift Trend Chart ---

function renderChart(details) {
    const canvas = document.getElementById('drift-chart');
    const emptyMsg = document.getElementById('chart-empty');

    if (!details || details.length === 0) {
        canvas.style.display = 'none';
        emptyMsg.classList.remove('hidden');
        if (driftChart) { driftChart.destroy(); driftChart = null; }
        return;
    }

    // Group details by date if available, otherwise show single-point data
    const dateMap = {};
    details.forEach(item => {
        const date = item.date || item.checked_at || new Date().toISOString().slice(0, 10);
        if (!dateMap[date]) {
            dateMap[date] = { warnings: 0, critical: 0 };
        }
        if (item.severity === 'warning') dateMap[date].warnings++;
        if (item.severity === 'critical') dateMap[date].critical++;
    });

    const allDates = Object.keys(dateMap).sort();

    if (allDates.length <= 1) {
        // Only a single point -- generate labels for context
        const today = new Date().toISOString().slice(0, 10);
        const labels = generateDateLabels(currentRange);
        const warningsData = labels.map(d => d === today || d === allDates[0] ? (dateMap[allDates[0]] || { warnings: 0 }).warnings : 0);
        const criticalData = labels.map(d => d === today || d === allDates[0] ? (dateMap[allDates[0]] || { critical: 0 }).critical : 0);

        canvas.style.display = '';
        emptyMsg.classList.add('hidden');
        buildChart(labels, warningsData, criticalData);
        return;
    }

    // Filter by range
    const cutoff = new Date();
    cutoff.setDate(cutoff.getDate() - currentRange);
    const cutoffStr = cutoff.toISOString().slice(0, 10);

    const filtered = allDates.filter(d => d >= cutoffStr);

    if (filtered.length === 0) {
        canvas.style.display = 'none';
        emptyMsg.classList.remove('hidden');
        if (driftChart) { driftChart.destroy(); driftChart = null; }
        return;
    }

    canvas.style.display = '';
    emptyMsg.classList.add('hidden');

    const labels = filtered;
    const warningsData = labels.map(d => dateMap[d] ? dateMap[d].warnings : 0);
    const criticalData = labels.map(d => dateMap[d] ? dateMap[d].critical : 0);

    buildChart(labels, warningsData, criticalData);
}

function generateDateLabels(days) {
    const labels = [];
    const now = new Date();
    for (let i = days - 1; i >= 0; i--) {
        const d = new Date(now);
        d.setDate(d.getDate() - i);
        labels.push(d.toISOString().slice(0, 10));
    }
    return labels;
}

function buildChart(labels, warningsData, criticalData) {
    const style = getComputedStyle(document.documentElement);
    const warningColor = style.getPropertyValue('--warning').trim() || '#f0ad4e';
    const dangerColor = style.getPropertyValue('--danger').trim() || '#dc3545';

    if (driftChart) {
        driftChart.destroy();
    }

    const ctx = document.getElementById('drift-chart').getContext('2d');
    driftChart = new Chart(ctx, {
        type: 'line',
        data: {
            labels: labels,
            datasets: [
                {
                    label: 'Warnings',
                    data: warningsData,
                    borderColor: warningColor,
                    backgroundColor: hexToRgba(warningColor, 0.2),
                    fill: true,
                    tension: 0.3,
                    pointRadius: 3,
                },
                {
                    label: 'Critical',
                    data: criticalData,
                    borderColor: dangerColor,
                    backgroundColor: hexToRgba(dangerColor, 0.2),
                    fill: true,
                    tension: 0.3,
                    pointRadius: 3,
                },
            ],
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            interaction: {
                intersect: false,
                mode: 'index',
            },
            plugins: {
                legend: {
                    position: 'top',
                    labels: {
                        usePointStyle: true,
                        boxWidth: 8,
                    },
                },
                tooltip: {
                    callbacks: {
                        title: (items) => items[0].label,
                    },
                },
            },
            scales: {
                x: {
                    grid: { display: false },
                    ticks: {
                        maxTicksLimit: 10,
                        font: { size: 11 },
                    },
                },
                y: {
                    stacked: true,
                    beginAtZero: true,
                    ticks: {
                        stepSize: 1,
                        precision: 0,
                        font: { size: 11 },
                    },
                    grid: {
                        color: 'rgba(128,128,128,0.1)',
                    },
                },
            },
        },
    });
}

function hexToRgba(color, alpha) {
    // Handle both hex and named/rgb colors
    if (color.startsWith('#')) {
        const hex = color.replace('#', '');
        const r = parseInt(hex.substring(0, 2), 16);
        const g = parseInt(hex.substring(2, 4), 16);
        const b = parseInt(hex.substring(4, 6), 16);
        return `rgba(${r}, ${g}, ${b}, ${alpha})`;
    }
    // If already rgb/rgba, inject alpha
    if (color.startsWith('rgb')) {
        return color.replace(/rgba?\(/, 'rgba(').replace(/\)$/, `, ${alpha})`).replace(/,\s*[\d.]+,\s*[\d.]+\)$/, `, ${alpha})`);
    }
    return color;
}

function setRange(days) {
    currentRange = days;
    document.getElementById('btn-7d').className = days === 7 ? 'btn btn-sm btn-primary' : 'btn btn-sm btn-secondary';
    document.getElementById('btn-30d').className = days === 30 ? 'btn btn-sm btn-primary' : 'btn btn-sm btn-secondary';
    if (lastCheckData) {
        renderChart(lastCheckData.details || []);
    }
}

// --- Actions ---

async function runCheck() {
    const btn = document.getElementById('btn-run-check');
    btn.disabled = true;
    btn.textContent = 'Checking...';
    try {
        const data = await featcat.monitor.check();
        lastCheckData = data;
        renderSummary(data);
        renderTable(data.details || []);
        renderChart(data.details || []);
        document.getElementById('last-check').textContent = 'Last check: just now';
        showToast('Monitoring check complete');
    } catch (err) {
        console.error('Run check failed:', err);
        showToast('Check failed: ' + err.message, 'error');
    } finally {
        btn.disabled = false;
        btn.textContent = 'Run Check Now';
    }
}

function openBaselineModal() {
    document.getElementById('baseline-modal').classList.add('active');
}

function closeBaselineModal() {
    document.getElementById('baseline-modal').classList.remove('active');
}

async function confirmBaseline() {
    const btn = document.getElementById('btn-confirm-baseline');
    btn.disabled = true;
    btn.textContent = 'Computing...';
    try {
        await featcat.monitor.baseline();
        showToast('Baseline refreshed successfully');
        closeBaselineModal();
        await loadMonitoring();
    } catch (err) {
        console.error('Baseline refresh failed:', err);
        showToast('Baseline refresh failed: ' + err.message, 'error');
    } finally {
        btn.disabled = false;
        btn.textContent = 'Confirm';
    }
}

async function exportReport() {
    const btn = document.getElementById('btn-export');
    btn.disabled = true;
    btn.textContent = 'Generating...';
    try {
        const report = await featcat.monitor.report();
        const markdown = buildReportMarkdown(report);
        const blob = new Blob([markdown], { type: 'text/markdown;charset=utf-8' });
        const url = URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = url;
        a.download = `featcat-monitoring-report-${new Date().toISOString().slice(0, 10)}.md`;
        document.body.appendChild(a);
        a.click();
        document.body.removeChild(a);
        URL.revokeObjectURL(url);
        showToast('Report exported');
    } catch (err) {
        console.error('Export failed:', err);
        showToast('Export failed: ' + err.message, 'error');
    } finally {
        btn.disabled = false;
        btn.textContent = 'Export Report';
    }
}

function buildReportMarkdown(report) {
    let md = `# featcat Monitoring Report\n\n`;
    md += `**Generated:** ${new Date().toISOString()}\n\n`;

    if (report.checked !== undefined) {
        md += `## Summary\n\n`;
        md += `| Metric | Value |\n|--------|-------|\n`;
        md += `| Checked | ${report.checked} |\n`;
        md += `| Healthy | ${report.healthy || 0} |\n`;
        md += `| Warnings | ${report.warnings || 0} |\n`;
        md += `| Critical | ${report.critical || 0} |\n\n`;
    }

    const details = report.details || [];
    if (details.length > 0) {
        md += `## Feature Details\n\n`;
        md += `| Feature | Severity | PSI | Issues |\n|---------|----------|-----|--------|\n`;
        details.forEach(item => {
            const issues = (item.issues || []).map(i => i.message).join('; ') || '-';
            const psi = item.psi !== undefined && item.psi !== null ? Number(item.psi).toFixed(4) : '-';
            md += `| ${item.feature} | ${item.severity} | ${psi} | ${issues} |\n`;
        });
        md += '\n';
    }

    return md;
}

// --- Auto-Refresh ---

function startAutoRefresh() {
    stopAutoRefresh();
    autoRefreshTimer = setInterval(() => {
        if (!document.hidden) {
            loadMonitoring();
        }
    }, 60000);
}

function stopAutoRefresh() {
    if (autoRefreshTimer) {
        clearInterval(autoRefreshTimer);
        autoRefreshTimer = null;
    }
}

function handleVisibility() {
    if (document.hidden) {
        stopAutoRefresh();
    } else {
        loadMonitoring();
        startAutoRefresh();
    }
}
