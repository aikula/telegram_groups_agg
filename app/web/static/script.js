/**
 * Telegram Chat Analytics - Dashboard JavaScript
 */

// Global state
let activityChart = null;
let chats = [];
let currentToken = localStorage.getItem('token');
let isSuperadmin = false;

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

            // Add body class for CSS-based visibility control
            if (isSuperadmin) {
                document.body.classList.add('is-superadmin');
            }

            // Update page title
            if (!isSuperadmin) {
                document.title = 'Мои чаты - Telegram Chat Analytics';
            }
        } else {
            throw new Error('Failed to get user info');
        }
    } catch (error) {
        console.error('Error loading user info:', error);
        // Fallback to localStorage
        isSuperadmin = localStorage.getItem('is_superadmin') === 'true';
        const username = localStorage.getItem('username') || 'User';
        document.getElementById('userName').textContent = username;
        document.getElementById('userAvatar').textContent = username.charAt(0).toUpperCase();

        if (isSuperadmin) {
            document.body.classList.add('is-superadmin');
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
        logout();
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

        // Populate chat selects
        const chatSelect = document.getElementById('chatSelect');
        const summaryChatSelect = document.getElementById('summaryChatSelect');

        // Save current selection
        const currentChat = chatSelect.value;

        // Clear and populate
        chatSelect.innerHTML = '<option value="">Все чаты</option>';
        summaryChatSelect.innerHTML = '<option value="">Выберите чат...</option>';

        chats.forEach(chat => {
            const option = `<option value="${chat.chat_id}">${chat.title}</option>`;
            chatSelect.innerHTML += option;
            summaryChatSelect.innerHTML += option;
        });

        // Restore selection
        chatSelect.value = currentChat;

        // Update active chats count
        document.getElementById('activeChats').textContent = chats.length;

    } catch (error) {
        console.error('Error loading chats:', error);
        showAlert('Ошибка загрузки списка чатов', 'danger');
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

function logout() {
    localStorage.removeItem('token');
    localStorage.removeItem('username');
    window.location.href = '/login';
}

// ========== Event Listeners ==========

document.getElementById('chatSelect').addEventListener('change', loadData);
document.getElementById('daysSelect').addEventListener('change', loadData);

// Auto-refresh every 5 minutes
setInterval(loadData, 5 * 60 * 1000);
