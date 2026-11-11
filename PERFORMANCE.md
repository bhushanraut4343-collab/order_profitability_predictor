# Performance validation and limitations

Phase 5 was conditionally signed off for release preparation. Testing used OPP
`3a24c06` (0.2.0-rc.1), Frappe/ERPNext 16.52.0, Python 3.14.8, private MariaDB
11.8.9 and Redis 7 on a shared eight-logical-CPU host with approximately 7.65 GiB RAM.
These are synthetic local HTTP results, not production-capacity guarantees.

## Verified scope

Sequential fixtures covered one item/one BOM/two materials, 20 items, 100 simple
BOM items, depth-three manufacturing and 500 saved analyses. History and Compare
were measured separately. Query and memory instrumentation ran separately from
latency tests. Stage 1 distinguished warm measurements from application/Redis-cold
measurements; MariaDB/OS-cold behavior was not established.

Bounded concurrency used independent virtual clients of one authorized account,
a one-second think time, financial-oracle checks and restricted-user denials.
It does not establish capacity across distinct authorized-user permission caches.
The mixed workload allocated 20% each to small, medium, large, History and Compare.

| Measurement | One sync worker, five clients | Two sync workers, five clients |
| --- | --- | --- |
| Mixed p50 | 226 ms | 119 ms |
| Mixed p95 | 700 ms | 516 ms |
| Achieved requests/sec, including denials and think time | 4.20 | 4.70 |
| Small-calculation p95 | 544 ms | 124 ms |

All original absolute response-time targets passed. The two-worker small-result
p95 of 124 ms was below the original 750 ms absolute target, but exceeded its
41 ms one-client control by **3.05×**. The mixed-workload **2× per-operation
concurrency gate therefore failed**. All other two-worker operations passed that
gate. These thresholds were not retrospectively changed. Ten-client tests were
not run after the earlier escalation gate failed; four workers were not tested.

## Targeted small-only repeat

The final investigation kept two workers, with three paired batches of 100
measured small requests per condition: 300 at one client and 300 at five clients.
Five-client p95 values were 41.4, 70.3 and 60.6 ms; ratios to paired controls were
1.10×, 1.35× and 1.10×. Every pair passed both the original 750 ms absolute gate
and the 2× relative gate. Pooled p95 was 52.2 ms at one client and 62.0 ms at five.

This small-only pass does not supersede the mixed-workload failure. Passive
socket observations support queueing as a tail contributor; they are not exact
server accept times. Worker scheduling wait was small. Separate SQL profiling
measured 31 queries and approximately 11–15 ms SQL wall time per small request;
concurrent per-request SQL waits were not isolated. Passive monitoring introduces
overhead, and p99 estimates from individual 100-request batches are imprecise.

## Known efficiency work and claim limits

History used **215 SQL queries per measured 20-analysis page**, including 189
repeated source Quotation/child-table loads. EXPLAIN also showed a snapshot scan
and filesort in the 500-analysis fixture. Future optimization should consider
request-local source reuse while retaining all financial and source permissions;
no query/index optimization was performed in this campaign.

Correctness, restricted-user security and data-preservation checks passed. All
999 protected record hashes and 500 snapshots remained unchanged in the final
performance environment. HTTP/API checks are not manual browser-rendering tests.

No maximum throughput, supported production user count, 1,000-analysis history,
deeper-BOM, four-worker, ten-client or arbitrary-host performance claim is made.
Achieved requests/sec includes think time and is not saturation capacity. Size a
deployment using its own records and permissions; retain the mixed-workload
limitation when assessing response-time commitments.
