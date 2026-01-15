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
