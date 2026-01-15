// image_uploader.js

let imageUploadActive = false;

// Инициализация загрузки изображений
function initImageUploader(inputId, previewId, urlInputId) {
    const imageInput = document.getElementById(inputId);
    const imagePreview = document.getElementById(previewId);
    const imageUrlInput = document.getElementById(urlInputId);
    
    if (!imageInput || !imagePreview || !imageUrlInput) return;
    
    // Обработка выбора файла
    imageInput.addEventListener('change', function(e) {
        const file = e.target.files[0];
        if (file) {
            if (file.size > 5 * 1024 * 1024) { // 5MB limit
                alert('Файл слишком большой. Максимальный размер: 5MB');
                return;
            }
            
            if (!file.type.match('image.*')) {
                alert('Пожалуйста, выберите файл изображения');
                return;
            }
            
            const reader = new FileReader();
            reader.onload = function(e) {
                // Показываем превью
                imagePreview.innerHTML = `<img src="${e.target.result}" class="img-fluid rounded" alt="Превью">`;
                imagePreview.style.display = 'block';
                
                // Сохраняем как base64
                const base64 = e.target.result.split(',')[1];
                uploadImageAsBase64(base64, file.type, urlInputId);
            };
            reader.readAsDataURL(file);
        }
    });
    
    // Обработка вставки из буфера обмена
    document.addEventListener('paste', function(e) {
        if (imageUploadActive) {
            const items = e.clipboardData.items;
            
            for (let i = 0; i < items.length; i++) {
                if (items[i].type.indexOf('image') !== -1) {
                    const blob = items[i].getAsFile();
                    const reader = new FileReader();
                    
                    reader.onload = function(e) {
                        imagePreview.innerHTML = `<img src="${e.target.result}" class="img-fluid rounded" alt="Превью">`;
                        imagePreview.style.display = 'block';
                        
                        const base64 = e.target.result.split(',')[1];
                        uploadImageAsBase64(base64, blob.type, urlInputId);
                    };
                    
                    reader.readAsDataURL(blob);
                    e.preventDefault();
                    break;
                }
            }
        }
    });
    
    // Обработка перетаскивания файла
    imagePreview.addEventListener('dragover', function(e) {
        e.preventDefault();
        e.stopPropagation();
        this.style.borderColor = '#0d6efd';
    });
    
    imagePreview.addEventListener('dragleave', function(e) {
        e.preventDefault();
        e.stopPropagation();
        this.style.borderColor = '#dee2e6';
    });
    
    imagePreview.addEventListener('drop', function(e) {
        e.preventDefault();
        e.stopPropagation();
        this.style.borderColor = '#dee2e6';
        
        const files = e.dataTransfer.files;
        if (files.length > 0) {
            const file = files[0];
            
            if (file.size > 5 * 1024 * 1024) {
                alert('Файл слишком большой. Максимальный размер: 5MB');
                return;
            }
            
            if (!file.type.match('image.*')) {
                alert('Пожалуйста, перетащите файл изображения');
                return;
            }
            
            const reader = new FileReader();
            reader.onload = function(e) {
                imagePreview.innerHTML = `<img src="${e.target.result}" class="img-fluid rounded" alt="Превью">`;
                imagePreview.style.display = 'block';
                
                const base64 = e.target.result.split(',')[1];
                uploadImageAsBase64(base64, file.type, urlInputId);
            };
            reader.readAsDataURL(file);
        }
    });
    
    // Обработка URL изображения
    imageUrlInput.addEventListener('change', function() {
        if (this.value && this.value.startsWith('http')) {
            // Проверяем URL
            const tempImg = new Image();
            tempImg.onload = function() {
                imagePreview.innerHTML = `<img src="${imageUrlInput.value}" class="img-fluid rounded" alt="Превью">`;
                imagePreview.style.display = 'block';
            };
            tempImg.onerror = function() {
                alert('Не удалось загрузить изображение по указанному URL');
                imagePreview.style.display = 'none';
                imagePreview.innerHTML = '';
            };
            tempImg.src = this.value;
        }
    });
}

// Загрузка изображения как base64
function uploadImageAsBase64(base64, mimeType, urlInputId) {
    showLoading('Загрузка изображения...');
    
    fetch('/seller/upload_image', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({
            base64: base64,
            mime_type: mimeType
        })
    })
    .then(response => response.json())
    .then(data => {
        hideLoading();
        if (data.success) {
            const urlInput = document.getElementById(urlInputId);
            if (urlInput) {
                urlInput.value = data.image_url;
                showToast('Изображение успешно загружено', 'success');
            }
        } else {
            showToast('Ошибка загрузки изображения: ' + data.error, 'danger');
        }
    })
    .catch(error => {
        hideLoading();
        showToast('Ошибка сети: ' + error.message, 'danger');
    });
}

// Активация/деактивация загрузки изображений
function activateImageUpload() {
    imageUploadActive = true;
}

function deactivateImageUpload() {
    imageUploadActive = false;
}
