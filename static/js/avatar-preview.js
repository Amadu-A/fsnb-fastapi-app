// /static/js/avatar-preview.js
(function () {
  const fi = document.getElementById('avatar-input');
  const out = document.getElementById('avatar-filename');
  const previewLarge = document.getElementById('avatar-preview-img');
  const previewMini = document.getElementById('avatar-mini');

  if (!fi) return;

  const MAX_BYTES = 3 * 1024 * 1024;  // 3MB
  const MIN_W = 40, MIN_H = 40;

  function showAlert(msg) {
    alert(msg);
  }

  fi.addEventListener('change', () => {
    const file = fi.files && fi.files[0] ? fi.files[0] : null;
    if (out) out.textContent = file ? file.name : '';
    if (!file) return;

    if (file.size > MAX_BYTES) {
      showAlert('Файл слишком большой. Максимум 3 МБ.');
      fi.value = '';
      if (out) out.textContent = '';
      return;
    }

    const url = URL.createObjectURL(file);
    const img = new Image();
    img.onload = () => {
      if (img.width < MIN_W || img.height < MIN_H) {
        showAlert('Минимальный размер изображения — 40×40 пикселей.');
        URL.revokeObjectURL(url);
        fi.value = '';
        if (out) out.textContent = '';
        return;
      }
      // Мгновенный предпросмотр (без сохранения на сервере)
      if (previewLarge) previewLarge.src = url;
      if (previewMini) previewMini.src = url;
      // URL будет отревокнут после перезагрузки страницы
    };
    img.onerror = () => {
      showAlert('Не удалось прочитать файл как изображение.');
      fi.value = '';
      if (out) out.textContent = '';
      URL.revokeObjectURL(url);
    };
    img.src = url;
  });
})();
