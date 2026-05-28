
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
