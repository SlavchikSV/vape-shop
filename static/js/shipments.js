// ==================== УПРАВЛЕНИЕ ПОСТАВКАМИ ====================
// Глобальные переменные
let currentShipmentId = null;
let currentShipmentNumber = null;
let deleteMode = false;

// Показать модальное окно добавления поставки
function showAddShipmentModal() {
    const modal = new bootstrap.Modal(document.getElementById('addShipmentModal'));
    modal.show();
}

// Создать поставку
function createShipment() {
    const orderDate = document.getElementById('shipmentOrderDate').value;
    const status = 'в пути'; // Все новые поставки по умолчанию "в пути"
    
    if (!orderDate) {
        showToast('Укажите дату заказа', 'warning');
        return;
    }
    
    showLoading('Создание поставки...');
    
    fetch('/seller/shipments/create', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({
            order_date: orderDate,
            status: status
        })
    })
    .then(response => response.json())
    .then(data => {
        hideLoading();
        if (data.success) {
            showToast(`Поставка создана! Номер: ${data.shipment_number}`, 'success');
            bootstrap.Modal.getInstance(document.getElementById('addShipmentModal')).hide();
            loadShipments();
        } else {
            showToast('Ошибка: ' + data.error, 'danger');
        }
    })
    .catch(error => {
        hideLoading();
        showToast('Ошибка сети: ' + error, 'danger');
    });
}

// Загрузить список поставок
function loadShipments() {
    const section = document.getElementById('shipments-section');
    if (section) section.style.display = 'block';
    
    showLoading('Загрузка поставок...');
    
    fetch('/seller/shipments')
        .then(response => response.json())
        .then(data => {
            hideLoading();
            if (data.shipments) {
                displayShipments(data.shipments);
            } else {
                showToast('Ошибка загрузки поставок', 'danger');
            }
        })
        .catch(error => {
            hideLoading();
            console.error('Ошибка загрузки поставок:', error);
            const container = document.getElementById('shipments-list');
            if (container) {
                container.innerHTML = 
                    '<div class="alert alert-danger">Ошибка загрузки поставок</div>';
            }
        });
}

// Отобразить поставки
function displayShipments(shipments) {
    const container = document.getElementById('shipments-list');
    if (!container) return;
    
    if (!shipments || shipments.length === 0) {
        container.innerHTML = '<div class="alert alert-info">Нет поставок</div>';
        return;
    }
    
    let html = '<div class="row">';
    
    shipments.forEach(shipment => {
        const statusClass = {
            'в пути': 'warning',
            'в наличии': 'success',
            'завершена': 'secondary'
        }[shipment.status] || 'info';
        
        const hasItems = shipment.total_items > 0;
        const itemsText = hasItems ? 
            `${shipment.total_items} товар(ов)` : 
            '<span class="text-danger">Нет товаров</span>';
        
        html += `
        <div class="col-md-6 mb-3">
            <div class="card h-100">
                <div class="card-header bg-${statusClass} text-white d-flex justify-content-between">
                    <h6 class="mb-0">${shipment.shipment_number}</h6>
                    <span class="badge bg-light text-dark">${itemsText}</span>
                </div>
                <div class="card-body">
                    <p><i class="fas fa-calendar"></i> <strong>Дата заказа:</strong> ${shipment.order_date}</p>
                    <p><i class="fas fa-truck"></i> <strong>Доставка:</strong> ${shipment.delivery_cost} BYN</p>
                    <p><i class="fas fa-flag"></i> <strong>Статус:</strong> 
                        <span class="badge bg-${statusClass}">${shipment.status}</span>
                    </p>
                    ${shipment.received_date ? 
                      `<p><i class="fas fa-calendar-check"></i> <strong>Получено:</strong> ${shipment.received_date}</p>` : ''}
                    <p><i class="fas fa-clock"></i> <strong>Создана:</strong> ${formatDateTime(shipment.created_at)}</p>
                    
                    <div class="btn-group btn-group-sm mt-2 w-100">
                        <button class="btn btn-outline-primary" 
                                onclick="showAddItemsToShipment(${shipment.id}, '${shipment.shipment_number}')"
                                ${shipment.status === 'в наличии' ? 'disabled' : ''}>
                            <i class="fas fa-plus"></i> Товары
                        </button>
                        <button class="btn btn-outline-warning" 
                                onclick="showUpdateShipmentStatusModal(${shipment.id}, '${shipment.status}')">
                            <i class="fas fa-sync"></i> Статус
                        </button>
                        <button class="btn btn-outline-info" 
                                onclick="showShipmentItems(${shipment.id}, '${shipment.shipment_number}')">
                            <i class="fas fa-eye"></i> Просмотр
                        </button>
                    </div>
                </div>
            </div>
        </div>
        `;
    });
    
    html += '</div>';
    container.innerHTML = html;
}

// Показать модальное окно добавления товаров в поставку
function showAddItemsToShipment(shipmentId, shipmentNumber) {
    currentShipmentId = shipmentId;
    currentShipmentNumber = shipmentNumber;
    
    // Обновляем заголовок модального окна
    document.querySelector('#addItemsModal .modal-title').innerHTML = 
        `<i class="fas fa-boxes"></i> Добавить товары в поставку ${shipmentNumber}`;
    
    const modal = new bootstrap.Modal(document.getElementById('addItemsModal'));
    modal.show();
}

// Добавить несколько товаров в поставку
function addItemsToShipment() {
    const itemsText = document.getElementById('itemsTextArea').value.trim();
    
    if (!itemsText) {
        showToast('Введите товары', 'warning');
        return;
    }
    
    // Парсим товары (каждая строка = один товар)
    const lines = itemsText.split('\n').filter(line => line.trim());
    const items = [];
    const errors = [];
    
    lines.forEach((line, index) => {
        const parts = line.split(',').map(part => part.trim());
        if (parts.length >= 3) {
            const name = parts[0];
            const costPrice = parseFloat(parts[1]);
            const sellPrice = parseFloat(parts[2]);
            
            if (!name) {
                errors.push(`Строка ${index + 1}: нет названия`);
                return;
            }
            
            if (isNaN(costPrice) || costPrice < 0) {
                errors.push(`Строка ${index + 1}: некорректная себестоимость`);
                return;
            }
            
            if (isNaN(sellPrice) || sellPrice < 0) {
                errors.push(`Строка ${index + 1}: некорректная цена продажи`);
                return;
            }
            
            items.push({
                name: name,
                cost_price: costPrice,
                sell_price: sellPrice
            });
        } else {
            errors.push(`Строка ${index + 1}: неверный формат`);
        }
    });
    
    if (errors.length > 0) {
        showToast(`Ошибки в ${errors.length} строках. Проверьте формат.`, 'danger');
        return;
    }
    
    if (items.length === 0) {
        showToast('Нет корректных товаров для добавления', 'warning');
        return;
    }
    
    showLoading(`Добавление ${items.length} товаров...`);
    
    fetch(`/seller/shipments/${currentShipmentId}/add_items`, {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({
            items: items,
            status: document.getElementById('itemsStatus').value
        })
    })
    .then(response => response.json())
    .then(data => {
        hideLoading();
        if (data.success) {
            showToast(`Добавлено ${data.added_count} товаров в поставку ${currentShipmentNumber}`, 'success');
            bootstrap.Modal.getInstance(document.getElementById('addItemsModal')).hide();
            loadShipments();
            // Обновляем таблицу товаров через 1 секунду
            setTimeout(() => {
                if (typeof updateItemTable === 'function') {
                    updateItemTable();
                } else {
                    location.reload();
                }
            }, 1000);
        } else {
            showToast('Ошибка: ' + data.error, 'danger');
        }
    })
    .catch(error => {
        hideLoading();
        showToast('Ошибка сети: ' + error, 'danger');
    });
}

// Показать модальное окно изменения статуса поставки
function showUpdateShipmentStatusModal(shipmentId, currentStatus) {
    currentShipmentId = shipmentId;
    
    const modal = new bootstrap.Modal(document.getElementById('updateShipmentStatusModal'));
    const statusSelect = document.getElementById('newShipmentStatus');
    const dateGroup = document.getElementById('receivedDateGroup');
    const deliveryCostGroup = document.getElementById('deliveryCostGroup');
    
    // Устанавливаем текущий статус
    statusSelect.value = currentStatus;
    
    // Показываем/скрываем поля
    statusSelect.addEventListener('change', function() {
        const showDeliveryFields = this.value === 'в наличии';
        dateGroup.style.display = showDeliveryFields ? 'block' : 'none';
        deliveryCostGroup.style.display = showDeliveryFields ? 'block' : 'none';
    });
    
    // Инициализируем состояние
    const showDeliveryFields = currentStatus === 'в наличии';
    dateGroup.style.display = showDeliveryFields ? 'block' : 'none';
    deliveryCostGroup.style.display = showDeliveryFields ? 'block' : 'none';
    
    modal.show();
}

// Подтвердить изменение статуса поставки
function confirmUpdateShipmentStatus() {
    const newStatus = document.getElementById('newShipmentStatus').value;
    const receivedDate = newStatus === 'в наличии' ? 
        document.getElementById('shipmentReceivedDate').value : 
        null;
    const deliveryCost = newStatus === 'в наличии' ? 
        parseFloat(document.getElementById('shipmentDeliveryCost').value) || 0 : 
        0;
    
    if (newStatus === 'в наличии') {
        if (!receivedDate) {
            showToast('Укажите дату получения', 'warning');
            return;
        }
        if (isNaN(deliveryCost) || deliveryCost < 0) {
            showToast('Укажите корректную стоимость доставки', 'warning');
            return;
        }
    }
    
    const message = newStatus === 'в наличии' ? 
        `Вы уверены, что хотите изменить статус поставки на "${new_status}"? Все товары в поставке также изменят свой статус. Стоимость доставки ${deliveryCost} BYN будет вычтена из капитала.` :
        `Вы уверены, что хотите изменить статус поставки на "${new_status}"? Все товары в поставке также изменят свой статус.`;
    
    if (!confirm(message)) {
        return;
    }
    
    showLoading('Обновление статуса...');
    
    fetch(`/seller/shipments/${currentShipmentId}/update_status_with_delivery`, {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({
            status: newStatus,
            received_date: receivedDate,
            delivery_cost: deliveryCost
        })
    })
    .then(response => response.json())
    .then(data => {
        hideLoading();
        if (data.success) {
            showToast(`Статус поставки изменен на "${newStatus}"${deliveryCost > 0 ? ` (Доставка: ${deliveryCost} BYN)` : ''}`, 'success');
            bootstrap.Modal.getInstance(document.getElementById('updateShipmentStatusModal')).hide();
            loadShipments();
            setTimeout(() => {
                if (typeof updateItemTable === 'function') {
                    updateItemTable();
                } else {
                    location.reload();
                }
            }, 1000);
        } else {
            showToast('Ошибка: ' + data.error, 'danger');
        }
    })
    .catch(error => {
        hideLoading();
        showToast('Ошибка сети: ' + error, 'danger');
    });
}

// Показать товары поставки
function showShipmentItems(shipmentId, shipmentNumber) {
    showLoading('Загрузка товаров...');
    
    fetch(`/seller/items/shipment/${shipmentId}`)
        .then(response => response.json())
        .then(data => {
            hideLoading();
            displayShipmentItems(data.items, shipmentId, shipmentNumber);
        })
        .catch(error => {
            hideLoading();
            console.error('Ошибка загрузки товаров:', error);
            showToast('Ошибка загрузки товаров', 'danger');
        });
}

// Отобразить товары поставки
function displayShipmentItems(items, shipmentId, shipmentNumber) {
    // Создаем модальное окно
    const modalId = `shipment-items-${shipmentId}`;
    let modalDiv = document.getElementById(modalId);
    
    if (!modalDiv) {
        modalDiv = document.createElement('div');
        modalDiv.className = 'modal fade';
        modalDiv.id = modalId;
        modalDiv.innerHTML = `
        <div class="modal-dialog modal-xl">
            <div class="modal-content">
                <div class="modal-header bg-primary text-white">
                    <h5 class="modal-title">
                        <i class="fas fa-boxes"></i> Товары поставки ${shipmentNumber}
                    </h5>
                    <button type="button" class="btn-close btn-close-white" data-bs-dismiss="modal"></button>
                </div>
                <div class="modal-body">
                    <div id="${modalId}-content"></div>
                </div>
                <div class="modal-footer">
                    <button type="button" class="btn btn-secondary" data-bs-dismiss="modal">Закрыть</button>
                </div>
            </div>
        </div>
        `;
        document.body.appendChild(modalDiv);
    }
    
    // Заполняем контент
    const contentDiv = document.getElementById(`${modalId}-content`);
    let html = '';
    
    if (!items || items.length === 0) {
        html = '<div class="alert alert-info">Нет товаров в этой поставке</div>';
    } else {
        // Статистика
        const totalCost = items.reduce((sum, item) => sum + parseFloat(item.cost_price || 0), 0);
        const totalSell = items.reduce((sum, item) => sum + parseFloat(item.manual_price || item.sell_price || 0), 0);
        const totalProfit = totalSell - totalCost;
        
        html += `
        <div class="alert alert-info mb-3">
            <div class="row">
                <div class="col-md-3">
                    <strong>Товаров:</strong> ${items.length}
                </div>
                <div class="col-md-3">
                    <strong>Себестоимость:</strong> ${totalCost.toFixed(2)} BYN
                </div>
                <div class="col-md-3">
                    <strong>Цена продажи:</strong> ${totalSell.toFixed(2)} BYN
                </div>
                <div class="col-md-3">
                    <strong>Прибыль:</strong> <span class="${totalProfit >= 0 ? 'text-success' : 'text-danger'}">
                        ${totalProfit.toFixed(2)} BYN
                    </span>
                </div>
            </div>
        </div>
        
        <div class="table-responsive">
            <table class="table table-sm table-hover">
                <thead class="table-light">
                    <tr>
                        <th>ID</th>
                        <th>Название</th>
                        <th>Себест.</th>
                        <th>Цена</th>
                        <th>Статус</th>
                        <th>Дата</th>
                        <th>Действия</th>
                    </tr>
                </thead>
                <tbody>
        `;
        
        items.forEach(item => {
            const statusClass = {
                'в наличии': 'success',
                'в пути': 'warning',
                'продано': 'danger',
                'взял себе': 'info'
            }[item.status] || 'secondary';
            
            const displayPrice = item.manual_price || item.sell_price;
            const dateDisplay = item.status === 'в наличии' ? 
                (item.date_arrived ? item.date_arrived.slice(0, 10) : '—') :
                (item.status === 'продано' ? 
                    (item.date_sold ? item.date_sold.slice(0, 10) : '—') :
                    (item.status === 'взял себе' ? 
                        (item.date_taken ? item.date_taken.slice(0, 10) : '—') : '—'));
            
            html += `
            <tr>
                <td>${item.id}</td>
                <td>${item.name}</td>
                <td>${parseFloat(item.cost_price).toFixed(2)} BYN</td>
                <td>
                    <div class="input-group input-group-sm" style="width: 150px;">
                        <input type="number" class="form-control price-input" 
                               value="${parseFloat(displayPrice).toFixed(2)}" 
                               step="0.01" min="0"
                               id="price-${item.id}">
                        <button class="btn btn-outline-primary" type="button" 
                                onclick="updateItemPrice(${item.id})">
                            <i class="fas fa-save"></i>
                        </button>
                    </div>
                </td>
                <td>
                    <span class="badge bg-${statusClass}">${item.status}</span>
                </td>
                <td>
                    <small>${dateDisplay}</small>
                </td>
                <td>
                    ${deleteMode ? 
                    `<button class="btn btn-sm btn-danger" onclick="deleteItem(${item.id}, '${item.name}')">
                        <i class="fas fa-trash"></i>
                    </button>` : 
                    `<button class="btn btn-sm btn-outline-primary update-btn" 
                            onclick="updateStatus(${item.id}, '${item.status}')">
                        <i class="fas fa-edit"></i> Статус
                    </button>`}
                </td>
            </tr>
            `;
        });
        
        html += `
                </tbody>
            </table>
        </div>
        `;
    }
    
    contentDiv.innerHTML = html;
    
    // Показываем модальное окно
    const modal = new bootstrap.Modal(modalDiv);
    modal.show();
}

// Обновить цену товара
function updateItemPrice(itemId) {
    const input = document.getElementById(`price-${itemId}`);
    if (!input) return;
    
    const newPrice = parseFloat(input.value);
    if (isNaN(newPrice) || newPrice < 0) {
        showToast('Некорректная цена', 'warning');
        return;
    }
    
    if (!confirm(`Изменить цену товара на ${newPrice.toFixed(2)} BYN?`)) {
        return;
    }
    
    showLoading('Обновление цены...');
    
    fetch(`/seller/items/${itemId}/update_price`, {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({ sell_price: newPrice })
    })
    .then(response => response.json())
    .then(data => {
        hideLoading();
        if (data.success) {
            showToast('Цена обновлена', 'success');
        } else {
            showToast('Ошибка: ' + data.error, 'danger');
        }
    })
    .catch(error => {
        hideLoading();
        showToast('Ошибка сети: ' + error, 'danger');
    });
}

// Удалить товар (ТОЛЬКО ДЛЯ ТЕСТИРОВАНИЯ)
function deleteItem(itemId, itemName) {
    if (!confirm(`ВНИМАНИЕ: Вы собираетесь удалить товар "${itemName}". Это действие нельзя отменить. Продолжить?`)) {
        return;
    }
    
    showLoading('Удаление товара...');
    
    fetch(`/seller/items/${itemId}/delete`, {
        method: 'POST',
        headers: {'Content-Type': 'application/json'}
    })
    .then(response => response.json())
    .then(data => {
        hideLoading();
        if (data.success) {
            showToast('Товар удален', 'success');
            // Закрываем модальное окно и обновляем данные
            const modal = bootstrap.Modal.getInstance(document.querySelector('.modal.show'));
            if (modal) modal.hide();
            
            setTimeout(() => {
                if (currentShipmentId) {
                    showShipmentItems(currentShipmentId, currentShipmentNumber);
                }
                loadShipments();
                location.reload();
            }, 500);
        } else {
            showToast('Ошибка: ' + data.error, 'danger');
        }
    })
    .catch(error => {
        hideLoading();
        showToast('Ошибка сети: ' + error, 'danger');
    });
}

// Показать модальное окно добавления отдельного товара
function showAddSingleItemModal() {
    const modal = new bootstrap.Modal(document.getElementById('addSingleItemModal'));
    modal.show();
}

// Добавить отдельный товар
function addSingleItem() {
    const name = document.getElementById('singleItemName').value.trim();
    const costPrice = parseFloat(document.getElementById('singleItemCostPrice').value);
    const sellPrice = parseFloat(document.getElementById('singleItemSellPrice').value);
    const status = document.getElementById('singleItemStatus').value;
    
    if (!name) {
        showToast('Введите название товара', 'warning');
        return;
    }
    
    if (isNaN(costPrice) || costPrice < 0) {
        showToast('Укажите корректную себестоимость', 'warning');
        return;
    }
    
    if (isNaN(sellPrice) || sellPrice < 0) {
        showToast('Укажите корректную цену продажи', 'warning');
        return;
    }
    
    showLoading('Добавление товара...');
    
    // Используем существующий маршрут добавления товара
    fetch('/seller/add', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({
            name: name,
            cost_price: costPrice,
            sell_price: sellPrice,
            status: status
        })
    })
    .then(response => response.json())
    .then(data => {
        hideLoading();
        if (data.success) {
            showToast(`Товар добавлен! ID: ${data.id}`, 'success');
            bootstrap.Modal.getInstance(document.getElementById('addSingleItemModal')).hide();
            location.reload();
        } else {
            showToast('Ошибка: ' + data.error, 'danger');
        }
    })
    .catch(error => {
        hideLoading();
        showToast('Ошибка сети: ' + error, 'danger');
    });
}

// Включить/выключить режим удаления
function toggleDeleteMode() {
    deleteMode = !deleteMode;
    const btn = document.getElementById('delete-mode-btn');
    
    if (deleteMode) {
        btn.classList.remove('btn-danger');
        btn.classList.add('btn-warning');
        btn.innerHTML = '<i class="fas fa-exclamation-triangle"></i> Режим удаления ВКЛЮЧЕН';
        showToast('ВНИМАНИЕ: Режим удаления включен. Все кнопки редактирования заменены на кнопки удаления.', 'warning', 5000);
    } else {
        btn.classList.remove('btn-warning');
        btn.classList.add('btn-danger');
        btn.innerHTML = '<i class="fas fa-trash"></i> Режим удаления (тест)';
    }
    
    // Обновляем отображение кнопок в открытых модальных окнах
    if (currentShipmentId) {
        showShipmentItems(currentShipmentId, currentShipmentNumber);
    }
}

// Вспомогательные функции
function showToast(message, type = 'info', duration = 3000) {
    const toastId = 'toast-' + Date.now();
    const toastHTML = `
    <div id="${toastId}" class="toast show" role="alert" aria-live="assertive" aria-atomic="true">
        <div class="toast-header bg-${type} text-white">
            <strong class="me-auto">
                ${type === 'success' ? '<i class="fas fa-check-circle"></i>' : 
                  type === 'warning' ? '<i class="fas fa-exclamation-triangle"></i>' : 
                  type === 'danger' ? '<i class="fas fa-times-circle"></i>' : 
                  '<i class="fas fa-info-circle"></i>'}
                ${type === 'success' ? 'Успешно' : 
                  type === 'warning' ? 'Внимание' : 
                  type === 'danger' ? 'Ошибка' : 'Информация'}
            </strong>
            <button type="button" class="btn-close btn-close-white" data-bs-dismiss="toast"></button>
        </div>
        <div class="toast-body">
            ${message}
        </div>
    </div>
    `;
    
    const container = document.getElementById('toast-container');
    if (!container) {
        const newContainer = document.createElement('div');
        newContainer.id = 'toast-container';
        newContainer.className = 'position-fixed bottom-0 end-0 p-3';
        newContainer.style.zIndex = '1060';
        document.body.appendChild(newContainer);
        container = newContainer;
    }
    
    container.insertAdjacentHTML('beforeend', toastHTML);
    
    // Автоматическое удаление
    setTimeout(() => {
        const toast = document.getElementById(toastId);
        if (toast) {
            toast.remove();
        }
    }, duration);
}

function showLoading(message = 'Загрузка...') {
    let loadingDiv = document.getElementById('loading-overlay');
    if (!loadingDiv) {
        loadingDiv = document.createElement('div');
        loadingDiv.id = 'loading-overlay';
        loadingDiv.style.cssText = `
            position: fixed;
            top: 0;
            left: 0;
            width: 100%;
            height: 100%;
            background: rgba(0,0,0,0.5);
            z-index: 9999;
            display: flex;
            justify-content: center;
            align-items: center;
        `;
        document.body.appendChild(loadingDiv);
    }
    
    loadingDiv.innerHTML = `
    <div class="bg-white p-4 rounded shadow-lg text-center">
        <div class="spinner-border text-primary mb-2" role="status">
            <span class="visually-hidden">Загрузка...</span>
        </div>
        <div>${message}</div>
    </div>
    `;
    
    loadingDiv.style.display = 'flex';
}

function hideLoading() {
    const loadingDiv = document.getElementById('loading-overlay');
    if (loadingDiv) {
        loadingDiv.style.display = 'none';
    }
}

function formatDateTime(dateTimeStr) {
    if (!dateTimeStr) return '—';
    try {
        const date = new Date(dateTimeStr);
        return date.toLocaleString('ru-RU', {
            day: '2-digit',
            month: '2-digit',
            year: 'numeric',
            hour: '2-digit',
            minute: '2-digit'
        });
    } catch (e) {
        return dateTimeStr;
    }
}

// Инициализация при загрузке страницы
document.addEventListener('DOMContentLoaded', function() {
    // Добавляем обработчики для кнопок управления поставками
    const addShipmentBtn = document.getElementById('add-shipment-btn');
    if (addShipmentBtn) {
        addShipmentBtn.addEventListener('click', showAddShipmentModal);
    }
    
    const loadShipmentsBtn = document.getElementById('load-shipments-btn');
    if (loadShipmentsBtn) {
        loadShipmentsBtn.addEventListener('click', loadShipments);
    }
    
    const deleteModeBtn = document.getElementById('delete-mode-btn');
    if (deleteModeBtn) {
        deleteModeBtn.addEventListener('click', toggleDeleteMode);
    }
    
    const addSingleItemBtn = document.getElementById('add-single-item-btn');
    if (addSingleItemBtn) {
        addSingleItemBtn.addEventListener('click', showAddSingleItemModal);
    }
    
    // Добавляем обработчик изменения статуса для поля выбора статуса
    const statusSelect = document.getElementById('newShipmentStatus');
    if (statusSelect) {
        statusSelect.addEventListener('change', function() {
            const dateGroup = document.getElementById('receivedDateGroup');
            if (dateGroup) {
                dateGroup.style.display = this.value === 'в наличии' ? 'block' : 'none';
            }
        });
    }
});
