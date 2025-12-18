// path: static/js/fsnb_matcher.js

(function () {
  function $(id) { return document.getElementById(id); }

  function showModal() {
    const m = $("fsnb-modal");
    if (!m) return;
    m.style.display = "block";
    m.setAttribute("aria-hidden", "false");
  }

  function hideModal() {
    const m = $("fsnb-modal");
    if (!m) return;
    m.style.display = "none";
    m.setAttribute("aria-hidden", "true");
  }

  function showError(text) {
    const el = $("fsnb-error");
    if (!el) return;
    el.textContent = text;
    el.style.display = "block";
  }

  function clearError() {
    const el = $("fsnb-error");
    if (!el) return;
    el.textContent = "";
    el.style.display = "none";
  }

  function filenameFromDisposition(disposition) {
    if (!disposition) return null;
    // attachment; filename="smeta.xlsx"
    const m = /filename\*?=(?:UTF-8''|")?([^\";]+)/i.exec(disposition);
    if (!m) return null;
    try { return decodeURIComponent(m[1].replace(/"/g, "")); } catch { return m[1].replace(/"/g, ""); }
  }

  document.addEventListener("DOMContentLoaded", () => {
    const form = $("fsnb-match-form");
    const fileInput = $("fsnb-file");
    const status = $("fsnb-file-status");

    if (!form || !fileInput) return;

    fileInput.addEventListener("change", () => {
      clearError();
      const f = fileInput.files && fileInput.files[0];
      if (status) status.textContent = f ? `Выбран: ${f.name}` : "Файл не выбран";
    });

    form.addEventListener("submit", async (e) => {
      e.preventDefault();
      clearError();

      const f = fileInput.files && fileInput.files[0];
      if (!f) {
        showError("Выбери JSON-файл перед сопоставлением.");
        return;
      }

      const fd = new FormData();
      fd.append("file", f);

      showModal();

      try {
        const resp = await fetch("/api/v1/fsnb/match", {
          method: "POST",
          body: fd,
          credentials: "include",
        });

        if (!resp.ok) {
          let detail = `Ошибка сопоставления: HTTP ${resp.status}`;
          try {
            const data = await resp.json();
            if (data && data.detail) detail = String(data.detail);
          } catch (_) {}
          throw new Error(detail);
        }

        const blob = await resp.blob();

        const cd = resp.headers.get("Content-Disposition");
        const name = filenameFromDisposition(cd) || "smeta.xlsx";

        const url = window.URL.createObjectURL(blob);
        const a = document.createElement("a");
        a.href = url;
        a.download = name;
        document.body.appendChild(a);
        a.click();
        a.remove();
        window.URL.revokeObjectURL(url);

      } catch (err) {
        showError(err?.message ? String(err.message) : "Неизвестная ошибка");
      } finally {
        hideModal();
      }
    });
  });
})();
