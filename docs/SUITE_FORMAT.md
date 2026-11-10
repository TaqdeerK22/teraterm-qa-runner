# Suite format (schema 1)

A suite is one UTF-8 JSON file. `qa-runner validate` checks everything below and lists all
problems at once.

## Top level

| Key | Required | Description |
|---|---|---|
| `schema` | no | Must be `1` if present |
| `id` | yes | Short identifier, `A-Z a-z 0-9 _ . -`, max 32 chars. Names the results workbook (`<id>_results.xlsx`) |
| `name` | yes | Human title shown in pop-ups, the macro and the workbook |
| `version` | no | Free text, shown in the Summary sheet (default `"1"`) |
| `description` | no | Free text, not used by the tool |
| `default_wait` | no | Seconds paused after each `send` unless a step overrides it (default `2`) |
| `setup` | no | Steps run once before the first test (log in, power on...) |
| `tests` | yes | Non-empty list of tests, performed in this order |
| `teardown` | no | Steps run once after the last test (log out, restore state) |

## Test

| Key | Required | Description |
|---|---|---|
| `id` | yes | Unique within the suite; same character rules as the suite id |
| `title` | yes | One line; shown in Excel and in the verification pop-up |
| `group` | no | Used for the per-group table in the Summary sheet and `generate --group` (default `General`) |
| `steps` | no | List of steps performed **before** the verification pop-up |
| `verify` | yes | What the tester must check. Shown last, then the result is requested |

## Steps

Each step is an object with exactly one of these keys:

| Key | Extra keys | Behaviour |
|---|---|---|
| `instruct` | - | Pop-up with instructions for a manual action |
| `send` | `wait_after` | `sendln` the command, then `pause` for `wait_after` (or `default_wait`) seconds. `0` = no pause |
| `send_secret` | `prompt`, `wait_after` | Masked password box (`prompt`, default "Password"); the text must contain `{secret}` exactly once, replaced by the typed value in memory only |
| `wait` | - | `pause` for the given number of seconds (0-3600) |

## Limits and rules

- Macro-bound strings (`name`, `title`, `verify`, step texts, `prompt`) must be printable ASCII and at most 250 characters.
- `{secret}` is the only placeholder. Literal `%` characters in a `send_secret` are handled for you.
- Apostrophes are allowed; the generator encodes them for TTL (`#39`).
- IDs are case-sensitive. Changing an ID later orphans old results for it: they are not carried into
  the regenerated workbook.

## Partial and repeat runs

```bat
qa-runner generate suite.json -o macros\storage.ttl --group Storage
qa-runner generate suite.json -o macros\resume.ttl  --from NET-003
qa-runner generate suite.json -o macros\some.ttl    --ids BOOT-001 NET-002
qa-runner generate suite.json -o macros\rerun.ttl   --results book.xlsx --only-status FAIL,NOT_RUN
```

Filters combine (they all must match) and the original suite order is kept.
