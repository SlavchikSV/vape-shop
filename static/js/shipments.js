// ==================== УПРАВЛЕНИЕ ПОСТАВКАМИ ====================
// Глобальные переменные
let currentShipmentId = null;
let currentShipmentNumber = null;
let itemRowCounter = 1;
let currentShipmentForDeletion = null;
let currentItemForDeletion = null;
let itemStatuses = [];

// Загрузить список статусов товаров
function loadItemStatuses() {
    fetch('/seller/item_statuses')
        .then(response => response.json())
        .then(data => {
            if (data.statuses) {
                itemStatuses = data.statuses;
            }
        })
        .catch(error => {
            console.error('Ошибка загрузки статусов:', error);
            itemStatuses = [
                {value: 'в наличии', label: 'В наличии'},
                {value: 'продано', label: 'Продано'},
                {value: 'зарезервировано', label: 'Зарезервировано'},
                {value: 'взял себе', label: 'Взял себе'},
                {value: 'в пути', label: 'В пути'},
            ];
        });
}

// ==================== ФУНКЦИИ ДЛЯ РАБОТЫ С ФОРМОЙ ====================

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

// Показать модальное окно добавления поставки
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
    
    // Генерируем номер поставки на клиенте для немедленного отображения
    const tempShipmentNumber = `SHIP-${Date.now().toString().slice(-6)}`;
    
    // Сначала создаем поставку
    fetch('/seller/shipments/create', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({
            order_date: orderDate,
            status: status
        })
    })
    .then(response => {
        if (!response.ok) {
            throw new Error(`HTTP ${response.status}: ${response.statusText}`);
        }
        const contentType = response.headers.get("content-type");
        if (contentType && contentType.includes("application/json")) {
            return response.json();
        } else {
            return response.text().then(text => {
                console.error("Non-JSON response:", text);
                throw new Error("Сервер вернул не JSON ответ");
            });
        }
    })
    .then(data => {
        if (data.success) {
            const shipmentId = data.shipment_id;
            const shipmentNumber = data.shipment_number || tempShipmentNumber;
            
            // Затем добавляем товары в поставку
            return fetch(`/seller/shipments/${shipmentId}/add_items`, {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({
                    items: items,
                    status: status
                })
            })
            .then(response => {
                if (!response.ok) {
                    throw new Error(`HTTP ${response.status}: ${response.statusText}`);
                }
                const contentType = response.headers.get("content-type");
                if (contentType && contentType.includes("application/json")) {
                    return response.json();
                } else {
                    return response.text().then(text => {
                        console.error("Non-JSON response:", text);
                        throw new Error("Сервер вернул не JSON ответ");
                    });
                }
            })
            .then(itemData => {
                return { shipmentId, shipmentNumber, itemData };
            });
        } else {
            throw new Error(data.error || 'Ошибка создания поставки');
        }
    })
    .then(({ shipmentId, shipmentNumber, itemData }) => {
        hideLoading();
        if (itemData.success) {
            showToast(`Создана поставка ${shipmentNumber} с ${itemData.added_count} товарами!`, 'success');
            bootstrap.Modal.getInstance(document.getElementById('addShipmentModal')).hide();
            
            // Обновляем список поставок с правильным номером
            loadShipments();
            setTimeout(() => location.reload(), 1000);
        } else {
            showToast('Ошибка добавления товаров: ' + itemData.error, 'danger');
        }
    })
    .catch(error => {
        hideLoading();
        console.error('Full error:', error);
        showToast('Ошибка: ' + error.message, 'danger');
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
            'завершена': 'secondary',
            'продано': 'danger',
            'частично продана': 'info'
        }[shipment.status] || 'info';
        
        const hasItems = shipment.total_items > 0;
        const itemsText = hasItems ? 
            `${shipment.total_items} товар(ов)` : 
            '<span class="text-danger">Нет товаров</span>';
        
        // Используем shipment_number из базы данных
        const shipmentNumber = shipment.shipment_number || 
                              (shipment.id ? `SHIP-${String(shipment.id).padStart(3, '0')}` : 'Без номера');
        
        html += `
        <div class="col-md-6 mb-3">
            <div class="card h-100 shipment-card">
                <div class="card-header bg-${statusClass} text-white d-flex justify-content-between">
                    <h6 class="mb-0">${shipmentNumber}</h6>
                    <span class="badge bg-light text-dark">${itemsText}</span>
                </div>
                <div class="card-body">
                    <p><i class="fas fa-calendar"></i> <strong>Дата заказа:</strong> ${shipment.order_date}</p>
                    ${shipment.delivery_cost > 0 ? 
                      `<p><i class="fas fa-truck"></i> <strong>Доставка:</strong> ${shipment.delivery_cost} BYN</p>` : ''}
                    <p><i class="fas fa-flag"></i> <strong>Статус:</strong> 
                        <span class="badge bg-${statusClass}">${shipment.status}</span>
                    </p>
                    ${shipment.received_date ? 
                      `<p><i class="fas fa-calendar-check"></i> <strong>Получено:</strong> ${shipment.received_date}</p>` : ''}
                    <p><i class="fas fa-clock"></i> <strong>Создана:</strong> ${formatDateTime(shipment.created_at)}</p>
                    
                    <div class="btn-group btn-group-sm mt-2 w-100">
                        <button class="btn btn-outline-primary" 
                                onclick="showAddMoreItemsModal(${shipment.id}, '${shipmentNumber.replace(/'/g, "\\'")}')">
                            <i class="fas fa-plus"></i> Ещё товары
                        </button>
                        ${shipment.status !== 'продано' && shipment.status !== 'завершена' ? `
                        <button class="btn btn-outline-warning" 
                                onclick="showUpdateShipmentStatusModal(${shipment.id}, '${shipment.status.replace(/'/g, "\\'")}')">
                            <i class="fas fa-sync"></i> Статус
                        </button>
                        ` : ''}
                        <button class="btn btn-outline-info" 
                                onclick="showShipmentItems(${shipment.id}, '${shipmentNumber.replace(/'/g, "\\'")}')">
                            <i class="fas fa-eye"></i> Просмотр
                        </button>
                        <button class="btn btn-outline-danger" 
                                onclick="showDeleteShipmentModal(${shipment.id}, '${shipmentNumber.replace(/'/g, "\\'")}', ${shipment.total_items})">
                            <i class="fas fa-trash"></i>
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

// Показать модальное окно добавления товаров в поставку (новая версия с полями ввода)
function showAddMoreItemsModal(shipmentId, shipmentNumber) {
    currentShipmentId = shipmentId;
    currentShipmentNumber = shipmentNumber;
    
    // Создаем динамическое модальное окно
    const modalId = `addMoreItemsModal-${shipmentId}`;
    let modalDiv = document.getElementById(modalId);
    
    if (!modalDiv) {
        modalDiv = document.createElement('div');
        modalDiv.className = 'modal fade';
        modalDiv.id = modalId;
        modalDiv.innerHTML = `
        <div class="modal-dialog modal-lg">
            <div class="modal-content">
                <div class="modal-header bg-info text-white">
                    <h5 class="modal-title">
                        <i class="fas fa-boxes"></i> Добавить товары в поставку ${shipmentNumber}
                    </h5>
                    <button type="button" class="btn-close btn-close-white" data-bs-dismiss="modal"></button>
                </div>
                <div class="modal-body">
                    <div class="card mb-3">
                        <div class="card-header bg-secondary text-white">
                            <h6 class="mb-0">
                                <i class="fas fa-boxes"></i> Товары
                                <button type="button" class="btn btn-sm btn-light float-end" onclick="addMoreItemRow('${modalId}')">
                                    <i class="fas fa-plus"></i> Добавить товар
                                </button>
                            </h6>
                        </div>
                        <div class="card-body">
                            <div class="table-responsive">
                                <table class="table table-sm">
                                    <thead>
                                        <tr>
                                            <th>Название</th>
                                            <th>Себестоимость</th>
                                            <th>Цена продажи</th>
                                            <th>Действия</th>
                                        </tr>
                                    </thead>
                                    <tbody id="${modalId}-itemsTableBody">
                                        <tr id="${modalId}-itemRow_0">
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
                                                        onclick="removeMoreItemRow('${modalId}', 0)" disabled>
                                                    <i class="fas fa-trash"></i>
                                                </button>
                                            </td>
                                        </tr>
                                    </tbody>
                                </table>
                            </div>
                            <small class="text-muted">Добавьте товары в поставку</small>
                        </div>
                    </div>
                    <div class="alert alert-info">
                        <i class="fas fa-info-circle"></i>
                        Товары будут добавлены с текущим статусом поставки.
                    </div>
                </div>
                <div class="modal-footer">
                    <button type="button" class="btn btn-secondary" data-bs-dismiss="modal">Отмена</button>
                    <button type="button" class="btn btn-primary" onclick="addMoreItemsToShipment('${modalId}')">
                        <i class="fas fa-plus-circle"></i> Добавить товары
                    </button>
                </div>
            </div>
        </div>
        `;
        document.body.appendChild(modalDiv);
    }
    
    // Сбрасываем форму
    const tbody = document.getElementById(`${modalId}-itemsTableBody`);
    tbody.innerHTML = `
        <tr id="${modalId}-itemRow_0">
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
                        onclick="removeMoreItemRow('${modalId}', 0)" disabled>
                    <i class="fas fa-trash"></i>
                </button>
            </td>
        </tr>
    `;
    
    const modal = new bootstrap.Modal(modalDiv);
    modal.show();
}

// Добавить строку товара в модальное окно добавления товаров
function addMoreItemRow(modalId) {
    const tbody = document.getElementById(`${modalId}-itemsTableBody`);
    const rows = tbody.querySelectorAll('tr');
    const rowId = rows.length;
    
    const newRow = document.createElement('tr');
    newRow.id = `${modalId}-itemRow_${rowId}`;
    
    newRow.innerHTML = `
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
                    onclick="removeMoreItemRow('${modalId}', ${rowId})">
                <i class="fas fa-trash"></i>
            </button>
        </td>
    `;
    
    tbody.appendChild(newRow);
    
    // Активируем кнопку удаления для первой строки
    if (rowId === 1) {
        document.querySelector(`#${modalId}-itemRow_0 .btn-danger`).removeAttribute('disabled');
    }
}

// Удалить строку товара из модального окна добавления товаров
function removeMoreItemRow(modalId, rowId) {
    const row = document.getElementById(`${modalId}-itemRow_${rowId}`);
    if (row) {
        row.remove();
    }
    
    // Проверяем, осталась ли хотя бы одна строка
    const remainingRows = document.querySelectorAll(`#${modalId}-itemsTableBody tr`);
    if (remainingRows.length === 1) {
        // Деактивируем кнопку удаления для последней строки
        document.querySelector(`#${modalId}-itemRow_0 .btn-danger`).setAttribute('disabled', 'disabled');
    }
}

// Добавить товары в поставку через модальное окно
function addMoreItemsToShipment(modalId) {
    // Собираем данные о товарах
    const items = [];
    const itemRows = document.querySelectorAll(`#${modalId}-itemsTableBody tr`);
    
    if (itemRows.length === 0) {
        showToast('Добавьте хотя бы один товар', 'warning');
        return;
    }
    
    let hasErrors = false;
    itemRows.forEach((row, index) => {
        // Исправляем получение элементов
        const nameInput = row.querySelector('input[type="text"]');
        const numberInputs = row.querySelectorAll('input[type="number"]');
        const costInput = numberInputs[0];
        const priceInput = numberInputs[1];
        
        // Проверяем заполненность полей
        if (!nameInput || !nameInput.value.trim()) {
            showToast(`Товар ${index + 1}: укажите название`, 'warning');
            hasErrors = true;
            return;
        }
        
        if (!costInput || !priceInput) {
            showToast(`Товар ${index + 1}: некорректные поля ввода`, 'warning');
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
    
    showLoading(`Добавление ${items.length} товаров...`);
    
    // Получаем текущий статус поставки
    fetch(`/seller/shipments/${currentShipmentId}`)
        .then(response => {
            if (!response.ok) {
                throw new Error(`HTTP ${response.status}: ${response.statusText}`);
            }
            return response.json();
        })
        .then(data => {
            if (data.shipments && data.shipments.length > 0) {
                const shipment = data.shipments[0];
                const currentStatus = shipment.status;
                
                // Добавляем товары в поставку
                return fetch(`/seller/shipments/${currentShipmentId}/add_items`, {
                    method: 'POST',
                    headers: {'Content-Type': 'application/json'},
                    body: JSON.stringify({
                        items: items,
                        status: currentStatus
                    })
                });
            } else {
                throw new Error('Поставка не найдена');
            }
        })
        .then(response => {
            if (!response.ok) {
                throw new Error(`HTTP ${response.status}: ${response.statusText}`);
            }
            return response.json();
        })
        .then(data => {
            hideLoading();
            if (data.success) {
                showToast(`Добавлено ${data.added_count} товаров в поставку ${currentShipmentNumber}`, 'success');
                
                // Закрываем модальное окно
                const modal = bootstrap.Modal.getInstance(document.getElementById(modalId));
                if (modal) modal.hide();
                
                // Обновляем список поставок
                loadShipments();
                setTimeout(() => location.reload(), 1000);
            } else {
                showToast('Ошибка: ' + (data.error || 'Неизвестная ошибка'), 'danger');
            }
        })
        .catch(error => {
            hideLoading();
            console.error('Ошибка добавления товаров:', error);
            showToast('Ошибка: ' + error.message, 'danger');
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
        `Вы уверены, что хотите изменить статус поставки на "${newStatus}"? Все товары в поставке также изменят свой статус. Стоимость доставки ${deliveryCost} BYN будет вычтена из капитала.` :
        `Вы уверены, что хотите изменить статус поставки на "${newStatus}"? Все товары в поставке также изменят свой статус.`;
    
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
                'зарезервировано': 'info',
                'взял себе': 'secondary'
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
                    <div class="btn-group btn-group-sm">
                        ${item.status !== 'в пути' ? `
                        <button class="btn btn-outline-primary" 
                                onclick="showUpdateItemStatusModal(${item.id}, '${item.status.replace(/'/g, "\\'")}', '${item.name.replace(/'/g, "\\'")}')">
                            <i class="fas fa-edit"></i>
                        </button>
                        ` : ''}
                        <button class="btn btn-outline-danger" 
                                onclick="showDeleteItemModal(${item.id}, '${item.name.replace(/'/g, "\\'")}', 'Поставка: ${shipmentNumber}')">
                            <i class="fas fa-trash"></i>
                        </button>
                    </div>
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

// Показать модальное окно изменения статуса товара
function showUpdateItemStatusModal(itemId, currentStatus, itemName) {
    // Создаем динамическое модальное окно
    const modalId = `updateItemStatusModal-${itemId}`;
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
                            <input type="text" class="form-control" value="${itemName}" readonly>
                        </div>
                        <div class="mb-3">
                            <label class="form-label">Новый статус:</label>
                            <select class="form-control" id="${modalId}-statusSelect" required>
                                <!-- Опции будут добавлены динамически -->
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
    
    // Заполняем выпадающий список статусов
    const statusSelect = document.getElementById(`${modalId}-statusSelect`);
    statusSelect.innerHTML = '';
    
    const availableStatuses = [
        {value: 'в наличии', label: 'В наличии'},
        {value: 'продано', label: 'Продано'},
        {value: 'зарезервировано', label: 'Зарезервировано'},
        {value: 'взял себе', label: 'Взял себе'}
    ];
    
    availableStatuses.forEach(status => {
        const option = document.createElement('option');
        option.value = status.value;
        option.textContent = status.label;
        if (status.value === currentStatus) {
            option.selected = true;
        }
        statusSelect.appendChild(option);
    });
    
    const modal = new bootstrap.Modal(modalDiv);
    modal.show();
}

// Подтвердить изменение статуса товара
function confirmUpdateItemStatus(itemId, modalId) {
    const statusSelect = document.getElementById(`${modalId}-statusSelect`);
    const newStatus = statusSelect.value;
    
    if (!newStatus) {
        showToast('Выберите статус', 'warning');
        return;
    }
    
    if (!confirm(`Изменить статус товара на "${newStatus}"?`)) {
        return;
    }
    
    showLoading('Обновление статуса...');
    
    fetch(`/seller/update/${itemId}`, {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({status: newStatus})
    })
    .then(response => response.json())
    .then(data => {
        hideLoading();
        if (data.success) {
            showToast('Статус товара обновлен', 'success');
            
            // Закрываем модальное окно
            const modal = bootstrap.Modal.getInstance(document.getElementById(modalId));
            if (modal) modal.hide();
            
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
    
    let container = document.getElementById('toast-container');
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
        // Если строка содержит 'T' (ISO формат), парсим как ISO
        if (dateTimeStr.includes('T')) {
            const date = new Date(dateTimeStr);
            // Добавляем 3 часа для Минского времени
            date.setHours(date.getHours() + 3);
            return date.toLocaleString('ru-RU', {
                day: '2-digit',
                month: '2-digit',
                year: 'numeric',
                hour: '2-digit',
                minute: '2-digit'
            });
        } else {
            // Пытаемся распарсить как локальную дату
            const date = new Date(dateTimeStr.replace(' ', 'T') + 'Z');
            if (!isNaN(date.getTime())) {
                // Добавляем 3 часа для Минского времени
                date.setHours(date.getHours() + 3);
                return date.toLocaleString('ru-RU', {
                    day: '2-digit',
                    month: '2-digit',
                    year: 'numeric',
                    hour: '2-digit',
                    minute: '2-digit'
                });
            }
            return dateTimeStr;
        }
    } catch (e) {
        console.log('Ошибка форматирования даты:', e);
        return dateTimeStr;
    }
}

// Инициализация при загрузке страницы
document.addEventListener('DOMContentLoaded', function() {
    // Загружаем статусы товаров
    loadItemStatuses();
    
    // Добавляем обработчики для кнопок управления поставками
    const addShipmentBtn = document.getElementById('add-shipment-btn');
    if (addShipmentBtn) {
        addShipmentBtn.addEventListener('click', showAddShipmentModal);
    }
    
    const loadShipmentsBtn = document.getElementById('load-shipments-btn');
    if (loadShipmentsBtn) {
        loadShipmentsBtn.addEventListener('click', loadShipments);
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
            const deliveryCostGroup = document.getElementById('deliveryCostGroup');
            if (dateGroup && deliveryCostGroup) {
                const showDeliveryFields = this.value === 'в наличии';
                dateGroup.style.display = showDeliveryFields ? 'block' : 'none';
                deliveryCostGroup.style.display = showDeliveryFields ? 'block' : 'none';
            }
        });
    }
});
