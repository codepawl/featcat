/* featcat Jobs Page */

let allJobs = [];
let allLogs = [];
let filteredLogs = [];
let statsData = {};
let statsChart = null;
let currentPage = 1;
const PAGE_SIZE = 50;
let editingJobName = null;

/* --- Cron Helper --- */

function cronToHuman(cron) {
    if (!cron) return 'No schedule';
    const parts = cron.trim().split(/\s+/);
    if (parts.length !== 5) return cron;

    const [minute, hour, dom, month, dow] = parts;
    const dayNames = ['Sunday', 'Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday'];

    // Every N minutes: */N * * * *
    const everyMin = minute.match(/^\*\/(\d+)$/);
    if (everyMin && hour === '*' && dom === '*' && month === '*' && dow === '*') {
        return `Every ${everyMin[1]} minutes`;
    }

    // Every hour: 0 * * * *
    if (minute === '0' && hour === '*' && dom === '*' && month === '*' && dow === '*') {
        return 'Every hour';
    }

    // Every N hours: 0 */N * * *
    const everyHr = hour.match(/^\*\/(\d+)$/);
    if (minute === '0' && everyHr && dom === '*' && month === '*' && dow === '*') {
        return `Every ${everyHr[1]} hours`;
    }

    // Weekly: 0 H * * D
    if (dom === '*' && month === '*' && dow !== '*' && !dow.includes('/') && !dow.includes(',')) {
        const dayIdx = parseInt(dow, 10);
        const dayName = dayNames[dayIdx] || dow;
        const h = hour.padStart(2, '0');
        const m = minute.padStart(2, '0');
        return `Weekly on ${dayName} at ${h}:${m}`;
    }

    // Daily: 0 H * * *
    if (dom === '*' && month === '*' && dow === '*' && !hour.includes('/') && !hour.includes('*')) {
        const h = hour.padStart(2, '0');
        const m = minute.padStart(2, '0');
        return `Daily at ${h}:${m}`;
    }

    return cron;
}

/* --- Load Data --- */

async function loadJobs() {
    document.getElementById('error-banner').classList.add('hidden');

    try {
        const [jobs, logs, stats] = await Promise.all([
            featcat.jobs.list(),
            featcat.jobs.logs({ limit: 500 }),
            featcat.jobs.stats(),
        ]);

        allJobs = jobs;
        allLogs = logs;
        statsData = stats;

        renderJobCards();
        populateJobFilter();
        applyFilters();
        renderStatsChart();
        document.getElementById('last-updated').textContent = 'Updated ' + new Date().toLocaleTimeString();
    } catch (err) {
        console.error('Failed to load jobs data:', err);
        document.getElementById('error-banner').classList.remove('hidden');
    }
}

/* --- Job Cards --- */

function renderJobCards() {
    const container = document.getElementById('job-cards');
    if (!allJobs.length) {
        container.innerHTML = '<div class="card" style="text-align:center;padding:40px;color:var(--text-secondary)">No jobs configured</div>';
        return;
    }

    container.innerHTML = allJobs.map(job => {
        const enabledClass = job.enabled ? 'active' : '';
        const statusBadge = job.enabled
            ? '<span class="badge success">Enabled</span>'
            : '<span class="badge warning">Disabled</span>';

        return `
        <div class="card">
            <div style="display:flex;justify-content:space-between;align-items:start;margin-bottom:8px">
                <div>
                    <strong style="font-size:1rem">${esc(job.job_name)}</strong>
                    ${statusBadge}
                </div>
                <div class="toggle ${enabledClass}" onclick="toggleJob('${esc(job.job_name)}', ${!job.enabled})" title="${job.enabled ? 'Disable' : 'Enable'}"></div>
            </div>
            ${job.description ? `<p style="margin:0 0 10px;font-size:0.85rem;color:var(--text-secondary)">${esc(job.description)}</p>` : ''}
            <div style="font-size:0.85rem;color:var(--text-secondary);margin-bottom:4px">
                Schedule: ${esc(cronToHuman(job.cron_expression))}
            </div>
            <div style="font-size:0.85rem;color:var(--text-secondary);margin-bottom:12px">
                Last run: ${timeAgo(job.last_run_at)}
            </div>
            <div style="display:flex;gap:8px;align-items:center">
                <button class="btn btn-sm btn-primary" onclick="runJob('${esc(job.job_name)}')">Run Now</button>
                <a href="#" style="font-size:0.85rem" onclick="openScheduleModal('${esc(job.job_name)}', '${esc(job.cron_expression || '')}');return false">Edit Schedule</a>
            </div>
        </div>`;
    }).join('');
}

function esc(str) {
    if (!str) return '';
    const div = document.createElement('div');
    div.textContent = str;
    return div.innerHTML;
}

/* --- Toggle Job --- */

async function toggleJob(name, enabled) {
    try {
        await featcat.jobs.update(name, { enabled });
        showToast(`${name} ${enabled ? 'enabled' : 'disabled'}`);
        const job = allJobs.find(j => j.job_name === name);
        if (job) job.enabled = enabled;
        renderJobCards();
    } catch (err) {
        showToast(`Failed to update ${name}: ${err.message}`, 'error');
    }
}

/* --- Run Job --- */

async function runJob(name) {
    try {
        await featcat.jobs.run(name);
        showToast(`${name} triggered`);
        // Refresh logs after a short delay to allow the job to start
        setTimeout(async () => {
            try {
                allLogs = await featcat.jobs.logs({ limit: 500 });
                applyFilters();
            } catch (_) {}
        }, 2000);
    } catch (err) {
        showToast(`Failed to run ${name}: ${err.message}`, 'error');
    }
}

/* --- Execution History --- */

function populateJobFilter() {
    const select = document.getElementById('filter-job');
    const current = select.value;
    // Keep the "All Jobs" option, clear the rest
    select.innerHTML = '<option value="">All Jobs</option>';
    const names = [...new Set(allJobs.map(j => j.job_name))];
    names.sort();
    names.forEach(name => {
        const opt = document.createElement('option');
        opt.value = name;
        opt.textContent = name;
        select.appendChild(opt);
    });
    select.value = current;
}

function applyFilters() {
    const jobFilter = document.getElementById('filter-job').value;
    const statusFilter = document.getElementById('filter-status').value;

    filteredLogs = allLogs.filter(log => {
        if (jobFilter && log.job_name !== jobFilter) return false;
        if (statusFilter && log.status !== statusFilter) return false;
        return true;
    });

    currentPage = 1;
    renderLogs();
    renderPagination();
}

function renderLogs() {
    const tbody = document.getElementById('logs-tbody');
    const start = (currentPage - 1) * PAGE_SIZE;
    const page = filteredLogs.slice(start, start + PAGE_SIZE);

    if (!page.length) {
        tbody.innerHTML = '<tr><td colspan="6" style="text-align:center;padding:24px;color:var(--text-secondary)">No execution logs found</td></tr>';
        return;
    }

    tbody.innerHTML = page.map(log => {
        const statusClass = log.status === 'success' ? 'success'
            : log.status === 'failed' ? 'danger'
            : log.status === 'warning' ? 'warning'
            : 'info';

        const started = log.started_at ? new Date(log.started_at).toLocaleString() : '-';
        const duration = log.duration_seconds != null ? `${log.duration_seconds.toFixed(1)}s` : '-';
        const summary = log.result_summary
            ? (log.result_summary.length > 60 ? log.result_summary.substring(0, 60) + '...' : log.result_summary)
            : '-';

        return `
        <tr class="log-row" onclick="toggleLogDetail(this)" style="cursor:pointer">
            <td>${esc(log.job_name)}</td>
            <td><span class="badge ${statusClass}">${esc(log.status)}</span></td>
            <td>${started}</td>
            <td>${duration}</td>
            <td>${esc(summary)}</td>
            <td>${esc(log.triggered_by || '-')}</td>
        </tr>
        <tr class="log-detail hidden">
            <td colspan="6" style="background:var(--bg);padding:12px 16px">
                <div style="margin-bottom:8px"><strong>Full Result:</strong></div>
                <pre style="margin:0;white-space:pre-wrap;font-size:0.8rem;background:var(--bg-surface);padding:10px;border-radius:var(--radius);max-height:300px;overflow:auto">${formatResultSummary(log.result_summary)}</pre>
                ${log.error_message ? `
                <div style="margin-top:10px;margin-bottom:4px"><strong style="color:var(--danger)">Error:</strong></div>
                <pre style="margin:0;white-space:pre-wrap;font-size:0.8rem;color:var(--danger);background:rgba(220,53,69,0.05);padding:10px;border-radius:var(--radius)">${esc(log.error_message)}</pre>
                ` : ''}
            </td>
        </tr>`;
    }).join('');
}

function formatResultSummary(summary) {
    if (!summary) return '-';
    try {
        const parsed = JSON.parse(summary);
        return esc(JSON.stringify(parsed, null, 2));
    } catch {
        return esc(summary);
    }
}

function toggleLogDetail(row) {
    const detail = row.nextElementSibling;
    if (detail && detail.classList.contains('log-detail')) {
        detail.classList.toggle('hidden');
    }
}

/* --- Pagination --- */

function renderPagination() {
    const container = document.getElementById('logs-pagination');
    const totalPages = Math.max(1, Math.ceil(filteredLogs.length / PAGE_SIZE));

    if (totalPages <= 1) {
        container.innerHTML = '';
        return;
    }

    let html = '';
    html += `<button ${currentPage === 1 ? 'disabled' : ''} onclick="goToPage(${currentPage - 1})">&laquo;</button>`;

    const start = Math.max(1, currentPage - 2);
    const end = Math.min(totalPages, currentPage + 2);

    if (start > 1) {
        html += `<button onclick="goToPage(1)">1</button>`;
        if (start > 2) html += `<button disabled>...</button>`;
    }

    for (let i = start; i <= end; i++) {
        html += `<button class="${i === currentPage ? 'active' : ''}" onclick="goToPage(${i})">${i}</button>`;
    }

    if (end < totalPages) {
        if (end < totalPages - 1) html += `<button disabled>...</button>`;
        html += `<button onclick="goToPage(${totalPages})">${totalPages}</button>`;
    }

    html += `<button ${currentPage === totalPages ? 'disabled' : ''} onclick="goToPage(${currentPage + 1})">&raquo;</button>`;

    container.innerHTML = html;
}

function goToPage(page) {
    const totalPages = Math.max(1, Math.ceil(filteredLogs.length / PAGE_SIZE));
    if (page < 1 || page > totalPages) return;
    currentPage = page;
    renderLogs();
    renderPagination();
}

/* --- Stats Chart --- */

function renderStatsChart() {
    const canvas = document.getElementById('stats-chart');
    if (!statsData || !statsData.jobs) return;

    // Aggregate sparkline data across all jobs for the last 14 days
    const dayMap = {};

    Object.values(statsData.jobs).forEach(jobStats => {
        if (!jobStats.sparkline) return;
        jobStats.sparkline.forEach(entry => {
            if (!dayMap[entry.date]) {
                dayMap[entry.date] = { success: 0, warning: 0, failed: 0 };
            }
            dayMap[entry.date].success += entry.success || 0;
            dayMap[entry.date].warning += entry.warning || 0;
            dayMap[entry.date].failed += entry.failed || 0;
        });
    });

    const dates = Object.keys(dayMap).sort().slice(-14);
    const successData = dates.map(d => dayMap[d].success);
    const warningData = dates.map(d => dayMap[d].warning);
    const failedData = dates.map(d => dayMap[d].failed);

    if (statsChart) {
        statsChart.destroy();
    }

    statsChart = new Chart(canvas, {
        type: 'bar',
        data: {
            labels: dates.map(d => {
                const dt = new Date(d);
                return dt.toLocaleDateString(undefined, { month: 'short', day: 'numeric' });
            }),
            datasets: [
                {
                    label: 'Success',
                    data: successData,
                    backgroundColor: 'rgba(29, 158, 117, 0.8)',
                    borderRadius: 2,
                },
                {
                    label: 'Warning',
                    data: warningData,
                    backgroundColor: 'rgba(240, 173, 78, 0.8)',
                    borderRadius: 2,
                },
                {
                    label: 'Failed',
                    data: failedData,
                    backgroundColor: 'rgba(220, 53, 69, 0.8)',
                    borderRadius: 2,
                },
            ],
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            plugins: {
                legend: {
                    position: 'bottom',
                    labels: {
                        usePointStyle: true,
                        padding: 16,
                    },
                },
            },
            scales: {
                x: {
                    stacked: true,
                    grid: { display: false },
                },
                y: {
                    stacked: true,
                    beginAtZero: true,
                    ticks: { stepSize: 1 },
                },
            },
        },
    });
}

/* --- Schedule Modal --- */

function openScheduleModal(jobName, currentCron) {
    editingJobName = jobName;
    document.getElementById('modal-job-name').textContent = jobName;
    document.getElementById('cron-input').value = currentCron || '';
    updateCronPreview();
    document.getElementById('schedule-modal').classList.add('active');
}

function closeScheduleModal() {
    document.getElementById('schedule-modal').classList.remove('active');
    editingJobName = null;
}

function setCronPreset(cron) {
    document.getElementById('cron-input').value = cron;
    updateCronPreview();
}

function updateCronPreview() {
    const input = document.getElementById('cron-input').value.trim();
    const preview = document.getElementById('cron-preview');
    if (!input) {
        preview.textContent = '';
        return;
    }
    preview.textContent = cronToHuman(input);
}

async function saveSchedule() {
    if (!editingJobName) return;
    const cron = document.getElementById('cron-input').value.trim();
    if (!cron) {
        showToast('Please enter a cron expression', 'warning');
        return;
    }

    const btn = document.getElementById('btn-save-schedule');
    btn.disabled = true;
    btn.textContent = 'Saving...';

    try {
        await featcat.jobs.update(editingJobName, { cron_expression: cron });
        showToast(`Schedule updated for ${editingJobName}`);
        closeScheduleModal();
        // Update local data
        const job = allJobs.find(j => j.job_name === editingJobName);
        if (job) job.cron_expression = cron;
        renderJobCards();
    } catch (err) {
        showToast(`Failed to save: ${err.message}`, 'error');
    } finally {
        btn.disabled = false;
        btn.textContent = 'Save';
    }
}

// Close modal on overlay click
document.getElementById('schedule-modal').addEventListener('click', function(e) {
    if (e.target === this) closeScheduleModal();
});

// Close modal on Escape
document.addEventListener('keydown', function(e) {
    if (e.key === 'Escape') closeScheduleModal();
});

/* --- Init --- */

document.addEventListener('DOMContentLoaded', loadJobs);
