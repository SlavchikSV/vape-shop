// ==================== УПРАВЛЕНИЕ ПОСТАВКАМИ ====================
let currentShipmentId = null;
let currentShipmentNumber = null;

// Показать модальное окно добавления поставки
function showAddShipmentModal() {
    const modal = new bootstrap.Modal(document.getElementById('addShipmentModal'));
    modal.show();
}

// Создать поставку
function createShipment() {
    const orderDate = document.getElementById('shipmentOrderDate').value;
    const isWholesale = document.getElementById('shipmentIsWholesale').checked;
    
    if (!orderDate) {
        showToast('Укажите дату заказа', 'warning');
        return;
    }
    
    fetch('/seller/shipments/create', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({
            order_date: orderDate,
            is_wholesale: isWholesale
        })
    })
    .then(response => response.json())
    .then(data => {
        if (data.success) {
            showToast(`Поставка создана! Номер: ${data.shipment_number}`, 'success');
            bootstrap.Modal.getInstance(document.getElementById('addShipmentModal')).hide();
            loadShipments();
        } else {
            showToast('Ошибка: ' + data.error, 'danger');
        }
    })
    .catch(error => showToast('Ошибка сети: ' + error, 'danger'));
}

// Загрузить список поставок
function loadShipments() {
    const section = document.getElementById('shipments-section');
    if (section) section.style.display = 'block';
    
    fetch('/seller/shipments')
        .then(response => response.json())
        .then(data => {
            if (data.shipments) {
                displayShipments(data.shipments);
            } else {
                showToast('Ошибка загрузки поставок', 'danger');
            }
        })
        .catch(error => {
            console.error('Ошибка загрузки поставок:', error);
            const container = document.getElementById('shipments-list');
            if (container) {
                container.innerHTML = '<div class="alert alert-danger">Ошибка загрузки поставок</div>';
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
            'продано': 'danger'
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
                    <p><i class="fas fa-flag"></i> <strong>Статус:</strong> 
                        <span class="badge bg-${statusClass}">${shipment.status}</span>
                    </p>
                    ${shipment.received_date ? 
                      `<p><i class="fas fa-calendar-check"></i> <strong>Получено:</strong> ${shipment.received_date}</p>` : ''}
                    ${shipment.delivery_cost > 0 ? 
                      `<p><i class="fas fa-truck"></i> <strong>Доставка:</strong> ${shipment.delivery_cost} BYN</p>` : ''}
                    <p><i class="fas fa-clock"></i> <strong>Создана:</strong> ${shipment.created_at}</p>
                    
                    <div class="btn-group btn-group-sm mt-2 w-100">
                        <button class="btn btn-outline-primary" 
                                onclick="showAddItemsToShipment(${shipment.id}, '${shipment.shipment_number}')"
                                ${shipment.status === 'в наличии' || shipment.status === 'продано' ? 'disabled' : ''}>
                            <i class="fas fa-plus"></i> Товары
                        </button>
                        <button class="btn btn-outline-warning" 
                                onclick="showUpdateShipmentStatusModal(${shipment.id}, '${shipment.status}')"
                                ${shipment.status !== 'в пути' ? 'disabled' : ''}>
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

// Добавить строку товара
function addItemRow() {
    const container = document.getElementById('itemsContainer');
    const newRow = document.createElement('div');
    newRow.className = 'item-row mb-3 border p-3 rounded';
    newRow.innerHTML = `
        <div class="row">
            <div class="col-md-5">
                <label class="form-label">Название:</label>
                <input type="text" class="form-control item-name" 
                       placeholder="Название товара">
            </div>
            <div class="col-md-3">
                <label class="form-label">Себестоимость:</label>
                <input type="number" class="form-control item-cost" 
                       step="0.01" min="0" placeholder="0.00">
            </div>
            <div class="col-md-3">
                <label class="form-label">Цена продажи:</label>
                <input type="number" class="form-control item-price" 
                       step="0.01" min="0" placeholder="0.00">
            </div>
            <div class="col-md-1 d-flex align-items-end">
                <button type="button" class="btn btn-danger btn-sm" onclick="removeItemRow(this)">
                    <i class="fas fa-times"></i>
                </button>
            </div>
        </div>
    `;
    container.appendChild(newRow);
}

// Удалить строку товара
function removeItemRow(button) {
    const row = button.closest('.item-row');
    if (row) {
        row.remove();
    }
}

// Показать модальное окно добавления товаров в поставку
function showAddItemsToShipment(shipmentId, shipmentNumber) {
    currentShipmentId = shipmentId;
    currentShipmentNumber = shipmentNumber;
    
    document.getElementById('itemsContainer').innerHTML = `
        <div class="item-row mb-3 border p-3 rounded">
            <div class="row">
                <div class="col-md-5">
                    <label class="form-label">Название:</label>
                    <input type="text" class="form-control item-name" 
                           placeholder="Название товара">
                </div>
                <div class="col-md-3">
                    <label class="form-label">Себестоимость:</label>
                    <input type="number" class="form-control item-cost" 
                           step="0.01" min="0" placeholder="0.00">
                </div>
                <div class="col-md-3">
                    <label class="form-label">Цена продажи:</label>
                    <input type="number" class="form-control item-price" 
                           step="0.01" min="0" placeholder="0.00">
                </div>
                <div class="col-md-1 d-flex align-items-end">
                    <button type="button" class="btn btn-danger btn-sm" onclick="removeItemRow(this)">
                        <i class="fas fa-times"></i>
                    </button>
                </div>
            </div>
        </div>
    `;
    
    const modal = new bootstrap.Modal(document.getElementById('addItemsModal'));
    modal.show();
}

// Добавить товары в поставку
function addItemsToShipment() {
    const itemRows = document.querySelectorAll('.item-row');
    const items = [];
    
    itemRows.forEach(row => {
        const name = row.querySelector('.item-name').value.trim();
        const cost = parseFloat(row.querySelector('.item-cost').value);
        const price = parseFloat(row.querySelector('.item-price').value);
        
        if (name && !isNaN(cost) && cost >= 0 && !isNaN(price) && price >= 0) {
            items.push({
                name: name,
                cost_price: cost,
                sell_price: price
            });
        }
    });
    
    if (items.length === 0) {
        showToast('Добавьте хотя бы один корректный товар', 'warning');
        return;
    }
    
    fetch(`/seller/shipments/${currentShipmentId}/add_items`, {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({ items: items })
    })
    .then(response => response.json())
    .then(data => {
        if (data.success) {
            showToast(`Добавлено ${data.added_count} товаров`, 'success');
            bootstrap.Modal.getInstance(document.getElementById('addItemsModal')).hide();
            loadShipments();
            setTimeout(() => location.reload(), 1000);
        } else {
            showToast('Ошибка: ' + data.error, 'danger');
        }
    })
    .catch(error => showToast('Ошибка сети: ' + error, 'danger'));
}

// Показать модальное окно изменения статуса поставки
function showUpdateShipmentStatusModal(shipmentId, currentStatus) {
    currentShipmentId = shipmentId;
    
    const modal = new bootstrap.Modal(document.getElementById('updateShipmentStatusModal'));
    modal.show();
}

// Подтвердить изменение статуса поставки
function confirmUpdateShipmentStatus() {
    const receivedDate = document.getElementById('shipmentReceivedDate').value;
    const deliveryCost = parseFloat(document.getElementById('shipmentDeliveryCost').value);
    
    if (!receivedDate) {
        showToast('Укажите дату получения', 'warning');
        return;
    }
    
    if (isNaN(deliveryCost) || deliveryCost < 0) {
        showToast('Укажите корректную стоимость доставки', 'warning');
        return;
    }
    
    if (!confirm(`Изменить статус поставки на "в наличии"? Будут созданы транзакции закупки и доставки.`)) {
        return;
    }
    
    fetch(`/seller/shipments/${currentShipmentId}/update_status`, {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({
            status: 'в наличии',
            received_date: receivedDate,
            delivery_cost: deliveryCost
        })
    })
    .then(response => response.json())
    .then(data => {
        if (data.success) {
            showToast('Статус поставки изменен', 'success');
            bootstrap.Modal.getInstance(document.getElementById('updateShipmentStatusModal')).hide();
            loadShipments();
            setTimeout(() => location.reload(), 1000);
        } else {
            showToast('Ошибка: ' + data.error, 'danger');
        }
    })
    .catch(error => showToast('Ошибка сети: ' + error, 'danger'));
}

// Показать товары поставки
function showShipmentItems(shipmentId, shipmentNumber) {
    fetch(`/seller/items/shipment/${shipmentId}`)
        .then(response => response.json())
        .then(data => {
            displayShipmentItems(data.items, shipmentId, shipmentNumber);
        })
        .catch(error => {
            console.error('Ошибка загрузки товаров:', error);
            showToast('Ошибка загрузки товаров', 'danger');
        });
}

// Отобразить товары поставки
function displayShipmentItems(items, shipmentId, shipmentNumber) {
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
    
    const contentDiv = document.getElementById(`${modalId}-content`);
    let html = '';
    
    if (!items || items.length === 0) {
        html = '<div class="alert alert-info">Нет товаров в этой поставке</div>';
    } else {
        const totalCost = items.reduce((sum, item) => sum + parseFloat(item.cost_price || 0), 0);
        const totalSell = items.reduce((sum, item) => sum + parseFloat(item.manual_price || item.sell_price || 0), 0);
        const totalProfit = totalSell - totalCost;
        const soldCount = items.filter(item => item.status === 'продано').length;
        
        html += `
        <div class="alert alert-info mb-3">
            <div class="row">
                <div class="col-md-3">
                    <strong>Всего:</strong> ${items.length}
                </div>
                <div class="col-md-3">
                    <strong>Продано:</strong> ${soldCount}
                </div>
                <div class="col-md-3">
                    <strong>Себестоимость:</strong> ${totalCost.toFixed(2)} BYN
                </div>
                <div class="col-md-3">
                    <strong>Потенциальная прибыль:</strong> 
                    <span class="${totalProfit >= 0 ? 'text-success' : 'text-danger'}">
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
                'зарезервировано': 'info',
                'взял себе': 'secondary'
            }[item.status] || 'light';
            
            const displayPrice = item.manual_price || item.sell_price;
            
            html += `
            <tr class="status-${item.status.replace(' ', '-').toLowerCase()}">
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
                    <button class="btn btn-sm btn-outline-primary" 
                            onclick="window.updateItemStatus(${item.id}, '${item.status}')">
                        <i class="fas fa-edit"></i> Статус
                    </button>
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
    
    fetch(`/seller/items/${itemId}/update_price`, {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({ sell_price: newPrice })
    })
    .then(response => response.json())
    .then(data => {
        if (data.success) {
            showToast('Цена обновлена', 'success');
        } else {
            showToast('Ошибка: ' + data.error, 'danger');
        }
    })
    .catch(error => showToast('Ошибка сети: ' + error, 'danger'));
}

// Вспомогательные функции
function showToast(message, type = 'info') {
    const toastId = 'toast-' + Date.now();
    const toastHTML = `
    <div id="${toastId}" class="toast show" role="alert" style="position: fixed; top: 20px; right: 20px; z-index: 1060;">
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
            <button type="button" class="btn-close btn-close-white" onclick="document.getElementById('${toastId}').remove()"></button>
        </div>
        <div class="toast-body">
            ${message}
        </div>
    </div>
    `;
    
    document.body.insertAdjacentHTML('beforeend', toastHTML);
    
    setTimeout(() => {
        const toast = document.getElementById(toastId);
        if (toast) toast.remove();
    }, 3000);
}

// Инициализация
document.addEventListener('DOMContentLoaded', function() {
    const addShipmentBtn = document.getElementById('add-shipment-btn');
    if (addShipmentBtn) {
        addShipmentBtn.addEventListener('click', showAddShipmentModal);
    }
    
    const loadShipmentsBtn = document.getElementById('load-shipments-btn');
    if (loadShipmentsBtn) {
        loadShipmentsBtn.addEventListener('click', loadShipments);
    }
});
