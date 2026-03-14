# Overview

This folder contains the project documentation, including the RTIv2 protocol specification, Doxygen configuration,
and supporting artifacts.

## Docs Overview

```
docs/
├─ README.md                              # This overview
├─ THIRD_PARTY_LICENSES.txt               # License information
├─ LICENSES                               # Directory with Licenses
├─ protocol_specification/
│  ├─ RTI_2.0_Protocol_Specification.md   # RTIv2 protocol specification
│  └─ media/                              # Figures referenced by the spec
├─ scl/
│  └─ rti_v1.0.scd                        # SCL file used for the PoC
└─ doxygen/
   └─ Doxyfile                            # Doxygen configuration for generating documentation
```

## Generate Doxygen

From the repository root, run:

```bash
doxygen docs/doxygen/Doxyfile
```

The generated HTML output is written to:

```text
docs/doxygen/html/index.html
```

Make sure `doxygen` is installed locally before running this command.
