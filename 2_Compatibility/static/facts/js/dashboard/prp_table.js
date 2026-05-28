(function () {
    "use strict";
    const PRP_TABLE_JS_VERSION = "tip-missing-render-20260504";
    console.info(`[FACTS] prp_table.js version=${PRP_TABLE_JS_VERSION}`);

    function qs(id) {
        return document.getElementById(id);
    }

    function parseJsonScript(id, fallback) {
        const el = qs(id);
        if (!el) return fallback;
        try {
            return JSON.parse(el.textContent);
        } catch (e) {
            console.error(`[dashboard.js] JSON parse failed: ${id}`, e);
            return fallback;
        }
    }

    const dashboardMeta = parseJsonScript("dashboard-meta", {});
    const guidePagesData = parseJsonScript("guide-pages-data", []);
    const dashboardApiUrls = parseJsonScript("dashboard-api-urls", {});
    let combinedSeries = parseJsonScript("facts-combined-series-data", {
        labels: [],
        total_values: [],
        body_values: [],
        cham_values: [],
        target_values: [],
    });

    const state = {
        chart: null,
        currentPlanTargetItems: [],
        currentPlanTargetInfo: null,
        currentTipMissingTargetItems: [],
        currentTipMissingTargetInfo: null,
        currentOverrideTargetInfo: null,
        currentOverrideFieldType: "",
        guideCurrentIndex: 0,
        guideWheelLock: false,
        currentRows: [],
        optionFetchTimer: null,
        optionFetchInFlight: false,
        optionCache: new Map(),
        dashboardOptionCache: new Map(),
        summaryFetchInFlight: false,
        prpFetchInFlight: false,
        currentPlanEditRow: null,
        tableDescriptOptions: [],
        tableRecipeOptions: [],
        exportButtonTimers: new Map(),
    };
    const textSuggestState = {};

    function syncLayerDropdownFromSelect() {
        const select = qs("tblFilterLayer");
        if (!select) return;
        select.dispatchEvent(new Event("change", { bubbles: true }));
    }

    function bindLayerDropdown() {
        if (window.FACTSDashboardFilters && window.FACTSDashboardFilters.initDashboardDropdowns) {
            window.FACTSDashboardFilters.initDashboardDropdowns(document);
        }

    }

    function getCsrfToken() {
        const cookie = document.cookie
            .split("; ")
            .find((row) => row.startsWith("csrftoken="));
        return cookie ? cookie.split("=")[1] : "";
    }

    function showLoading() {
        if (window.showGlobalLoading) window.showGlobalLoading();
    }

    function hideLoading() {
        if (window.hideGlobalLoading) window.hideGlobalLoading();
    }

    function openModal(el) {
        if (el) el.classList.remove("hidden");
    }

    function closeModal(el) {
        if (el) el.classList.add("hidden");
    }

    function normalizeUpperInput(el) {
        if (!el) return;
        el.value = String(el.value || "").toUpperCase();
    }

    function bindUppercaseInput(el) {
        if (!el) return;
        el.addEventListener("input", () => {
            const start = el.selectionStart;
            const end = el.selectionEnd;
            el.value = String(el.value || "").toUpperCase();
            try {
                el.setSelectionRange(start, end);
            } catch (e) {}
        });
    }

    function ensureTextSuggestDropdown(inputEl, options, stateKey) {
        if (!inputEl) return;
        const key = stateKey || inputEl.id;
        const normalized = Array.from(new Set((options || []).map((v) => String(v || "").trim()).filter(Boolean)));
        textSuggestState[key] = normalized;

        let wrap = inputEl.closest(".facts-text-suggest-wrap");
        if (!wrap) {
            wrap = document.createElement("div");
            wrap.className = "facts-text-suggest-wrap";
            inputEl.parentNode.insertBefore(wrap, inputEl);
            wrap.appendChild(inputEl);
            const panel = document.createElement("div");
            panel.className = "facts-dropdown-panel facts-text-suggest-panel";
            panel.innerHTML = '<div class="facts-dropdown-options"></div>';
            wrap.appendChild(panel);
            wrap.addEventListener("click", (e) => e.stopPropagation());
        }
        const panel = wrap.querySelector(".facts-text-suggest-panel");
        const list = wrap.querySelector(".facts-dropdown-options");

        function render(keyword) {
            const term = String(keyword || "").toLowerCase();
            list.innerHTML = "";
            textSuggestState[key].filter((v) => !term || v.toLowerCase().includes(term)).slice(0, 100).forEach((v) => {
                const btn = document.createElement("button");
                btn.type = "button";
                btn.className = "facts-dropdown-option";
                btn.innerHTML = `<span>${escapeHtml(v)}</span>`;
                btn.addEventListener("mousedown", (e) => e.preventDefault());
                btn.addEventListener("click", () => {
                    inputEl.value = v;
                    inputEl.dispatchEvent(new Event("change", { bubbles: true }));
                    panel.classList.remove("open");
                });
                list.appendChild(btn);
            });
        }
        inputEl.onfocus = () => { render(inputEl.value); panel.classList.add("open"); };
        inputEl.oninput = () => { render(inputEl.value); panel.classList.add("open"); };
    }

    function stopEnterSubmitWithinModal(modalEl) {
        if (!modalEl) return;
        modalEl.addEventListener("keydown", (e) => {
            if (e.key === "Enter" && e.target && e.target.tagName !== "TEXTAREA") {
                e.preventDefault();
            }
        });
    }

    function escapeHtml(value) {
        return String(value ?? "")
            .replaceAll("&", "&amp;")
            .replaceAll("<", "&lt;")
            .replaceAll(">", "&gt;")
            .replaceAll('"', "&quot;")
            .replaceAll("'", "&#39;");
    }

    async function apiJson(url, method = "GET", body = null) {
        const options = {
            method,
            headers: {
                "X-Requested-With": "XMLHttpRequest",
            },
        };

        if (body !== null) {
            options.headers["Content-Type"] = "application/json";
            options.headers["X-CSRFToken"] = getCsrfToken();
            options.body = JSON.stringify(body);
        }

        const res = await fetch(url, options);
        const text = await res.text();

        let data = null;
        try {
            data = JSON.parse(text);
        } catch (e) {
            console.error("[dashboard.js] non-json response:", {
                url: url,
                status: res.status,
                text: text,
            });
            throw new Error("서버 응답이 JSON 형식이 아닙니다. URL 또는 서버 응답을 확인하십시오.");
        }

        if (!res.ok || !data.ok) {
            throw new Error(data.message || "요청 처리 중 오류가 발생했습니다.");
        }

        return data;
    }

    function getSelectedLineId() {
        const form = qs("dashboardFilterForm");
        if (!form) return "";
        const el = form.querySelector('select[name="lineid"]');
        return el ? (el.value || "") : "";
    }

    function buildDashboardQueryString() {
        const form = qs("dashboardFilterForm");
        const fd = new FormData(form);

        ["include_measure", "include_emergency", "exclude_skiprule_100", "tip_mode"].forEach((name) => {
            fd.delete(name);
            const checked = form.querySelector(`input[name="${name}"][type="checkbox"]`)?.checked;
            fd.append(name, checked ? "1" : "0");
        });

        const params = new URLSearchParams();
        for (const [k, v] of fd.entries()) {
            params.append(k, v);
        }
        return params.toString();
    }

    function getCurrentPrpSnapDate() {
        return qs("tblFilterSnapDate")?.value || dashboardMeta.snap_date || "";
    }

    function isCurrentPrpDateEditable() {
        const selected = getCurrentPrpSnapDate();
        const today = dashboardMeta.snap_date || "";
        return !!selected && !!today && selected === today;
    }

    async function ensureCurrentPrpDateEditable() {
        if (isCurrentPrpDateEditable()) {
            return true;
        }
        await showFactsMessage("현재일로 조회 후 수정바랍니다.");
        return false;
    }

    function buildPrpQueryString() {
        const params = new URLSearchParams();
        const layerSelect = qs("tblFilterLayer");
        const selectedLayers = layerSelect
            ? Array.from(layerSelect.selectedOptions || []).map((opt) => opt.value).filter((v) => String(v).trim() !== "")
            : [];
        const mapping = {
            prp_snap_date: qs("tblFilterSnapDate")?.value || "",
            prp_lineid: qs("tblFilterLine")?.value || "",
            prp_processid: qs("tblFilterPrp")?.value || "",
            prp_area: qs("tblFilterArea")?.value || "",
            prp_step: qs("tblFilterStep")?.value || "",
            prp_descript: qs("tblFilterDescript")?.value || "",
            prp_recipe: qs("tblFilterRecipe")?.value || "",
            prp_type: qs("tblFilterType")?.value || "",
            prp_body_flag: qs("tblFilterBodyFlag")?.value || "",
            prp_cham_flag: qs("tblFilterChamFlag")?.value || "",
            prp_compat_type: qs("tblFilterCompatType")?.value || "",
            prp_always: qs("tblFilterAlways")?.value || "",
            prp_major: qs("tblFilterMajor")?.value || "",
            prp_plan: qs("tblFilterPlan")?.value || "",
        };

        Object.entries(mapping).forEach(([k, v]) => {
            params.set(k, v);
        });
        selectedLayers.forEach((v) => params.append("prp_layer", v));

        return params.toString();
    }


    function validatePrpSearchBeforeRequest() {
        const prp = qs("tblFilterPrp")?.value || "";
        const others = [
            qs("tblFilterLine")?.value || "",
            qs("tblFilterArea")?.value || "",
            Array.from(qs("tblFilterLayer")?.selectedOptions || []).map((opt) => opt.value).filter(Boolean).join(","),
            qs("tblFilterStep")?.value || "",
            qs("tblFilterDescript")?.value || "",
            qs("tblFilterRecipe")?.value || "",
            qs("tblFilterType")?.value || "",
            qs("tblFilterBodyFlag")?.value || "",
            qs("tblFilterChamFlag")?.value || "",
            qs("tblFilterCompatType")?.value || "",
            qs("tblFilterAlways")?.value || "",
            qs("tblFilterMajor")?.value || "",
            qs("tblFilterPlan")?.value || "",
        ];

        if (!prp) {
            return {
                ok: false,
                message: "PRP조건은 필수입니다."
            };
        }

        if (!others.some((x) => String(x).trim() !== "")) {
            return {
                ok: false,
                message: "PRP조건과 그 외 1개 이상의 필터 조건 선택 후 조회 해주십시오."
            };
        }

        return { ok: true, message: "" };
    }

    function validateDashboardSummarySearch() {
        const line = document.querySelector('select[name="lineid"]')?.value || "";
        const prp = document.querySelector('select[name="processid"]')?.value || "";
        if (!String(line).trim() || !String(prp).trim()) {
            return {
                ok: false,
                message: "LINE과 PRP를 모두 선택한 뒤 조회하세요."
            };
        }
        return { ok: true, message: "" };
    }

    function buildDataApiUrl(mode = "all") {
        const merged = new URLSearchParams();
        const debugPrpTableEnabled = (() => {
            try {
                return String(window.localStorage?.getItem("FACTS_DEBUG_PRP_TABLE") || "").trim() === "1";
            } catch (e) {
                return false;
            }
        })();

        if (mode === "summary") {
            const dashboardQs = buildDashboardQueryString();
            for (const [k, v] of new URLSearchParams(dashboardQs).entries()) {
                merged.append(k, v);
            }
            merged.set("summary_only", "1");
        } else if (mode === "prp") {
            const prpQs = buildPrpQueryString();
            for (const [k, v] of new URLSearchParams(prpQs).entries()) {
                merged.append(k, v);
            }
            merged.set("prp_only", "1");
            if (debugPrpTableEnabled) merged.set("debug_prp_table", "1");
        } else {
            const dashboardQs = buildDashboardQueryString();
            const prpQs = buildPrpQueryString();

            for (const [k, v] of new URLSearchParams(dashboardQs).entries()) {
                merged.append(k, v);
            }
            for (const [k, v] of new URLSearchParams(prpQs).entries()) {
                merged.append(k, v);
            }
        }

        return `${dashboardApiUrls.dashboardDataApi}?${merged.toString()}`;
    }

    function updateExportLinks() {
        const filteredBtn = qs("prpExcelDownloadBtn");
        const allBtn = qs("prpExcelDownloadAllBtn");
        const prpQs = new URLSearchParams(buildPrpQueryString());

        if (filteredBtn) {
            filteredBtn.setAttribute(
                "data-export-url",
                `${dashboardApiUrls.prpExportCsvApi}?${prpQs.toString()}`
            );
        }

        const merged = new URLSearchParams();
        merged.set("prp_snap_date", qs("tblFilterSnapDate")?.value || "");
        merged.set("prp_lineid", qs("tblFilterLine")?.value || "");
        merged.set("prp_processid", qs("tblFilterPrp")?.value || "");
        if (allBtn) {
            allBtn.setAttribute(
                "data-export-url",
                `${dashboardApiUrls.prpExportCsvAllApi}?${merged.toString()}`
            );
        }

    }

    const factsMessageModal = qs("factsMessageModal");
    const factsMessageTitle = qs("factsMessageTitle");
    const factsMessageBody = qs("factsMessageBody");
    const factsMessageOkBtn = qs("factsMessageOkBtn");

    const factsConfirmModal = qs("factsConfirmModal");
    const factsConfirmTitle = qs("factsConfirmTitle");
    const factsConfirmBody = qs("factsConfirmBody");
    const factsConfirmCancelBtn = qs("factsConfirmCancelBtn");
    const factsConfirmOkBtn = qs("factsConfirmOkBtn");

    function showFactsMessage(message, title = "FACTS의 메시지") {
        return new Promise((resolve) => {
            factsMessageTitle.textContent = title;
            factsMessageBody.textContent = message;
            openModal(factsMessageModal);

            const handleOk = () => {
                factsMessageOkBtn.removeEventListener("click", handleOk);
                closeModal(factsMessageModal);
                resolve(true);
            };

            factsMessageOkBtn.addEventListener("click", handleOk);
        });
    }

    
    function validateDownloadPreconditions(requireMultiPrp = false) {
        const line = qs("tblFilterLine")?.value || "";
        const prp = qs("tblFilterPrp")?.value || "";
        const hasRows = Array.isArray(state.currentRows) && state.currentRows.length > 0;
        if (!line || !prp) return { ok:false, message:"LINE과 PRP를 선택한 뒤 조회 후 다운로드하세요." };
        if (!hasRows) return { ok:false, message:"조회 후 다운로드하세요." };
        return {ok:true};
    }

    function showFactsConfirm(message, title = "FACTS의 메시지") {
        return new Promise((resolve) => {
            factsConfirmTitle.textContent = title;
            factsConfirmBody.textContent = message;
            openModal(factsConfirmModal);

            const cleanup = () => {
                factsConfirmOkBtn.removeEventListener("click", handleOk);
                factsConfirmCancelBtn.removeEventListener("click", handleCancel);
            };

            const handleOk = () => {
                cleanup();
                closeModal(factsConfirmModal);
                resolve(true);
            };

            const handleCancel = () => {
                cleanup();
                closeModal(factsConfirmModal);
                resolve(false);
            };

            factsConfirmOkBtn.addEventListener("click", handleOk);
            factsConfirmCancelBtn.addEventListener("click", handleCancel);
        });
    }

    stopEnterSubmitWithinModal(factsMessageModal);
    stopEnterSubmitWithinModal(factsConfirmModal);

    function renderSummary(data) {
        if (data?.pre_query_state || data?.requires_line_prp) {
            if (qs("summaryCompatRate")) qs("summaryCompatRate").textContent = "PRP 선택 필요";
            if (qs("summaryTotalSteps")) qs("summaryTotalSteps").textContent = "-";
            if (qs("summarySingleCnt")) qs("summarySingleCnt").textContent = "-";
            if (qs("summaryBodyCnt")) qs("summaryBodyCnt").textContent = "-";
            if (qs("summaryChamCnt")) qs("summaryChamCnt").textContent = "-";
            if (qs("summaryUnregisteredCnt")) qs("summaryUnregisteredCnt").textContent = "-";
            if (qs("summaryNoPathCnt")) qs("summaryNoPathCnt").textContent = "-";
            if (qs("summaryTargetMonthly")) qs("summaryTargetMonthly").textContent = "-";
            return;
        }
        if (qs("summaryCompatRate")) {
            qs("summaryCompatRate").textContent = `${Number(data.summary?.compat_rate ?? 0).toFixed(1)}%`;
        }
        if (qs("summaryTotalSteps")) {
            qs("summaryTotalSteps").textContent = String(data.summary?.total_steps ?? 0);
        }
        if (qs("summarySingleCnt")) {
            qs("summarySingleCnt").textContent = String(data.summary?.single_cnt ?? 0);
        }
        if (qs("summaryBodyCnt")) {
            qs("summaryBodyCnt").textContent = String(data.summary?.body_cnt ?? 0);
        }
        if (qs("summaryChamCnt")) {
            qs("summaryChamCnt").textContent = String(data.summary?.cham_cnt ?? 0);
        }
        if (qs("summaryUnregisteredCnt")) {
            qs("summaryUnregisteredCnt").textContent = String(data.summary?.unregistered_cnt ?? 0);
        }
        if (qs("summaryNoPathCnt")) {
            qs("summaryNoPathCnt").textContent = String(data.summary?.no_path_cnt ?? 0);
        }
        if (qs("summaryTargetMonthly")) {
            qs("summaryTargetMonthly").textContent =
                data.target_monthly === null || data.target_monthly === undefined
                    ? "-"
                    : `${Number(data.target_monthly).toFixed(1)}%`;
        }

    }

    function renderFilterOptions(data) {
        const refresh = window.FACTSDashboardFilters && window.FACTSDashboardFilters.refreshSelectOptions;
        if (refresh) {
            const currentLayerValues = Array.from(qs("tblFilterLayer")?.options || []).map((opt) => String(opt.value || "")).filter(Boolean);
            const nextLayerValues = (data.table_layer_options || []).length ? (data.table_layer_options || []) : currentLayerValues;
            refresh(qs("tblFilterLine"), data.table_line_options || [], true, false);
            refresh(qs("tblFilterArea"), data.table_area_options || [], true, false);
            refresh(qs("tblFilterLayer"), nextLayerValues, false, false);
            refresh(qs("tblFilterType"), data.table_type_options || [], true, false);
            refresh(qs("tblFilterBodyFlag"), data.table_body_options || [], true, false);
            refresh(qs("tblFilterChamFlag"), data.table_cham_options || [], true, false);
            refresh(qs("tblFilterCompatType"), data.table_compat_options || [], true, false);
            refresh(qs("tblFilterAlways"), data.table_always_options || [], true, false);
            refresh(qs("tblFilterMajor"), data.table_major_options || [], true, false);
            refresh(qs("tblFilterPlan"), data.table_plan_options || [], true, false);
            refresh(qs("tblFilterPrp"), data.table_prp_options || [], true, false);
            refresh(qs("tblFilterStep"), data.table_step_options || [], true, false);
            state.tableDescriptOptions = data.table_descript_options || [];
            state.tableRecipeOptions = data.table_recipe_options || [];
        }
        ensureTextSuggestDropdown(qs("tblFilterDescript"), state.tableDescriptOptions, "descript");
        ensureTextSuggestDropdown(qs("tblFilterRecipe"), state.tableRecipeOptions, "recipe");
        bindLayerDropdown();
        if (window.FACTSSearchableSelect && window.FACTSSearchableSelect.init) {
            window.FACTSSearchableSelect.init(document);
        }
        if (window.FACTSDashboardFilters && window.FACTSDashboardFilters.syncMultiDropdowns) {
            window.FACTSDashboardFilters.syncMultiDropdowns(document);
        }
    }


    function renderDashboardFilterOptions(data) {
        const refresh = window.FACTSDashboardFilters && window.FACTSDashboardFilters.refreshSelectOptions;
        if (!refresh) return;
        refresh(document.querySelector('select[name="lineid"]'), data.lineids || [], true, false);
        refresh(document.querySelector('select[name="processid"]'), data.processes || [], true, false);
        refresh(document.querySelector('select[name="areaname"]'), data.areas || [], true, false);
        refresh(document.querySelector('select[name="layerid"]'), data.layers || [], false, false);
        bindLayerDropdown();
    }


    async function loadDashboardFilterOptionsOnly() {
            const urls = dashboardApiUrls || {};
            const snapDateEl = document.querySelector('input[name="snap_date"]');
            const lineEl = document.querySelector('select[name="lineid"]');
            const prpEl = document.querySelector('select[name="processid"]');
            const areaEl = document.querySelector('select[name="areaname"]');
            const layerEl = document.querySelector('select[name="layerid"]');

            const selectedLayers = layerEl
                ? Array.from(layerEl.selectedOptions || []).map((opt) => opt.value).filter((v) => String(v).trim() !== "")
                : [];

            const params = new URLSearchParams({
                snap_date: snapDateEl ? snapDateEl.value : "",
                lineid: lineEl ? lineEl.value : "",
                processid: prpEl ? prpEl.value : "",
                areaname: areaEl ? areaEl.value : "",
                include_measure: document.querySelector('input[name="include_measure"]:checked') ? "1" : "0",
                include_emergency: document.querySelector('input[name="include_emergency"]:checked') ? "1" : "0",
                exclude_skiprule_100: document.querySelector('input[name="exclude_skiprule_100"]:checked') ? "1" : "0",
                tip_mode: document.querySelector('input[name="tip_mode"]:checked') ? "1" : "0",
            });
            selectedLayers.forEach((v) => params.append("layerid", v));

            if (!urls.dashboardFilterOptionsApi) return;
            const cacheKey = params.toString();
            if (state.dashboardOptionCache.has(cacheKey)) {
                renderDashboardFilterOptions(state.dashboardOptionCache.get(cacheKey));
                return;
            }
            const data = await apiJson(`${urls.dashboardFilterOptionsApi}?${cacheKey}`, "GET");
            state.dashboardOptionCache.set(cacheKey, data);
            renderDashboardFilterOptions(data);
    }


    async function loadPrpOptionsOnly(forceRefresh = false) {
        const prpQs = buildPrpQueryString();
        if (!forceRefresh && state.optionCache.has(prpQs)) {
            renderFilterOptions(state.optionCache.get(prpQs));
            return;
        }
        if (state.optionFetchInFlight) return;
        state.optionFetchInFlight = true;
        try {
            const url = `${dashboardApiUrls.dashboardPrpOptionsApi}?${prpQs}`;
            const data = await apiJson(url, "GET");
            state.optionCache.set(prpQs, data);
            renderFilterOptions(data);
        } finally {
            state.optionFetchInFlight = false;
        }

    }

    function schedulePrpOptionRefresh(delayMs = 120) {
        if (state.optionFetchTimer) {
            clearTimeout(state.optionFetchTimer);
        }
        state.optionFetchTimer = setTimeout(() => {
            loadPrpOptionsOnly(false).catch((e) => console.error(e));
        }, delayMs);
    }

    async function showDownloadFeedback(buttonId) {
        const btn = qs(buttonId);
        if (!btn || btn.dataset.downloading === "1") return false;
        btn.dataset.downloading = "1";
        btn.disabled = true;
        await showFactsMessage("확인 버튼을 누르면 다운로드를 준비합니다. 잠시만 기다려주세요.");
        if (state.exportButtonTimers.get(buttonId)) clearTimeout(state.exportButtonTimers.get(buttonId));
        const timer = setTimeout(() => {
            btn.dataset.downloading = "0";
            btn.disabled = false;
            state.exportButtonTimers.delete(buttonId);
        }, 4000);
        state.exportButtonTimers.set(buttonId, timer);
        return true;
    }


    function renderEmptyPrpMessage(message) {
        const tbody = qs("prpDashboardTbody");
        if (!tbody) return;
        tbody.innerHTML = `<tr><td colspan="40" class="empty-cell">${escapeHtml(message)}</td></tr>`;
    }

    function renderTable(rows) {
        state.currentRows = rows || [];

        if (!rows || rows.length === 0) {
            renderEmptyPrpMessage("조회 결과가 없습니다.");
            return;
        }

        let html = "";

        rows.forEach((row) => {
            html += `
                <tr
                    data-lineid="${escapeHtml(row.lineid || "")}"
                    data-processid="${escapeHtml(row.processid)}"
                    data-step="${escapeHtml(row.stepseq)}"
                    data-area="${escapeHtml(row.areaname)}"
                    data-layer="${escapeHtml(row.layerid)}"
                    data-descript="${escapeHtml(row.descript)}"
                    data-recipe="${escapeHtml(row.recipeid)}"
                    data-type="${escapeHtml(row.stepseq_type)}"
                    data-bodyflag="${escapeHtml(row.body_compat_flag)}"
                    data-chamflag="${escapeHtml(row.cham_compat_flag)}"
                    data-compattype="${escapeHtml(row.compat_type)}"
                    data-always="${escapeHtml(row.always_summary_text || `상시:0, 비상시:0`)}"
                    data-major="${escapeHtml(row.major_summary_text || `주요:0, 비주요:0`)}"
                    data-plan="${escapeHtml(row.plan_flag || "N")}"
                    data-tipmissing="${escapeHtml(row.tip_missing_flag || "N")}"
                >
                    <td class="center-cell"><input type="checkbox" class="row-check prp-row-check" tabindex="0"></td>
                    <td class="center-cell"><div class="cell-readonly" tabindex="0">${escapeHtml(row.lineid || "")}</div></td>
                    <td class="center-cell"><div class="cell-readonly" tabindex="0">${escapeHtml(row.processid)}</div></td>
                    <td class="center-cell"><div class="cell-readonly" tabindex="0">${escapeHtml(row.areaname)}</div></td>
                    <td class="center-cell"><div class="cell-readonly" tabindex="0">${escapeHtml(row.layerid)}</div></td>
                    <td class="center-cell"><div class="cell-readonly" tabindex="0">${escapeHtml(row.stepseq)}</div></td>
                    <td class="center-cell"><div class="cell-readonly" tabindex="0">${escapeHtml(row.skiprule)}</div></td>
                    <td class="left-cell"><div class="cell-readonly" tabindex="0">${escapeHtml(row.descript)}</div></td>
                    <td class="left-cell"><div class="cell-readonly" tabindex="0">${escapeHtml(row.recipeid)}</div></td>
                    <td class="center-cell eqpgroup-cell">
                        <div class="cell-readonly" tabindex="0">${row.eqpgroup_html || escapeHtml(row.eqpgroup || "")}</div>
                    </td>
                    <td class="center-cell">
                        <div class="cell-readonly cham-info-cell" tabindex="0">${row.cham_html || escapeHtml(row.cham_display || "")}</div>
                    </td>
                    <td class="center-cell"><div class="cell-readonly" tabindex="0">${escapeHtml(row.stepseq_type)}</div></td>
                    <td class="center-cell"><div class="cell-readonly" tabindex="0">${escapeHtml(row.body_compat_flag)}</div></td>
                    <td class="center-cell"><div class="cell-readonly" tabindex="0">${escapeHtml(row.cham_compat_flag)}</div></td>
                    <td class="center-cell"><div class="cell-readonly" tabindex="0">${escapeHtml(row.body_path_count)}</div></td>
                    <td class="center-cell"><div class="cell-readonly" tabindex="0">${escapeHtml(row.cham_path_count)}</div></td>
                    <td class="center-cell compat-cell compat-${escapeHtml(row.compat_type_base || row.compat_type)}">
                        <div class="cell-readonly compat-label-cell" tabindex="0">${escapeHtml(row.compat_type_base || row.compat_type)}</div>
                    </td>
                    <td class="center-cell"><div class="cell-readonly" tabindex="0">${escapeHtml((row.body_compat_flag === "Y" || row.cham_compat_flag === "Y") ? "Y" : "N")}</div></td>
                    <td class="center-cell">
                        ${
                            row.override_editable
                                ? `
                                    <button
                                        type="button"
                                        class="cell-action-btn open-always-modal-btn"
                                        data-lineid="${escapeHtml(row.lineid || "")}"
                                        data-processid="${escapeHtml(row.processid)}"
                                        data-step="${escapeHtml(row.stepseq)}"
                                    >
                                        ${escapeHtml(row.always_summary_text || `상시:0, 비상시:0`)}
                                    </button>
                                `
                                : `
                                    <span
                                        class="disabled-action-tooltip-trigger"
                                        data-tooltip="${escapeHtml(row.override_disabled_reason || "")}"
                                        tabindex="0"
                                        style="display:inline-block;"
                                    >
                                        <button
                                            type="button"
                                            class="cell-action-btn"
                                            disabled
                                            style="pointer-events:none;"
                                        >
                                            ${escapeHtml(row.always_summary_text || `상시:0, 비상시:0`)}
                                        </button>
                                    </span>
                                `
                        }
                    </td>
                    <td class="center-cell">
                        ${
                            row.override_editable
                                ? `
                                    <button
                                        type="button"
                                        class="cell-action-btn open-major-modal-btn"
                                        data-lineid="${escapeHtml(row.lineid || "")}"
                                        data-processid="${escapeHtml(row.processid)}"
                                        data-step="${escapeHtml(row.stepseq)}"
                                    >
                                        ${escapeHtml(row.major_summary_text || `주요:0, 비주요:0`)}
                                    </button>
                                `
                                : `
                                    <span
                                        class="disabled-action-tooltip-trigger"
                                        data-tooltip="${escapeHtml(row.override_disabled_reason || "")}"
                                        tabindex="0"
                                        style="display:inline-block;"
                                    >
                                        <button
                                            type="button"
                                            class="cell-action-btn"
                                            disabled
                                            style="pointer-events:none;"
                                        >
                                            ${escapeHtml(row.major_summary_text || `주요:0, 비주요:0`)}
                                        </button>
                                    </span>
                                `
                        }
                    </td>
                    <td class="center-cell">
                        <button
                            type="button"
                            class="cell-action-btn open-plan-modal-btn"
                            data-lineid="${escapeHtml(row.lineid || "")}"
                            data-processid="${escapeHtml(row.processid)}"
                            data-step="${escapeHtml(row.stepseq)}"
                        >
                            ${escapeHtml(row.plan_flag || "N")}
                        </button>
                    </td>
                    <td class="left-cell"><div class="cell-readonly long-cell" tabindex="0">${escapeHtml(row.plan_body_names || "")}</div></td>
                    <td class="left-cell"><div class="cell-readonly long-cell" tabindex="0">${escapeHtml(row.plan_cham_names || "")}</div></td>
                    <td class="left-cell"><div class="cell-readonly long-cell" tabindex="0">${escapeHtml(row.plan_due_dates || "")}</div></td>
                    <td class="left-cell"><div class="cell-readonly long-cell" tabindex="0">${escapeHtml(row.plan_eval_lot_ids || "")}</div></td>
                    <td class="left-cell"><div class="cell-readonly long-cell" tabindex="0">${escapeHtml(row.plan_eval_stages || "")}</div></td>
                    <td class="left-cell"><div class="cell-readonly long-cell" tabindex="0">${escapeHtml(row.plan_memos || "")}</div></td>
                    <td class="center-cell">
                        <button
                            type="button"
                            class="cell-action-btn open-tip-missing-modal-btn"
                            data-lineid="${escapeHtml(row.lineid || "")}"
                            data-processid="${escapeHtml(row.processid)}"
                            data-step="${escapeHtml(row.stepseq)}"
                        >
                            ${escapeHtml(row.tip_missing_flag || "N")}
                        </button>
                    </td>
                    <td class="left-cell"><div class="cell-readonly long-cell" tabindex="0">${escapeHtml(row.tip_missing_always || "")}</div></td>
                    <td class="left-cell"><div class="cell-readonly long-cell" tabindex="0">${escapeHtml(row.tip_missing_major || "")}</div></td>
                    <td class="left-cell"><div class="cell-readonly long-cell" tabindex="0">${escapeHtml(row.tip_missing_body || "")}</div></td>
                    <td class="left-cell"><div class="cell-readonly long-cell" tabindex="0">${escapeHtml(row.tip_missing_cham || "")}</div></td>
                    <td class="center-cell compat-cell compat-${escapeHtml(row.compat_type_tip || "")}">
                        <div class="cell-readonly compat-label-cell" tabindex="0">${escapeHtml(row.compat_type_tip || "")}</div>
                    </td>
                    <td class="center-cell"><div class="cell-readonly" tabindex="0">${escapeHtml((row.body_compat_tip === "Y" || row.cham_compat_tip === "Y") ? "Y" : "N")}</div></td>
                    <td class="center-cell"><div class="cell-readonly" tabindex="0">${escapeHtml(row.body_compat_tip)}</div></td>
                    <td class="center-cell"><div class="cell-readonly" tabindex="0">${escapeHtml(row.cham_compat_tip)}</div></td>
                    <td class="center-cell"><div class="cell-readonly" tabindex="0">${escapeHtml(row.body_compat_count_tip)}</div></td>
                    <td class="center-cell"><div class="cell-readonly" tabindex="0">${escapeHtml(row.cham_compat_count_tip)}</div></td>
                    <td class="left-cell"><div class="cell-readonly long-cell" tabindex="0">${escapeHtml(row.tip || "")}</div></td>
                    <td class="left-cell"><div class="cell-readonly long-cell" tabindex="0">${escapeHtml(row.childeqp || "")}</div></td>
                </tr>
            `;
        });

        qs("prpDashboardTbody").innerHTML = html;
        bindPrpShiftRangeCheck();
        bindDynamicButtons();
        initCellKeyboardNavigation("#prpCellTable");
        if (window.bindFactsTooltipTargets) {
            window.bindFactsTooltipTargets(".disabled-action-tooltip-trigger");
        }

    }

    function renderChart(chartData) {
        const canvas = qs("factsMainChart");
        const emptyMsg = qs("chartEmptyMessage");

        if (!canvas) {
            console.error("[dashboard.js] #factsMainChart canvas not found");
            if (emptyMsg) {
                emptyMsg.textContent = "그래프 캔버스를 찾을 수 없습니다.";
                emptyMsg.classList.remove("hidden");
            }
            return;
        }

        if (typeof Chart === "undefined") {
            console.error("[dashboard.js] Chart is undefined. Chart.js 로드 여부를 확인하십시오.");
            if (emptyMsg) {
                emptyMsg.textContent = "Chart.js가 로드되지 않았습니다.";
                emptyMsg.classList.remove("hidden");
            }
            return;
        }

        const labels = chartData?.labels || [];
        const totalValues = chartData?.total_values || [];
        const bodyValues = chartData?.body_values || [];
        const chamValues = chartData?.cham_values || [];
        const targetValues = chartData?.target_values || [];

        const hasAnyXAxis = labels.length > 0;
        const hasAnyValue = [...totalValues, ...bodyValues, ...chamValues, ...targetValues].some(
            (v) => v !== null && v !== undefined
        );

        if (!hasAnyXAxis || !hasAnyValue) {
            if (emptyMsg) {
                emptyMsg.classList.remove("hidden", "pre-query");
                emptyMsg.classList.add("no-data");
            }
            if (state.chart) {
                state.chart.destroy();
                state.chart = null;
            }
            return;
        }

        if (emptyMsg) emptyMsg.classList.add("hidden");

        const segmentDividerPlugin = {
            id: "segmentDividerPlugin",
            afterDraw(chart) {
                const { ctx, scales } = chart;
                const x = scales.x;
                if (!x) return;

                const labels = chart.data.labels || [];
                const boundaries = [];
                for (let i = 1; i < labels.length; i++) {
                    const prev = labels[i - 1];
                    const curr = labels[i];
                    if ((prev === "" && curr !== "") || (prev !== "" && curr === "")) {
                        boundaries.push(i - 0.5);
                    }
                }

                ctx.save();
                ctx.strokeStyle = "rgba(15,93,160,0.18)";
                ctx.lineWidth = 1;

                boundaries.forEach((idx) => {
                    const xPos = x.getPixelForValue(idx);
                    ctx.beginPath();
                    ctx.moveTo(xPos, chart.chartArea.top);
                    ctx.lineTo(xPos, chart.chartArea.bottom);
                    ctx.stroke();
                });

                ctx.restore();
            }
        };

        const smartValueLabelPlugin = {
            id: "smartValueLabelPlugin",
            afterDatasetsDraw(chart) {
                const { ctx } = chart;
                const totalMeta = chart.getDatasetMeta(0);
                const totalDataset = chart.data.datasets[0];
                const bodyMeta = chart.getDatasetMeta(1);
                const bodyDataset = chart.data.datasets[1];

                ctx.save();
                ctx.font = "12px Arial";
                ctx.textAlign = "center";

                totalMeta.data.forEach((point, index) => {
                    const totalVal = totalDataset.data[index];
                    if (totalVal === null || totalVal === undefined || Number.isNaN(totalVal)) return;
                    ctx.fillStyle = "#0f5da0";
                    ctx.textBaseline = "bottom";
                    ctx.fillText(`${Number(totalVal).toFixed(1)}%`, point.x, point.y - 8);
                });

                bodyMeta.data.forEach((point, index) => {
                    const bodyVal = bodyDataset.data[index];
                    if (bodyVal === null || bodyVal === undefined || Number.isNaN(bodyVal)) return;
                    ctx.fillStyle = "#22a06b";
                    ctx.textBaseline = "top";
                    ctx.fillText(`${Number(bodyVal).toFixed(1)}%`, point.x, point.y + 8);
                });

                ctx.restore();
            }
        };

        try {
            if (state.chart) {
                state.chart.destroy();
            }

            state.chart = new Chart(canvas.getContext("2d"), {
                type: "line",
                data: {
                    labels: labels,
                    datasets: [
                        {
                            label: "TOTAL",
                            data: totalValues,
                            borderWidth: 2,
                            tension: 0.15,
                            fill: false,
                            borderColor: "#0f5da0",
                            backgroundColor: "#0f5da0",
                            pointRadius: 3,
                            spanGaps: false,
                        },
                        {
                            label: "BODY",
                            data: bodyValues,
                            borderWidth: 2,
                            tension: 0.15,
                            fill: false,
                            borderColor: "#22a06b",
                            backgroundColor: "#22a06b",
                            pointRadius: 3,
                            spanGaps: false,
                        },
                        {
                            label: "CHAM",
                            data: chamValues,
                            borderWidth: 2,
                            tension: 0.15,
                            fill: false,
                            borderColor: "#6f42c1",
                            backgroundColor: "#6f42c1",
                            pointRadius: 3,
                            spanGaps: false,
                        },
                        {
                            label: "TARGET",
                            data: targetValues,
                            borderWidth: 2,
                            tension: 0,
                            fill: false,
                            borderColor: "#e55353",
                            backgroundColor: "#e55353",
                            borderDash: [8, 6],
                            pointRadius: 0,
                            spanGaps: false,
                        }
                    ]
                },
                options: {
                    responsive: true,
                    maintainAspectRatio: false,
                    animation: false,
                    interaction: {
                        mode: "nearest",
                        intersect: false
                    },
                    layout: {
                        padding: { left: 6, right: 6, bottom: 0 }
                    },
                    plugins: {
                        legend: {
                            position: "top"
                        },
                        tooltip: {
                            enabled: true,
                            callbacks: {
                                label: function (context) {
                                    if (context.raw === null || context.raw === undefined) return "";
                                    return `${context.dataset.label}: ${Number(context.raw).toFixed(1)}%`;
                                }
                            }
                        }
                    },
                    scales: {
                        x: {
                            offset: true,
                            ticks: {
                                autoSkip: false,
                                maxRotation: 0,
                                minRotation: 0,
                                padding: 4
                            }
                        },
                        y: {
                            beginAtZero: true,
                            max: 100
                        }
                    }
                },
                plugins: [smartValueLabelPlugin, segmentDividerPlugin]
            });
        } catch (e) {
            console.error("Chart render error:", e);
            if (emptyMsg) emptyMsg.classList.remove("hidden");
        }

    }

    async function refreshSummaryOnly() {
        const validation = validateDashboardSummarySearch();
        if (!validation.ok) {
            await showFactsMessage(validation.message);
            return;
        }

        if (state.summaryFetchInFlight) return;
        state.summaryFetchInFlight = true;
        try {
            showLoading();
            const data = await apiJson(buildDataApiUrl("summary"), "GET");

            renderSummary(data);
            if (data.requires_line_prp) {
                await showFactsMessage(data.message || "LINE과 PRP를 모두 선택한 뒤 조회하세요.");
            }

            combinedSeries = data.combined_series || {
                labels: [],
                total_values: [],
                body_values: [],
                cham_values: [],
                target_values: [],
            };

            renderChart(combinedSeries);
        } catch (e) {
            console.error(e);
            hideLoading();
            await showFactsMessage(e.message || "조회 중 오류가 발생했습니다.");
        } finally {
            state.summaryFetchInFlight = false;
            hideLoading();
        }

    }
