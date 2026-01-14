// Поддержание активности каждую минуту
function startKeepAlive() {
    setInterval(() => {
        fetch('/seller/keepalive').catch(e => console.log('Keepalive error:', e));
    }, 60000);
}

// Инициализация после загрузки страницы
document.addEventListener('DOMContentLoaded', function() {
    // Если мы на странице продавца
    if (document.querySelector('.update-btn')) {
        startKeepAlive();
    }
});
