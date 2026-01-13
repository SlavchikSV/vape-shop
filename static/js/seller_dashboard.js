// Глобальные переменные
let currentItemId = null;
let currentShipmentId = null;

// ==================== ПОСТАВКИ ====================

// Показать модальное окно добавления поставки
function showAddShipmentModal() {
    const modal = new bootstrap.Modal(document.getElementById('addShipmentModal'));
    modal.show();
}

// Создать поставку
function createShipment() {
    const orderDate = document.getElementById('shipmentOrderDate').value;
    const deliveryCost = parseFloat(document.getElementById('shipmentDeliveryCost').value) || 0;
    const itemsText = document.getElementById('shipmentItems').value.trim();
    
    if (!orderDate) {
        showToast('Укажите дату заказа', 'danger');
        return;
    }
    
    if (isNaN(deliveryCost) || deliveryCost < 0) {
        showToast('Некорректная стоимость доставки', 'danger');
        return;
    }
    
    // Парсим товары если есть
    const items = [];
    if (itemsText) {
        const lines = itemsText.split('\n').filter(line => line.trim());
        for (const line of lines) {
            const parts = line.split(',').map(part => part.trim());
            if (parts.length >= 3) {
                const name = parts[0];
                const costPrice = parseFloat(parts[1]);
                const sellPrice = parseFloat(parts[2]);
                
                if (!name || isNaN(costPrice) || isNaN(sellPrice)) {
                    showToast('Некорректный формат товаров', 'danger');
                    return;
                }
                
                items.push({
                    name: name,
                    cost_price: costPrice,
                    sell_price: sellPrice
                });
            }
        }
    }
    
    showLoading('Создание поставки...');
    
    fetch('/seller/shipments/create', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({
            order_date: orderDate,
            delivery_cost: deliveryCost,
            items: items
        })
    })
    .then(response => response.json())
    .then(data => {
        hideLoading();
        if (data.success) {
            showToast(`Поставка создана! №${data.shipment_number}`, 'success');
            bootstrap.Modal.getInstance(document.getElementById('addShipmentModal')).hide();
            setTimeout(() => location.reload(), 1000);
        } else {
            showToast('Ошибка: ' + data.error, 'danger');
        }
    })
    .catch(error => {
        hideLoading();
        showToast('Ошибка сети: ' + error, 'danger');
    });
}

// Показать модальное окно получения поставки
function showUpdateShipmentStatusModal(shipmentId) {
    currentShipmentId = shipmentId;
    document.getElementById('updateShipmentId').value = shipmentId;
    document.getElementById('shipmentReceivedDeliveryCost').value = '';
    
    const modal = new bootstrap.Modal(document.getElementById('updateShipmentStatusModal'));
    modal.show();
}

// Получить поставку
function receiveShipment() {
    const deliveryCost = parseFloat(document.getElementById('shipmentReceivedDeliveryCost').value);
    const shipmentId = document.getElementById('updateShipmentId').value;
    
    if (isNaN(deliveryCost) || deliveryCost < 0) {
        showToast('Укажите стоимость доставки', 'danger');
        return;
    }
    
    if (!confirm('Вы уверены, что хотите получить поставку? Будут списаны деньги за товары и доставку.')) {
        return;
    }
    
    showLoading('Получение поставки...');
    
    fetch(`/seller/shipments/${shipmentId}/update_status`, {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({
            status: 'в наличии',
            delivery_cost: deliveryCost
        })
    })
    .then(response => response.json())
    .then(data => {
        hideLoading();
        if (data.success) {
            showToast('Поставка получена!', 'success');
            bootstrap.Modal.getInstance(document.getElementById('updateShipmentStatusModal')).hide();
            setTimeout(() => location.reload(), 1000);
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
    currentShipmentId = shipmentId;
    document.getElementById('shipmentItemsTitle').textContent = `Товары поставки ${shipmentNumber}`;
    
    showLoading('Загрузка товаров...');
    
    // Здесь нужно добавить endpoint для получения товаров поставки
    // Пока просто покажем сообщение
    setTimeout(() => {
        hideLoading();
        document.getElementById('shipmentItemsList').innerHTML = `
            <div class="alert alert-info">
                <i class="fas fa-info-circle"></i>
                Функционал просмотра товаров поставки будет добавлен позже.
                Товары можно увидеть в общей таблице товаров.
            </div>
        `;
        
        const modal = new bootstrap.Modal(document.getElementById('shipmentItemsModal'));
        modal.show();
    }, 500);
}

// ==================== ТОВАРЫ ====================

// Показать модальное окно добавления товара
function showAddItemModal() {
    const modal = new bootstrap.Modal(document.getElementById('addItemModal'));
    modal.show();
}

// Добавить товар
function addItem() {
    const name = document.getElementById('itemName').value.trim();
    const costPrice = parseFloat(document.getElementById('itemCostPrice').value);
    const sellPrice = parseFloat(document.getElementById('itemSellPrice').value);
    const shipmentId = document.getElementById('itemShipment').value;
    const status = document.getElementById('itemStatus').value;
    
    if (!name) {
        showToast('Введите название товара', 'danger');
        return;
    }
    
    if (isNaN(costPrice) || costPrice < 0) {
        showToast('Некорректная себестоимость', 'danger');
        return;
    }
    
    if (isNaN(sellPrice) || sellPrice < 0) {
        showToast('Некорректная цена продажи', 'danger');
        return;
    }
    
    showLoading('Добавление товара...');
    
    fetch('/seller/items/add', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({
            name: name,
            cost_price: costPrice,
            sell_price: sellPrice,
            shipment_id: shipmentId || null,
            status: status
        })
    })
    .then(response => response.json())
    .then(data => {
        hideLoading();
        if (data.success) {
            showToast('Товар добавлен!', 'success');
            bootstrap.Modal.getInstance(document.getElementById('addItemModal')).hide();
            setTimeout(() => location.reload(), 1000);
        } else {
            showToast('Ошибка: ' + data.error, 'danger');
        }
    })
    .catch(error => {
        hideLoading();
        showToast('Ошибка сети: ' + error, 'danger');
    });
}

// Показать модальное окно изменения статуса товара
function showUpdateItemStatusModal(itemId, currentStatus) {
    currentItemId = itemId;
    document.getElementById('updateItemId').value = itemId;
    document.getElementById('newItemStatus').value = currentStatus;
    
    const modal = new bootstrap.Modal(document.getElementById('updateItemStatusModal'));
    modal.show();
}

// Обновить статус товара
function updateItemStatus() {
    const itemId = document.getElementById('updateItemId').value;
    const newStatus = document.getElementById('newItemStatus').value;
    
    if (!itemId || !newStatus) {
        showToast('Ошибка параметров', 'danger');
        return;
    }
    
    if (newStatus === 'продано') {
        if (!confirm('Вы уверены, что хотите отметить товар как проданный? Будет добавлена транзакция продажи.')) {
            return;
        }
    }
    
    showLoading('Обновление статуса...');
    
    fetch(`/seller/items/${itemId}/update_status`, {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({ status: newStatus })
    })
    .then(response => response.json())
    .then(data => {
        hideLoading();
        if (data.success) {
            showToast('Статус обновлен!', 'success');
            bootstrap.Modal.getInstance(document.getElementById('updateItemStatusModal')).hide();
            setTimeout(() => location.reload(), 1000);
        } else {
            showToast('Ошибка: ' + data.error, 'danger');
        }
    })
    .catch(error => {
        hideLoading();
        showToast('Ошибка сети: ' + error, 'danger');
    });
}

// Показать модальное окно изменения цены
function showUpdatePriceModal(itemId, currentPrice) {
    currentItemId = itemId;
    document.getElementById('updatePriceItemId').value = itemId;
    document.getElementById('newItemPrice').value = currentPrice;
    
    const modal = new bootstrap.Modal(document.getElementById('updatePriceModal'));
    modal.show();
}

// Обновить цену товара
function updateItemPrice() {
    const itemId = document.getElementById('updatePriceItemId').value;
    const newPrice = parseFloat(document.getElementById('newItemPrice').value);
    
    if (!itemId || isNaN(newPrice) || newPrice < 0) {
        showToast('Некорректная цена', 'danger');
        return;
    }
    
    showLoading('Обновление цены...');
    
    fetch(`/seller/items/${itemId}/update_price`, {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({ price: newPrice })
    })
    .then(response => response.json())
    .then(data => {
        hideLoading();
        if (data.success) {
            showToast('Цена обновлена!', 'success');
            bootstrap.Modal.getInstance(document.getElementById('updatePriceModal')).hide();
            setTimeout(() => location.reload(), 1000);
        } else {
            showToast('Ошибка: ' + data.error, 'danger');
        }
    })
    .catch(error => {
        hideLoading();
        showToast('Ошибка сети: ' + error, 'danger');
    });
}

// ==================== ТРАНЗАКЦИИ ====================

// Показать транзакции
function showTransactionsModal() {
    showLoading('Загрузка транзакций...');
    
    fetch('/seller/transactions')
        .then(response => response.json())
        .then(data => {
            hideLoading();
            
            let html = '';
            if (data.transactions && data.transactions.length > 0) {
                html += `
                <div class="alert alert-success mb-3">
                    <strong>Текущий капитал:</strong> ${data.capital.toFixed(2)} BYN
                </div>
                <div class="table-responsive">
                    <table class="table table-sm">
                        <thead>
                            <tr>
                                <th>Дата</th>
                                <th>Тип</th>
                                <th>Сумма</th>
                                <th>Описание</th>
                            </tr>
                        </thead>
                        <tbody>
                `;
                
                data.transactions.forEach(transaction => {
                    const typeClass = transaction.amount > 0 ? 'text-success' : 'text-danger';
                    const typeIcon = transaction.amount > 0 ? '↑' : '↓';
                    const typeText = transaction.type === 'продажа' ? 'Продажа' :
                                   transaction.type === 'закупка' ? 'Закупка' :
                                   transaction.type === 'доставка' ? 'Доставка' : transaction.type;
                    
                    html += `
                    <tr>
                        <td>${transaction.date}</td>
                        <td>${typeText}</td>
                        <td class="${typeClass}">
                            <strong>${typeIcon} ${Math.abs(transaction.amount).toFixed(2)} BYN</strong>
                        </td>
                        <td>${transaction.note || ''}</td>
                    </tr>
                    `;
                });
                
                html += `
                        </tbody>
                    </table>
                </div>
                `;
            } else {
                html = '<div class="alert alert-info">Нет транзакций</div>';
            }
            
            document.getElementById('transactionsList').innerHTML = html;
            
            const modal = new bootstrap.Modal(document.getElementById('transactionsModal'));
            modal.show();
        })
        .catch(error => {
            hideLoading();
            showToast('Ошибка загрузки транзакций: ' + error, 'danger');
        });
}

// ==================== ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ ====================

// Показать уведомление
function showToast(message, type = 'info') {
    // Используем функцию из base.html
    if (typeof window.showToast === 'function') {
        window.showToast(message, type);
    } else {
        alert(message);
    }
}

// Показать загрузку
function showLoading(message = 'Загрузка...') {
    let overlay = document.getElementById('loadingOverlay');
    if (!overlay) {
        overlay = document.createElement('div');
        overlay.id = 'loadingOverlay';
        overlay.style.cssText = `
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
            color: white;
        `;
        document.body.appendChild(overlay);
    }
    
    overlay.innerHTML = `
    <div class="text-center">
        <div class="spinner-border text-light" style="width: 3rem; height: 3rem;" role="status">
            <span class="visually-hidden">Loading...</span>
        </div>
        <div class="mt-3">${message}</div>
    </div>
    `;
    overlay.style.display = 'flex';
}

// Скрыть загрузку
function hideLoading() {
    const overlay = document.getElementById('loadingOverlay');
    if (overlay) {
        overlay.style.display = 'none';
    }
}

// Поддержание активности сессии
setInterval(() => {
    fetch('/seller/keepalive').catch(() => {});
}, 60000); // Каждую минуту

// Инициализация
document.addEventListener('DOMContentLoaded', function() {
    // Автоматическое обновление каждые 2 минуты
    setInterval(() => {
        // Обновляем только если пользователь активен
        if (!document.hidden) {
            fetch('/seller/keepalive').catch(() => {});
        }
    }, 120000);
});
