// ==================== ФУНКЦИИ ДЛЯ РАБОТЫ С ФОРМОЙ ====================

let itemRowCounter = 1;
let currentShipmentForDeletion = null;
let currentItemForDeletion = null;

// Добавить строку товара
function addItemRow() {
    const tbody = document.getElementById('itemsTableBody');
    const newRow = document.createElement('tr');
    newRow.id = `itemRow_${itemRowCounter}`;
    
    newRow.innerHTML = `
        <td>
            <input type="text" class="form-control form-control-sm item-name" 
                   placeholder="Название товара" required>
        </td>
        <td>
            <div class="input-group input-group-sm">
                <input type="number" class="form-control item-cost" 
                       step="0.01" min="0" value="10.50" required>
                <span class="input-group-text">BYN</span>
            </div>
        </td>
        <td>
            <div class="input-group input-group-sm">
                <input type="number" class="form-control item-price" 
                       step="0.01" min="0" value="15.00" required>
                <span class="input-group-text">BYN</span>
            </div>
        </td>
        <td>
            <button type="button" class="btn btn-sm btn-danger" 
                    onclick="removeItemRow(${itemRowCounter})">
                <i class="fas fa-trash"></i>
            </button>
        </td>
    `;
    
    tbody.appendChild(newRow);
    itemRowCounter++;
    
    // Активируем кнопку удаления для первой строки
    if (itemRowCounter === 2) {
        document.querySelector('#itemRow_0 .btn-danger').removeAttribute('disabled');
    }
}

// Удалить строку товара
function removeItemRow(rowId) {
    const row = document.getElementById(`itemRow_${rowId}`);
    if (row) {
        row.remove();
    }
    
    // Проверяем, осталась ли хотя бы одна строка
    const remainingRows = document.querySelectorAll('#itemsTableBody tr');
    if (remainingRows.length === 1) {
        // Деактивируем кнопку удаления для последней строки
        document.querySelector('#itemRow_0 .btn-danger').setAttribute('disabled', 'disabled');
    }
}

// Создать поставку с товарами
function createShipmentWithItems() {
    const orderDate = document.getElementById('shipmentOrderDate').value;
    const status = document.getElementById('shipmentStatus').value;
    
    if (!orderDate) {
        showToast('Укажите дату заказа', 'warning');
        return;
    }
    
    // Собираем данные о товарах
    const items = [];
    const itemRows = document.querySelectorAll('#itemsTableBody tr');
    
    if (itemRows.length === 0) {
        showToast('Добавьте хотя бы один товар в поставку', 'warning');
        return;
    }
    
    let hasErrors = false;
    itemRows.forEach((row, index) => {
        const nameInput = row.querySelector('.item-name');
        const costInput = row.querySelector('.item-cost');
        const priceInput = row.querySelector('.item-price');
        
        // Проверяем заполненность полей
        if (!nameInput || !nameInput.value.trim()) {
            showToast(`Товар ${index + 1}: укажите название`, 'warning');
            hasErrors = true;
            return;
        }
        
        const cost = parseFloat(costInput.value);
        const price = parseFloat(priceInput.value);
        
        if (isNaN(cost) || cost < 0) {
            showToast(`Товар ${index + 1}: некорректная себестоимость`, 'warning');
            hasErrors = true;
            return;
        }
        
        if (isNaN(price) || price < 0) {
            showToast(`Товар ${index + 1}: некорректная цена продажи`, 'warning');
            hasErrors = true;
            return;
        }
        
        items.push({
            name: nameInput.value.trim(),
            cost_price: cost,
            sell_price: price
        });
    });
    
    if (hasErrors || items.length === 0) {
        return;
    }
    
    showLoading('Создание поставки с товарами...');
    
    // Сначала создаем поставку
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
        if (data.success) {
            // Затем добавляем товары в поставку
            return fetch(`/seller/shipments/${data.shipment_id}/add_items`, {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({
                    items: items,
                    status: status
                })
            });
        } else {
            throw new Error(data.error || 'Ошибка создания поставки');
        }
    })
    .then(response => response.json())
    .then(data => {
        hideLoading();
        if (data.success) {
            showToast(`Создана поставка с ${data.added_count} товарами!`, 'success');
            bootstrap.Modal.getInstance(document.getElementById('addShipmentModal')).hide();
            
            // Сбрасываем форму
            document.getElementById('itemsTableBody').innerHTML = `
                <tr id="itemRow_0">
                    <td>
                        <input type="text" class="form-control form-control-sm" 
                               placeholder="Название товара" required>
                    </td>
                    <td>
                        <div class="input-group input-group-sm">
                            <input type="number" class="form-control" 
                                   step="0.01" min="0" value="10.50" required>
                            <span class="input-group-text">BYN</span>
                        </div>
                    </td>
                    <td>
                        <div class="input-group input-group-sm">
                            <input type="number" class="form-control" 
                                   step="0.01" min="0" value="15.00" required>
                            <span class="input-group-text">BYN</span>
                        </div>
                    </td>
                    <td>
                        <button type="button" class="btn btn-sm btn-danger" 
                                onclick="removeItemRow(0)" disabled>
                            <i class="fas fa-trash"></i>
                        </button>
                    </td>
                </tr>
            `;
            itemRowCounter = 1;
            
            // Обновляем список поставок
            loadShipments();
            setTimeout(() => location.reload(), 1000);
        } else {
            showToast('Ошибка: ' + data.error, 'danger');
        }
    })
    .catch(error => {
        hideLoading();
        showToast('Ошибка: ' + error.message, 'danger');
    });
}

// Показать диалог удаления поставки
function showDeleteShipmentModal(shipmentId, shipmentNumber, itemCount) {
    currentShipmentForDeletion = shipmentId;
    
    document.getElementById('deleteShipmentNumber').textContent = shipmentNumber;
    document.getElementById('deleteShipmentInfo').textContent = 
        `Поставка содержит ${itemCount} товар(ов).`;
    
    const modal = new bootstrap.Modal(document.getElementById('deleteShipmentModal'));
    modal.show();
}

// Подтвердить удаление поставки
function confirmDeleteShipment() {
    if (!currentShipmentForDeletion) return;
    
    showLoading('Удаление поставки...');
    
    fetch(`/seller/shipments/${currentShipmentForDeletion}/delete`, {
        method: 'POST',
        headers: {'Content-Type': 'application/json'}
    })
    .then(response => response.json())
    .then(data => {
        hideLoading();
        if (data.success) {
            showToast('Поставка успешно удалена', 'success');
            bootstrap.Modal.getInstance(document.getElementById('deleteShipmentModal')).hide();
            loadShipments();
            setTimeout(() => location.reload(), 1000);
        } else {
            showToast('Ошибка: ' + data.error, 'danger');
        }
    })
    .catch(error => {
        hideLoading();
        showToast('Ошибка сети: ' + error, 'danger');
    })
    .finally(() => {
        currentShipmentForDeletion = null;
    });
}

// Показать диалог удаления товара
function showDeleteItemModal(itemId, itemName, shipmentInfo = '') {
    currentItemForDeletion = itemId;
    
    document.getElementById('deleteItemName').textContent = itemName;
    document.getElementById('deleteItemInfo').textContent = 
        `ID товара: ${itemId}${shipmentInfo ? `, ${shipmentInfo}` : ''}`;
    
    const modal = new bootstrap.Modal(document.getElementById('deleteItemModal'));
    modal.show();
}

// Подтвердить удаление товара
function confirmDeleteItem() {
    if (!currentItemForDeletion) return;
    
    showLoading('Удаление товара...');
    
    fetch(`/seller/items/${currentItemForDeletion}/delete`, {
        method: 'POST',
        headers: {'Content-Type': 'application/json'}
    })
    .then(response => response.json())
    .then(data => {
        hideLoading();
        if (data.success) {
            showToast('Товар успешно удален', 'success');
            bootstrap.Modal.getInstance(document.getElementById('deleteItemModal')).hide();
            
            // Если мы в модальном окне товаров поставки, обновляем его
            if (currentShipmentId) {
                showShipmentItems(currentShipmentId, currentShipmentNumber);
            }
            
            // Обновляем страницу
            setTimeout(() => location.reload(), 1000);
        } else {
            showToast('Ошибка: ' + data.error, 'danger');
        }
    })
    .catch(error => {
        hideLoading();
        showToast('Ошибка сети: ' + error, 'danger');
    })
    .finally(() => {
        currentItemForDeletion = null;
    });
}

// Обновляем функцию showAddShipmentModal
function showAddShipmentModal() {
    // Сбрасываем форму
    document.getElementById('itemsTableBody').innerHTML = `
        <tr id="itemRow_0">
            <td>
                <input type="text" class="form-control form-control-sm" 
                       placeholder="Название товара" required>
            </td>
            <td>
                <div class="input-group input-group-sm">
                    <input type="number" class="form-control" 
                           step="0.01" min="0" value="10.50" required>
                    <span class="input-group-text">BYN</span>
                </div>
            </td>
            <td>
                <div class="input-group input-group-sm">
                    <input type="number" class="form-control" 
                           step="0.01" min="0" value="15.00" required>
                    <span class="input-group-text">BYN</span>
                </div>
            </td>
            <td>
                <button type="button" class="btn btn-sm btn-danger" 
                        onclick="removeItemRow(0)" disabled>
                    <i class="fas fa-trash"></i>
                </button>
            </td>
        </tr>
    `;
    itemRowCounter = 1;
    
    const modal = new bootstrap.Modal(document.getElementById('addShipmentModal'));
    modal.show();
}

// Удаляем старую функцию createShipment (заменяем на createShipmentWithItems)
// Старая функция больше не нужна
