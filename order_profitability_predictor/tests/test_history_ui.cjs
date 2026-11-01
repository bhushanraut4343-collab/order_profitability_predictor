const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const dialogs = [];
let historyResponse, comparisonResponse, request;
const context = {
    __: value => value,
    format_currency: (value,currency) => `${currency} ${value}`,
    format_number: value => Number(value).toFixed(2),
    frappe: {
        ui: {form: {on() {}}, Dialog: class {
            constructor(options) {
                this.options = options;
                this.fields_dict = {};
                for (const field of options.fields) {
                    this.fields_dict[field.fieldname] = {$wrapper: {
                        html: value => { this.html = value; },
                        on: (event,selector,handler) => { this.pageHandler=handler; },
                    }};
                }
                dialogs.push(this);
            }
            set_primary_action(label,handler) {this.primary=handler;}
            get_value() { return historyResponse.analyses[0].name; }
            show() {}
            hide() {}
        }},
        utils: {escape_html: value => value.replaceAll('&','&amp;').replaceAll('<','&lt;').replaceAll('>','&gt;')},
        datetime: {str_to_user: value => value},
        call: options => {
            request=options;
            options.callback({message: options.method.endsWith('get_quotation_history') ? historyResponse : comparisonResponse});
        },
    },
};
vm.runInNewContext(fs.readFileSync(path.join(__dirname,'../public/js/quotation.js'),'utf8'),context);
const row = {name:'SNAP-NEW',quotation:'Q-1',analyzed_at:'2026-10-24 12:00:00',analyzed_by:'Manager',
    currency:'INR',is_complete:true,net_selling_value:1200,estimated_total_cost:720,
    expected_gross_profit:480,expected_gross_margin_percentage:40};
historyResponse = {analyses:[row,{...row,name:'SNAP-OLD'}],has_more:true};
context.opp_view_profitability_history('Q-1');
const history=dialogs.at(-1);
assert.ok(history.html.indexOf('SNAP-NEW') < history.html.indexOf('SNAP-OLD'));
assert.match(history.html,/Historical snapshots, newest first/);
assert.match(history.html,/data-history-page="next"/);
comparisonResponse = {historical:row,current:{...row,estimated_total_cost:700,expected_gross_profit:500,expected_gross_margin_percentage:42,
    risks:[{severity:'Information',message:'<script>Saved estimate</script>'}]},calculated_at:'2026-10-24 14:00:00',
    changes:{estimated_total_cost:-20,expected_gross_profit:20,expected_gross_margin_percentage:2,margin_direction:'increased'},comparison_note:'Current minus historical'};
history.primary();
assert.equal(request.args.quotation_name,'Q-1');
assert.equal(request.args.analysis_name,'SNAP-NEW');
let comparison=dialogs.at(-1);
assert.match(comparison.html,/Margin increased/);
assert.match(comparison.html,/Historical snapshot/);
assert.match(comparison.html,/Fresh current estimate/);
assert.match(comparison.html,/2.00 percentage points/);
assert.match(comparison.html,/text-success/);
assert.match(comparison.html,/&lt;script&gt;/);
assert.doesNotMatch(comparison.html,/<script>/);
comparisonResponse.current.is_complete=false;
comparisonResponse.current.estimated_total_cost=null;
comparisonResponse.changes={estimated_total_cost:null,expected_gross_profit:null,expected_gross_margin_percentage:null,margin_direction:'not_available'};
context.opp_show_profitability_comparison(comparisonResponse);
assert.match(dialogs.at(-1).html,/Margin change not available/);
assert.match(dialogs.at(-1).html,/Not available/);
history.pageHandler.call({dataset:{historyPage:'next'}});
assert.equal(request.args.start,20);
historyResponse={analyses:[],has_more:false};
context.opp_view_profitability_history('Q-1');
assert.match(dialogs.at(-1).html,/No saved analyses/);
assert.equal(dialogs.at(-1).primary,undefined);
process.stdout.write('History UI checks passed: ordering, selection, comparison highlights, missing values, escaping, pagination, empty history.' + '\n');
