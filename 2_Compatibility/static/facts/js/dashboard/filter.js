(function (window) {
  "use strict";

  function closeAllDropdowns() {
    document.querySelectorAll('.facts-dropdown.open').forEach((el) => el.classList.remove('open'));
  }

  function escapeHtml(value) {
    return String(value ?? "")
      .replaceAll("&", "&amp;")
      .replaceAll("<", "&lt;")
      .replaceAll(">", "&gt;")
      .replaceAll('"', "&quot;")
      .replaceAll("'", "&#39;");
  }

  function buildSearchableOptions(selectEl, listEl, keyword) {
    const term = String(keyword || "").toLowerCase().trim();
    const currentValue = String(selectEl.value || "");
    listEl.innerHTML = "";

    Array.from(selectEl.options || []).forEach((opt) => {
      const value = String(opt.value || "");
      const text = String(opt.text || "");
      if (!text && !value) return;
      if (term && !text.toLowerCase().includes(term)) return;

      const item = document.createElement("button");
      item.type = "button";
      item.className = "facts-dropdown-option";
      if (value === currentValue) item.classList.add("active");
      item.innerHTML = `<span>${escapeHtml(text)}</span>`;
      item.addEventListener("click", () => {
        selectEl.value = value;
        selectEl.dispatchEvent(new Event("change", { bubbles: true }));
      });
      listEl.appendChild(item);
    });
  }

  function syncSearchableLabel(selectEl, triggerEl) {
    const selected = selectEl.options[selectEl.selectedIndex];
    triggerEl.textContent = selected ? selected.text : "전체";
    triggerEl.classList.toggle("has-values", !!(selected && selected.value));
  }

  function initSearchableDropdown(selectEl) {
    if (!selectEl || selectEl.dataset.dashboardSearchableBound === "1") return;

    const wrap = document.createElement("div");
    wrap.className = "facts-dropdown facts-dropdown-searchable";

    const trigger = document.createElement("button");
    trigger.type = "button";
    trigger.className = "facts-dropdown-trigger";

    const panel = document.createElement("div");
    panel.className = "facts-dropdown-panel";

    const searchInput = document.createElement("input");
    searchInput.type = "text";
    searchInput.className = "facts-dropdown-search-input";
    searchInput.placeholder = selectEl.dataset.placeholder || "검색 또는 선택";

    const list = document.createElement("div");
    list.className = "facts-dropdown-options";

    panel.appendChild(searchInput);
    panel.appendChild(list);
    wrap.appendChild(trigger);
    wrap.appendChild(panel);

    selectEl.classList.add("facts-hidden-native-select");
    selectEl.parentNode.insertBefore(wrap, selectEl);
    wrap.appendChild(selectEl);

    trigger.addEventListener("click", (e) => {
      e.stopPropagation();
      const willOpen = !wrap.classList.contains("open");
      closeAllDropdowns();
      if (willOpen) {
        wrap.classList.add("open");
        searchInput.value = "";
        buildSearchableOptions(selectEl, list, "");
        searchInput.focus();
      }
    });

    searchInput.addEventListener("click", (e) => e.stopPropagation());
    searchInput.addEventListener("input", () => buildSearchableOptions(selectEl, list, searchInput.value));

    wrap.addEventListener("click", (e) => e.stopPropagation());

    function syncFromSelect() {
      syncSearchableLabel(selectEl, trigger);
      buildSearchableOptions(selectEl, list, searchInput.value);
      wrap.classList.remove("open");
    }
    selectEl.addEventListener("change", syncFromSelect);

    syncSearchableLabel(selectEl, trigger);
    buildSearchableOptions(selectEl, list, "");
    selectEl.__dashboardSearchableSync = syncFromSelect;
    selectEl.dataset.dashboardSearchableBound = "1";
  }

  function syncMultiLabel(selectEl, triggerEl) {
    const selected = Array.from(selectEl.selectedOptions || []).map((opt) => String(opt.value || "")).filter(Boolean);
    if (selected.length === 0) {
      triggerEl.textContent = "전체";
      triggerEl.classList.remove("has-values");
      return;
    }
    if (selected.length <= 2) {
      triggerEl.textContent = selected.join(", ");
    } else {
      const label = selectEl.dataset.summaryLabel || "Layer";
      triggerEl.textContent = `${label} ${selected.length}개 선택`;
    }
    triggerEl.classList.add("has-values");
  }

  function buildMultiOptions(selectEl, listEl) {
    listEl.innerHTML = "";

    const allItem = document.createElement("label");
    allItem.className = "facts-dropdown-check-option";
    const allChecked = Array.from(selectEl.selectedOptions || []).filter((opt) => String(opt.value || "")).length === 0;
    allItem.innerHTML = `<input type="checkbox" data-role="all" ${allChecked ? "checked" : ""}><span>전체</span>`;
    listEl.appendChild(allItem);

    Array.from(selectEl.options || []).forEach((opt) => {
      const value = String(opt.value || "");
      if (!value) return;
      const item = document.createElement("label");
      item.className = "facts-dropdown-check-option";
      item.innerHTML = `<input type="checkbox" data-role="item" value="${escapeHtml(value)}" ${opt.selected ? "checked" : ""}><span>${escapeHtml(opt.text || value)}</span>`;
      listEl.appendChild(item);
    });
  }

  function initMultiSelectDropdown(selectEl) {
    if (!selectEl || selectEl.dataset.dashboardMultiBound === "1") return;

    const wrap = document.createElement("div");
    wrap.className = "facts-dropdown facts-dropdown-multi";

    const trigger = document.createElement("button");
    trigger.type = "button";
    trigger.className = "facts-dropdown-trigger";

    const panel = document.createElement("div");
    panel.className = "facts-dropdown-panel";

    const list = document.createElement("div");
    list.className = "facts-dropdown-options";

    panel.appendChild(list);
    wrap.appendChild(trigger);
    wrap.appendChild(panel);

    selectEl.classList.add("facts-hidden-native-select");
    selectEl.parentNode.insertBefore(wrap, selectEl);
    wrap.appendChild(selectEl);

    function syncFromSelect() {
      buildMultiOptions(selectEl, list);
      syncMultiLabel(selectEl, trigger);
    }

    trigger.addEventListener("click", (e) => {
      e.stopPropagation();
      const willOpen = !wrap.classList.contains("open");
      closeAllDropdowns();
      if (willOpen) wrap.classList.add("open");
    });

    wrap.addEventListener("click", (e) => e.stopPropagation());

    list.addEventListener("change", (e) => {
      const target = e.target;
      if (!(target instanceof HTMLInputElement)) return;

      if (target.dataset.role === "all") {
        if (!target.checked) {
          target.checked = true;
          return;
        }
        Array.from(selectEl.options || []).forEach((opt) => { opt.selected = false; });
      } else {
        const checkedValues = Array.from(list.querySelectorAll('input[data-role="item"]:checked')).map((el) => el.value);
        Array.from(selectEl.options || []).forEach((opt) => {
          opt.selected = checkedValues.includes(String(opt.value || ""));
        });
      }

      syncFromSelect();
      selectEl.dispatchEvent(new Event("change", { bubbles: true }));
    });

    selectEl.addEventListener("change", syncFromSelect);

    syncFromSelect();
    selectEl.__dashboardMultiSync = syncFromSelect;
    selectEl.dataset.dashboardMultiBound = "1";
  }

  function refreshSelectOptions(selectEl, values, includeAllOption = true, emitChange = false) {
    if (!selectEl) return;
    const isMultiple = !!selectEl.multiple;
    const prevMulti = Array.from(selectEl.selectedOptions || []).map((opt) => String(opt.value || "")).filter(Boolean);
    const prevSingle = String(selectEl.value || "");

    let html = "";
    if (includeAllOption && !isMultiple) {
      html += '<option value="">전체</option>';
    }
    html += (values || []).map((v) => `<option value="${escapeHtml(v)}">${escapeHtml(v)}</option>`).join("");
    selectEl.innerHTML = html;

    if (isMultiple) {
      Array.from(selectEl.options || []).forEach((opt) => {
        opt.selected = prevMulti.includes(String(opt.value || ""));
      });
    } else {
      const hasPrev = (values || []).includes(prevSingle);
      selectEl.value = hasPrev ? prevSingle : "";
    }

    if (typeof selectEl.__dashboardSearchableSync === "function") {
      selectEl.__dashboardSearchableSync();
    }
    if (typeof selectEl.__dashboardMultiSync === "function") {
      selectEl.__dashboardMultiSync();
    }
    if (emitChange) {
      selectEl.dispatchEvent(new Event("change", { bubbles: true }));
    }
  }

  function initDashboardDropdowns(root) {
    const scope = root || document;
    scope.querySelectorAll("select.dashboard-searchable-select").forEach(initSearchableDropdown);
    scope.querySelectorAll("select[data-multi-dropdown]").forEach(initMultiSelectDropdown);
  }

  document.addEventListener("click", () => closeAllDropdowns());

  window.FACTSDashboardFilters = {
    initDashboardDropdowns,
    initSearchableDropdown,
    initMultiSelectDropdown,
    refreshSelectOptions,
  };
})(window);
