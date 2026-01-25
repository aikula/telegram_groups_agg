/**
 * Telegram Chat Analytics - Dashboard JavaScript
 */

// Global state
let activityChart = null;
let chats = [];
let currentToken = localStorage.getItem('token');

// Check authentication on load
document.addEventListener('DOMContentLoaded', () => {
    if (!currentToken) {
        window.location.href = '/login';
        return;
    }

    // Set user info
    const username = localStorage.getItem('username') || 'Admin';
    document.getElementById('userName').textContent = username;
    document.getElementById('userAvatar').textContent = username.charAt(0).toUpperCase();

    // Initialize
    initChart();
    loadChats();
    loadData();
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
        const response = await apiCall('/api/chats?active_only=true');
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
            const option = `<option value="${chat.chat_id}">${chat.chat_name}</option>`;
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
        const text = msg.message_text || '[медиа]';
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
