frappe.ui.form.on("Quotation", {
    refresh(frm) {
        if (frm.is_new() || ![0, 1].includes(frm.doc.docstatus)) return;

        frm.add_custom_button(__("Check Profitability"), () => {
            frappe.call({
                method: "order_profitability_predictor.api.check_quotation_profitability",
                args: { quotation_name: frm.doc.name },
                freeze: true,
                freeze_message: __("Checking profitability…"),
                callback(response) {
                    if (!response.message) return;
                    const result = response.message;
                    const escape = (value) => frappe.utils.escape_html(String(value));
                    const unavailable = __("Not available");
                    const amount = (value) =>
                        value == null ? unavailable : format_currency(value, result.currency);
                    const cost = (value) =>
                        result.is_complete ? amount(value) : unavailable;
                    const margin = result.is_complete && result.expected_gross_margin_percentage != null
                        ? `${format_number(result.expected_gross_margin_percentage, null, 2)}%`
                        : unavailable;
                    const rows = [
                        [__("Quotation"), result.quotation],
                        [__("Company currency"), result.currency],
                        [__("Net selling value"), amount(result.net_selling_value)],
                        [__("Estimated total cost"), cost(result.estimated_total_cost)],
                        [__("Expected gross profit"), cost(result.expected_gross_profit)],
                        [__("Expected gross margin"), margin],
                        [__("Minimum gross margin"), `${format_number(result.minimum_gross_margin_percentage ?? 15, null, 2)}%`],
                        [__("Cost completeness"), result.is_complete ? __("Complete estimate") : __("Incomplete — costing information missing")],
                    ];
                    const risks = result.risks || (result.warnings || []).map((message) =>
                        ({ severity: "Information", message }));
                    const warnings = [
                        ["Critical", "danger"], ["Warning", "warning"], ["Information", "info"],
                    ].map(([severity, style]) => {
                        const entries = risks.filter((risk) => risk.severity === severity);
                        if (!entries.length) return "";
                        return `<div class="alert alert-${style}"><strong>${escape(__(severity))}</strong>
                            <ul class="mb-0">${entries.map((risk) =>
                                `<li>${escape(__(risk.message))}</li>`).join("")}</ul></div>`;
                    }).join("");
                    const dialog = new frappe.ui.Dialog({
                        title: __("Quotation Profitability"),
                        fields: [{ fieldname: "result", fieldtype: "HTML" }],
                    });
                    const purchaseEvidence = (result.material_rate_evidence || []).map((row) => {
                        const evidence = row.purchase_evidence || {};
                        const observed = evidence.status === "observed";
                        const columns = [row.item_code, __(row.costing_basis),
                            row.saved_bom_rate == null ? unavailable : format_currency(row.saved_bom_rate, row.currency),
                            row.uom,
                            observed ? format_currency(evidence.rate, evidence.currency) : unavailable,
                            observed ? frappe.datetime.str_to_user(evidence.date) : unavailable,
                            observed ? `${evidence.doctype}: ${evidence.document}` : unavailable,
                            observed ? (evidence.stale ? __("Review: older than 90 days") : __("Within 90 days")) : __("Not established"),
                        ];
                        return `<tr>${columns.map((value) => `<td>${escape(value)}</td>`).join("")}</tr>`;
                    }).join("");
                    const purchaseSection = purchaseEvidence ? `
                        <h6>${escape(__("Inventory Valuation and Purchase Observations"))}</h6>
                        <p class="text-muted">${escape(__("Purchase prices are separate, live observations from accessible documents. They do not replace saved BOM costs or guarantee future prices, and are not stored in analysis snapshots. Exact UOM and company-currency matches only."))}</p>
                        <div class="table-responsive"><table class="table table-bordered"><thead><tr>
                        ${["Material", "BOM costing basis", "Saved BOM rate", "UOM", "Observed purchase price", "Evidence date", "Evidence document", "Freshness"].map((label) => `<th>${escape(__(label))}</th>`).join("")}
                        </tr></thead><tbody>${purchaseEvidence}</tbody></table></div>` : "";
                    if (frappe.model.can_read("Profitability Analysis")) {
                        dialog.set_secondary_action_label(__("View History"));
                        dialog.set_secondary_action(() => opp_view_profitability_history(result.quotation));
                    }
                    if (frappe.model.can_create("Profitability Analysis")) {
                        dialog.set_primary_action(__("Save Analysis"), () => {
                            const button = dialog.get_primary_btn();
                            button.prop("disabled", true);
                            frappe.call({
                                method: "order_profitability_predictor.api.save_quotation_analysis",
                                args: { quotation_name: result.quotation },
                                freeze: true,
                                freeze_message: __("Saving a fresh analysis…"),
                                callback(saved) {
                                    if (!saved.message) return;
                                    dialog.hide();
                                    frappe.set_route("Form", "Profitability Analysis", saved.message.name);
                                },
                                always() { button.prop("disabled", false); },
                            });
                        });
                    }
                    dialog.fields_dict.result.$wrapper.html(`
                        <p class="text-muted">${escape(__("Based on saved quotation values. Amounts exclude taxes. Unsaved edits are not included. Save Analysis calculates a fresh snapshot using current saved data."))}</p>
                        <table class="table table-bordered">
                            <tbody>${rows.map(([label, value]) =>
                                `<tr><th scope="row">${escape(label)}</th><td>${escape(value)}</td></tr>`
                            ).join("")}</tbody>
                        </table>
                        ${purchaseSection}
                        <h6>${escape(__("Risk warnings"))}</h6>
                        ${warnings || `<p>${escape(__("No additional warnings."))}</p>`}
                    `);
                    dialog.show();
                },
            });
        });
    },
});

function opp_view_profitability_history(quotation, start = 0) {
    frappe.call({
        method: "order_profitability_predictor.history.get_quotation_history",
        args: { quotation_name: quotation, start }, freeze: true,
        callback(response) {
            if (!response.message) return;
            const data = response.message;
            const escape = (value) => frappe.utils.escape_html(String(value));
            const unavailable = __("Not available");
            const number = (row, key, percent = false) => {
                const value = row[key];
                if (value == null || (key !== "net_selling_value" && !row.is_complete)) return unavailable;
                return percent ? `${format_number(value, null, 2)}%` : format_currency(value, row.currency);
            };
            const rows = data.analyses;
            const dialog = new frappe.ui.Dialog({
                title: __("Saved Profitability History"), size: "extra-large",
                fields: [
                    {fieldname: "history", fieldtype: "HTML"},
                    {fieldname: "analysis", fieldtype: "Select", label: __("Saved analysis to compare"),
                        options: rows.map((row) => row.name), default: rows[0]?.name,
                        hidden: !rows.length, reqd: !!rows.length},
                ],
            });
            if (rows.length) {
                dialog.set_primary_action(__("Compare with Current Estimate"), () => {
                    frappe.call({
                        method: "order_profitability_predictor.history.compare_quotation_analysis",
                        args: {quotation_name: quotation, analysis_name: dialog.get_value("analysis")},
                        freeze: true,
                        callback(r) { if (r.message) opp_show_profitability_comparison(r.message); },
                    });
                });
            }
            const headers = ["Analysis", "Analysis date", "Selling value", "Estimated cost", "Gross profit", "Margin", "Completeness", "User"];
            dialog.fields_dict.history.$wrapper.html(`
                <p>${escape(quotation)} — ${escape(__("Historical snapshots, newest first"))}</p>
                ${rows.length ? `<div class="table-responsive"><table class="table table-bordered">
                <thead><tr>${headers.map((h) => `<th>${escape(__(h))}</th>`).join("")}</tr></thead>
                <tbody>${rows.map((row) => `<tr>${[
                    row.name, frappe.datetime.str_to_user(row.analyzed_at), number(row, "net_selling_value"),
                    number(row, "estimated_total_cost"), number(row, "expected_gross_profit"),
                    number(row, "expected_gross_margin_percentage", true),
                    row.is_complete ? __("Complete") : __("Incomplete"), row.analyzed_by,
                ].map((value) => `<td>${escape(value)}</td>`).join("")}</tr>`).join("")}</tbody></table></div>`
                : `<p class="text-muted">${escape(__("No saved analyses for this quotation."))}</p>`}
                ${start > 0 ? `<button class="btn btn-default btn-sm" data-history-page="previous">${escape(__("Previous"))}</button>` : ""}
                ${data.has_more ? `<button class="btn btn-default btn-sm" data-history-page="next">${escape(__("Next"))}</button>` : ""}
            `);
            dialog.fields_dict.history.$wrapper.on("click", "[data-history-page]", function () {
                const offset = this.dataset.historyPage === "next" ? 20 : -20;
                dialog.hide();
                opp_view_profitability_history(quotation, Math.max(0, start + offset));
            });
            dialog.show();
        },
    });
}

function opp_show_profitability_comparison(data) {
    const escape = (value) => frappe.utils.escape_html(String(value));
    const unavailable = __("Not available");
    const old = data.historical, current = data.current;
    const money = (value, currency) => value == null ? unavailable : format_currency(value, currency);
    const value = (row, key, percent) => {
        if (key !== "net_selling_value" && !row.is_complete) return unavailable;
        return percent ? (row[key] == null ? unavailable : `${format_number(row[key], null, 2)}%`)
            : money(row[key], row.currency);
    };
    const metrics = [
        ["Net selling value", "net_selling_value", false],
        ["Estimated cost", "estimated_total_cost", false],
        ["Gross profit", "expected_gross_profit", false],
        ["Gross margin", "expected_gross_margin_percentage", true],
    ];
    const direction = {increased: __("Margin increased"), decreased: __("Margin decreased"),
        unchanged: __("Margin unchanged"), not_available: __("Margin change not available")};
    const dialog = new frappe.ui.Dialog({title: __("Historical vs Current Profitability"), size: "large",
        fields: [{fieldname: "comparison", fieldtype: "HTML"}]});
    dialog.fields_dict.comparison.$wrapper.html(`
        <p><strong>${escape(__("Historical snapshot"))}:</strong> ${escape(old.name)} — ${escape(frappe.datetime.str_to_user(old.analyzed_at))}</p>
        <p><strong>${escape(__("Fresh current estimate"))}:</strong> ${escape(current.quotation)} — ${escape(frappe.datetime.str_to_user(data.calculated_at))}</p>
        <table class="table table-bordered"><thead><tr>${["Metric", "Historical", "Current", "Change"].map((h) => `<th>${escape(__(h))}</th>`).join("")}</tr></thead>
        <tbody>${metrics.map(([label, key, percent]) => {
            const delta = data.changes[key];
            const favorable = key === "estimated_total_cost" ? delta < 0 : delta > 0;
            const style = delta == null || delta === 0 ? "text-muted" : favorable ? "text-success" : "text-danger";
            const change = key === "net_selling_value" ? "—" : delta == null ? unavailable
                : `${delta > 0 ? "+" : ""}${percent ? `${format_number(delta, null, 2)} ${__("percentage points")}` : money(delta, current.currency)}`;
            return `<tr><th>${escape(__(label))}</th><td>${escape(value(old, key, percent))}</td><td>${escape(value(current, key, percent))}</td><td class="${style}"><strong>${escape(change)}</strong></td></tr>`;
        }).join("")}
        <tr><th>${escape(__("Completeness"))}</th><td>${escape(old.is_complete ? __("Complete") : __("Incomplete"))}</td><td>${escape(current.is_complete ? __("Complete") : __("Incomplete"))}</td><td></td></tr>
        </tbody></table>
        <p><strong>${escape(direction[data.changes.margin_direction] || unavailable)}</strong></p>
        <p class="text-muted">${escape(data.comparison_note)}</p>
        <h6>${escape(__("Current estimate risk warnings"))}</h6>
        <ul>${(current.risks || []).map((risk) => `<li><strong>${escape(__(risk.severity))}:</strong> ${escape(risk.message)}</li>`).join("")}</ul>
    `);
    dialog.show();
}
