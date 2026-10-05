# Demo playbooks

A playbook is a YAML (or JSON) file listing the steps of a demo with one SO
and its FSPs. `run.py` executes it through the BFF, the same way the HMI
does, so the HMI's **Traffic** page shows each step as it happens: the link
pulses, the timeline rows, the report values. Each step is checked as it
runs.

The same file runs as an integration test, so the demo you present is the
demo the tests run.

## From the HMI

Traffic → Playbook: pick a playbook and Run it, watch ✓ / ✗ come in per step,
Stop it, or Download / Upload / Delete one. Record turns clicks on the pinned
demo buttons into playbook steps, and Stop recording saves it. Built-in
playbooks are this folder; saved ones live under `BFF_PLAYBOOKS_DIR`
(`/config/playbooks` on the `bff-config` volume in `docker-compose.yml`). A
recording is an ordinary playbook file - download it, drop it in here, and it
runs the same from the CLI and as the test.

The CLI imports the runner from the BFF package (`bff.playbook`), so run
`uv sync --all-packages` (or `uv sync --package bff`) before using it.

## Running

With the stack up (`docker compose up -d`) and the SO and FSPs registered
with the BFF (HMI → Connections):

```bash
cd examples/rti-demo
uv run python -m playbooks.run playbooks/demo.yaml            # paced for an audience
uv run python -m playbooks.run playbooks/demo.yaml --pace 0   # as fast as it goes
uv run python -m playbooks.run playbooks/demo.yaml --steps 5-7
```

| Option | |
|---|---|
| `--pace 2s` | pause between steps (default: the playbook's `pace`) |
| `--keep-going` | run on after a failed step (default: stop there) |
| `--steps 3` / `--steps 2-5` | only these steps |
| `--bff URL` | the BFF (default: the playbook's `bff`, else `http://localhost:5000`) |

Each step prints a line, `[ 6/12] ✓ Reports come in at the SO · 5 report(s) from FSP02 (5.0s)`.
The exit code is 0 when every step passed, 1 when one failed, and 2 when the
playbook couldn't run at all (bad file, unknown FSP, BFF unreachable).

As a test:

```bash
uv run pytest tests/integration -m integration -k playbook -q
RTI_PLAYBOOK=playbooks/other.yaml uv run pytest tests/integration -m integration -k playbook -q
```

## File

```yaml
name: SO with two FSPs
bff: http://localhost:5000     # optional
pace: 2s                       # optional, pause between steps
so: SO                         # optional - needed only with several SOs
cps: {FSP01: cp1}              # optional - otherwise each FSP is asked
steps:
  - label: FSP01 dials the SO  # optional, shown instead of the step itself
    link: {fsp: FSP01}
    expect: ok                 # optional, see below
```

FSPs and the SO are named as registered with the BFF. A step's `fsp` can
also be a list of names. The step then runs on each FSP, like the HMI's
**All FSPs**, and passes when all of them pass. Wherever an FSP needs its
own value (the FSPs' models differ), give a map from FSP name to value:
`ref: {FSP01: LD0/LLN0.Mod.stVal, FSP02: GenericIO/LLN0.Beh.stVal}`.

Durations take `5`, `5s`, `500ms` or `2m`.

## Steps

| Step | Does | Fields |
|---|---|---|
| `link` | the FSP dials the SO on its cp, then waits until the SO has associated it | `fsp`, `timeout` (15s) |
| `unlink` | the FSP stops; waits until the SO no longer lists its cp | `fsp`, `timeout` |
| `drop` | `unlink`, wait, `link` again: the FSP drops off for a while | `fsp`, `for` (10s) |
| `read` | SO reads a data attribute from the FSP | `fsp`, `ref`, `fc` (st) |
| `write` | SO writes a data attribute | `fsp`, `ref`, `value`, `fc` (sp), `type` |
| `operate` | SO operates a controllable DO | `fsp`, `ref`, `cdc`, `value`, `ctlNum` (0), `origin` ({orCat: 2, orIdent: playbook}), `test` (false) |
| `select` | SO selects an SBO control (select-before-operate) | `fsp`, `ref` |
| `enable-report` | turns a report control block's reporting on, keeping its own configuration | `fsp`, `rcb`, `type` (BRCB / URCB) |
| `disable-report` | turns it off again | `fsp`, `rcb`, `type` |
| `wait` | pauses | the duration: `wait: 5s` |

`operate` takes values as the HMI's Operate dialog does: `on` / `off` for SPC
and DPC, a number for APC, INC, ENC, ING and ENG, `up` / `down` for BSC.
Quote `"on"` and `"off"` in YAML, since bare on/off parse as booleans.

## Expectations

By default a step passes when the FSP did what was asked: a read that
returned data, an operate the FSP carried out. `expect` changes that:

| `expect` | Passes when |
|---|---|
| `ok` (default) | the step succeeded |
| `fail` | the FSP refused it, e.g. an operate on an interlocked control |
| `{reports: {fsp: FSP02, min: 3}}` | the SO received at least `min` reports from that FSP during the step (put it on a `wait`) |
| `{linked: [FSP01, FSP02]}` / `{unlinked: FSP02}` | the SO has, or hasn't, associated those FSPs' cps |
