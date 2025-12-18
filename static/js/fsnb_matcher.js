// static/js/fsnb_matcher.js
(function () {
  const form = document.getElementById('fsnb-form');
  if (!form) return;

  const overlay = document.getElementById('fsnb-overlay');

  form.addEventListener('submit', async (e) => {
    e.preventDefault();
    const fileInput = document.getElementById('fsnb-file');
    if (!fileInput.files || fileInput.files.length === 0) {
      alert('Выберите JSON файл');
      return;
    }

    const fd = new FormData();
    fd.append('file', fileInput.files[0]);

    overlay.style.display = 'flex';
    try {
      const res = await fetch('/api/v1/fsnb/match', { method: 'POST', body: fd });
      if (res.status === 401) {
        alert('Нужно авторизоваться для использования сервиса.');
        return;
      }
      if (!res.ok) {
        const msg = await res.text();
        throw new Error(msg || 'Ошибка сервера');
      }
      const blob = await res.blob();
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url; a.download = 'smeta.xlsx'; a.click();
      URL.revokeObjectURL(url);
    } catch (err) {
      alert(String(err));
    } finally {
      overlay.style.display = 'none';
      form.reset();
    }
  });
})();
