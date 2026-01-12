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
    const newStatus = prompt('Новый статус:', currentStatus);
    if (!newStatus || newStatus === currentStatus) return;
    
    fetch('/seller/update/' + itemId, {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({status: newStatus})
    })
    .then(response => response.json())
    .then(data => {
        if (data.success) {
            alert('Статус обновлён!');
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