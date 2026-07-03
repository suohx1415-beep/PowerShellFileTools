/**
 * PowerShellFileTools - Frontend Application Logic
 * Handles UI interactions, drag/drop, modals, and communication with Python backend via pywebview
 */

// ===== Global State =====
let currentFilePath = '';
let currentFileName = '';
let pendingAction = null;
let pendingPids = null;
let countdownTimer = null;

// ===== Initialization =====
document.addEventListener('DOMContentLoaded', async () => {
    setupDragAndDrop();

    if (window.pywebview) {
        window.pywebview.addEventListener('loaded', init);
    } else {
        window.addEventListener('pywebviewready', init);
    }
});

async function init() {
    try {
        const info = await window.pywebview.api.get_file_info();
        updateFileInfo(info);

        const action = await window.pywebview.api.get_action();
        if (info.has_file && action === 'shred') {
            document.title = '粉碎文件 - PowerShellFileTools';
            setTimeout(() => handleShred(), 400);
        } else if (info.has_file && action === 'unlock') {
            document.title = '解除占用 - PowerShellFileTools';
            setTimeout(() => handleUnlock(), 400);
        } else {
            document.title = 'PowerShellFileTools';
        }
    } catch (e) {
        console.error('Failed to initialize:', e);
        showEmptyState('初始化失败');
    }
}

function updateFileInfo(info) {
    const hasFile = Boolean(info && info.has_file && info.file_path);
    const dropZone = document.getElementById('dropZone');
    const fileInfoCard = document.getElementById('fileInfoCard');
    const actionButtons = document.querySelector('.action-buttons');

    if (!hasFile) {
        currentFilePath = '';
        currentFileName = '';
        dropZone?.classList.remove('is-hidden');
        fileInfoCard?.classList.add('is-hidden');
        actionButtons?.classList.add('is-hidden');
        return;
    }

    currentFilePath = info.file_path || '';
    currentFileName = info.name || '未知文件';

    dropZone?.classList.add('is-hidden');
    fileInfoCard?.classList.remove('is-hidden');
    actionButtons?.classList.remove('is-hidden');

    document.getElementById('fileName').textContent = currentFileName;
    document.getElementById('fileSize').textContent = info.size || '--';
    document.getElementById('fileType').textContent = info.type || '--';
    document.getElementById('filePath').textContent = info.directory || '--';

    const statusDot = document.querySelector('.status-dot');
    const statusText = document.querySelector('.status-text');
    if (info.exists) {
        statusDot.className = 'status-dot';
        statusText.textContent = '就绪';
    } else {
        statusDot.className = 'status-dot error';
        statusText.textContent = '文件不存在';
    }

    const shredTitle = document.querySelector('.shred-btn .btn-title');
    if (shredTitle) {
        shredTitle.textContent = info.is_directory ? '粉碎文件夹' : '粉碎文件';
    }

    const fileIconWrapper = document.getElementById('fileIconWrapper');
    if (fileIconWrapper) {
        fileIconWrapper.innerHTML = info.is_directory ? folderIconSvg() : fileIconSvg();
    }
}

function showEmptyState(statusText = '等待文件') {
    updateFileInfo({ has_file: false });
    const status = document.querySelector('.status-text');
    if (status) status.textContent = statusText;
}

// ===== Drag And Drop =====
function setupDragAndDrop() {
    const dropZone = document.getElementById('dropZone');
    if (!dropZone) return;

    ['dragenter', 'dragover', 'dragleave', 'drop'].forEach(eventName => {
        document.addEventListener(eventName, event => {
            event.preventDefault();
            event.stopPropagation();
        });
    });

    ['dragenter', 'dragover'].forEach(eventName => {
        document.addEventListener(eventName, () => dropZone.classList.add('is-dragover'));
    });

    ['dragleave', 'drop'].forEach(eventName => {
        document.addEventListener(eventName, () => dropZone.classList.remove('is-dragover'));
    });

    document.addEventListener('drop', handleDrop);
}

async function handleDrop(event) {
    const path = getDroppedFilePath(event);
    if (path) {
        await setTargetPath(path, '文件已识别，可以执行操作');
        return;
    }

    const entries = getDroppedEntries(event);
    if (entries.length > 0) {
        await resolveDroppedEntries(entries);
        return;
    }

    showToast('当前 WebView 没有暴露完整路径，也没有可解析的文件信息', 'info');
    pulseDropZone();
}

async function resolveDroppedEntries(entries) {
    showLoading('正在还原拖放路径...');
    try {
        const result = await window.pywebview.api.resolve_drop_entries(entries);
        hideLoading();

        if (!result.success) {
            showToast(result.message, 'error');
            pulseDropZone();
            return;
        }

        updateFileInfo(result.info);
        showToast('拖放目标已识别', 'success');
    } catch (e) {
        hideLoading();
        showToast('拖放解析失败: ' + e.message, 'error');
    }
}

async function setTargetPath(path, successMessage) {
    showLoading('正在识别文件...');
    try {
        const result = await window.pywebview.api.set_file(path);
        hideLoading();

        if (!result.success) {
            showToast(result.message, 'error');
            return;
        }

        updateFileInfo(result.info);
        showToast(successMessage, 'success');
    } catch (e) {
        hideLoading();
        showToast('识别失败: ' + e.message, 'error');
    }
}

function pulseDropZone() {
    const dropZone = document.getElementById('dropZone');
    if (!dropZone) return;
    dropZone.classList.remove('needs-picker');
    dropZone.offsetHeight;
    dropZone.classList.add('needs-picker');
}

function getDroppedEntries(event) {
    const transfer = event.dataTransfer;
    if (!transfer) return [];

    const entries = [];
    const files = Array.from(transfer.files || []);
    const items = Array.from(transfer.items || []);

    files.forEach((file, index) => {
        const entry = {
            index,
            name: file.name || '',
            size: typeof file.size === 'number' ? file.size : null,
            type: file.type || '',
            lastModified: file.lastModified || null,
            path: file.path || file.mozFullPath || file.msPath || '',
            webkitRelativePath: file.webkitRelativePath || '',
            isFile: true,
            isDirectory: false,
            fullPath: '',
        };

        const item = items[index];
        if (item && item.webkitGetAsEntry) {
            try {
                const webkitEntry = item.webkitGetAsEntry();
                if (webkitEntry) {
                    entry.fullPath = webkitEntry.fullPath || '';
                    entry.isFile = Boolean(webkitEntry.isFile);
                    entry.isDirectory = Boolean(webkitEntry.isDirectory);
                }
            } catch (_) {
                // Ignore unavailable Chromium entry metadata.
            }
        }

        entries.push(entry);
    });

    return entries.filter(entry => entry.name);
}

function getDroppedFilePath(event) {
    const transfer = event.dataTransfer;
    if (!transfer) return '';

    if (transfer.files && transfer.files.length > 0) {
        const file = transfer.files[0];
        const directPath = file.path || file.mozFullPath || file.msPath || '';
        if (directPath) return normalizeDroppedPath(directPath);
    }

    const dataTypes = ['text/uri-list', 'text/plain', 'DownloadURL', 'text/html'];
    for (const type of dataTypes) {
        const raw = transfer.getData(type);
        const parsed = extractPathFromDropData(raw);
        if (parsed) return normalizeDroppedPath(parsed);
    }

    if (transfer.items && transfer.items.length > 0) {
        for (const item of transfer.items) {
            if (item.kind === 'file') {
                const file = item.getAsFile();
                const itemPath = file?.path || file?.mozFullPath || file?.msPath || '';
                if (itemPath) return normalizeDroppedPath(itemPath);
            }
        }
    }

    return '';
}

function extractPathFromDropData(raw) {
    if (!raw) return '';

    const lines = raw.split(/\r?\n/).map(line => line.trim()).filter(Boolean);
    for (const line of lines) {
        if (line.startsWith('#')) continue;

        if (line.startsWith('file:///')) return line;

        // DownloadURL format: mime:name:file:///C:/path/file.ext
        const fileUrlIndex = line.indexOf('file:///');
        if (fileUrlIndex >= 0) return line.slice(fileUrlIndex);

        const htmlMatch = line.match(/file:\/\/\/[^\"'<>\s]+/i);
        if (htmlMatch) return htmlMatch[0];

        if (/^[a-zA-Z]:[\\/]/.test(line) || line.startsWith('\\\\')) return line;
    }

    return '';
}

function normalizeDroppedPath(path) {
    if (!path) return '';
    let value = String(path).trim().replace(/^\"|\"$/g, '');

    if (value.startsWith('file:///')) {
        try {
            value = decodeURIComponent(value);
        } catch (_) {
            // Keep original value when decoding fails.
        }
        value = value.replace(/^file:\/\/\//i, '');
        if (/^[a-zA-Z]:/.test(value)) return value.replace(/\//g, '\\');
        if (value.startsWith('/') && /^[a-zA-Z]:/.test(value.slice(1))) {
            return value.slice(1).replace(/\//g, '\\');
        }
        return value.replace(/\//g, '\\');
    }

    return value;
}

// ===== Shred Action =====
async function handleShred() {
    if (!currentFilePath) {
        showToast('请先拖入文件或文件夹', 'error');
        return;
    }

    pendingAction = 'shred';

    showModal({
        title: '确认粉碎文件',
        message: '此操作将对目标进行三次安全覆写后永久删除，数据将无法恢复。',
        danger: true,
        confirmText: '确认粉碎',
        showProcessList: false
    });
}

async function executeShred() {
    showLoading('正在粉碎文件...');

    try {
        const result = await window.pywebview.api.shred_file(currentFilePath);
        hideLoading();

        if (result.success) {
            currentFilePath = '';
            currentFileName = '';
            showSuccessModal(result.message);
        } else {
            showToast(result.message, 'error');
        }
    } catch (e) {
        hideLoading();
        showToast('粉碎失败: ' + e.message, 'error');
    }
}

// ===== Unlock Action =====
async function handleUnlock() {
    if (!currentFilePath) {
        showToast('请先拖入文件或文件夹', 'error');
        return;
    }

    showLoading('正在检测占用进程...');

    try {
        const result = await window.pywebview.api.find_locking_processes(currentFilePath);
        hideLoading();

        if (!result.success) {
            showToast(result.message, 'error');
            return;
        }

        if (result.processes.length === 0) {
            showToast('没有进程占用此文件', 'info');
            return;
        }

        pendingAction = 'unlock';
        pendingPids = result.processes.map(p => p.pid);
        showUnlockModal(result.processes);

    } catch (e) {
        hideLoading();
        showToast('检测失败: ' + e.message, 'error');
    }
}

async function executeUnlock(pids = pendingPids) {
    if (!pids || pids.length === 0) {
        showToast('没有需要终止的进程', 'info');
        return;
    }

    showLoading('正在终止占用进程...');

    try {
        const result = await window.pywebview.api.kill_processes(pids);
        hideLoading();

        if (result.success) {
            showSuccessModal(result.message);
        } else {
            const succeeded = result.results.filter(r => r.success).length;
            if (succeeded > 0) {
                showSuccessModal(`${result.message}\n部分进程可能需要管理员权限`);
            } else {
                showToast(result.message, 'error');
            }
        }
    } catch (e) {
        hideLoading();
        showToast('操作失败: ' + e.message, 'error');
    }
}

// ===== Modal Helpers =====
function showModal({ title, message, danger = false, confirmText = '确认执行', showProcessList = false }) {
    const modal = document.getElementById('confirmModal');
    const header = document.getElementById('modalHeader');
    const titleEl = document.getElementById('modalTitle');
    const messageEl = document.getElementById('modalMessage');
    const confirmBtn = document.getElementById('modalConfirmBtn');
    const processList = document.getElementById('processList');
    const targetBadge = document.getElementById('targetFileBadge');
    const targetName = document.getElementById('targetFileName');

    titleEl.textContent = title;
    messageEl.textContent = message;
    confirmBtn.textContent = confirmText;
    processList.style.display = showProcessList ? 'block' : 'none';

    targetName.textContent = currentFileName || '未选择文件';
    targetBadge.style.display = 'inline-flex';

    header.className = 'modal-header' + (danger ? ' danger' : '');

    if (danger) {
        confirmBtn.style.background = '';
        confirmBtn.style.boxShadow = '';
    } else {
        confirmBtn.style.background = 'var(--accent-gradient)';
        confirmBtn.style.boxShadow = '0 2px 12px rgba(102, 126, 234, 0.3)';
    }

    modal.style.display = 'flex';
}

function showUnlockModal(processes) {
    const modal = document.getElementById('confirmModal');
    const header = document.getElementById('modalHeader');
    const titleEl = document.getElementById('modalTitle');
    const messageEl = document.getElementById('modalMessage');
    const confirmBtn = document.getElementById('modalConfirmBtn');
    const processList = document.getElementById('processList');
    const processListContent = document.getElementById('processListContent');
    const targetBadge = document.getElementById('targetFileBadge');
    const targetName = document.getElementById('targetFileName');

    titleEl.textContent = '解除文件占用';
    messageEl.textContent = `检测到 ${processes.length} 个进程正在占用此文件：`;
    confirmBtn.textContent = '终止全部进程';

    targetName.textContent = currentFileName || '未选择文件';
    targetBadge.style.display = 'inline-flex';

    header.className = 'modal-header';
    confirmBtn.style.background = 'var(--accent-gradient)';
    confirmBtn.style.boxShadow = '0 2px 12px rgba(102, 126, 234, 0.3)';

    processListContent.innerHTML = processes.map(p => `
        <div class="process-item">
            <div class="process-item-info">
                <div class="process-dot"></div>
                <span class="process-name">${escapeHtml(p.name)}</span>
            </div>
            <span class="process-pid">PID ${p.pid}</span>
        </div>
    `).join('');

    processList.style.display = 'block';
    modal.style.display = 'flex';
}

function closeModal() {
    document.getElementById('confirmModal').style.display = 'none';
    pendingAction = null;
    pendingPids = null;
}

function confirmAction() {
    const action = pendingAction;
    const pids = pendingPids ? [...pendingPids] : [];
    closeModal();

    if (action === 'shred') {
        executeShred();
    } else if (action === 'unlock') {
        executeUnlock(pids);
    }
}

function showSuccessModal(message) {
    document.getElementById('successMessage').textContent = message;
    document.getElementById('countdownNum').textContent = '3';
    document.getElementById('successModal').style.display = 'flex';

    const fill = document.getElementById('countdownFill');
    if (fill) {
        fill.style.animation = 'none';
        fill.offsetHeight;
        fill.style.animation = 'countdownShrink 3s linear forwards';
    }

    let seconds = 3;
    if (countdownTimer) clearInterval(countdownTimer);

    countdownTimer = setInterval(() => {
        seconds--;
        document.getElementById('countdownNum').textContent = seconds;
        if (seconds <= 0) {
            clearInterval(countdownTimer);
            closeSuccess();
        }
    }, 1000);
}

function closeSuccess() {
    if (countdownTimer) {
        clearInterval(countdownTimer);
        countdownTimer = null;
    }
    document.getElementById('successModal').style.display = 'none';

    if (currentFilePath) {
        window.pywebview.api.close_window();
    } else {
        showEmptyState();
    }
}

// ===== Loading =====
function showLoading(text = '处理中...') {
    document.getElementById('loadingText').textContent = text;
    document.getElementById('loadingOverlay').style.display = 'flex';
}

function hideLoading() {
    document.getElementById('loadingOverlay').style.display = 'none';
}

// ===== Toast Notifications =====
function showToast(message, type = 'info') {
    const container = document.getElementById('toastContainer');
    const toast = document.createElement('div');
    toast.className = `toast ${type}`;
    toast.textContent = message;
    container.appendChild(toast);

    setTimeout(() => {
        toast.style.animation = 'toastOut 0.3s ease forwards';
        setTimeout(() => toast.remove(), 300);
    }, 3500);
}

// ===== Icons =====
function fileIconSvg() {
    return `
        <svg width="40" height="40" viewBox="0 0 24 24" fill="none">
            <path d="M14 2H6a2 2 0 00-2 2v16a2 2 0 002 2h12a2 2 0 002-2V8l-6-6z" stroke="currentColor" stroke-width="1.2" fill="none" opacity="0.8"/>
            <path d="M14 2v6h6" stroke="currentColor" stroke-width="1.2" fill="none" opacity="0.8"/>
        </svg>`;
}

function folderIconSvg() {
    return `
        <svg width="40" height="40" viewBox="0 0 24 24" fill="none">
            <path d="M22 19a2 2 0 01-2 2H4a2 2 0 01-2-2V5a2 2 0 012-2h5l2 3h9a2 2 0 012 2v11z" stroke="currentColor" stroke-width="1.2" fill="none" opacity="0.8"/>
        </svg>`;
}

// ===== Utility =====
function escapeHtml(text) {
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
}
