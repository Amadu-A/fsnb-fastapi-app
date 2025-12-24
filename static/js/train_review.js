// path: static/js/train_review.js
(function () {
  function qs(root, sel) {
    return root.querySelector(sel);
  }

  function qsa(root, sel) {
    return Array.from(root.querySelectorAll(sel));
  }

  function safeInt(v) {
    const n = parseInt(String(v), 10);
    return Number.isFinite(n) ? n : null;
  }

  document.addEventListener("DOMContentLoaded", () => {
    const table = document.getElementById("reviewTable");
    const btn = document.getElementById("btnCommit");
    const sourceNameNode = document.getElementById("reviewSourceName");

    if (!table || !btn || !sourceNameNode) return;

    const sourceName = sourceNameNode.getAttribute("data-source-name");

    const rows = qsa(table.tBodies[0], "tr").map((tr) => {
      const rowIdx = safeInt(tr.getAttribute("data-row-idx")) ?? 0;

      const caption = (tr.children[1]?.innerText || "").trim();
      const units = (tr.children[4]?.innerText || "").trim() || null;
      const qty = (tr.children[6]?.innerText || "").trim() || null;

      const fsnbSelect = qs(tr, ".js-fsnb-select");
      const labelSelect = qs(tr, ".js-label-select");
      const noteInput = qs(tr, ".js-note-input");
      const autoIdEl = qs(tr, ".js-auto-id");

      const autoId = (autoIdEl?.innerText || "").trim();
      const selectedId = fsnbSelect && fsnbSelect.value ? safeInt(fsnbSelect.value) : null;

      return {
        row_idx: rowIdx,
        caption: caption,
        units: units,
        qty: qty,
        label: labelSelect ? labelSelect.value : "gold",
        selected_item_id: selectedId,
        auto_selected_item_id: autoId ? safeInt(autoId) : null,
        negatives: [],
        note: noteInput && noteInput.value ? noteInput.value : null,
      };
    });

    function findRow(rowIdx) {
      return rows.find((r) => r.row_idx === rowIdx);
    }

    function updateMeta(tr, optionEl) {
      const codeCell = qs(tr, ".js-cell-code");
      const unitCell = qs(tr, ".js-cell-fsnb-unit");
      if (!codeCell || !unitCell) return;

      if (!optionEl) {
        codeCell.innerText = "";
        unitCell.innerText = "";
        return;
      }

      codeCell.innerText = optionEl.getAttribute("data-code") || "";
      unitCell.innerText = optionEl.getAttribute("data-unit") || "";
    }

    // init meta
    qsa(table.tBodies[0], "tr").forEach((tr) => {
      const sel = qs(tr, ".js-fsnb-select");
      if (!sel) return;
      const opt = sel.options[sel.selectedIndex];
      updateMeta(tr, opt && opt.value ? opt : null);
    });

    // top-K change
    qsa(document, ".js-fsnb-select").forEach((sel) => {
      sel.addEventListener("change", (e) => {
        const target = e.target;
        const tr = target.closest("tr");
        if (!tr) return;

        const rowIdx = safeInt(tr.getAttribute("data-row-idx"));
        if (rowIdx === null) return;

        const r = findRow(rowIdx);
        if (!r) return;

        const nextSelected = target.value ? safeInt(target.value) : null;

        if (r.auto_selected_item_id && nextSelected && nextSelected !== r.auto_selected_item_id) {
          if (!r.negatives.includes(r.auto_selected_item_id)) {
            r.negatives.push(r.auto_selected_item_id);
          }
          r.label = "gold";
          const labelSelect = qs(tr, ".js-label-select");
          if (labelSelect) labelSelect.value = "gold";
        }

        if (!nextSelected) {
          r.label = "none_match";
          const labelSelect = qs(tr, ".js-label-select");
          if (labelSelect) labelSelect.value = "none_match";
        }

        r.selected_item_id = nextSelected;
        updateMeta(tr, target.value ? target.options[target.selectedIndex] : null);
      });
    });

    // label change
    qsa(document, ".js-label-select").forEach((sel) => {
      sel.addEventListener("change", (e) => {
        const target = e.target;
        const tr = target.closest("tr");
        if (!tr) return;

        const rowIdx = safeInt(tr.getAttribute("data-row-idx"));
        if (rowIdx === null) return;

        const r = findRow(rowIdx);
        if (!r) return;

        r.label = target.value;
      });
    });

    // note change
    qsa(document, ".js-note-input").forEach((inp) => {
      inp.addEventListener("input", (e) => {
        const target = e.target;
        const tr = target.closest("tr");
        if (!tr) return;

        const rowIdx = safeInt(tr.getAttribute("data-row-idx"));
        if (rowIdx === null) return;

        const r = findRow(rowIdx);
        if (!r) return;

        r.note = target.value || null;
      });
    });

    // AJAX search
    qsa(table.tBodies[0], "tr").forEach((tr) => {
      const searchInput = qs(tr, ".js-fsnb-search");
      const resultsBox = qs(tr, ".js-fsnb-search-results");
      const topkSelect = qs(tr, ".js-fsnb-select");

      if (!searchInput || !resultsBox || !topkSelect) return;

      let lastQ = "";
      let timer = null;

      function hideResults() {
        resultsBox.classList.add("u-hidden");
        resultsBox.innerHTML = "";
      }

      searchInput.addEventListener("input", () => {
        const q = (searchInput.value || "").trim();
        if (q.length < 3) {
          hideResults();
          return;
        }
        lastQ = q;

        if (timer) clearTimeout(timer);
        timer = setTimeout(async () => {
          try {
            const resp = await fetch(
              `/api/v1/train/review/items/search?q=${encodeURIComponent(q)}&limit=20`,
              { credentials: "include" }
            );
            const data = await resp.json();
            if (q !== lastQ) return;

            resultsBox.innerHTML = "";
            (data.items || []).forEach((it) => {
              const div = document.createElement("div");
              div.className = "review__search-item";
              div.innerText = `${it.code} — ${it.name} (${it.unit || ""})`;

              div.addEventListener("click", () => {
                const opt = document.createElement("option");
                opt.value = String(it.id);
                opt.setAttribute("data-code", it.code || "");
                opt.setAttribute("data-unit", it.unit || "");
                opt.text = `${it.code} — ${it.name} (${it.unit || ""}) [manual]`;
                topkSelect.appendChild(opt);

                topkSelect.value = String(it.id);
                topkSelect.dispatchEvent(new Event("change"));

                hideResults();
              });

              resultsBox.appendChild(div);
            });

            resultsBox.classList.remove("u-hidden");
          } catch (e) {
            hideResults();
          }
        }, 250);
      });

      document.addEventListener("click", (e) => {
        if (!resultsBox.contains(e.target) && e.target !== searchInput) {
          hideResults();
        }
      });
    });

    // Commit
    btn.addEventListener("click", async () => {
      const payload = { source_name: sourceName, rows: rows };

      const resp = await fetch("/api/v1/train/review/commit", {
        method: "POST",
        credentials: "include",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });

      if (!resp.ok) {
        alert("Не удалось сформировать отчёт. Проверь логи.");
        return;
      }

      const blob = await resp.blob();
      const url = window.URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = "VOR.xlsx";
      document.body.appendChild(a);
      a.click();
      a.remove();
      window.URL.revokeObjectURL(url);
    });
  });
})();
