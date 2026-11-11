# Customer troubleshooting

Use saved source records and an authorized staff account. Do not grant broad
roles, remove field restrictions or uninstall the app as a workaround. Never
send credentials, encryption keys or unredacted financial snapshot JSON to support.

| Symptom | Checks and supported next step |
| --- | --- |
| Check Profitability button missing | Confirm OPP is installed on the correct site, open a saved Quotation, reload Desk, and check browser console/network errors. A Bench administrator can rebuild app assets and clear the site's cache. |
| Access denied | Ask an administrator to check Quotation/BOM read access, Company User Permissions, financial field visibility and masking. Role combinations are described in the README; Sales Manager alone does not grant BOM read access. |
| BOM inaccessible or no applicable BOM | Verify a matching company/item, active submitted default BOM or a permitted explicit Link-to-BOM selection. Check access to nested BOMs too. Resolve conflicting selections through the normal Quotation workflow. |
| Cost, profit or margin Not available | Read the Critical messages. Check positive quantities, process loss, saved material rates, configured operation costs and parent/child cost consistency. Unsupported costing stays incomplete; unknown values are not zero. |
| Purchase evidence missing | Check purchase document and financial-field access, submitted non-return status, same company/base currency and exact material UOM. Missing, conflicting, future-dated or bounded-out evidence is withheld. Do not broaden permissions merely to display evidence. |
| Browser shows old dialog or buttons | Reload Desk and perform a hard refresh after an approved deployment. An administrator can run the asset/cache commands below. If it persists, capture sanitized console errors and confirm the site and deployed revision. |
| Old snapshots denied after role changes | Historical access requires current source Quotation and financial-field access. Revoked access intentionally blocks saved financial data; sharing snapshots is not a workaround. |
| Preview differs from Save Analysis or Compare | Each operation computes from current saved source records. Unsaved edits are excluded, and live purchase observations are omitted from newly saved snapshots. |
| Latest purchase differs from BOM rate | Expected: purchase evidence is an observation, not a rate update. Review saved BOM costs separately using approved ERPNext workflows. |
| Requests slow during mixed use | Worker capacity, shared host load and database work affect tails. History currently uses 215 queries per measured page; see the performance limitations. Do not assume a permission error is a timeout. |

Administrator asset refresh, only for the intended Bench/site:

```bash
cd /absolute/path/to/target/frappe-bench
bench build --app order_profitability_predictor
bench --site <site-name> clear-cache
```

Then reload Desk. Asset building is Bench-wide and must follow the site's normal
change procedure. Do not rotate encryption keys to address an authentication
error: have an administrator verify correct site routing and configuration first.

Before reporting a problem, record app/framework versions, sanitized reproduction
steps, request status and timestamps, expected versus actual behavior and whether
it reproduces after reload. Support contact: bhushanraut4343@gmail.com. No support
response-time commitment is published yet; paid-plan support terms remain pending.
See [lifecycle procedures](LIFECYCLE.md), [costing details](PROFITABILITY.md) and
[performance findings](PERFORMANCE.md).
