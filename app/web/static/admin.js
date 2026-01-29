/**
 * Superadmin Panel JavaScript
 */

// Global state
let currentToken = localStorage.getItem('token');
let selectedAdminChatId = null;
let currentAdminChatSettings = null;
let allChats = [];

// Check authentication on load
document.addEventListener('DOMContentLoaded', async () => {
    if (!currentToken) {
        window.location.href = '/login';
        return;
    }

    // Get current user info
    try {
        const response = await fetch('/api/auth/me', {
            headers: { 'Authorization': `Bearer ${currentToken}` }
        });
        if (response.ok) {
            const user = await response.json();
            if (!user.is_superadmin) {
                showAlert('Доступ запрещен. Требуются права суперадмина.', 'danger');
                setTimeout(() => window.location.href = '/', 2000);
                return;
            }
            document.getElementById('userName').textContent = user.username;
            document.getElementById('userAvatar').textContent = user.username.charAt(0).toUpperCase();
        } else if (response.status === 401) {
            logout();
            return;
        }
    } catch (error) {
        console.error('Error loading user info:', error);
        logout();
        return;
    }

    // Load data
    loadAllChats();
    loadFeedback();
    loadUsersStats();
    loadSkillPrompts();
});

// ========== API Functions ==========

async function apiCall(endpoint, options = {}) {
    const headers = {
        'Authorization': `Bearer ${currentToken}`,
        'Content-Type': 'application/json',
        ...options.headers
    };

    const response = await fetch(endpoint, { ...options, headers });

    if (response.status === 401) {
        logout();
        throw new Error('Unauthorized');
    }

    return response;
}

// ========== All Chats ==========

async function loadAllChats() {
    try {
        const response = await apiCall('/api/chats');

        if (!response.ok) {
            throw new Error('Failed to load chats');
        }

        const data = await response.json();
        allChats = data;

        const select = document.getElementById('adminChatSelect');
        select.innerHTML = '<option value="">Выберите чат...</option>';

        allChats.forEach(chat => {
            const option = `<option value="${chat.chat_id}">${escapeHtml(chat.title)} (${chat.chat_id})</option>`;
            select.innerHTML += option;
        });

    } catch (error) {
        console.error('Error loading all chats:', error);
        showAlert('Ошибка загрузки списка чатов', 'danger');
    }
}

async function loadSelectedChatSettings() {
    const chatId = document.getElementById('adminChatSelect').value;

    if (!chatId) {
        showAlert('Выберите чат', 'warning');
        return;
    }

    selectedAdminChatId = parseInt(chatId);

    try {
        const response = await apiCall(`/api/chats/${chatId}/settings`);

        if (!response.ok) {
            throw new Error('Failed to load chat settings');
        }

        const settings = await response.json();
        currentAdminChatSettings = settings;

        // Show settings content
        document.getElementById('adminChatSettingsContent').style.display = 'block';

        // Populate skills toggles
        populateAdminSkills(settings.enabled_skills || []);

        // Populate additional settings
        document.getElementById('adminSettingLanguage').value = settings.language || 'ru';
        document.getElementById('adminSettingSummaryTime').value = settings.summary_time_local || '16:00';
        document.getElementById('adminSettingTimezone').value = settings.summary_timezone || 'Europe/Moscow';
        document.getElementById('adminSettingBotPersonality').value = settings.bot_personality || '';

        showAlert('Настройки загружены', 'success');

    } catch (error) {
        console.error('Error loading chat settings:', error);
        showAlert('Ошибка загрузки настроек: ' + error.message, 'danger');
    }
}

function populateAdminSkills(enabledSkills) {
    const container = document.getElementById('adminSkillsContainer');

    const skills = [
        { key: 'summary', name: '📊 Ежедневные сводки', desc: 'Автоматические сводки чата' },
        { key: 'coach', name: '🎓 Коучинг', desc: 'Рекомендации по коммуникации' },
        { key: 'qa', name: '❓ Вопрос-ответ', desc: 'Ответы на вопросы с контекстом' },
        { key: 'analytics', name: '📈 Аналитика', desc: 'SQL-запросы и статистика' }
    ];

    container.innerHTML = skills.map(skill => {
        const isEnabled = enabledSkills.includes(skill.key);
        return `
            <div class="skill-card">
                <div class="skill-info">
                    <div class="skill-icon">${skill.name.split(' ')[0]}</div>
                    <div>
                        <div class="skill-name">${skill.name.split(' ').slice(1).join(' ')}</div>
                        <div class="skill-desc">${skill.desc}</div>
                    </div>
                </div>
                <label class="toggle-switch">
                    <input type="checkbox"
                           id="adminSkill_${skill.key}"
                           ${isEnabled ? 'checked' : ''}
                           onchange="toggleAdminSkill('${skill.key}')">
                    <span class="toggle-slider"></span>
                </label>
            </div>
        `;
    }).join('');
}

async function toggleAdminSkill(skillKey) {
    if (!currentAdminChatSettings || !selectedAdminChatId) {
        showAlert('Сначала загрузите настройки чата', 'warning');
        document.getElementById(`adminSkill_${skillKey}`).checked =
            !document.getElementById(`adminSkill_${skillKey}`).checked;
        return;
    }

    const checkbox = document.getElementById(`adminSkill_${skillKey}`);
    const isEnabled = checkbox.checked;

    let enabledSkills = currentAdminChatSettings.enabled_skills || [];
    if (isEnabled && !enabledSkills.includes(skillKey)) {
        enabledSkills.push(skillKey);
    } else if (!isEnabled && enabledSkills.includes(skillKey)) {
        enabledSkills = enabledSkills.filter(s => s !== skillKey);
    }

    try {
        const response = await apiCall(`/api/chats/${selectedAdminChatId}/settings`, {
            method: 'PUT',
            body: JSON.stringify({ enabled_skills: enabledSkills })
        });

        if (!response.ok) {
            throw new Error('Failed to update settings');
        }

        const updated = await response.json();
        currentAdminChatSettings = updated;

        showAlert(`Навык "${skillKey}" ${isEnabled ? 'включен' : 'выключен'}`, 'success');

    } catch (error) {
        console.error('Error toggling skill:', error);
        showAlert('Ошибка обновления настроек: ' + error.message, 'danger');
        checkbox.checked = !checkbox.checked;
    }
}

async function saveAdminChatSettings() {
    if (!selectedAdminChatId) {
        showAlert('Выберите чат', 'warning');
        return;
    }

    const language = document.getElementById('adminSettingLanguage').value;
    const summaryTimeLocal = document.getElementById('adminSettingSummaryTime').value;
    const summaryTimezone = document.getElementById('adminSettingTimezone').value;
    const botPersonality = document.getElementById('adminSettingBotPersonality').value.trim();

    try {
        const bodyData = {
            language: language,
            summary_time_local: summaryTimeLocal,
            summary_timezone: summaryTimezone
        };

        if (botPersonality) {
            bodyData.bot_personality = botPersonality;
        }

        const response = await apiCall(`/api/chats/${selectedAdminChatId}/settings`, {
            method: 'PUT',
            body: JSON.stringify(bodyData)
        });

        if (!response.ok) {
            throw new Error('Failed to save settings');
        }

        showAlert('Настройки сохранены!', 'success');
        await loadSelectedChatSettings();

    } catch (error) {
        console.error('Error saving chat settings:', error);
        showAlert('Ошибка сохранения настроек: ' + error.message, 'danger');
    }
}

// ========== Admin Actions ==========

async function adminGenerateSummary() {
    if (!selectedAdminChatId) {
        showAlert('Выберите чат', 'warning');
        return;
    }

    try {
        showAlert('Генерация сводки...', 'info');

        const response = await apiCall(`/api/summary/manual?chat_id=${selectedAdminChatId}`, {
            method: 'POST'
        });

        const data = await response.json();

        if (response.ok) {
            showSummaryModal(data);
        } else {
            showAlert('Ошибка: ' + (data.detail || 'Неизвестная ошибка'), 'danger');
        }
    } catch (error) {
        console.error('Summary error:', error);
        showAlert('Ошибка генерации сводки', 'danger');
    }
}

async function adminSendSummary() {
    if (!selectedAdminChatId) {
        showAlert('Выберите чат', 'warning');
        return;
    }

    if (!confirm('Отправить сводку в чат?')) {
        return;
    }

    try {
        const response = await apiCall(`/api/summary/send?chat_id=${selectedAdminChatId}`, {
            method: 'POST'
        });

        const data = await response.json();

        if (response.ok) {
            showAlert('Сводка отправлена!', 'success');
        } else {
            showAlert('Ошибка: ' + (data.detail || 'Неизвестная ошибка'), 'danger');
        }
    } catch (error) {
        console.error('Send summary error:', error);
        showAlert('Ошибка отправки', 'danger');
    }
}

async function adminSendBotMessage() {
    if (!selectedAdminChatId) {
        showAlert('Выберите чат для контекста', 'warning');
        return;
    }

    const input = document.getElementById('adminChatInput');
    const message = input.value.trim();

    if (!message) {
        return;
    }

    input.value = '';
    addAdminChatMessage('user', message);

    const sendBtn = document.getElementById('adminChatSendBtn');
    sendBtn.disabled = true;

    try {
        const response = await apiCall('/api/bot/send', {
            method: 'POST',
            body: JSON.stringify({
                chat_id: selectedAdminChatId,
                message: message
            })
        });

        const data = await response.json();

        if (data.success && data.response) {
            addAdminChatMessage('bot', data.response);
        } else if (data.error) {
            addAdminChatMessage('system', 'Ошибка: ' + data.error);
        } else {
            addAdminChatMessage('system', 'Бот не вернул ответ');
        }

    } catch (error) {
        console.error('Error sending bot message:', error);
        addAdminChatMessage('system', 'Ошибка отправки');
    } finally {
        sendBtn.disabled = false;
    }
}

function addAdminChatMessage(type, text) {
    const container = document.getElementById('adminChatMessages');
    const messageDiv = document.createElement('div');
    messageDiv.className = `chat-message ${type}`;
    messageDiv.textContent = text;
    container.appendChild(messageDiv);
    container.scrollTop = container.scrollHeight;
}

// ========== Feedback ==========

async function loadFeedback() {
    const status = document.getElementById('feedbackFilter').value;

    try {
        let url = '/api/admin/feedback';
        if (status) {
            url += `?status=${status}`;
        }

        const response = await apiCall(url);

        if (!response.ok) {
            throw new Error('Failed to load feedback');
        }

        const feedback = await response.json();
        renderFeedback(feedback);

    } catch (error) {
        console.error('Error loading feedback:', error);
        showAlert('Ошибка загрузки отзывов', 'danger');
    }
}

function renderFeedback(feedback) {
    const container = document.getElementById('feedbackList');

    if (!feedback || feedback.length === 0) {
        container.innerHTML = '<p style="text-align: center; color: var(--text-secondary); padding: 20px;">Нет отзывов</p>';
        return;
    }

    container.innerHTML = feedback.map(item => {
        const statusIcons = {
            'new': '🆕',
            'in_progress': '🔄',
            'resolved': '✅'
        };
        const categoryIcons = {
            'bug': '🐛',
            'feature': '💡',
            'other': '📝'
        };

        return `
            <div style="background: #f8f9fa; padding: 15px; border-radius: 8px; margin-bottom: 10px; border: 1px solid var(--border-color);">
                <div style="display: flex; justify-content: space-between; margin-bottom: 10px;">
                    <div>
                        <span style="font-weight: 500;">${categoryIcons[item.category] || '????'} ${item.category}</span>
                        <span style="margin-left: 10px; color: var(--text-secondary);">#${item.id}</span>
                    </div>
                    <div>
                        <span style="margin-right: 10px;">${statusIcons[item.status] || item.status}</span>
                        ${item.status !== 'resolved' ? `
                            <button class="btn btn-sm btn-success" onclick="updateFeedbackStatus(${item.id}, 'resolved')" style="padding: 4px 8px; font-size: 12px;">
                                Решить
                            </button>
                        ` : ''}
                    </div>
                </div>
                <div style="margin-bottom: 8px;">${escapeHtml(item.message)}</div>
                <div style="font-size: 12px; color: var(--text-secondary); display: flex; justify-content: space-between;">
                    <span>От: ${item.username || 'User #' + item.user_id} | ${item.source}</span>
                    <span>${new Date(item.created_at).toLocaleString('ru-RU')}</span>
                </div>
            </div>
        `;
    }).join('');
}

async function updateFeedbackStatus(feedbackId, status) {
    try {
        const response = await apiCall(`/api/feedback/${feedbackId}/status?status=${status}`, {
            method: 'PUT'
        });

        if (!response.ok) {
            throw new Error('Failed to update status');
        }

        showAlert('Статус обновлен', 'success');
        loadFeedback();

    } catch (error) {
        console.error('Error updating feedback:', error);
        showAlert('Ошибка обновления статуса', 'danger');
    }
}

// ========== Users Stats ==========

async function loadUsersStats() {
    try {
        const response = await apiCall('/api/admin/users');

        if (!response.ok) {
            throw new Error('Failed to load users stats');
        }

        const stats = await response.json();
        renderUsersStats(stats);

    } catch (error) {
        console.error('Error loading users stats:', error);
        document.getElementById('usersStatsContent').innerHTML =
            '<p style="text-align: center; color: var(--text-secondary);">Нет данных</p>';
    }
}

function renderUsersStats(stats) {
    const container = document.getElementById('usersStatsContent');

    if (!stats || stats.length === 0) {
        container.innerHTML = '<p style="text-align: center; color: var(--text-secondary);">Нет данных</p>';
        return;
    }

    container.innerHTML = `
        <div style="overflow-x: auto;">
            <table style="width: 100%; border-collapse: collapse;">
                <thead>
                    <tr style="border-bottom: 2px solid var(--border-color);">
                        <th style="padding: 10px; text-align: left;">Пользователь</th>
                        <th style="padding: 10px; text-align: center;">Чатов</th>
                        <th style="padding: 10px; text-align: center;">Сообщений</th>
                        <th style="padding: 10px; text-align: center;">LLM запросов</th>
                    </tr>
                </thead>
                <tbody>
                    ${stats.map(user => `
                        <tr style="border-bottom: 1px solid var(--border-color);">
                            <td style="padding: 10px;">
                                <strong>${escapeHtml(user.username || 'Unknown')}</strong>
                                <div style="font-size: 12px; color: var(--text-secondary);">
                                    ID: ${user.user_id}
                                </div>
                            </td>
                            <td style="padding: 10px; text-align: center;">${user.chat_count || 0}</td>
                            <td style="padding: 10px; text-align: center;">${user.message_count || 0}</td>
                            <td style="padding: 10px; text-align: center;">${user.llm_requests || 0}</td>
                        </tr>
                    `).join('')}
                </tbody>
            </table>
        </div>
    `;
}

// ========== Utility ==========

function showSummaryModal(data) {
    const existingModal = document.getElementById('adminSummaryModal');
    if (existingModal) existingModal.remove();

    const modal = document.createElement('div');
    modal.id = 'adminSummaryModal';
    modal.style.cssText = `
        position: fixed;
        top: 0;
        left: 0;
        width: 100%;
        height: 100%;
        background: rgba(0, 0, 0, 0.5);
        display: flex;
        align-items: center;
        justify-content: center;
        z-index: 9999;
    `;

    modal.innerHTML = `
        <div style="background: white; border-radius: 8px; max-width: 600px; max-height: 80vh; overflow-y: auto; padding: 20px; margin: 20px;">
            <h2 style="margin-bottom: 15px; color: var(--secondary-color);">📊 Сводка</h2>
            <div style="white-space: pre-wrap; margin-bottom: 15px;">${escapeHtml(data.summary)}</div>
            ${data.recommendations ? `
                <h3 style="margin-bottom: 10px; color: var(--secondary-color);">🎓 Рекомендации</h3>
                <div style="white-space: pre-wrap; margin-bottom: 15px;">${escapeHtml(data.recommendations)}</div>
            ` : ''}
            <button class="btn btn-primary" onclick="document.getElementById('adminSummaryModal').remove()">Закрыть</button>
        </div>
    `;

    document.body.appendChild(modal);
}

function showAlert(message, type = 'info') {
    const container = document.getElementById('alertContainer');
    const alert = document.createElement('div');
    alert.className = `alert alert-${type}`;
    alert.textContent = message;
    container.appendChild(alert);

    setTimeout(() => alert.remove(), 5000);
}

function escapeHtml(text) {
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
}

async function logout() {
    try {
        if (currentToken) {
            await fetch('/api/auth/logout', {
                method: 'POST',
                headers: { 'Authorization': `Bearer ${currentToken}` }
            }).catch(() => {});
        }
    } finally {
        localStorage.removeItem('token');
        localStorage.removeItem('username');
        localStorage.removeItem('is_superadmin');
        currentToken = null;
        window.location.href = '/login';
    }
}

// ========== Skill Prompts Management ==========

const SKILL_INFO = {
    'qa': { name: '❓ Вопрос-ответ', desc: 'Отвечает на вопросы по содержимому чата' },
    'summary': { name: '📊 Сводки', desc: 'Генерирует краткие обзоры обсуждений' },
    'coach': { name: '🎓 Коучинг', desc: 'Рекомендации по коммуникации' },
    'analytics': { name: '📈 Аналитика', desc: 'SQL-запросы и статистика' },
    'about': { name: 'ℹ️ О боте', desc: 'Информация о возможностях' }
};

// Current selected skill data
let currentSkillData = null;
let currentSkillName = null;

async function loadSkillPrompts() {
    // Just cache the prompts, no rendering needed
    try {
        const response = await apiCall('/api/admin/skill-prompts');
        if (!response.ok) {
            throw new Error('Failed to load skill prompts');
        }
        // Cache for later use
        window.allSkillPrompts = await response.json();
    } catch (error) {
        console.error('Error loading skill prompts:', error);
        showAlert('Ошибка загрузки промптов', 'danger');
    }
}

async function loadSelectedSkillPrompt() {
    const skillName = document.getElementById('skillPromptSelect').value;

    if (!skillName) {
        // Show empty state
        document.getElementById('promptEditorSection').style.display = 'none';
        document.getElementById('promptEditorEmpty').style.display = 'block';
        currentSkillData = null;
        currentSkillName = null;
        return;
    }

    try {
        // Show loading state
        document.getElementById('promptEditorEmpty').style.display = 'none';
        document.getElementById('promptEditorSection').style.display = 'block';
        document.getElementById('promptText').value = 'Загрузка...';
        document.getElementById('versionHistoryList').innerHTML = '<p style="text-align: center; padding: 10px;">Загрузка версий...</p>';

        // Get skill data from cache or reload
        if (!window.allSkillPrompts) {
            await loadSkillPrompts();
        }

        const skillData = window.allSkillPrompts.find(s => s.skill_name === skillName);
        if (!skillData) {
            throw new Error('Skill not found');
        }

        currentSkillData = skillData;
        currentSkillName = skillName;

        // Update UI with skill info
        const info = SKILL_INFO[skillName];
        document.getElementById('currentSkillName').textContent = info.name;
        document.getElementById('currentSkillDesc').textContent = info.desc;

        // Update status badge
        const statusBadge = document.getElementById('promptStatusBadge');
        if (skillData.is_custom) {
            statusBadge.textContent = `Версия ${skillData.version}`;
            statusBadge.style.background = skillData.is_active ? '#4caf50' : '#9e9e9e';
            statusBadge.style.color = 'white';
        } else {
            statusBadge.textContent = 'Дефолтный';
            statusBadge.style.background = '#2196f3';
            statusBadge.style.color = 'white';
        }

        // Load prompt text
        document.getElementById('promptText').value = skillData.prompt || '';

        // Load version history
        await loadVersionHistory(skillName);

    } catch (error) {
        console.error('Error loading skill prompt:', error);
        showAlert('Ошибка загрузки промпта', 'danger');
    }
}

async function loadVersionHistory(skillName) {
    try {
        const response = await apiCall(`/api/admin/skill-prompts/${skillName}/history?limit=20`);
        if (!response.ok) {
            throw new Error('Failed to load history');
        }

        const history = await response.json();
        renderVersionHistory(history);

    } catch (error) {
        console.error('Error loading version history:', error);
        document.getElementById('versionHistoryList').innerHTML = '<p style="text-align: center; color: #f44336;">Ошибка загрузки версий</p>';
    }
}

function renderVersionHistory(history) {
    const container = document.getElementById('versionHistoryList');

    if (!history || history.length === 0) {
        container.innerHTML = '<p style="text-align: center; color: var(--text-secondary); padding: 10px;">Нет сохранённых версий</p>';
        return;
    }

    // Find current active version
    const currentVersion = currentSkillData ? currentSkillData.version : null;
    const isActive = currentSkillData && currentSkillData.is_active;

    let html = '';
    history.forEach((version, index) => {
        const isCurrentActive = (version.version === currentVersion && isActive);
        const isCurrentVersion = (version.version === currentVersion);

        html += `
            <div style="padding: 10px; margin-bottom: 8px; border-radius: 4px;
                       background: ${isCurrentActive ? '#e8f5e9' : 'white'};
                       border: 1px solid ${isCurrentActive ? '#4caf50' : '#e0e0e0'};">
                <div style="display: flex; justify-content: space-between; align-items: center;">
                    <div>
                        <strong>v${version.version}</strong>
                        ${isCurrentActive ? '<span style="margin-left: 8px; color: #4caf50; font-size: 12px;">● Актуальная</span>' : ''}
                        ${isCurrentVersion && !isActive ? '<span style="margin-left: 8px; color: #ff9800; font-size: 12px;">● Сохранена</span>' : ''}
                    </div>
                    <span style="font-size: 11px; color: var(--text-secondary);">${new Date(version.created_at).toLocaleString('ru-RU')}</span>
                </div>
                ${version.change_reason ? `<div style="font-size: 11px; color: var(--text-secondary); margin-top: 4px;">${version.change_reason}</div>` : ''}
                <div style="display: flex; gap: 8px; margin-top: 8px;">
                    <button class="btn btn-sm btn-secondary" onclick="event.stopPropagation(); activatePromptVersion(${version.version})">
                        📝 Загрузить в редактор
                    </button>
                    ${!isCurrentActive ? `
                    <button class="btn btn-sm btn-success" onclick="event.stopPropagation(); restoreVersionAsActive(${version.version})">
                        ✅ Сделать активной
                    </button>
                    ` : '<span style="font-size: 11px; color: #999; padding: 6px 12px;">Эта версия активна</span>'}
                </div>
            </div>
        `;
    });

    container.innerHTML = html;
}

async function activatePromptVersion(versionNumber) {
    if (!currentSkillName) return;

    try {
        // Load the full prompt from history
        const response = await apiCall(`/api/admin/skill-prompts/${currentSkillName}/history?limit=50`);
        if (!response.ok) {
            throw new Error('Failed to load history');
        }

        const history = await response.json();
        const versionData = history.find(v => v.version === versionNumber);

        if (!versionData) {
            showAlert('Версия не найдена', 'danger');
            return;
        }

        // Load into editor WITHOUT saving
        document.getElementById('promptText').value = versionData.prompt;

        // Show indicator that we're editing a specific version
        const statusBadge = document.getElementById('promptStatusBadge');
        statusBadge.textContent = `Редактируется v${versionNumber}`;
        statusBadge.style.background = '#ff9800';
        statusBadge.style.color = 'white';

        showAlert(`Версия ${versionNumber} загружена в редактор. Нажмите "Сохранить" для создания новой версии.`, 'info');

    } catch (error) {
        console.error('Error loading version:', error);
        showAlert('Ошибка загрузки версии', 'danger');
    }
}

async function restoreVersionAsActive(versionNumber) {
    if (!currentSkillName) return;

    if (!confirm(`Сделать версию ${versionNumber} активной? Это создаст новую запись в истории.`)) {
        return;
    }

    try {
        // Load the full prompt from history
        const response = await apiCall(`/api/admin/skill-prompts/${currentSkillName}/history?limit=50`);
        if (!response.ok) {
            throw new Error('Failed to load history');
        }

        const history = await response.json();
        const versionData = history.find(v => v.version === versionNumber);

        if (!versionData) {
            showAlert('Версия не найдена', 'danger');
            return;
        }

        // Save this version as the new active prompt
        const saveResponse = await apiCall(`/api/admin/skill-prompts/${currentSkillName}`, {
            method: 'PUT',
            body: JSON.stringify({
                prompt: versionData.prompt,
                is_active: true,
                change_reason: `Восстановление версии ${versionNumber}`
            })
        });

        if (saveResponse.ok) {
            showAlert(`Версия ${versionNumber} теперь актуальна`, 'success');
            await loadSelectedSkillPrompt();
            await loadSkillPrompts(); // Refresh cache
        } else {
            const data = await saveResponse.json();
            showAlert('Ошибка: ' + (data.detail || 'Неизвестная ошибка'), 'danger');
        }

    } catch (error) {
        console.error('Error restoring version:', error);
        showAlert('Ошибка восстановления версии', 'danger');
    }
}

async function saveSkillPrompt() {
    const skillName = document.getElementById('skillPromptSelect').value;

    if (!skillName) {
        showAlert('Сначала выберите навык', 'warning');
        return;
    }

    const prompt = document.getElementById('promptText').value.trim();

    if (!prompt || prompt.length < 50) {
        showAlert('Промпт должен быть не менее 50 символов', 'warning');
        return;
    }

    try {
        const response = await apiCall(`/api/admin/skill-prompts/${skillName}`, {
            method: 'PUT',
            body: JSON.stringify({
                prompt: prompt,
                is_active: true,
                change_reason: 'Обновление через редактор'
            })
        });

        if (response.ok) {
            showAlert('Промпт сохранён как новая версия!', 'success');
            await loadSelectedSkillPrompt();
            await loadSkillPrompts(); // Refresh cache
        } else {
            const data = await response.json();
            showAlert('Ошибка: ' + (data.detail || 'Неизвестная ошибка'), 'danger');
        }
    } catch (error) {
        console.error('Error saving prompt:', error);
        showAlert('Ошибка сохранения', 'danger');
    }
}

async function resetToDefaultPrompt() {
    const skillName = document.getElementById('skillPromptSelect').value;

    if (!skillName) {
        showAlert('Сначала выберите навык', 'warning');
        return;
    }

    if (!confirm('Сбросить промпт на дефолтный? Все кастомные версии сохранятся в истории.')) {
        return;
    }

    try {
        const response = await apiCall(`/api/admin/skill-prompts/${skillName}/reset`, {
            method: 'POST'
        });

        if (response.ok) {
            showAlert('Промпт сброшен на дефолтный', 'success');
            await loadSelectedSkillPrompt();
            await loadSkillPrompts(); // Refresh cache
        } else {
            const data = await response.json();
            showAlert('Ошибка: ' + (data.detail || 'Неизвестная ошибка'), 'danger');
        }
    } catch (error) {
        console.error('Error resetting prompt:', error);
        showAlert('Ошибка сброса', 'danger');
    }
}

function previewPrompt() {
    const prompt = document.getElementById('promptText').value;

    // Show modal with preview
    const modal = document.createElement('div');
    modal.style.cssText = `
        position: fixed;
        top: 0;
        left: 0;
        width: 100%;
        height: 100%;
        background: rgba(0, 0, 0, 0.5);
        display: flex;
        align-items: center;
        justify-content: center;
        z-index: 9999;
    `;

    // Example values for substitution
    const exampleValues = {
        '{chat_title}': 'Мой рабочий чат',
        '{chat_id}': '123456',
        '{username}': 'ivan_petrov',
        '{full_name}': 'Иван Петров',
        '{date}': '29 января 2026',
        '{language}': 'ru',
        '{model_name}': 'gpt-4o-mini'
    };

    let preview = prompt;
    for (const [placeholder, value] of Object.entries(exampleValues)) {
        preview = preview.replace(new RegExp(placeholder.replace('{', '\\{').replace('}', '\\}'), 'g'), value);
    }

    modal.innerHTML = `
        <div style="background: white; border-radius: 8px; max-width: 700px; max-height: 80vh; overflow-y: auto; padding: 20px; margin: 20px;">
            <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 15px;">
                <h2 style="margin: 0;">👁️ Предпросмотр промпта</h2>
                <button onclick="this.closest('div').parentElement.parentElement.remove()" style="background: none; border: none; font-size: 24px; cursor: pointer;">&times;</button>
            </div>
            <div style="background: #f5f5f5; padding: 10px; border-radius: 4px; margin-bottom: 15px; font-size: 12px; color: #666;">
                <strong>Пример подстановки переменных:</strong>
                ${Object.entries(exampleValues).map(([k, v]) => `<div>${k} → ${v}</div>`).join('')}
            </div>
            <pre style="background: white; padding: 15px; border-radius: 6px; overflow-x: auto; font-size: 13px; line-height: 1.5; white-space: pre-wrap; word-wrap: break-word;">${escapeHtml(preview)}</pre>
            <button onclick="this.closest('div').parentElement.parentElement.remove()" class="btn btn-primary" style="width: 100%; margin-top: 15px;">Закрыть</button>
        </div>
    `;

    document.body.appendChild(modal);
}
