// Lightweight form/dialog behavior checks without a browser or extra dependencies.
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const path = require('node:path');
const source = fs.readFileSync(path.join(__dirname, '../public/js/quotation.js'), 'utf8');
let refresh, button, html, request;
let response;
let primaryAction;
let route;
let canCreate = true;
const context = {
    __: value => value,
    format_currency: (value, currency) => `${currency} ${value}`,
    format_number: value => Number(value).toFixed(2),
    frappe: {
        model: { can_create: () => canCreate, can_read: () => true },
        set_route: (...args) => { route = args; },
        datetime: { str_to_user: value => value },
        utils: { escape_html: value => value.replaceAll('&', '&amp;').replaceAll('<', '&lt;').replaceAll('>', '&gt;') },
        ui: {
            form: { on: (doctype, handlers) => { assert.equal(doctype, 'Quotation'); refresh = handlers.refresh; } },
            Dialog: class {
                constructor() { this.fields_dict = { result: { $wrapper: { html: value => { html = value; } } } }; }
                show() {}
                set_primary_action(label, handler) { assert.equal(label, 'Save Analysis'); primaryAction = handler; }
                get_primary_btn() { return { prop() {} }; }
                hide() {}
                set_secondary_action_label(label) { assert.equal(label, 'View History'); }
                set_secondary_action(handler) { assert.equal(typeof handler, 'function'); }
            },
        },
        call: options => { request = options; options.callback({ message: response }); },
    },
};
vm.runInNewContext(source, context);
const form = (status, isNew = false) => ({
    doc: { name: 'Q-TEST', docstatus: status }, is_new: () => isNew,
    add_custom_button: (label, handler) => { assert.equal(label, 'Check Profitability'); button = handler; },
    save: () => { throw new Error('Must not save'); },
});
for (const status of [0, 1]) {
    button = undefined; refresh(form(status)); assert.equal(typeof button, 'function');
}
for (const frm of [form(0, true), form(2)]) {
    button = undefined; refresh(frm); assert.equal(button, undefined);
}
refresh(form(0));
response = { quotation: 'Q-TEST', currency: 'INR', net_selling_value: 1200, estimated_total_cost: 720,
    expected_gross_profit: 480, expected_gross_margin_percentage: 40, is_complete: true, warnings: ['<script>risk</script>'] };
button();
assert.equal(request.method, 'order_profitability_predictor.api.check_quotation_profitability');
assert.equal(request.args.quotation_name, 'Q-TEST');
assert.match(html, /INR 720/); assert.match(html, /40.00%/);
assert.match(html, /&lt;script&gt;/); assert.doesNotMatch(html, /<script>/);
response = { ...response, is_complete: false, estimated_total_cost: 0, expected_gross_profit: 0,
    expected_gross_margin_percentage: 0, warnings: ['Missing BOM'] };
button();
assert.equal((html.match(/Not available/g) || []).length, 3);
assert.match(html, /Missing BOM/);
response.risks = [
    {severity: 'Critical', message: 'Missing material cost'},
    {severity: 'Warning', message: 'Potentially outdated rate'},
    {severity: 'Information', message: '<script>Assumption</script>'},
];
button();
assert.match(html, /alert-danger/);
assert.match(html, /alert-warning/);
assert.match(html, /alert-info/);
assert.match(html, /Missing material cost/);
assert.match(html, /Potentially outdated rate/);
assert.match(html, /&lt;script&gt;Assumption/);
assert.doesNotMatch(html, /<script>/);
response = { ...response, is_complete: true, estimated_total_cost: 720, expected_gross_profit: 480,
    expected_gross_margin_percentage: 40, material_rate_evidence: [{
        item_code: 'RAW-VALUATION-TEST', costing_basis: 'Inventory Valuation', saved_bom_rate: 4250,
        currency: 'INR', uom: 'Nos', purchase_evidence: {status: 'observed',rate: 6000,currency: 'INR',
            date: '2026-10-25',doctype: 'Purchase Invoice',document: '<script>private</script>',stale: false},
    }] };
button();
assert.match(html, /Inventory Valuation/);
assert.match(html, /INR 4250/);
assert.match(html, /INR 6000/);
assert.match(html, /2026-10-25/);
assert.match(html, /not stored in analysis snapshots/);
assert.match(html, /&lt;script&gt;private/);
assert.doesNotMatch(html, /<script>/);
response.material_rate_evidence[0].purchase_evidence = {status: 'unavailable'};
button();
assert.match(html, /Not established/);
assert.doesNotMatch(html, /INR 6000/);
assert.equal(typeof primaryAction, 'function');
response = {name: 'SNAPSHOT-TEST'};
primaryAction();
assert.equal(request.method, 'order_profitability_predictor.api.save_quotation_analysis');
assert.equal(Object.keys(request.args).length, 1);
assert.equal(request.args.quotation_name, 'Q-TEST');
assert.deepEqual(route, ['Form', 'Profitability Analysis', 'SNAPSHOT-TEST']);
response = {quotation: 'Q-TEST', currency: 'INR', is_complete: false, warnings: []};
canCreate = false;
primaryAction = undefined;
button();
assert.equal(primaryAction, undefined);
process.stdout.write('Quotation UI checks passed: saved draft/submitted, unsaved/cancelled hidden, complete/incomplete display, escaping, API call.' + '\n');
