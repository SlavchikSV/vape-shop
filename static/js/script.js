// Поддержание активности каждую минуту
function startKeepAlive() {
    setInterval(() => {
        fetch('/seller/keepalive').catch(e => console.log('Keepalive error:', e));
    }, 60000);
}

// Добавление товара
function addItem() {
    const name = prompt('Название товара:');
    if (!name) return;
    
    const cost = parseFloat(prompt('Себестоимость (BYN):'));
    if (isNaN(cost)) return;
    
    const sell = parseFloat(prompt('Цена продажи (BYN):'));
    if (isNaN(sell)) return;
    
    const status = prompt('Статус (в наличии/в пути/продано/взял себе):', 'в наличии');
    if (!status) return;
    
    fetch('/seller/add', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({
            name: name,
            cost_price: cost,
            sell_price: sell,
            status: status
        })
    })
    .then(response => response.json())
    .then(data => {
        if (data.success) {
            alert('Товар добавлен! ID: ' + data.id);
            location.reload();
        } else {
            alert('Ошибка: ' + data.error);
        }
    })
    .catch(error => alert('Ошибка сети: ' + error));
}

// Изменение статуса
function updateStatus(itemId, currentStatus) {
    // Показываем модальное окно вместо prompt
    showUpdateItemStatusModal(itemId, currentStatus);
}

// Функция для показа модального окна изменения статуса товара
function showUpdateItemStatusModal(itemId, currentStatus) {
    // Запрашиваем название товара
    fetch(`/seller/item_info/${itemId}`)
        .then(response => response.json())
        .then(data => {
            if (data.success) {
                // Создаем модальное окно
                const modalId = `update-item-status-${itemId}`;
                let modalDiv = document.getElementById(modalId);
                
                if (!modalDiv) {
                    modalDiv = document.createElement('div');
                    modalDiv.className = 'modal fade';
                    modalDiv.id = modalId;
                    modalDiv.innerHTML = `
                    <div class="modal-dialog">
                        <div class="modal-content">
                            <div class="modal-header bg-warning">
                                <h5 class="modal-title">
                                    <i class="fas fa-sync"></i> Изменить статус товара
                                </h5>
                                <button type="button" class="btn-close" data-bs-dismiss="modal"></button>
                            </div>
                            <div class="modal-body">
                                <form id="${modalId}-form">
                                    <div class="mb-3">
                                        <label class="form-label">Товар:</label>
                                        <input type="text" class="form-control" value="${data.item.name.replace(/'/g, "\\'")}" readonly>
                                    </div>
                                    <div class="mb-3">
                                        <label class="form-label">Новый статус:</label>
                                        <select class="form-control" id="${modalId}-statusSelect" required>
                                            <option value="в наличии" ${currentStatus === 'в наличии' ? 'selected' : ''}>В наличии</option>
                                            <option value="продано" ${currentStatus === 'продано' ? 'selected' : ''}>Продано</option>
                                            <option value="зарезервировано" ${currentStatus === 'зарезервировано' ? 'selected' : ''}>Зарезервировано</option>
                                            <option value="взял себе" ${currentStatus === 'взял себе' ? 'selected' : ''}>Взял себе</option>
                                        </select>
                                    </div>
                                    <div class="alert alert-info">
                                        <i class="fas fa-info-circle"></i>
                                        При смене статуса на "продано" будет создана транзакция продажи.
                                    </div>
                                </form>
                            </div>
                            <div class="modal-footer">
                                <button type="button" class="btn btn-secondary" data-bs-dismiss="modal">Отмена</button>
                                <button type="button" class="btn btn-warning" onclick="confirmUpdateItemStatus(${itemId}, '${modalId}')">
                                    <i class="fas fa-check"></i> Обновить статус
                                </button>
                            </div>
                        </div>
                    </div>
                    `;
                    document.body.appendChild(modalDiv);
                }
                
                const modal = new bootstrap.Modal(modalDiv);
                modal.show();
            } else {
                alert('Ошибка: ' + data.error);
            }
        })
        .catch(error => {
            alert('Ошибка сети: ' + error);
        });
}

// Функция для подтверждения изменения статуса товара
function confirmUpdateItemStatus(itemId, modalId) {
    const statusSelect = document.getElementById(`${modalId}-statusSelect`);
    const newStatus = statusSelect.value;
    
    if (!newStatus) {
        alert('Выберите статус');
        return;
    }
    
    fetch(`/seller/update/${itemId}`, {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({status: newStatus})
    })
    .then(response => response.json())
    .then(data => {
        if (data.success) {
            alert('Статус обновлён!');
            
            // Закрываем модальное окно
            const modal = bootstrap.Modal.getInstance(document.getElementById(modalId));
            if (modal) modal.hide();
            
            location.reload();
        } else {
            alert('Ошибка: ' + data.error);
        }
    })
    .catch(error => alert('Ошибка сети: ' + error));
}

// Инициализация после загрузки страницы
document.addEventListener('DOMContentLoaded', function() {
    // Если мы на странице продавца
    if (document.querySelector('.update-btn')) {
        startKeepAlive();
        
        // Обработчики для кнопок "Сменить статус"
        document.querySelectorAll('.update-btn').forEach(button => {
            button.addEventListener('click', function() {
                const itemId = this.dataset.id;
                const currentStatus = this.dataset.status;
                updateStatus(itemId, currentStatus);
            });
        });
        
        // Обработчик для кнопки "Добавить товар"
        const addBtn = document.querySelector('#add-item-btn');
        if (addBtn) {
            addBtn.addEventListener('click', addItem);
        }
    }

});

// ==================== ОТЛАДКА И АДМИНИСТРИРОВАНИЕ ====================

// Горячие клавиши для администратора
document.addEventListener('keydown', function(e) {
    // Ctrl+Shift+D - панель отладки
    if (e.ctrlKey && e.shiftKey && e.key === 'D') {
        e.preventDefault();
        
        // Проверяем, является ли пользователь администратором
        const sellerUsername = '{{ session.get("seller_username", "") }}';
        if (sellerUsername === 'SlavchikSV') {
            window.location.href = '/seller/debug';
        } else {
            console.log('Панель отладки доступна только администратору SlavchikSV');
        }
    }
    
    // Ctrl+Shift+L - очистить консоль (для разработки)
    if (e.ctrlKey && e.shiftKey && e.key === 'L') {
        console.clear();
        console.log('✅ Консоль очищена');
    }
});

// Функция для проверки прав администратора
function checkAdminAccess() {
    // Проверяем, является ли текущий пользователь администратором
    const sellerUsername = '{{ session.get("seller_username", "") }}';
    return sellerUsername === 'SlavchikSV';
}

// Добавляем иконку отладки для администратора
function addDebugIconIfAdmin() {
    if (checkAdminAccess()) {
        // Создаем стили для иконки
        const style = document.createElement('style');
        style.textContent = `
            .debug-icon {
                position: fixed;
                bottom: 20px;
                left: 20px;
                z-index: 9998;
                opacity: 0.3;
                transition: opacity 0.3s, transform 0.3s;
            }
            
            .debug-icon:hover {
                opacity: 1;
                transform: scale(1.1);
            }
        `;
        document.head.appendChild(style);
        
        // Создаем иконку
        const debugIcon = document.createElement('a');
        debugIcon.href = '/seller/debug';
        debugIcon.className = 'debug-icon';
        debugIcon.title = 'Панель отладки (Ctrl+Shift+D)';
        debugIcon.innerHTML = `
            <div class="bg-danger text-white rounded-circle p-3 shadow-lg">
                <i class="fas fa-bug fa-2x"></i>
            </div>
        `;
        
        // Добавляем иконку в документ
        document.body.appendChild(debugIcon);
    }
}

// Добавляем иконку отладки при загрузке страницы
if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', addDebugIconIfAdmin);
} else {
    addDebugIconIfAdmin();
}

// Функции для отладки
if (checkAdminAccess()) {
    // Добавляем глобальную переменную debug с полезными функциями
    window.debug = {
        // Очистить логи
        clearLogs: function() {
            if (confirm('Очистить все логи действий и уведомления?')) {
                const password = prompt('Введите пароль администратора:');
                if (password) {
                    const formData = new FormData();
                    formData.append('action', 'clear_logs');
                    formData.append('password', password);
                    
                    fetch('/seller/debug', {
                        method: 'POST',
                        body: formData
                    }).then(response => {
                        if (response.ok) {
                            location.reload();
                        }
                    });
                }
            }
        },
        
        // Получить статистику БД
        getDbStats: function() {
            fetch('/seller/debug/api/statistics')
                .then(response => response.json())
                .then(data => {
                    console.log('📊 Статистика базы данных:', data.statistics);
                });
        },
        
        // Проверить активные сессии
        checkSessions: function() {
            fetch('/seller/active_sellers')
                .then(response => response.json())
                .then(data => {
                    console.log('👥 Активные сессии:', data.active_sellers);
                });
        }
    };
    
    console.log('🔧 Панель отладки доступна. Используйте Ctrl+Shift+D для открытия.');
    console.log('📋 Доступные команды: debug.clearLogs(), debug.getDbStats(), debug.checkSessions()');
}


