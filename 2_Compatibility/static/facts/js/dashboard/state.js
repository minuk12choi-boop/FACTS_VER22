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
