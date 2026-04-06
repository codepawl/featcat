/* featcat Dashboard */

let lastUpdated = null;
let updateTimerInterval = null;

document.addEventListener('DOMContentLoaded', () => {
    loadDashboard();
    setInterval(loadDashboard, 30000);

    updateTimerInterval = setInterval(updateLastUpdatedText, 1000);
});

function updateLastUpdatedText() {
    const el = document.getElementById('last-updated');
    if (!el || !lastUpdated) return;
    const seconds = Math.floor((Date.now() - lastUpdated) / 1000);
    el.textContent = `Last updated: ${seconds}s ago`;
}

async function loadDashboard() {
    const errorBanner = document.getElementById('error-banner');
    const metricCards = document.getElementById('metric-cards');
    const alertsSection = document.getElementById('alerts-section');
    const activitySection = document.getElementById('activity-section');
    const jobsSection = document.getElementById('jobs-section');

    try {
        const [stats, monitorData, jobStats, jobLogs] = await Promise.all([
            featcat.stats().catch(() => null),
            featcat.monitor.check().catch(() => null),
            featcat.jobs.stats().catch(() => null),
            featcat.jobs.logs({ limit: 10 }).catch(() => null),
        ]);

        errorBanner.classList.add('hidden');
        metricCards.classList.remove('hidden');
        alertsSection.classList.remove('hidden');
        activitySection.classList.remove('hidden');
        jobsSection.classList.remove('hidden');

        lastUpdated = Date.now();
        updateLastUpdatedText();

        renderMetricCards(stats, monitorData);
        renderAlerts(monitorData);
        renderActivity(jobLogs);
        renderJobsTable(jobStats);
    } catch (err) {
        errorBanner.classList.remove('hidden');
        metricCards.classList.add('hidden');
    }
}

function renderMetricCards(stats, monitorData) {
    const featureCount = stats ? (stats.features != null ? stats.features : 0) : 0;
    const totalFeatures = stats ? (stats.total_features != null ? stats.total_features : featureCount) : 0;
    const documented = stats ? (stats.documented != null ? stats.documented : 0) : 0;
    const sourcesCount = stats ? (stats.sources != null ? stats.sources : 0) : 0;

    const docPct = totalFeatures > 0 ? Math.round((documented / totalFeatures) * 100) : 0;

    const alerts = extractAlerts(monitorData);
    const alertCount = alerts.length;
    const hasCritical = alerts.some(a => (a.severity || '').toLowerCase() === 'critical');

    let alertColorClass = 'success';
    if (alertCount > 0) alertColorClass = 'warning';
    if (hasCritical) alertColorClass = 'danger';

    document.getElementById('metric-features').innerHTML =
        `<div class="label">Features</div>
         <div class="value">${featureCount}</div>`;

    document.getElementById('metric-docs').innerHTML =
        `<div class="label">Doc Coverage</div>
         <div class="value">${docPct}%</div>
         <div class="progress-bar"><div class="progress-fill" style="width:${docPct}%"></div></div>`;

    document.getElementById('metric-alerts').innerHTML =
        `<div class="label">Drift Alerts</div>
         <div class="value ${alertColorClass}">${alertCount}</div>`;

    document.getElementById('metric-sources').innerHTML =
        `<div class="label">Sources</div>
         <div class="value">${sourcesCount}</div>`;
}

function extractAlerts(monitorData) {
    if (!monitorData) return [];
    let details = [];
    if (Array.isArray(monitorData)) {
        details = monitorData;
    } else if (Array.isArray(monitorData.details)) {
        details = monitorData.details;
    } else if (Array.isArray(monitorData.results)) {
        details = monitorData.results;
    }
    return details.filter(d => d && (d.severity || '').toLowerCase() !== 'healthy');
}

function renderAlerts(monitorData) {
    const section = document.getElementById('alerts-section');
    const alerts = extractAlerts(monitorData);
    const display = alerts.slice(0, 5);

    let html = '<h3 style="margin-top:0">Recent Drift Alerts</h3>';

    if (display.length === 0) {
        html += '<p class="text-secondary">No drift alerts detected.</p>';
    } else {
        html += '<table class="data-table"><thead><tr><th>Severity</th><th>Feature</th><th>PSI</th></tr></thead><tbody>';
        for (const alert of display) {
            const sev = (alert.severity || 'warning').toLowerCase();
            const badgeClass = sev === 'critical' ? 'danger' : sev === 'warning' ? 'warning' : 'info';
            const featureName = alert.feature || alert.feature_name || alert.name || 'unknown';
            const psi = alert.psi != null ? Number(alert.psi).toFixed(3) : '-';
            html += `<tr>
                <td><span class="badge ${badgeClass}">${escapeHtml(sev)}</span></td>
                <td><a href="/monitoring">${escapeHtml(featureName)}</a></td>
                <td>${psi}</td>
            </tr>`;
        }
        html += '</tbody></table>';
        if (alerts.length > 5) {
            html += '<p class="mt-1"><a href="/monitoring">View all &rarr;</a></p>';
        }
    }

    section.innerHTML = html;
}

function renderActivity(jobLogs) {
    const section = document.getElementById('activity-section');
    const logs = Array.isArray(jobLogs) ? jobLogs : (jobLogs && Array.isArray(jobLogs.logs) ? jobLogs.logs : []);
    const display = logs.slice(0, 5);

    let html = '<h3 style="margin-top:0">Recent Activity</h3>';

    if (display.length === 0) {
        html += '<p class="text-secondary">No recent activity.</p>';
    } else {
        html += '<table class="data-table"><thead><tr><th>Status</th><th>Job</th><th>When</th></tr></thead><tbody>';
        for (const log of display) {
            const status = (log.status || 'unknown').toLowerCase();
            const badgeClass = status === 'success' ? 'success' : status === 'failed' ? 'danger' : status === 'running' ? 'info' : 'warning';
            const jobName = log.job_name || log.name || log.job || 'unknown';
            const triggeredBy = log.triggered_by ? ` (${escapeHtml(log.triggered_by)})` : '';
            const when = timeAgo(log.started_at || log.created_at || log.timestamp);
            html += `<tr>
                <td><span class="badge ${badgeClass}">${escapeHtml(status)}</span></td>
                <td>${escapeHtml(jobName)}${triggeredBy}</td>
                <td>${when}</td>
            </tr>`;
        }
        html += '</tbody></table>';
    }

    section.innerHTML = html;
}

function renderJobsTable(jobStats) {
    const section = document.getElementById('jobs-section');
    const jobs = Array.isArray(jobStats) ? jobStats : (jobStats && Array.isArray(jobStats.jobs) ? jobStats.jobs : []);

    let html = '<h3 style="margin-top:0">Scheduled Jobs</h3>';

    if (jobs.length === 0) {
        html += '<p class="text-secondary">No scheduled jobs configured.</p>';
    } else {
        html += '<table class="data-table"><thead><tr><th>Job</th><th>Cron</th><th>Runs</th><th>Last 7 Days</th><th>Last Status</th><th></th></tr></thead><tbody>';
        for (const job of jobs) {
            const name = job.name || job.job_name || 'unknown';
            const cron = job.cron || job.schedule || '-';
            const totalRuns = job.total_runs != null ? job.total_runs : (job.runs != null ? job.runs : 0);
            const lastStatus = (job.last_status || '-').toLowerCase();
            const badgeClass = lastStatus === 'success' ? 'success' : lastStatus === 'failed' ? 'danger' : lastStatus === 'running' ? 'info' : 'warning';
            const sparklineHtml = buildSparkline(job.sparkline || job.daily || []);
            const statusBadge = lastStatus !== '-' ? `<span class="badge ${badgeClass}">${escapeHtml(lastStatus)}</span>` : '-';

            html += `<tr>
                <td><strong>${escapeHtml(name)}</strong></td>
                <td><code>${escapeHtml(cron)}</code></td>
                <td>${totalRuns}</td>
                <td>${sparklineHtml}</td>
                <td>${statusBadge}</td>
                <td><button class="btn btn-sm btn-secondary" onclick="runJob('${escapeHtml(name)}')">Run Now</button></td>
            </tr>`;
        }
        html += '</tbody></table>';
    }

    section.innerHTML = html;
}

function buildSparkline(data) {
    if (!Array.isArray(data) || data.length === 0) {
        return '<span class="text-secondary">-</span>';
    }

    const bars = data.slice(-7);
    const maxVal = Math.max(...bars.map(b => {
        if (typeof b === 'number') return b;
        return (b.count || b.total || 0);
    }), 1);

    let html = '<span class="sparkline">';
    for (const bar of bars) {
        let count, status;
        if (typeof bar === 'number') {
            count = bar;
            status = 'success';
        } else {
            count = bar.count || bar.total || 0;
            status = (bar.status || 'success').toLowerCase();
        }

        const height = Math.max(2, Math.round((count / maxVal) * 18));
        let color = 'var(--success)';
        if (status === 'failed' || status === 'failure') color = 'var(--danger)';
        else if (status === 'warning' || status === 'partial') color = 'var(--warning)';

        html += `<span class="sparkline-bar" style="height:${height}px;background:${color}"></span>`;
    }
    html += '</span>';
    return html;
}

async function runJob(name) {
    try {
        await featcat.jobs.run(name);
        showToast(`Job "${name}" triggered successfully`);
        loadDashboard();
    } catch (err) {
        showToast(`Failed to run "${name}": ${err.message}`, 'error');
    }
}

function escapeHtml(str) {
    const div = document.createElement('div');
    div.textContent = str;
    return div.innerHTML;
}
