<!--
SPDX-FileCopyrightText: 2026 Netbeheer Nederland

SPDX-License-Identifier: Apache-2.0
-->

# dr_leds: playbooks (proposals)

Demo playbooks that show what the sample plugin does: each one drives the FSPs and the SO through the events dr_leds
reacts to, so its LEDs light up next to the FSPs and the SO on the HMI's Overview and Traffic. They are ordinary
playbooks, in the format of the demo's [`playbooks/`](../../../rti-demo/playbooks/README.md), for the demo stack with
its dr_leds overlay (`docker-compose.leds.yaml`: one dr_leds per FSP and SO).

The runner checks the ACSI side of each step (ok or refused, reports received, linked). It can't see the LEDs: they are
watched, not tested. These are proposals and haven't been run against the stack yet.

| Playbook | Shows | dr_leds event |
|---|---|---|
| [`01-green-follows-the-link.yaml`](01-green-follows-the-link.yaml) | Green on while associated; dark while FSP02 drops off, green when it's back | `Associated`, `ServerStopped` |
| [`02-green-blinks-on-operate-and-write.yaml`](02-green-blinks-on-operate-and-write.yaml) | Green blinks at FSP02 and the SO on each good Operate and write | `OperateResponse`, `ValueWritten` |
| [`03-green-blinks-on-reports.yaml`](03-green-blinks-on-reports.yaml) | The SO's green ticks once a second with FSP02's integrity reports, one burst for FSP01 | `ReportReceived` (SO only) |
| [`04-red-on-failure.yaml`](04-red-on-failure.yaml) | Red on after a refused Operate (FSP02 and SO) or a failed read (SO only); off after a good Operate | `OperateResponse`, `ValueRead` |
| [`05-interlock-while-red.yaml`](05-interlock-while-red.yaml) | A claimed control is refused (`blockedByInterlocking`) while red is on | `/control` |

05 needs a claim the demo stack doesn't set: in the HMI, edit dr_leds on FSP02 (ACSI Server → Plugins → Edit) and set
its settings to `{"claims": ["GenericIO/GGIO1.SPCSO2.Oper.ctlVal"]}` (decision
[0042](../../../../docs/rti-demo/decisions/0042-plugin-claims-in-settings.md)); Details then lists the claim.

## Running

With the demo stack and its dr_leds up, and the SO and FSPs registered with the BFF:

```bash
cd examples/rti-demo
docker compose -f docker-compose.yml -f docker-compose.leds.yaml up -d
uv run python -m playbooks.run ../rti-plugins/dr_leds/playbooks/01-green-follows-the-link.yaml
```

From the HMI: Traffic → Playbook → Upload, then Run. The BFF's built-in playbooks are only those in
`examples/rti-demo/playbooks/`; these are uploaded, or copied there once accepted.

## Open questions

- Keep these here, with the plugin, or move the accepted ones to `examples/rti-demo/playbooks/`, so the BFF has them
  built in and the integration test can run them?
- 05: put the claim in FSP02's plugin configuration (`config/plugin-configuration/rti-fsp02.json`), so it runs on the
  stack as it comes up? The claim only bites while red is on, so the other demos are unaffected.
- A step type that reads a plugin's own routes (`GET /api/plugins/dr_leds/leds-api/leds` via the BFF), so a playbook
  could check the LEDs as well as watch them?
