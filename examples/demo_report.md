# Acme Widget Controller - Demo Regression

Suite `widget-demo` v1.0

| Status | Count |
|---|---:|
| PASS | 5 |
| FAIL | 1 |
| BLOCKED | 1 |
| SKIP | 1 |
| NOT RUN | 4 |
| **Total** | **12** |

- Progress: **66.7%** (8/12 executed)
- Pass rate: **83.3%** (PASS / (PASS + FAIL))

## By group

| Group | PASS | FAIL | BLOCKED | SKIP | NOT RUN |
|---|---:|---:|---:|---:|---:|
| Startup | 3 | 0 | 0 | 0 | 0 |
| Connectivity | 1 | 1 | 1 | 0 | 1 |
| Indicators | 1 | 0 | 0 | 1 | 0 |
| Storage | 0 | 0 | 0 | 0 | 3 |

## Needs attention

| ID | Status | Test | Comment |
|---|---|---|---|
| NET-002 | FAIL | Static address can be applied | Link LED went off for ~8 s after net apply |
| NET-003 | BLOCKED | Ping from a workstation succeeds | No workstation available on the bench network |
