/**
 * Telegram Chat Analytics - Dashboard JavaScript
 */

// Global state
let activityChart = null;
let chats = [];
let currentToken = localStorage.getItem('token');
let isSuperadmin = false;

// Chat state
let currentChatSettings = null;
let selectedSettingsChatId = null;

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
            isSuperadmin = user.is_superadmin;
            localStorage.setItem('username', user.username);
            localStorage.setItem('is_superadmin', user.is_superadmin);

            // Set user info
            document.getElementById('userName').textContent = user.username;
            document.getElementById('userAvatar').textContent = user.username.charAt(0).toUpperCase();

            // Show admin link for superadmins
            if (user.is_superadmin) {
                const adminLink = document.getElementById('adminLink');
                if (adminLink) {
                    adminLink.style.display = 'inline-block';
                }
            }

            // Add body class for CSS-based visibility control
            if (isSuperadmin) {
                document.body.classList.add('is-superadmin');
            }

            // Update page title
            if (!isSuperadmin) {
                document.title = 'Мои чаты - Telegram Chat Analytics';
            }
        } else if (response.status === 401) {
            // Token is invalid or expired - redirect to login
            logout();
            return;
        } else {
            throw new Error('Failed to get user info');
        }
    } catch (error) {
        console.error('Error loading user info:', error);
        // On 401 or other auth errors - redirect to login
        if (error.message === 'Unauthorized' || !currentToken) {
            logout();
            return;
        }
        // Fallback only if token exists (network error, etc)
        isSuperadmin = localStorage.getItem('is_superadmin') === 'true';
        const username = localStorage.getItem('username') || 'User';
        document.getElementById('userName').textContent = username;
        document.getElementById('userAvatar').textContent = username.charAt(0).toUpperCase();

        if (isSuperadmin) {
            document.body.classList.add('is-superadmin');
            // Show admin link for superadmins
            const adminLink = document.getElementById('adminLink');
            if (adminLink) {
                adminLink.style.display = 'inline-block';
            }
        }
    }

    // Initialize
    initChart();
    loadChats();
    loadData();
    if (isSuperadmin) {
        loadLlmStats();
    }
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
        // Don't call logout() here to avoid recursion
        // Let the calling code handle the error
        throw new Error('Unauthorized');
    }

    return response;
}

// ========== Load Data ==========

async function loadChats() {
    try {
        // Use /api/chats/my-chats for regular users, /api/chats for superadmins
        const endpoint = isSuperadmin ? '/api/chats?active_only=true' : '/api/chats/my-chats?active_only=true';
        const response = await apiCall(endpoint);

        if (!response.ok) {
            throw new Error('Failed to load chats');
        }

        const data = await response.json();
        chats = data;

        // Populate all chat selects
        populateChatSelects(chats);

        // Update active chats count
        document.getElementById('activeChats').textContent = chats.length;

    } catch (error) {
        console.error('Error loading chats:', error);
        showAlert('Ошибка загрузки списка чатов', 'danger');
    }
}

function populateChatSelects(chats) {
    // All selects that need to be populated
    const selects = [
        'chatSelect',
        'summaryChatSelect',
        'settingsChatSelect',
        'botChatSelect'
    ];

    selects.forEach(selectId => {
        const select = document.getElementById(selectId);
        if (!select) return;

        // Save current selection
        const currentValue = select.value;

        // Clear and populate
        if (selectId === 'chatSelect') {
            select.innerHTML = '<option value="">Все чаты</option>';
        } else {
            select.innerHTML = '<option value="">Выберите чат...</option>';
        }

        chats.forEach(chat => {
            const option = `<option value="${chat.chat_id}">${escapeHtml(chat.title)}</option>`;
            select.innerHTML += option;
        });

        // Restore selection
        select.value = currentValue;
    });

    // Setup role-based button state for settings chat select
    setupSettingsChatRoleCheck();
}

// Setup role checking for settings chat selection
async function setupSettingsChatRoleCheck() {
    const settingsSelect = document.getElementById('settingsChatSelect');
    const loadBtn = document.getElementById('loadSettingsBtn');

    if (!settingsSelect || !loadBtn) return;

    // Function to check role and update button state
    const checkRoleAndUpdateButton = async () => {
        const chatId = settingsSelect.value;

        // Reset button state if no chat selected
        if (!chatId) {
            loadBtn.disabled = true;
            loadBtn.title = 'Выберите чат для загрузки настроек';
            loadBtn.classList.remove('btn-secondary');
            loadBtn.classList.add('btn-primary');
            return;
        }

        try {
            // Check user's role in this chat
            const response = await apiCall(`/api/chats/${chatId}/role`);
            if (response.ok) {
                const roleData = await response.json();

                if (roleData.can_modify) {
                    // User is admin/owner/superadmin - enable button
                    loadBtn.disabled = false;
                    loadBtn.title = `Загрузить настройки для "${settingsSelect.options[settingsSelect.selectedIndex].text}"`;
                    loadBtn.classList.remove('btn-secondary');
                    loadBtn.classList.add('btn-primary');
                } else {
                    // User is only a member - disable button
                    loadBtn.disabled = true;
                    loadBtn.title = `Только администраторы могут настраивать этот чат (ваша роль: ${roleData.role || 'member'})`;
                    loadBtn.classList.remove('btn-primary');
                    loadBtn.classList.add('btn-secondary');
                }
            } else {
                // Error checking role - disable button
                loadBtn.disabled = true;
                loadBtn.title = 'Не удалось проверить права доступа';
                loadBtn.classList.remove('btn-primary');
                loadBtn.classList.add('btn-secondary');
            }
        } catch (error) {
            console.error('Error checking role:', error);
            loadBtn.disabled = true;
            loadBtn.title = 'Ошибка проверки прав доступа';
            loadBtn.classList.remove('btn-primary');
            loadBtn.classList.add('btn-secondary');
        }
    };

    // Add event listener for chat selection changes
    settingsSelect.addEventListener('change', checkRoleAndUpdateButton);

    // Initial check in case a chat is already selected
    if (settingsSelect.value) {
        checkRoleAndUpdateButton();
    }
}

async function loadData() {
    const chatId = document.getElementById('chatSelect').value || null;
    const days = parseInt(document.getElementById('daysSelect').value);

    try {
        // Load stats
        await loadStats(chatId, days);

        // Load messages for chart
        await loadMessages(chatId, days);

    } catch (error) {
        console.error('Error loading data:', error);
        showAlert('Ошибка загрузки данных', 'danger');
    }
}

async function loadStats(chatId, days) {
    const params = new URLSearchParams({ days: days.toString() });
    if (chatId) params.append('chat_id', chatId);

    const response = await apiCall(`/api/stats/messages?${params}`);
    const stats = await response.json();

    // Update stat cards
    document.getElementById('totalMessages').textContent = stats.total_messages;
    document.getElementById('activeUsers').textContent = stats.active_users;
    document.getElementById('avgPerDay').textContent = stats.avg_per_day;

    // Update contributors list
    updateContributors(stats.top_contributors);
}

async function loadMessages(chatId, days) {
    const params = new URLSearchParams({
        days: days.toString(),
        limit: '1000'
    });
    if (chatId) params.append('chat_id', chatId);

    const response = await apiCall(`/api/messages?${params}`);
    const data = await response.json();

    // Update chart
    updateChart(data.messages);

    // Update recent messages
    updateRecentMessages(data.messages.slice(0, 20));
}

// ========== Chat Settings ==========

async function loadChatSettings() {
    const chatId = document.getElementById('settingsChatSelect').value;

    if (!chatId) {
        showAlert('Выберите чат для загрузки настроек', 'warning');
        return;
    }

    selectedSettingsChatId = parseInt(chatId);

    // First check if user can modify settings in this chat
    try {
        const roleResponse = await apiCall(`/api/chats/${chatId}/role`);
        if (!roleResponse.ok) {
            throw new Error('Failed to check role');
        }
        const roleData = await roleResponse.json();

        if (!roleData.can_modify) {
            showAlert('Только администраторы могут настраивать этот чат', 'warning');
            return;
        }
    } catch (error) {
        console.error('Error checking role:', error);
        showAlert('Ошибка проверки прав доступа', 'danger');
        return;
    }

    try {
        const response = await apiCall(`/api/chats/${chatId}/settings`);

        if (!response.ok) {
            throw new Error('Failed to load chat settings');
        }

        const settings = await response.json();
        currentChatSettings = settings;

        // Show settings content
        document.getElementById('chatSettingsContent').style.display = 'block';

        // Populate skills toggles
        populateSkills(settings.enabled_skills || []);

        // Populate additional settings
        document.getElementById('settingLanguage').value = settings.language || 'ru';
        document.getElementById('settingSummaryTime').value = settings.summary_time_local || '16:00';
        document.getElementById('settingTimezone').value = settings.summary_timezone || 'Europe/Moscow';
        document.getElementById('settingBotPersonality').value = settings.bot_personality || '';

        showAlert('Настройки загружены', 'success');

    } catch (error) {
        console.error('Error loading chat settings:', error);
        showAlert('Ошибка загрузки настроек: ' + error.message, 'danger');
    }
}

function populateSkills(enabledSkills) {
    const container = document.getElementById('skillsContainer');

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
                           id="skill_${skill.key}"
                           ${isEnabled ? 'checked' : ''}
                           onchange="toggleSkill('${skill.key}')">
                    <span class="toggle-slider"></span>
                </label>
            </div>
        `;
    }).join('');
}

async function toggleSkill(skillKey) {
    if (!currentChatSettings || !selectedSettingsChatId) {
        showAlert('Сначала загрузите настройки чата', 'warning');
        // Reset checkbox
        document.getElementById(`skill_${skillKey}`).checked =
            !document.getElementById(`skill_${skillKey}`).checked;
        return;
    }

    const checkbox = document.getElementById(`skill_${skillKey}`);
    const isEnabled = checkbox.checked;

    // Update local state
    let enabledSkills = currentChatSettings.enabled_skills || [];
    if (isEnabled && !enabledSkills.includes(skillKey)) {
        enabledSkills.push(skillKey);
    } else if (!isEnabled && enabledSkills.includes(skillKey)) {
        enabledSkills = enabledSkills.filter(s => s !== skillKey);
    }

    // Save to server
    try {
        const response = await apiCall(`/api/chats/${selectedSettingsChatId}/settings`, {
            method: 'PUT',
            body: JSON.stringify({ enabled_skills: enabledSkills })
        });

        if (!response.ok) {
            throw new Error('Failed to update settings');
        }

        const updated = await response.json();
        currentChatSettings = updated;

        showAlert(`Навык "${skillKey}" ${isEnabled ? 'включен' : 'выключен'}`, 'success');

    } catch (error) {
        console.error('Error toggling skill:', error);
        showAlert('Ошибка обновления настроек: ' + error.message, 'danger');
        // Revert checkbox
        checkbox.checked = !checkbox.checked;
    }
}

async function saveChatSettings() {
    if (!selectedSettingsChatId) {
        showAlert('Выберите чат для сохранения настроек', 'warning');
        return;
    }

    const language = document.getElementById('settingLanguage').value;
    const summaryTimeLocal = document.getElementById('settingSummaryTime').value;
    const summaryTimezone = document.getElementById('settingTimezone').value;
    const botPersonality = document.getElementById('settingBotPersonality').value.trim();

    try {
        const bodyData = {
            language: language,
            summary_time_local: summaryTimeLocal,
            summary_timezone: summaryTimezone
        };

        // Only include bot_personality if not empty
        if (botPersonality) {
            bodyData.bot_personality = botPersonality;
        }

        const response = await apiCall(`/api/chats/${selectedSettingsChatId}/settings`, {
            method: 'PUT',
            body: JSON.stringify(bodyData)
        });

        if (!response.ok) {
            throw new Error('Failed to save settings');
        }

        showAlert('Настройки сохранены!', 'success');

        // Reload settings
        await loadChatSettings();

    } catch (error) {
        console.error('Error saving chat settings:', error);
        showAlert('Ошибка сохранения настроек: ' + error.message, 'danger');
    }
}

// ========== Bot Chat ==========

async function sendBotMessage() {
    const chatId = document.getElementById('botChatSelect').value;
    const input = document.getElementById('chatInput');
    const message = input.value.trim();

    if (!chatId) {
        showAlert('Выберите чат для контекста бота', 'warning');
        return;
    }

    if (!message) {
        return;
    }

    // Clear input
    input.value = '';

    // Add user message to chat
    addChatMessage('user', message);

    // Show typing indicator
    const typingId = showTypingIndicator();

    // Disable send button
    const sendBtn = document.getElementById('chatSendBtn');
    sendBtn.disabled = true;

    try {
        const response = await apiCall('/api/bot/send', {
            method: 'POST',
            body: JSON.stringify({
                chat_id: parseInt(chatId),
                message: message
            })
        });

        const data = await response.json();

        // Remove typing indicator
        removeTypingIndicator(typingId);

        if (data.success && data.response) {
            addChatMessage('bot', data.response);
        } else if (data.error) {
            addChatMessage('system', 'Ошибка: ' + data.error);
        } else {
            addChatMessage('system', 'Бот не вернул ответ');
        }

    } catch (error) {
        console.error('Error sending bot message:', error);
        // Remove typing indicator on error
        removeTypingIndicator(typingId);
        addChatMessage('system', 'Ошибка отправки сообщения');
    } finally {
        sendBtn.disabled = false;
    }
}

function addChatMessage(type, text) {
    const container = document.getElementById('chatMessages');

    const messageDiv = document.createElement('div');
    messageDiv.className = `chat-message ${type}`;

    // Use innerHTML with escapeHtml to preserve line breaks for bot messages
    if (type === 'bot') {
        messageDiv.innerHTML = escapeHtml(text);
    } else {
        messageDiv.textContent = text;
    }

    container.appendChild(messageDiv);

    // Scroll to bottom
    container.scrollTop = container.scrollHeight;
}

function showTypingIndicator() {
    const container = document.getElementById('chatMessages');

    const typingDiv = document.createElement('div');
    typingDiv.className = 'chat-message bot typing-indicator';
    const typingId = 'typing-' + Date.now();
    typingDiv.id = typingId;

    typingDiv.innerHTML = `
        <span></span>
        <span></span>
        <span></span>
    `;

    container.appendChild(typingDiv);
    container.scrollTop = container.scrollHeight;

    return typingId;
}

function removeTypingIndicator(typingId) {
    const typingElement = document.getElementById(typingId);
    if (typingElement) {
        typingElement.remove();
    }
}

function clearChat() {
    const container = document.getElementById('chatMessages');
    container.innerHTML = '<div class="chat-message system">История очищена. Выберите чат и задайте вопрос боту.</div>';
}

// ========== LLM Stats ==========

async function loadLlmStats() {
    try {
        const response = await apiCall('/api/stats/llm-usage?days=30');
        const stats = await response.json();

        // Update LLM stat cards
        document.getElementById('llmTokens').textContent = formatNumber(stats.total_tokens);
        document.getElementById('llmCost').textContent = '$' + stats.total_cost_usd.toFixed(4);

        // Update LLM by chat section
        updateLlmByChat(stats.by_chat, stats.by_skill);

    } catch (error) {
        console.error('Error loading LLM stats:', error);

        // Show zeros on error
        document.getElementById('llmTokens').textContent = '0';
        document.getElementById('llmCost').textContent = '$0.0000';
        document.getElementById('llmByChatContent').innerHTML =
            '<p style="text-align: center; color: var(--text-secondary); padding: 20px;">Нет данных</p>';
    }
}

function updateLlmByChat(byChat, bySkill) {
    const container = document.getElementById('llmByChatContent');

    if (!byChat || byChat.length === 0) {
        container.innerHTML = '<p style="text-align: center; color: var(--text-secondary); padding: 20px;">Нет данных об использовании LLM</p>';
        return;
    }

    // Create summary stats
    let html = '<div style="display: grid; grid-template-columns: repeat(auto-fit, minmax(300px, 1fr)); gap: 20px; margin-bottom: 20px;">';

    // By chat section
    html += '<div style="background: #f8f9fa; padding: 15px; border-radius: 8px;">';
    html += '<h3 style="margin: 0 0 15px 0; font-size: 16px; color: #333;">📊 По чатам</h3>';
    html += '<div style="max-height: 300px; overflow-y: auto;">';

    byChat.forEach(chat => {
        const chatName = getChatName(chat.chat_id);
        html += `
            <div style="padding: 10px; border-bottom: 1px solid #e0e0e0; display: flex; justify-content: space-between; align-items: center;">
                <div>
                    <div style="font-weight: 500;">${escapeHtml(chatName)}</div>
                    <div style="font-size: 12px; color: #666;">
                        Входящих: ${formatNumber(chat.tokens_prompt)} |
                        Исходящих: ${formatNumber(chat.tokens_completion)}
                    </div>
                </div>
                <div style="text-align: right;">
                    <div style="font-weight: 500; color: #667eea;">${formatNumber(chat.tokens_total)}</div>
                    <div style="font-size: 11px; color: #999;">токенов</div>
                </div>
            </div>
        `;
    });

    html += '</div></div>';

    // By skill section
    html += '<div style="background: #f8f9fa; padding: 15px; border-radius: 8px;">';
    html += '<h3 style="margin: 0 0 15px 0; font-size: 16px; color: #333;">⚡ По навыкам</h3>';
    html += '<div style="max-height: 300px; overflow-y: auto;">';

    bySkill.forEach(skill => {
        const skillNames = {
            'summary': '📊 Сводки',
            'coach': '🎯 Коуч',
            'thread_summary': '💬 Сводки тредов',
            'qa': '❓ Вопрос-ответ',
            'unknown': '❓ Неизвестно'
        };
        const skillName = skillNames[skill.skill] || skill.skill;

        html += `
            <div style="padding: 10px; border-bottom: 1px solid #e0e0e0; display: flex; justify-content: space-between; align-items: center;">
                <div style="flex: 1;">
                    <div style="font-weight: 500;">${skillName}</div>
                    <div style="font-size: 12px; color: #666;">
                        ${skill.requests} запросов
                    </div>
                </div>
                <div style="text-align: right;">
                    <div style="font-weight: 500; color: #764ba2;">${formatNumber(skill.tokens_total)}</div>
                    <div style="font-size: 11px; color: #999;">токенов</div>
                </div>
            </div>
        `;
    });

    html += '</div></div></div>';
    container.innerHTML = html;
}

function getChatName(chatId) {
    const chat = chats.find(c => c.chat_id === chatId);
    if (chat) {
        return chat.title || `Chat ${chatId}`;
    }
    return `Chat ${chatId}`;
}

function formatNumber(num) {
    if (num >= 1000000) {
        return (num / 1000000).toFixed(1) + 'M';
    } else if (num >= 1000) {
        return (num / 1000).toFixed(1) + 'K';
    }
    return num.toString();
}

// ========== Chart ==========

function initChart() {
    const ctx = document.getElementById('activityChart').getContext('2d');

    activityChart = new Chart(ctx, {
        type: 'bar',
        data: {
            labels: [],
            datasets: [{
                label: 'Сообщений',
                data: [],
                backgroundColor: 'rgba(0, 136, 204, 0.8)',
                borderColor: 'rgba(0, 136, 204, 1)',
                borderWidth: 1
            }]
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            plugins: {
                legend: {
                    display: false
                },
                tooltip: {
                    callbacks: {
                        label: function(context) {
                            return `${context.parsed.y} сообщений`;
                        }
                    }
                }
            },
            scales: {
                y: {
                    beginAtZero: true,
                    ticks: {
                        stepSize: 1
                    }
                },
                x: {
                    ticks: {
                        maxRotation: 45,
                        minRotation: 45
                    }
                }
            }
        }
    });
}

function updateChart(messages) {
    // Group messages by hour
    const hourCounts = new Array(24).fill(0);

    messages.forEach(msg => {
        if (msg.timestamp) {
            const date = new Date(msg.timestamp);
            hourCounts[date.getHours()]++;
        }
    });

    // Update chart data
    activityChart.data.labels = hourCounts.map((_, i) => `${i}:00`);
    activityChart.data.datasets[0].data = hourCounts;
    activityChart.update();
}

// ========== UI Updates ==========

function updateContributors(contributors) {
    const list = document.getElementById('contributorsList');

    if (!contributors || contributors.length === 0) {
        list.innerHTML = '<li style="text-align: center; color: var(--text-secondary); padding: 20px;">Нет данных</li>';
        return;
    }

    list.innerHTML = contributors.map(([name, count]) => `
        <li class="contributor-item">
            <span class="contributor-name">${name}</span>
            <span class="contributor-count">${count}</span>
        </li>
    `).join('');
}

function updateRecentMessages(messages) {
    const container = document.getElementById('recentMessages');

    if (!messages || messages.length === 0) {
        container.innerHTML = '<p style="text-align: center; color: var(--text-secondary); padding: 20px;">Нет сообщений</p>';
        return;
    }

    container.innerHTML = messages.map(msg => {
        const username = msg.username || msg.first_name || 'Unknown';
        const text = msg.content || '[медиа]';
        const time = msg.timestamp ? new Date(msg.timestamp).toLocaleString('ru-RU') : '';

        return `
            <div style="padding: 10px; border-bottom: 1px solid var(--border-color);">
                <div style="display: flex; justify-content: space-between; margin-bottom: 5px;">
                    <strong>${username}</strong>
                    <span style="font-size: 12px; color: var(--text-secondary);">${time}</span>
                </div>
                <div style="color: var(--text-primary); word-break: break-word;">${escapeHtml(text)}</div>
            </div>
        `;
    }).join('');
}

// ========== Actions ==========

async function exportCSV() {
    const chatId = document.getElementById('chatSelect').value || null;
    const days = document.getElementById('daysSelect').value;

    const params = new URLSearchParams({ days: days });
    if (chatId) params.append('chat_id', chatId);

    try {
        const response = await apiCall(`/api/export/csv?${params}`);

        if (response.ok) {
            // Download file
            const blob = await response.blob();
            const url = window.URL.createObjectURL(blob);
            const a = document.createElement('a');
            a.href = url;
            a.download = `messages_${new Date().toISOString().split('T')[0]}.csv`;
            document.body.appendChild(a);
            a.click();
            document.body.removeChild(a);
            window.URL.revokeObjectURL(url);

            showAlert('CSV файл успешно экспортирован', 'success');
        } else {
            showAlert('Ошибка при экспорте CSV', 'danger');
        }
    } catch (error) {
        console.error('Export error:', error);
        showAlert('Ошибка при экспорте', 'danger');
    }
}

async function generateSummary() {
    const chatId = document.getElementById('summaryChatSelect').value;

    if (!chatId) {
        showAlert('Выберите чат для генерации сводки', 'warning');
        return;
    }

    try {
        showAlert('Генерация сводки... Это может занять время.', 'info');

        const response = await apiCall(`/api/summary/manual?chat_id=${chatId}`, {
            method: 'POST'
        });

        const data = await response.json();

        if (response.ok) {
            // Show summary in alert/modal (simplified as alert for now)
            let message = '📊 Сводка:\n\n' + data.summary;
            if (data.recommendations) {
                message += '\n\n💡 Рекомендации:\n\n' + data.recommendations;
            }

            // Create a modal to show the summary
            showSummaryModal(data);

        } else {
            showAlert('Ошибка при генерации сводки: ' + (data.detail || 'Неизвестная ошибка'), 'danger');
        }
    } catch (error) {
        console.error('Summary error:', error);
        showAlert('Ошибка при генерации сводки', 'danger');
    }
}

async function sendSummary() {
    const chatId = document.getElementById('summaryChatSelect').value;

    if (!chatId) {
        showAlert('Выберите чат для отправки сводки', 'warning');
        return;
    }

    if (!confirm('Отправить сводку в чат?')) {
        return;
    }

    try {
        const response = await apiCall(`/api/summary/send?chat_id=${chatId}`, {
            method: 'POST'
        });

        const data = await response.json();

        if (response.ok) {
            showAlert('Сводка успешно отправлена в чат!', 'success');
        } else {
            showAlert('Ошибка при отправке: ' + (data.detail || 'Неизвестная ошибка'), 'danger');
        }
    } catch (error) {
        console.error('Send summary error:', error);
        showAlert('Ошибка при отправке сводки', 'danger');
    }
}

// ========== Feedback ==========

async function sendFeedback() {
    const category = document.getElementById('feedbackCategory').value;
    const message = document.getElementById('feedbackMessage').value.trim();

    if (!message) {
        showAlert('Напишите сообщение', 'warning');
        return;
    }

    try {
        const response = await apiCall('/api/feedback', {
            method: 'POST',
            body: JSON.stringify({ category, message })
        });

        const data = await response.json();

        if (response.ok) {
            showAlert('Спасибо за отзыв!', 'success');
            document.getElementById('feedbackMessage').value = '';
        } else {
            showAlert('Ошибка отправки: ' + (data.detail || 'Неизвестная ошибка'), 'danger');
        }
    } catch (error) {
        console.error('Feedback error:', error);
        showAlert('Ошибка отправки отзыва', 'danger');
    }
}

function showSummaryModal(data) {
    // Remove existing modal
    const existingModal = document.getElementById('summaryModal');
    if (existingModal) existingModal.remove();

    // Create modal
    const modal = document.createElement('div');
    modal.id = 'summaryModal';
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
                <h3 style="margin-bottom: 10px; color: var(--secondary-color);">💡 Рекомендации</h3>
                <div style="white-space: pre-wrap; margin-bottom: 15px;">${escapeHtml(data.recommendations)}</div>
            ` : ''}
            <button class="btn btn-primary" onclick="document.getElementById('summaryModal').remove()">Закрыть</button>
        </div>
    `;

    document.body.appendChild(modal);
}

// ========== Utility Functions ==========

function showAlert(message, type = 'info') {
    const container = document.getElementById('alertContainer');

    const alert = document.createElement('div');
    alert.className = `alert alert-${type}`;
    alert.textContent = message;

    container.appendChild(alert);

    setTimeout(() => {
        alert.remove();
    }, 5000);
}

function escapeHtml(text) {
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
}

async function logout() {
    try {
        // Notify server about logout (for logging/audit purposes)
        if (currentToken) {
            await fetch('/api/auth/logout', {
                method: 'POST',
                headers: { 'Authorization': `Bearer ${currentToken}` }
            }).catch(() => {}); // Ignore errors - we're logging out anyway
        }
    } finally {
        // Always clear local storage and redirect
        localStorage.removeItem('token');
        localStorage.removeItem('username');
        localStorage.removeItem('is_superadmin');
        currentToken = null;
        window.location.href = '/login';
    }
}

// ========== Event Listeners ==========

document.getElementById('chatSelect').addEventListener('change', loadData);
document.getElementById('daysSelect').addEventListener('change', loadData);

// Auto-refresh every 5 minutes
setInterval(loadData, 5 * 60 * 1000);
