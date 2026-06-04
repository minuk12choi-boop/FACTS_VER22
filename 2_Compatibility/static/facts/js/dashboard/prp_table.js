(function () {
    "use strict";
    const PRP_TABLE_JS_VERSION = "eqptype-delaytime-render-20260603";
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
        tbody.innerHTML = `<tr><td colspan="42" class="empty-cell">${escapeHtml(message)}</td></tr>`;
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
                    data-eqptype="${escapeHtml(row.eqptype || "")}"
                    data-delaytime="${escapeHtml(row.delaytime || "")}"
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
                    <td class="center-cell"><div class="cell-readonly" tabindex="0">${escapeHtml(row.eqptype || "")}</div></td>
                    <td class="center-cell"><div class="cell-readonly" tabindex="0">${escapeHtml(row.delaytime || "")}</div></td>
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


     async function refreshPrpTableOnly() {
        const validation = validatePrpSearchBeforeRequest();
        if (!validation.ok) {
            hideLoading();
            renderEmptyPrpMessage(validation.message);
            await showFactsMessage(validation.message);
            return;
        }

        if (state.prpFetchInFlight) return;
        state.prpFetchInFlight = true;
        try {
            showLoading();
            updateExportLinks();

            const data = await apiJson(buildDataApiUrl("prp"), "GET");

            renderFilterOptions(data);

            if (data.message) {
                hideLoading();
                renderEmptyPrpMessage(data.message);
                await showFactsMessage(data.message);
            } else if (data.rows && data.rows.length) {
                renderTable(data.rows);
            } else {
                renderEmptyPrpMessage("조회 결과가 없습니다.");
            }
        } catch (e) {
            console.error(e);
            hideLoading();
            await showFactsMessage(e.message || "조회 중 오류가 발생했습니다.");
        } finally {
            state.prpFetchInFlight = false;
            hideLoading();
        }

    }

    const calcInfoBtn = qs("calcInfoBtn");
    const guideModal = qs("guideModal");
    const guidePrevBtn = qs("guidePrevBtn");
    const guideNextBtn = qs("guideNextBtn");
    const guideCloseBtn = qs("guideCloseBtn");
    const guidePageInfo = qs("guidePageInfo");
    const guideImageViewer = qs("guideImageViewer");
    const guideEmptyMessage = qs("guideEmptyMessage");
    const guidePages = Array.isArray(guidePagesData) ? guidePagesData : [];



    function renderGuidePage() {
        if (!guidePages.length) {
            guideImageViewer.classList.add("hidden");
            guideEmptyMessage.classList.remove("hidden");
            guidePageInfo.textContent = "0 / 0";
            guidePrevBtn.disabled = true;
            guideNextBtn.disabled = true;
            return;
        }

        const page = guidePages[state.guideCurrentIndex];
        guideImageViewer.src = page.image_url;
        guideImageViewer.classList.remove("hidden");
        guideEmptyMessage.classList.add("hidden");
        guidePageInfo.textContent = `${state.guideCurrentIndex + 1} / ${guidePages.length}`;
        guidePrevBtn.disabled = state.guideCurrentIndex === 0;
        guideNextBtn.disabled = state.guideCurrentIndex === guidePages.length - 1;
    }

    function openGuideModal() {
        renderGuidePage();
        openModal(guideModal);
    }

    function moveGuidePage(delta) {
        if (!guidePages.length) return;
        const nextIndex = state.guideCurrentIndex + delta;
        if (nextIndex < 0 || nextIndex >= guidePages.length) return;
        state.guideCurrentIndex = nextIndex;
        renderGuidePage();
    }

    calcInfoBtn?.addEventListener("click", openGuideModal);
    guideCloseBtn?.addEventListener("click", () => closeModal(guideModal));
    guidePrevBtn?.addEventListener("click", () => moveGuidePage(-1));
    guideNextBtn?.addEventListener("click", () => moveGuidePage(1));

    guideModal?.addEventListener("wheel", (e) => {
        if (!guidePages.length) return;
        e.preventDefault();

        if (state.guideWheelLock) return;
        state.guideWheelLock = true;

        if (e.deltaY > 0) moveGuidePage(1);
        else if (e.deltaY < 0) moveGuidePage(-1);

        setTimeout(() => {
            state.guideWheelLock = false;
        }, 180);
    }, { passive: false });

    stopEnterSubmitWithinModal(guideModal);

    (function initHeaderTooltips() {
        let tooltipEl = null;

        function removeTooltip() {
            if (tooltipEl) {
                tooltipEl.remove();
                tooltipEl = null;
            }
        }

        function createTooltip(text) {
            removeTooltip();
            tooltipEl = document.createElement("div");
            tooltipEl.className = "custom-th-tooltip";
            tooltipEl.textContent = text;
            document.body.appendChild(tooltipEl);
            return tooltipEl;
        }

        function positionTooltip(target) {
            if (!tooltipEl || !target) return;

            const rect = target.getBoundingClientRect();
            const tooltipRect = tooltipEl.getBoundingClientRect();

            let top = rect.top - tooltipRect.height - 8;
            let left = rect.left + (rect.width / 2) - (tooltipRect.width / 2);

            if (left < 8) left = 8;
            if (left + tooltipRect.width > window.innerWidth - 8) {
                left = window.innerWidth - tooltipRect.width - 8;
            }
            if (top < 8) top = rect.bottom + 8;

            tooltipEl.style.top = `${top}px`;
            tooltipEl.style.left = `${left}px`;
        }

        function bindTooltipTargets(selector) {
            document.querySelectorAll(selector).forEach((el) => {
                if (el.dataset.tooltipBound === "1") return;
                el.dataset.tooltipBound = "1";

                el.addEventListener("mouseenter", () => {
                    const text = el.getAttribute("data-tooltip");
                    if (!text) return;
                    createTooltip(text);
                    positionTooltip(el);
                });
                el.addEventListener("mousemove", () => positionTooltip(el));
                el.addEventListener("mouseleave", removeTooltip);
                el.addEventListener("focus", () => {
                    const text = el.getAttribute("data-tooltip");
                    if (!text) return;
                    createTooltip(text);
                    positionTooltip(el);
                });
                el.addEventListener("blur", removeTooltip);
                el.addEventListener("click", () => {
                    const text = el.getAttribute("data-tooltip");
                    if (!text) return;
                    createTooltip(text);
                    positionTooltip(el);
                });
            });
        }

        bindTooltipTargets(".th-help");
        window.bindFactsTooltipTargets = bindTooltipTargets;

        window.addEventListener("scroll", removeTooltip, true);
        window.addEventListener("resize", removeTooltip);
    })();

    const prpWrap = qs("prpTableWrap");

    qs("prpScrollTopBtn")?.addEventListener("click", () => {
        prpWrap?.scrollTo({ top: 0, behavior: "smooth" });
    });

    qs("prpScrollBottomBtn")?.addEventListener("click", () => {
        prpWrap?.scrollTo({ top: prpWrap.scrollHeight, behavior: "smooth" });
    });

    qs("dashboardSearchBtn")?.addEventListener("click", refreshSummaryOnly);
    qs("tblFilterSearchBtn")?.addEventListener("click", refreshPrpTableOnly);

    const multiDownloadModal = qs("multiPrpDownloadModal");
    const MAX_MULTI_DOWNLOAD_PRP = 20;
    const multiDownloadState = { allPrps: [], selectedPrps: new Set() };

    function renderMultiDownloadPrpOptions() {
        const listEl = qs("multi-download-prp-dropdown");
        if (!listEl) return;
        const keyword = String(qs("multiDownloadPrpSearch")?.value || "").trim().toLowerCase();
        listEl.innerHTML = "";
        multiDownloadState.allPrps.filter((prp) => !keyword || prp.toLowerCase().includes(keyword)).forEach((prp) => {
            const row = document.createElement("label");
            row.className = "multi-download-prp-item";
            row.innerHTML = `<input type="checkbox" value="${escapeHtml(prp)}" ${multiDownloadState.selectedPrps.has(prp) ? "checked" : ""}><span>${escapeHtml(prp)}</span>`;
            const cb = row.querySelector("input");
            cb.addEventListener("change", async () => {
                if (cb.checked && multiDownloadState.selectedPrps.size >= MAX_MULTI_DOWNLOAD_PRP) {
                    cb.checked = false;
                    await showFactsMessage(`PRP는 최대 ${MAX_MULTI_DOWNLOAD_PRP}개까지 선택 가능합니다.`);
                    return;
                }
                if (cb.checked) multiDownloadState.selectedPrps.add(prp); else multiDownloadState.selectedPrps.delete(prp);
                qs("multiDownloadPrpCount").textContent = `${multiDownloadState.selectedPrps.size}개 PRP 선택`;
            });
            listEl.appendChild(row);
        });
        qs("multiDownloadPrpCount").textContent = `${multiDownloadState.selectedPrps.size}개 PRP 선택`;
    }

    async function loadMultiDownloadOptions() {
        const snapDate = qs("multiDownloadSnapDate")?.value || "";
        const line = qs("multiDownloadLine")?.value || "";
        const params = new URLSearchParams();
        params.set("prp_snap_date", snapDate);
        params.set("prp_lineid", line);
        const data = await apiJson(`${dashboardApiUrls.dashboardPrpOptionsApi}?${params.toString()}`, "GET");
        const lines = data.table_line_options || data.line_options || [];
        const lineSelect = qs("multiDownloadLine");
        if (lineSelect && lineSelect.options.length <= 1) {
            lineSelect.innerHTML = '<option value="">선택</option>' + lines.map((v) => `<option value="${escapeHtml(v)}">${escapeHtml(v)}</option>`).join("");
            if (line && lines.includes(line)) lineSelect.value = line;
        }
        multiDownloadState.allPrps = data.table_prp_options || data.prp_options || [];
        multiDownloadState.selectedPrps = new Set(Array.from(multiDownloadState.selectedPrps).filter((v) => multiDownloadState.allPrps.includes(v)));
        renderMultiDownloadPrpOptions();
    }

    async function openMultiDownloadModal() {
        qs("multiDownloadSnapDate").value = getCurrentPrpSnapDate();
        qs("multiDownloadLine").value = qs("tblFilterLine")?.value || "";
        qs("multiDownloadPrpSearch").value = "";
        multiDownloadState.selectedPrps.clear();
        await loadMultiDownloadOptions();
        openModal(multiDownloadModal);
    }
    async function exportByButton(buttonId) {
        const line = qs("tblFilterLine")?.value || "";
        const prp = qs("tblFilterPrp")?.value || "";
        if (!line || !prp || !state.currentRows.length) {
            showFactsMessage("LINE과 PRP를 선택한 뒤 조회 후 다운로드하세요.");
            return;
        }
        const btn = qs(buttonId);
        const url = btn?.getAttribute("data-export-url");
        if (!url) return;
        const ok = await showDownloadFeedback(buttonId);
        if (!ok) return;
        window.location.href = url;
    }

    qs("prpExcelDownloadBtn")?.addEventListener("click", () => exportByButton("prpExcelDownloadBtn"));
    qs("prpExcelDownloadAllBtn")?.addEventListener("click", () => exportByButton("prpExcelDownloadAllBtn"));
    qs("prpExcelDownloadSelectedBtn")?.addEventListener("click", openMultiDownloadModal);

    let prpLastCheckedIndex = null;

     function bindPrpShiftRangeCheck() {
        const checks = Array.from(document.querySelectorAll(".prp-row-check"));

        checks.forEach((chk) => {
            chk.onclick = function (e) {
                const currentIndex = checks.indexOf(this);

                if (e.shiftKey && prpLastCheckedIndex !== null) {
                    const start = Math.min(prpLastCheckedIndex, currentIndex);
                    const end = Math.max(prpLastCheckedIndex, currentIndex);
                    const checkedValue = this.checked;

                    for (let i = start; i <= end; i++) {
                        checks[i].checked = checkedValue;
                    }
                }

                prpLastCheckedIndex = currentIndex;
            };
        });

        qs("prpCheckAll")?.addEventListener("change", function () {
            checks.forEach((chk) => {
                chk.checked = this.checked;
            });
        });
    }

    const overrideModal = qs("overrideModal");
    const overrideModalTitle = qs("overrideModalTitle");
    const overrideFieldType = qs("overrideFieldType");
    const overrideMemberList = qs("overrideMemberList");
    const overrideSaveBtn = qs("overrideSaveBtn");
    const overrideCancelBtn = qs("overrideCancelBtn");

    function openOverrideModal(fieldType, lineid, processid, stepseq) {
        state.currentOverrideFieldType = fieldType;
        state.currentOverrideTargetInfo = { lineid, processid, stepseq };
        overrideFieldType.value = fieldType;
        overrideModalTitle.textContent = fieldType === "always_emergency" ? "상시/비상시 선택" : "주요/비주요 선택";

        const panel = overrideModal?.querySelector(".modal-panel");
        if (panel) {
            panel.style.width = "520px";
            panel.style.maxWidth = "92vw";
        }

        openModal(overrideModal);
    }

    overrideCancelBtn?.addEventListener("click", () => closeModal(overrideModal));

    overrideSaveBtn?.addEventListener("click", async () => {
        if (!(await ensureCurrentPrpDateEditable())) return;
        const selected = Array.from(document.querySelectorAll(".override-member-flag")).map((el) => ({
            member_key: el.dataset.memberKey || "",
            eqp_body_name: el.dataset.eqpBodyName || "",
            eqp_cham_name: el.dataset.eqpChamName || "",
            source_types: JSON.parse(el.dataset.sourceTypes || "[]"),
            path_refs: JSON.parse(el.dataset.pathRefs || "[]"),
            selected_flag: el.value || "N",
        }));

        try {
            showLoading();
            await apiJson(dashboardApiUrls.dashboardOverrideMemberSaveApi, "POST", {
                snap_date: getCurrentPrpSnapDate(),
                lineid: state.currentOverrideTargetInfo.lineid,
                processid: state.currentOverrideTargetInfo.processid,
                stepseq: state.currentOverrideTargetInfo.stepseq,
                field_type: state.currentOverrideFieldType,
                member_items: selected,
            });
            closeModal(overrideModal);
            await refreshPrpTableOnly();
        } catch (e) {
            console.error(e);
            hideLoading();
            await showFactsMessage(e.message || "저장 중 오류가 발생했습니다.");
        } finally {
            hideLoading();
        }

    });


     function renderOverrideMembersFromRow(row, fieldType) {
        if (!overrideMemberList) return;

        const items = Array.isArray(row?.override_target_list) ? row.override_target_list : [];
        if (!items.length) {
            overrideMemberList.innerHTML = `<div class="empty-cell">조회 결과가 없습니다.</div>`;
            return;
        }

        const labelY = fieldType === "always_emergency" ? "상시" : "주요";
        const labelN = fieldType === "always_emergency" ? "비상시" : "비주요";

        overrideMemberList.innerHTML = items.map((item) => {
            const sourceTypes = item.source_types || [];
            const isSourcePath = sourceTypes.includes("SOURCE_PATH");
            const isTipMissingOnly = sourceTypes.includes("TIP_MISSING") && !isSourcePath;

            const sourceDisplayParts = [];
            if (isSourcePath) sourceDisplayParts.push("TIP등록 Path");
            if (sourceTypes.includes("TIP_MISSING")) sourceDisplayParts.push("TIP미등록 호환Path");

            const current = isSourcePath
                ? "Y"
                : (
                    fieldType === "always_emergency"
                        ? (item.has_always ? "Y" : "N")
                        : (item.has_major ? "Y" : "N")
                );

            const disabledReason = "TIP등록된 설비는 상시, 주요 설정으로 변경이 불가합니다.";

            return `
                <div class="override-member-row" style="display:flex; align-items:center; justify-content:space-between; gap:8px; padding:8px 0;">
                    <div class="override-member-left" style="flex:1 1 auto; min-width:0;">
                        <div class="override-member-name" style="font-weight:700;">${escapeHtml(item.display_name || "")}</div>
                        <div class="override-member-source" style="font-size:11px; color:#6b7a90; max-width:120px; white-space:nowrap; overflow:hidden; text-overflow:ellipsis;" title="${escapeHtml(sourceDisplayParts.join(" / "))}">${escapeHtml(sourceDisplayParts.join(" / "))}</div>
                    </div>
                    <div class="override-member-right" style="flex:0 0 96px;">
                        ${
                            isTipMissingOnly
                                ? `
                                    <select
                                        class="override-member-flag"
                                        style="width:96px;"
                                        data-member-key="${escapeHtml(item.member_key || "")}"
                                        data-eqp-body-name="${escapeHtml(item.eqp_body_name || "")}"
                                        data-eqp-cham-name="${escapeHtml(item.eqp_cham_name || "")}"
                                        data-source-types='${escapeHtml(JSON.stringify(item.source_types || []))}'
                                        data-path-refs='${escapeHtml(JSON.stringify(item.path_refs || []))}'
                                    >
                                        <option value="Y" ${current === "Y" ? "selected" : ""}>${labelY}</option>
                                        <option value="N" ${current !== "Y" ? "selected" : ""}>${labelN}</option>
                                    </select>
                                `
                                : `
                                    <span
                                        class="disabled-action-tooltip-trigger"
                                        data-tooltip="${escapeHtml(disabledReason)}"
                                        tabindex="0"
                                        style="display:inline-block;"
                                    >
                                        <select
                                            class="override-member-flag"
                                            style="width:96px; pointer-events:none;"
                                            disabled
                                            data-member-key="${escapeHtml(item.member_key || "")}"
                                            data-eqp-body-name="${escapeHtml(item.eqp_body_name || "")}"
                                            data-eqp-cham-name="${escapeHtml(item.eqp_cham_name || "")}"
                                            data-source-types='${escapeHtml(JSON.stringify(item.source_types || []))}'
                                            data-path-refs='${escapeHtml(JSON.stringify(item.path_refs || []))}'
                                        >
                                            <option value="Y" selected>${labelY}</option>
                                            <option value="N">${labelN}</option>
                                        </select>
                                    </span>
                                `
                        }
                    </div>
                </div>
            `;
        }).join("");

        if (window.bindFactsTooltipTargets) {
            window.bindFactsTooltipTargets(".disabled-action-tooltip-trigger");
        }

    }

    async function loadOverrideMembers(lineid, processid, stepseq, fieldType) {
        const url =
            `${dashboardApiUrls.dashboardOverrideDetailApi}` +
            `?snap_date=${encodeURIComponent(getCurrentPrpSnapDate())}` +
            `&lineid=${encodeURIComponent(lineid || "")}` +
            `&processid=${encodeURIComponent(processid)}` +
            `&stepseq=${encodeURIComponent(stepseq)}`;

        const data = await apiJson(url, "GET");

        if (!overrideMemberList) return;

        if (!data.rows || !data.rows.length) {
            overrideMemberList.innerHTML = `<div class="empty-cell">조회 결과가 없습니다.</div>`;
            return;
        }

        const labelY = fieldType === "always_emergency" ? "상시" : "주요";
        const labelN = fieldType === "always_emergency" ? "비상시" : "비주요";

        overrideMemberList.innerHTML = data.rows.map((row) => {
            const current = fieldType === "always_emergency"
                ? (row.current_flag || "N")
                : (row.current_major_flag || "N");

            return `
                <div class="override-member-row">
                    <div class="override-member-left">
                        <div class="override-member-name">${escapeHtml(row.member_display || "")}</div>
                        <div class="override-member-source">${escapeHtml(row.source_display || "")}</div>
                    </div>
                    <div class="override-member-right">
                        <select
                            class="override-member-flag"
                            data-member-key="${escapeHtml(row.member_key || "")}"
                            data-eqp-body-name="${escapeHtml(row.eqp_body_name || "")}"
                            data-eqp-cham-name="${escapeHtml(row.eqp_cham_name || "")}"
                            data-source-types='${escapeHtml(JSON.stringify(row.source_types || []))}'
                            data-path-refs='${escapeHtml(JSON.stringify(row.path_refs || []))}'
                        >
                            <option value="Y" ${current === "Y" ? "selected" : ""}>${labelY}</option>
                            <option value="N" ${current !== "Y" ? "selected" : ""}>${labelN}</option>
                        </select>
                    </div>
                </div>
            `;
        }).join("");
    }

    const planListModal = qs("planListModal");
    const planEditModal = qs("planEditModal");
    const planListTbody = qs("planListTbody");
    const planListCloseBtn = qs("planListCloseBtn");
    const planAddNewBtn = qs("planAddNewBtn");
    const planCancelBtn = qs("planCancelBtn");
    const planSaveBtn = qs("planSaveBtn");
    const planEditId = qs("planEditId");
    const planAlwaysEmergency = qs("planAlwaysEmergency");
    const planMajorMinor = qs("planMajorMinor");
    const planEqpBodyName = qs("planEqpBodyName");
    const planEqpChamName = qs("planEqpChamName");
    const planDueDate = qs("planDueDate");
    const planEvalLotId = qs("planEvalLotId");
    const planEvalStage = qs("planEvalStage");
    const planMemo = qs("planMemo");

    bindUppercaseInput(planEqpBodyName);
    bindUppercaseInput(planEqpChamName);
    bindUppercaseInput(planEvalLotId);
    stopEnterSubmitWithinModal(planListModal);
    stopEnterSubmitWithinModal(planEditModal);

    function clearPlanEditForm() {
        state.currentPlanEditRow = null;
        planEditId.value = "";
        planAlwaysEmergency.value = "";
        planMajorMinor.value = "";
        planEqpBodyName.value = "";
        planEqpChamName.value = "";
        planDueDate.value = "";
        planEvalLotId.value = "";
        planEvalStage.value = "";
        planMemo.value = "";
    }

    function fillPlanEditForm(row) {
        if (!row) return;
        state.currentPlanEditRow = row;
        planEditId.value = row.id || "";
        planAlwaysEmergency.value = row.always_emergency || "";
        planMajorMinor.value = row.major_minor || "";
        planEqpBodyName.value = row.eqp_body_name || "";
        planEqpChamName.value = row.eqp_cham_name || "";
        planDueDate.value = row.compatibility_due_date || "";
        planEvalLotId.value = row.eval_lot_id || "";
        planEvalStage.value = row.required_eval_stage_id || "";
        planMemo.value = row.memo || "";
    }

    async function loadPlanList(lineid, processid, stepseq) {
        planListTbody.innerHTML = `<tr><td colspan="10" class="empty-cell">불러오는 중...</td></tr>`;

        const url =
            `${dashboardApiUrls.dashboardPlanDetailApi}` +
            `?snap_date=${encodeURIComponent(getCurrentPrpSnapDate())}` +
            `&lineid=${encodeURIComponent(lineid || "")}` +
            `&processid=${encodeURIComponent(processid)}` +
            `&stepseq=${encodeURIComponent(stepseq)}`;

        const data = await apiJson(url, "GET");

        if (!data.rows.length) {
            planListTbody.innerHTML = `<tr><td colspan="10" class="empty-cell">입력된 호환계획이 없습니다.</td></tr>`;
            return;
        }

        planListTbody.innerHTML = data.rows.map((row) => `
            <tr>
                <td>${escapeHtml(row.always_emergency || "")}</td>
                <td>${escapeHtml(row.major_minor || "")}</td>
                <td>${escapeHtml(row.eqp_body_name || "")}</td>
                <td>${escapeHtml(row.eqp_cham_name || "")}</td>
                <td>${escapeHtml(row.compatibility_due_date || "")}</td>
                <td>${escapeHtml(row.eval_lot_id || "")}</td>
                <td>${escapeHtml(row.required_eval_stage_name || "")}</td>
                <td>${escapeHtml(row.memo || "")}</td>
                <td><button type="button" class="btn-secondary btn-sm plan-edit-btn" data-id="${escapeHtml(row.id)}" data-plan-id="${escapeHtml(row.plan_id || row.id || "")}" data-history-id="${escapeHtml(row.history_id || "")}" data-body="${escapeHtml(row.eqp_body_name || "")}" data-cham="${escapeHtml(row.eqp_cham_name || "")}">수정</button></td>
                <td><button type="button" class="btn-secondary btn-sm plan-delete-btn" data-id="${escapeHtml(row.id)}" data-plan-id="${escapeHtml(row.plan_id || row.id || "")}" data-history-id="${escapeHtml(row.history_id || "")}" data-body="${escapeHtml(row.eqp_body_name || "")}" data-cham="${escapeHtml(row.eqp_cham_name || "")}">삭제</button></td>
            </tr>
        `).join("");

        const rowMap = new Map(data.rows.map((r) => [String(r.plan_id || r.id), r]));

        planListTbody.querySelectorAll(".plan-edit-btn").forEach((btn) => {
            btn.addEventListener("click", async () => {
                if (!(await ensureCurrentPrpDateEditable())) return;
                const row = rowMap.get(String(btn.dataset.tipMissingId || btn.dataset.id));
                clearPlanEditForm();
                fillPlanEditForm(row);
                openModal(planEditModal);
            });
        });

        planListTbody.querySelectorAll(".plan-delete-btn").forEach((btn) => {
            btn.addEventListener("click", async () => {
                if (!(await ensureCurrentPrpDateEditable())) return;
                const ok = await showFactsConfirm("해당 호환계획을 삭제하시겠습니까?");
                if (!ok) return;

                try {
                    showLoading();
                    await apiJson(dashboardApiUrls.dashboardPlanDeleteApi, "POST", {
                        snap_date: getCurrentPrpSnapDate(),
                        lineid: state.currentPlanTargetInfo.lineid,
                        processid: state.currentPlanTargetInfo.processid,
                        stepseq: state.currentPlanTargetInfo.stepseq,
                        plan_id: btn.dataset.planId || btn.dataset.id,
                        original_eqp_body_name: btn.dataset.body || "",
                        original_eqp_cham_name: btn.dataset.cham || "",
                    });
                    await loadPlanList(
                        state.currentPlanTargetInfo.lineid,
                        state.currentPlanTargetInfo.processid,
                        state.currentPlanTargetInfo.stepseq
                    );
                    await refreshPrpTableOnly();
                } catch (e) {
                    console.error(e);
                    hideLoading();
                    await showFactsMessage(e.message || "삭제 중 오류가 발생했습니다.");
                } finally {
                    hideLoading();
                }
            });
        });
    }

    planListCloseBtn?.addEventListener("click", () => closeModal(planListModal));

    planAddNewBtn?.addEventListener("click", async () => {
        if (!(await ensureCurrentPrpDateEditable())) return;
        clearPlanEditForm();
        openModal(planEditModal);
    });

    planCancelBtn?.addEventListener("click", () => closeModal(planEditModal));

    planSaveBtn?.addEventListener("click", async () => {
        if (!(await ensureCurrentPrpDateEditable())) return;
        normalizeUpperInput(planEqpBodyName);
        normalizeUpperInput(planEqpChamName);
        normalizeUpperInput(planEvalLotId);

        if (!String(planEqpBodyName.value || "").trim()) {
            await showFactsMessage("호환EQPBODY명은 필수기재입니다.");
            return;
        }

        try {
            showLoading();
            await apiJson(dashboardApiUrls.dashboardPlanSaveApi, "POST", {
                snap_date: getCurrentPrpSnapDate(),
                lineid: state.currentPlanTargetInfo.lineid,
                plan_id: planEditId.value || "",
                items: state.currentPlanTargetItems,
                always_emergency: planAlwaysEmergency.value,
                major_minor: planMajorMinor.value,
                eqp_body_name: planEqpBodyName.value,
                eqp_cham_name: planEqpChamName.value,
                compatibility_due_date: planDueDate.value,
                eval_lot_id: planEvalLotId.value,
                required_eval_stage_id: planEvalStage.value,
                memo: planMemo.value,
                original_eqp_body_name: state.currentPlanEditRow?.eqp_body_name || "",
                original_eqp_cham_name: state.currentPlanEditRow?.eqp_cham_name || "",
            });
            closeModal(planEditModal);
            await loadPlanList(
                state.currentPlanTargetInfo.lineid,
                state.currentPlanTargetInfo.processid,
                state.currentPlanTargetInfo.stepseq
            );
            await refreshPrpTableOnly();
        } catch (e) {
            console.error(e);
            hideLoading();
            await showFactsMessage(e.message || "저장 중 오류가 발생했습니다.");
        } finally {
            hideLoading();
        }

    });

    const openSimilarEqpBtn = qs("openSimilarEqpBtn");
    const similarEqpModal = qs("similarEqpModal");
    const similarEqpCloseBtn = qs("similarEqpCloseBtn");
    const similarEqpTbody = qs("similarEqpTbody");
    const similarEqpNotice = qs("similarEqpNotice");
    const similarEqpBaseInfo = qs("similarEqpBaseInfo");

    stopEnterSubmitWithinModal(similarEqpModal);

    async function loadSimilarEqpList(lineid, processid, stepseq) {
        similarEqpTbody.innerHTML = `<tr><td colspan="6" class="empty-cell">불러오는 중...</td></tr>`;
        similarEqpBaseInfo.textContent = "";

        const url =
            `${dashboardApiUrls.dashboardSimilarEqpApi}` +
            `?snap_date=${encodeURIComponent(getCurrentPrpSnapDate())}` +
            `&lineid=${encodeURIComponent(lineid || "")}` +
            `&processid=${encodeURIComponent(processid)}` +
            `&stepseq=${encodeURIComponent(stepseq)}`;

        const data = await apiJson(url, "GET");

        similarEqpNotice.textContent = data.notice || "해당 추천은 GPM 등록된 EQP_MODEL을 기준으로 합니다.";

        const baseEqps = Array.isArray(data.base_eqps) ? data.base_eqps.join(", ") : "";
        const baseModels = Array.isArray(data.base_models) ? data.base_models.join(" / ") : "";
        similarEqpBaseInfo.textContent = `기준 EQP: ${baseEqps || "-"} | 기준 MODEL: ${baseModels || "-"}`;

        if (!data.rows || !data.rows.length) {
            similarEqpTbody.innerHTML = `<tr><td colspan="6" class="empty-cell">추천 가능한 EQP가 없습니다.</td></tr>`;
            return;
        }

        similarEqpTbody.innerHTML = data.rows.map((row) => `
            <tr>
                <td>${escapeHtml(row.eqp_id || "")}</td>
                <td>${escapeHtml(row.origin_line_id || "")}</td>
                <td>${escapeHtml(row.eqp_model || "")}</td>
                <td>${escapeHtml(row.match_type || "")}</td>
                <td>${row.match_score != null ? escapeHtml(row.match_score) : ""}</td>
                <td>${escapeHtml(row.matched_base_model || "")}</td>
            </tr>
        `).join("");
    }

    openSimilarEqpBtn?.addEventListener("click", async () => {
        if (!state.currentPlanTargetInfo) {
            await showFactsMessage("먼저 호환계획 대상 step을 선택하십시오.");
            return;
        }

        try {

            showLoading();

            await loadSimilarEqpList(

                state.currentPlanTargetInfo.lineid,

                state.currentPlanTargetInfo.processid,

                state.currentPlanTargetInfo.stepseq

            );

            openModal(similarEqpModal);

        } catch (e) {

            console.error(e);

            hideLoading();

            await showFactsMessage(e.message || "조회 중 오류가 발생했습니다.");

        } finally {

            hideLoading();

        }

    });


    similarEqpCloseBtn?.addEventListener("click", () => closeModal(similarEqpModal));


    const tipMissingListModal = qs("tipMissingListModal");

    const tipMissingEditModal = qs("tipMissingEditModal");

    const tipMissingListTbody = qs("tipMissingListTbody");

    const tipMissingListCloseBtn = qs("tipMissingListCloseBtn");

    const tipMissingAddNewBtn = qs("tipMissingAddNewBtn");

    const tipMissingCancelBtn = qs("tipMissingCancelBtn");

    const tipMissingSaveBtn = qs("tipMissingSaveBtn");

    const tipMissingEditId = qs("tipMissingEditId");

    const tipMissingAlwaysEmergency = qs("tipMissingAlwaysEmergency");

    const tipMissingMajorMinor = qs("tipMissingMajorMinor");

    const tipMissingEqpBodyName = qs("tipMissingEqpBodyName");

    const tipMissingEqpChamName = qs("tipMissingEqpChamName");


    bindUppercaseInput(tipMissingEqpBodyName);

    bindUppercaseInput(tipMissingEqpChamName);

    stopEnterSubmitWithinModal(tipMissingListModal);

    stopEnterSubmitWithinModal(tipMissingEditModal);


    function clearTipMissingEditForm() {

        tipMissingEditId.value = "";

        tipMissingAlwaysEmergency.value = "";

        tipMissingMajorMinor.value = "";

        tipMissingEqpBodyName.value = "";

        tipMissingEqpChamName.value = "";

    }


    function fillTipMissingEditForm(row) {

        if (!row) return;

        tipMissingEditId.value = row.tip_missing_id || row.id || "";

        tipMissingAlwaysEmergency.value = row.always_emergency || "";

        tipMissingMajorMinor.value = row.major_minor || "";

        tipMissingEqpBodyName.value = row.eqp_body_name || "";

        tipMissingEqpChamName.value = row.eqp_cham_name || "";

    }


    async function loadTipMissingList(lineid, processid, stepseq) {

        tipMissingListTbody.innerHTML = `<tr><td colspan="6" class="empty-cell">불러오는 중...</td></tr>`;


        const url =

            `${dashboardApiUrls.dashboardTipMissingDetailApi}` +

            `?snap_date=${encodeURIComponent(getCurrentPrpSnapDate())}` +

            `&lineid=${encodeURIComponent(lineid || "")}` +

            `&processid=${encodeURIComponent(processid)}` +

            `&stepseq=${encodeURIComponent(stepseq)}`;


        const data = await apiJson(url, "GET");


        if (!data.rows.length) {

            tipMissingListTbody.innerHTML = `<tr><td colspan="6" class="empty-cell">입력된 미등록TIP호환Path가 없습니다.</td></tr>`;

            return;

        }


        tipMissingListTbody.innerHTML = data.rows.map((row) => `

            <tr>

                <td>${escapeHtml(row.always_emergency || "")}</td>

                <td>${escapeHtml(row.major_minor || "")}</td>

                <td>${escapeHtml(row.eqp_body_name || "")}</td>

                <td>${escapeHtml(row.eqp_cham_name || "")}</td>

                <td><button type="button" class="btn-secondary btn-sm tip-missing-edit-btn" data-id="${escapeHtml(row.id)}" data-tip-missing-id="${escapeHtml(row.tip_missing_id || row.id || "")}" data-history-id="${escapeHtml(row.history_id || "")}">수정</button></td>

                <td><button type="button" class="btn-secondary btn-sm tip-missing-delete-btn" data-id="${escapeHtml(row.id)}" data-tip-missing-id="${escapeHtml(row.tip_missing_id || row.id || "")}" data-history-id="${escapeHtml(row.history_id || "")}">삭제</button></td>

            </tr>

        `).join("");


        const rowMap = new Map(data.rows.map((r) => [String(r.tip_missing_id || r.id), r]));


        tipMissingListTbody.querySelectorAll(".tip-missing-edit-btn").forEach((btn) => {

            btn.addEventListener("click", async () => {

                if (!(await ensureCurrentPrpDateEditable())) return;

                const row = rowMap.get(String(btn.dataset.planId || btn.dataset.id));

                clearTipMissingEditForm();

                fillTipMissingEditForm(row);

                openModal(tipMissingEditModal);

            });

        });


        tipMissingListTbody.querySelectorAll(".tip-missing-delete-btn").forEach((btn) => {

            btn.addEventListener("click", async () => {

                if (!(await ensureCurrentPrpDateEditable())) return;

                const ok = await showFactsConfirm("해당 미등록TIP호환Path를 삭제하시겠습니까?");

                if (!ok) return;


                try {

                    showLoading();

                    await apiJson(dashboardApiUrls.dashboardTipMissingDeleteApi, "POST", {

                        snap_date: getCurrentPrpSnapDate(),
                        lineid: state.currentTipMissingTargetInfo.lineid,

                        tip_missing_id: btn.dataset.tipMissingId || btn.dataset.id,

                    });

                    await loadTipMissingList(

                        state.currentTipMissingTargetInfo.lineid,

                        state.currentTipMissingTargetInfo.processid,

                        state.currentTipMissingTargetInfo.stepseq

                    );

                    await refreshPrpTableOnly();

                } catch (e) {

                    console.error(e);

                    hideLoading();

                    await showFactsMessage(e.message || "삭제 중 오류가 발생했습니다.");

                } finally {

                    hideLoading();

                }

            });

        });

    }


    tipMissingListCloseBtn?.addEventListener("click", () => closeModal(tipMissingListModal));


    tipMissingAddNewBtn?.addEventListener("click", async () => {

        if (!(await ensureCurrentPrpDateEditable())) return;

        clearTipMissingEditForm();

        openModal(tipMissingEditModal);

    });


    tipMissingCancelBtn?.addEventListener("click", () => closeModal(tipMissingEditModal));


    tipMissingSaveBtn?.addEventListener("click", async () => {

        if (!(await ensureCurrentPrpDateEditable())) return;

        normalizeUpperInput(tipMissingEqpBodyName);

        normalizeUpperInput(tipMissingEqpChamName);


        if (!String(tipMissingAlwaysEmergency.value || "").trim()) {

            await showFactsMessage("상시/비상시는 필수기재입니다.");

            return;

        }

        if (!String(tipMissingMajorMinor.value || "").trim()) {

            await showFactsMessage("주요/비주요는 필수기재입니다.");

            return;

        }

        if (!String(tipMissingEqpBodyName.value || "").trim()) {

            await showFactsMessage("호환EQPBODY명은 필수기재입니다.");

            return;

        }


        try {

            showLoading();

            await apiJson(dashboardApiUrls.dashboardTipMissingSaveApi, "POST", {

                snap_date: getCurrentPrpSnapDate(),

                lineid: state.currentTipMissingTargetInfo.lineid,

                tip_missing_id: tipMissingEditId.value || "",

                items: state.currentTipMissingTargetItems,

                always_emergency: tipMissingAlwaysEmergency.value,

                major_minor: tipMissingMajorMinor.value,

                eqp_body_name: tipMissingEqpBodyName.value,

                eqp_cham_name: tipMissingEqpChamName.value,

            });

            closeModal(tipMissingEditModal);

            await loadTipMissingList(

                state.currentTipMissingTargetInfo.lineid,

                state.currentTipMissingTargetInfo.processid,

                state.currentTipMissingTargetInfo.stepseq

            );

            await refreshPrpTableOnly();

        } catch (e) {

            console.error(e);

            hideLoading();

            await showFactsMessage(e.message || "저장 중 오류가 발생했습니다.");

        } finally {

            hideLoading();

        }

    });


    const uploadModal = qs("uploadModal");

    qs("openUploadModalBtn")?.addEventListener("click", () => openModal(uploadModal));
    qs("uploadCancelBtn")?.addEventListener("click", () => closeModal(uploadModal));

    qs("uploadSaveBtn")?.addEventListener("click", async () => {
        const file = qs("bulkUploadFile").files[0];

        if (!file) {
            await showFactsMessage("파일을 선택하십시오.");
            return;
        }

        try {
            showLoading();

            const fd = new FormData();
            fd.append("file", file);
            fd.append("snap_date", dashboardMeta.snap_date);
            fd.append("lineid", getSelectedLineId() || "");

            const res = await fetch(dashboardApiUrls.dashboardBulkUploadApi, {
                method: "POST",
                headers: {
                    "X-CSRFToken": getCsrfToken(),
                    "X-Requested-With": "XMLHttpRequest",
                },
                body: fd,
            });

            const text = await res.text();

            let data = null;
            try {
                data = JSON.parse(text);
            } catch (e) {
                console.error("[dashboard.js] bulk upload non-json response:", {
                    status: res.status,
                    text: text,
                });
                throw new Error("서버 응답이 JSON 형식이 아닙니다. URL 또는 서버 응답을 확인하십시오.");
            }

            if (!res.ok || !data.ok) {
                throw new Error(data.message || "업로드 실패");
            }

            closeModal(uploadModal);
            qs("bulkUploadFile").value = "";

            hideLoading();

            const selectedPrp =
                (typeof getSelectedProcessId === "function" ? getSelectedProcessId() : "") ||
                (typeof getSelectedPrpProcessId === "function" ? getSelectedPrpProcessId() : "") ||
                "";

            if (selectedPrp) {
                await refreshPrpTableOnly();
                await showFactsMessage(data.message || "업로드 완료");
            } else {
                await showFactsMessage(
                    (data.message || "업로드 완료") + " 표는 자동 새로고침하지 않았습니다."
                );
            }
        } catch (e) {
            console.error(e);
            hideLoading();
            await showFactsMessage(e.message || "업로드 중 오류가 발생했습니다.");
        }

    });




    function bindDynamicButtons() {

        document.querySelectorAll(".open-always-modal-btn").forEach((btn) => {

            btn.addEventListener("click", async () => {

                const lineid = btn.dataset.lineid || "";

                const processid = btn.dataset.processid;

                const stepseq = btn.dataset.step;


                const row = state.currentRows.find(

                    (x) =>

                        (x.lineid || "") === lineid &&

                        x.processid === processid &&

                        x.stepseq === stepseq

                );

                if (!row) {

                    await showFactsMessage("조회 대상 row를 찾을 수 없습니다.");

                    return;

                }


                renderOverrideMembersFromRow(row, "always_emergency");

                openOverrideModal("always_emergency", lineid, processid, stepseq);

            });

        });


        document.querySelectorAll(".open-major-modal-btn").forEach((btn) => {

            btn.addEventListener("click", async () => {

                const lineid = btn.dataset.lineid || "";

                const processid = btn.dataset.processid;

                const stepseq = btn.dataset.step;


                const row = state.currentRows.find(

                    (x) =>

                        (x.lineid || "") === lineid &&

                        x.processid === processid &&

                        x.stepseq === stepseq

                );

                if (!row) {

                    await showFactsMessage("조회 대상 row를 찾을 수 없습니다.");

                    return;

                }


                renderOverrideMembersFromRow(row, "major_minor");

                openOverrideModal("major_minor", lineid, processid, stepseq);

            });

        });


        document.querySelectorAll(".open-plan-modal-btn").forEach((btn) => {

            btn.addEventListener("click", async () => {

                state.currentPlanTargetItems = [{

                    lineid: btn.dataset.lineid || "",

                    processid: btn.dataset.processid,

                    stepseq: btn.dataset.step,

                }];

                state.currentPlanTargetInfo = state.currentPlanTargetItems[0];

                clearPlanEditForm();


                try {
                    openModal(planListModal);
                    await loadPlanList(

                        state.currentPlanTargetInfo.lineid,

                        state.currentPlanTargetInfo.processid,

                        state.currentPlanTargetInfo.stepseq

                    );

                } catch (e) {

                    console.error(e);

                    hideLoading();

                    await showFactsMessage(e.message || "조회 중 오류가 발생했습니다.");

                } finally {

                    hideLoading();

                }

            });

        });


        document.querySelectorAll(".open-tip-missing-modal-btn").forEach((btn) => {

            btn.addEventListener("click", async () => {

                state.currentTipMissingTargetItems = [{

                    lineid: btn.dataset.lineid || "",

                    processid: btn.dataset.processid,

                    stepseq: btn.dataset.step,

                }];

                state.currentTipMissingTargetInfo = state.currentTipMissingTargetItems[0];

                clearTipMissingEditForm();


                try {
                    openModal(tipMissingListModal);
                    await loadTipMissingList(

                        state.currentTipMissingTargetInfo.lineid,

                        state.currentTipMissingTargetInfo.processid,

                        state.currentTipMissingTargetInfo.stepseq

                    );

                } catch (e) {

                    console.error(e);

                    hideLoading();

                    await showFactsMessage(e.message || "조회 중 오류가 발생했습니다.");

                } finally {

                    hideLoading();

                }

            });

        });

    }


 
    (function preventUnexpectedEnterSubmit() {

        document.addEventListener("keydown", function (e) {

            const target = e.target;

            if (!target) return;

            const inModal = target.closest(".modal");

            if (e.key === "Enter" && inModal && target.tagName !== "TEXTAREA") {

                e.preventDefault();

            }

        });

    })();

     function initCellKeyboardNavigation(tableSelector) {
        const table = document.querySelector(tableSelector);
        if (!table) return;
        const cells = Array.from(table.querySelectorAll(".cell-readonly, .row-check"));
        cells.forEach((cell) => {
            cell.addEventListener("keydown", function (e) {
                if (!e.ctrlKey) return;
                const current = e.currentTarget;
                const tr = current.closest("tr");
                if (!tr) return;
                const rowCells = Array.from(tr.querySelectorAll(".cell-readonly, .row-check"));
                const currentCol = rowCells.indexOf(current);
                const allRows = Array.from(table.querySelectorAll("tbody tr"));

                const currentRow = allRows.indexOf(tr);


                let target = null;


                if (e.key === "ArrowLeft") {

                    if (current.scrollWidth > current.clientWidth && current.classList.contains("cell-readonly")) {

                        current.scrollLeft = 0;

                    } else if (currentCol > 0) {

                        target = rowCells[currentCol - 1];

                    }

                } else if (e.key === "ArrowRight") {

                    if (current.scrollWidth > current.clientWidth && current.classList.contains("cell-readonly")) {

                        current.scrollLeft = current.scrollWidth;

                    } else if (currentCol < rowCells.length - 1) {

                        target = rowCells[currentCol + 1];

                    }

                } else if (e.key === "ArrowUp") {

                    for (let r = currentRow - 1; r >= 0; r--) {

                        const candidate = Array.from(allRows[r].querySelectorAll(".cell-readonly, .row-check"));

                        if (candidate[currentCol]) {

                            target = candidate[currentCol];

                            break;

                        }

                    }

                } else if (e.key === "ArrowDown") {

                    for (let r = currentRow + 1; r < allRows.length; r++) {

                        const candidate = Array.from(allRows[r].querySelectorAll(".cell-readonly, .row-check"));

                        if (candidate[currentCol]) {

                            target = candidate[currentCol];

                            break;

                        }

                    }

                }


                if (target) {

                    e.preventDefault();

                    target.focus();

                }

            });

        });

    }


    updateExportLinks();

    renderChart(combinedSeries);

    bindDynamicButtons();

    initCellKeyboardNavigation("#prpCellTable");
    if (window.FACTSDashboardFilters && window.FACTSDashboardFilters.initDashboardDropdowns) {
        window.FACTSDashboardFilters.initDashboardDropdowns(document);
    }
    bindLayerDropdown();
    syncLayerDropdownFromSelect();
    document.addEventListener("click", () => {
        document.querySelectorAll(".facts-text-suggest-panel.open").forEach((el) => el.classList.remove("open"));
    });

    const dashboardTopSections = qs("dashboardTopSections");
    const dashboardTopToggleBtn = qs("dashboardTopToggleBtn");
    const TOP_HIDDEN_KEY = "facts.dashboard.top.hidden";
    function applyTopSectionVisibility(hidden) {
        if (!dashboardTopSections || !dashboardTopToggleBtn) return;
        dashboardTopSections.style.display = hidden ? "none" : "";
        dashboardTopToggleBtn.textContent = hidden ? "대시보드 영역 보이기" : "대시보드 영역 숨기기";
        if (!hidden && state.chart && typeof state.chart.resize === "function") {
            setTimeout(() => {
                try { state.chart.resize(); state.chart.update(); } catch (e) { console.error(e); }
            }, 50);
        }

    }
    qs("multiDownloadCancelBtn")?.addEventListener("click", () => closeModal(multiDownloadModal));
    qs("multiDownloadPrpSearch")?.addEventListener("input", renderMultiDownloadPrpOptions);
    qs("multiDownloadLine")?.addEventListener("change", loadMultiDownloadOptions);
    qs("multiDownloadRunBtn")?.addEventListener("click", async () => {
        const line = qs("multiDownloadLine")?.value || "";
        const selected = Array.from(multiDownloadState.selectedPrps);
        if (!line) { await showFactsMessage("LINE을 선택하세요."); return; }
        if (!selected.length) { await showFactsMessage("다운로드할 PRP를 하나 이상 선택하세요."); return; }
        const params = new URLSearchParams();
        params.set("prp_snap_date", qs("multiDownloadSnapDate")?.value || "");
        params.set("prp_lineid", line);
        selected.forEach((v) => params.append("prp_processid", v));
        console.debug("[FACTS][multi-prp-download] selectedPrps", selected);
        console.debug("[FACTS][multi-prp-download] query", params.toString());
        const ok = await showDownloadFeedback("multiDownloadRunBtn");
        if (!ok) return;
        window.location.href = `${dashboardApiUrls.prpExportCsvAllApi}?${params.toString()}`;
        closeModal(multiDownloadModal);
    });

    if (dashboardTopToggleBtn) {
        const initialHidden = localStorage.getItem(TOP_HIDDEN_KEY) === "1";
        applyTopSectionVisibility(initialHidden);
        dashboardTopToggleBtn.addEventListener("click", () => {
            const nextHidden = !(localStorage.getItem(TOP_HIDDEN_KEY) === "1");
            localStorage.setItem(TOP_HIDDEN_KEY, nextHidden ? "1" : "0");
            applyTopSectionVisibility(nextHidden);
        });
    }


    [
        "tblFilterSnapDate",
        "tblFilterLine",
        "tblFilterPrp",
        "tblFilterArea",
        "tblFilterLayer",
        "tblFilterStep",
        "tblFilterType",
        "tblFilterBodyFlag",
        "tblFilterChamFlag",
        "tblFilterCompatType",
        "tblFilterAlways",
        "tblFilterMajor",
        "tblFilterPlan",
    ].forEach((id) => {
        qs(id)?.addEventListener("change", () => {
            schedulePrpOptionRefresh(id === "tblFilterLayer" ? 320 : 120);
        });
    });

    loadPrpOptionsOnly(false).catch((e) => console.error(e));


    // 최초 접속 시 자동조회 제거

    
[
    document.querySelector('input[name="snap_date"]'),
    document.querySelector('select[name="lineid"]'),
    document.querySelector('select[name="processid"]'),
    document.querySelector('select[name="areaname"]'),
    document.querySelector('select[name="layerid"]'),
].forEach((el) => {
    if (!el) return;
    el.addEventListener("change", async function () {
        try {
            await loadDashboardFilterOptionsOnly();
        } catch (e) {
            console.error(e);
        }

    });
});
})();
