<!--
SPDX-FileCopyrightText: 2026 Netbeheer Nederland

SPDX-License-Identifier: Apache-2.0
-->

# 23. The IO server's code is `rpi_io`, flat, in `src/`

- Status: proposed
- Date: 2026-10-11

## Context

[0018](0018-io-module-names.md) split the IO module's names: `io` for the role (folder, service, container
`rti-io`, port 9000), `rti_io` for the code, because `io` is a standard library module and can't be imported by its
own name. The code had two parts, `rti_io.server` and `rti_io.plugin`. Since [0022](0022-io-plugin-own-package.md)
the plugin is the package `acsi_io_plugin` in `modules/io-plugin`, and `modules/io` holds only the server. Its layout
still reflects the time it held both (2026-10-11):

| | `bff`, `fsp`, `so`, `plugins`, `io-plugin` | `io` |
|---|---|---|
| Code | `src/<package>/` | `rti_io/server/`, under a package with nothing else in it |
| Started with | `python -m fsp.bff_endpoint` | `python -m rti_io.server.main` |
| Build | `[build-system]`, `packages.find` in `src` | none: the image copies the folder, the code runs from `/app` |
| Tests | import the installed package | put `modules/io` on `sys.path` themselves |

- **The name says the demo, not the hardware.** `rti_` repeats the demo's name, which every module shares. The
  code itself is written for the Raspberry Pi: `gpiod.Chip("/dev/gpiochip0")`, I2C bus 1 ("Raspberry Pi I2C bus"),
  an ADS1115 or MCP3008 ADC, a PCF8574 LCD backpack, and an image with the Pi's default user and group IDs.
  `docker-compose.yml` targets the Pi ([0017](0017-hardware-is-optional.md)).
- **The `server` level separates nothing.** Every module of the IO server is `rti_io.server.<x>`; `rti_io` itself
  holds only a docstring.
- **The distribution name is the role name.** `b8e03c5` renamed the project from `rti-io` to `io`, like `fsp` and
  `so`. For those the role and the package have one name; for the IO server they can't.
- **It declares what it doesn't use.** The server imports `fastapi`, `pydantic`, `uvicorn`, `httpx2`, `gpiod`,
  `gpiozero`, `smbus2` and `Adafruit_ADS1x15` (and `spidev`, only for an MCP3008, not declared). `aiohttp`,
  `asn1tools`, `docker`, `PyJWT`, `requests`, `websockets` and `python-multipart` are left from the project that also
  held the plugin; they make the Pi image larger and its lock file longer.

Three options were considered for the name:

1. **Keep `rti_io`, flatten it.** The least change, but the name still says nothing the folder doesn't.
2. **`rpi`.** Short, but close to `RPi`, the import name of the common `RPi.GPIO` library (which `devices.py` already
   mentions), and it claims more than the code is: the Pi's IO server, not everything to do with the Pi.
3. **`rpi_io`** (chosen): what runs (IO) and what it runs on (the Raspberry Pi).

## Decision

1. **The role stays `io`.** The folder `modules/io`, the `launch.py` service, the image and container `rti-io`, port
   9000, `IO_URL`, and the plugin `io` with its routes `/api/plugins/io/...` keep their names (0018). The FSP, SO and
   HMI talk to "the IO server", not to a Pi: another board that serves the same IO API would be another code package
   for the same role.
2. **The code is `rpi_io`, flat, in `src/`.** `modules/io/rti_io/server/<x>.py` moves to `modules/io/src/rpi_io/<x>.py`
   (`api_endpoint.py`, `devices.py`, `io_config.py`, `io_config.json`, `io_controller.py`, `lcd_i2c_check.py`,
   `main.py`); `rti_io/__init__.py` goes, and `server/__init__.py` becomes the package's. The server is started with
   `python -m rpi_io.main`, the LCD check with `python -m rpi_io.lcd_i2c_check`. Imports inside the package stay
   relative; the few absolute `rti_io.server.` ones become relative or `rpi_io.`.
3. **The distribution is `rpi-io`,** after the package, as `acsi-plugins` and `acsi-io-plugin` are. `pyproject.toml`
   gets the `[build-system]`, `packages.find` and `package-data` (`io_config.json`) the other modules have, and
   `[tool.pytest.ini_options]` with `pythonpath = ["src"]`, `testpaths` and the `unit` marker.
4. **Its own uv project still.** `modules/io` keeps its `uv.lock` and stays out of the root workspace (0011, 0017): the
   hardware packages, `gpiod` with its C build above all, would otherwise land in every `uv sync --all-packages`. Its
   tests keep running under the FSP's environment (`uv run --package fsp pytest examples/rti-demo/modules/io/tests`),
   which has what the server imports without hardware; `pythonpath` finds the package, so the tests no longer edit
   `sys.path`. For the same reason `launch.py` runs the server from `modules/io/src` in the repository's environment,
   where a device whose hardware package is missing stays unavailable (0017).
5. **Only what it uses.** The dependencies are `fastapi`, `pydantic`, `uvicorn`, `httpx2`, `gpiod`, `gpiozero`,
   `smbus2` and `Adafruit-ADS1x15`. `spidev` stays an optional import, as it is now.
6. **The image installs the package.** The Dockerfile installs the dependencies from `pyproject.toml` and `uv.lock`
   first (`--no-install-project`, for the layer cache), then copies `README.md` and `src/`, installs the project with
   `uv sync --frozen --no-dev` and starts `python -m rpi_io.main`.

## Consequences

- `modules/io` has the layout of the other modules, and the IO server is found the same way: `src/<package>/`, a
  `pyproject.toml` that builds it, tests that import it.
- The name says what the code is for. A reader who sees `rpi_io` in a traceback or a command knows it is the Pi
  side; a reader who sees `io` in compose or a URL knows the role.
- **Breaking, without a transition**, as in 0021 and 0022: `python -m rti_io.server.main` and
  `python -m rti_io.server.lcd_i2c_check` no longer work. Inside the demo nothing else imports the server, and
  `launch.py`, the Dockerfile and compose change in the same commit. A Pi that runs the server by hand needs the new
  command; the image needs a rebuild.
- `IO_CONFIG_FILE` keeps working. Its default, the shipped file, moves to `src/rpi_io/io_config.json`; a file set by
  `IO_CONFIG_FILE` or kept on a volume is untouched.
- The image gets smaller by the unused packages. `uv.lock` is regenerated, so the next image build resolves nothing
  new but downloads less.
- Superseded in 0018: the code name `rti_io` (distribution `rti-io`) and `rti_io.server`; the role name `io` stands.
  Superseded in 0022, point 4: "`modules/io` keeps `rti_io.server`"; the rest stands.
- Superseded in [0038](0038-io-plugin-name-dr-panel.md): the names `rpi_io` / `rpi-io` and the image `rti-io` are now
  `dr_panel` / `dr-panel`.
- Older records (0011, 0017, 0019, 0021, 0022) keep the paths they were written with; this record says where those
  paths went.
- Review one month after the move: whether anything still starts `rti_io.server.main`, and whether a second IO
  implementation is in sight, which would test whether `io` and `rpi_io` were split in the right place.

## In the code

- `examples/rti-demo/modules/io/src/rpi_io/` (moved from `rti_io/server/`); `examples/rti-demo/modules/io/pyproject.toml`
  (name `rpi-io`, build, dependencies, pytest), `uv.lock`
- `examples/rti-demo/modules/io/docker/Dockerfile` (`COPY src/`, install, `CMD ["python", "-u", "-m", "rpi_io.main"]`)
- `examples/rti-demo/launch.py` (the `io` service's module, entry point and `working_dir`, `modules/io/src`)
- `REUSE.toml` (the path to `io_config.json`)
- Tests: `examples/rti-demo/modules/io/tests/` (`test_project.py`; the others without `sys.path`),
  `tests/unit/test_rti_demo_io_image.py`, `tests/unit/test_rti_demo_launch.py`, `tests/unit/test_rti_demo_ports.py`,
  `tests/unit/test_rti_demo_io_names.py` (`rti_io` only in the decision records),
  `examples/rti-demo/modules/io-plugin/tests/test_installed.py`
- Docs: the READMEs of `io`, `io-plugin` and the rti-demo; `examples/rti-demo/TESTING.md`
