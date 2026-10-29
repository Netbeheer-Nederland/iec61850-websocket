<!--
SPDX-FileCopyrightText: 2026 Netbeheer Nederland

SPDX-License-Identifier: Apache-2.0
-->

# rti-demo architecture decisions

Why the rti-demo is built the way it is. Each record describes one decision: its context, what was decided, the
consequences, and where to find it in the code. The format is in [0001](0001-record-architecture-decisions.md).

| # | Decision | Status |
|---|---|---|
| [0001](0001-record-architecture-decisions.md) | Record architecture decisions | accepted |
| [0002](0002-five-separate-services.md) | Five separate services: HMI, BFF, SO, FSP and IO | accepted |
| [0003](0003-so-passive-fsp-active.md) | The SO listens, the FSPs dial out | accepted |
| [0004](0004-bff-single-gateway-execute-proxy.md) | The BFF is the HMI's only backend, with a generic execute proxy | accepted |
| [0005](0005-push-channel-central-poll.md) | One central poll in the BFF, pushed to the browsers over /ws | accepted |
| [0006](0006-connections-json-source-of-truth.md) | connections.json is the source of truth, on a volume, seeded once | accepted |
| [0007](0007-bff-reapplies-security-config.md) | The SO and FSP keep TLS and OAuth in memory; the BFF re-applies them | accepted |
| [0008](0008-certificates-as-file-references.md) | Certificates as file: references to a mounted directory | accepted |
| [0009](0009-asyncio-runtime-in-own-thread.md) | The ACSI runtime runs on its own event loop thread | accepted |
| [0010](0010-models-as-python-modules.md) | IED models are Python modules, generated from SCL in the HMI | accepted |
| [0011](0011-io-separate-project-runtime-plugin.md) | IO is a separate project; its client is a plugin loaded at runtime | accepted |
| [0012](0012-log-kinds-tagged-at-source.md) | Log entries carry a kind, set where they are written | accepted |
| [0013](0013-playbooks-run-in-the-bff.md) | Demo playbooks run in the BFF | accepted |
| [0014](0014-hmi-bff-address-resolution.md) | Where the HMI finds the BFF | accepted |
| [0015](0015-fixed-default-ports.md) | Fixed default ports, pinned by a test | accepted |
| [0016](0016-container-build-and-image-names.md) | Container builds and image names | accepted |
| [0017](0017-hardware-is-optional.md) | Raspberry Pi hardware is optional | accepted |
| [0018](0018-io-module-names.md) | Names for the IO module: `io` for the role, `rti_io` for the code | accepted |
| [0019](0019-io-server-serves-only-plugin-files.md) | The IO server serves only the IO plugin's own files | accepted |
| [0020](0020-so-authorizes-tokens.md) | The SO checks what a token allows, not only that it's genuine | proposed |
| [0021](0021-acsi-plugin-host.md) | The FSP and SO host several plugins, behind one plugin contract | proposed |
| [0022](0022-io-plugin-own-package.md) | The IO plugin is its own package, installed with the FSP and SO | proposed |
| [0023](0023-io-server-package-rpi-io.md) | The IO server's code is `rpi_io`, flat, in `src/` | proposed |
| [0024](0024-ssd1306-oled-display-device.md) | The SSD1306 OLED is a display device of the IO server, on any Pi, shown by the IO plugin | proposed |
| [0025](0025-plugins-show-attached-devices-in-hmi.md) | Plugins describe what they attach as data, at `GET <url>/attached`; the HMI draws it next to the FSP or SO | proposed |
| [0026](0026-io-server-pins-are-configuration.md) | The IO server's pins are configuration, claimed per device and checked for conflicts | proposed |
| [0027](0027-plugin-contract-as-openapi.md) | The plugin contract is published as an OpenAPI 3.1 document, kept in step by a test | proposed |
| [0028](0028-rti-plugins-folder.md) | Plugins and the IO server move to `examples/rti-plugins`; the IO server is its own stack | proposed |
| [0029](0029-plugins-are-http-services.md) | Plugins are HTTP services the FSP and SO connect to, from a plugin configuration | proposed |
| [0030](0030-plugin-project-layout.md) | Every plugin is a project with one layout: `server` and `plugin` subpackages, `docker/`, a compose pair | proposed |
| [0031](0031-plugin-source-layout.md) | A plugin's source: `server/` is the service, `plugin/` the plugin API, and the plugin depends on the server | proposed |
| [0032](0032-io-plugin-folder-rpi-io.md) | The IO plugin's folder is `rpi_io`, after its package | proposed |
| [0033](0033-fsp-autostart.md) | The FSP's ACSI server starts with the service (`FSP_AUTOSTART`, on); connecting to the SO is `FSP_AUTOCONNECT` (off) | proposed |
| [0034](0034-demo-stack-plugins-sim-leds-io-opt-in.md) | The demo stack connects to sim_leds by default, run by an overlay; the IO server is opt-in | proposed |
| [0035](0035-connection-names-unique-ids-uuid.md) | A connection's name is unique; its id is a UUID | proposed |
| [0036](0036-plugin-definitions-editable.md) | A plugin's definition (URL, settings) can be edited, until the FSP or SO restarts | proposed |
| [0037](0037-plugin-allowed-sources-wildcards.md) | Allowed plugin sources take wildcards; `*` alone allows any URL, and is the default | proposed |
| [0038](0038-io-plugin-name-dr-panel.md) | The IO plugin's code, project and image are `dr_panel` / `dr-panel` | proposed |
| [0039](0039-sample-plugin-name-dr-leds.md) | The sample plugin's name, code, project and image are `dr_leds` / `dr-leds` | proposed |
| [0040](0040-io-plugin-plugin-name-dr-panel.md) | The IO plugin's plugin name is `dr_panel` | proposed |
| [0041](0041-oci-image-labels.md) | Every image carries the OCI labels; static ones in the Dockerfile, per-build ones from CI | proposed |
| [0042](0042-plugin-claims-in-settings.md) | A plugin's claims can be set in its settings, so the configuration and the HMI change them | proposed |

To add a decision, copy the layout of an existing record, take the next number, and add a line to this table.
