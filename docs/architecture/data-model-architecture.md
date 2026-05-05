# Data Model Architecture

This document describes the IEC 61850 data model layer (`ws61850.iec61850.data_model`), its relationship to the
wire-encoding layer, the design decisions made during the refactoring, and how to construct or load a model at runtime.

---

## Contents

1. [Module layout](#module-layout)
2. [The three-role problem](#the-three-role-problem)
3. [Protocol coupling — what the ASN1 layer requires](#protocol-coupling)
4. [Class reference](#class-reference)
5. [Builder pattern](#builder-pattern)
6. [JSON model loading](#json-model-loading)
7. [CDC registry](#cdc-registry)
8. [Known bugs fixed in this refactoring](#known-bugs-fixed)

---

## Module layout

```
src/ws61850/iec61850/data_model/
  ied_model.py          # Core node classes (IedModel, LogicalDevice, …)
  helper.py             # CDC factory functions (create_mv_do, create_apc_do, …)
  cdc_registry.py       # CdcRegistry: name → factory function mapping
  builder.py            # Fluent builders (IedModelBuilder, …)
  loader.py             # IedModelLoader: construct from JSON dict/file
  example_ieds.py       # build_model1() / build_model2() example trees
  schema/
    ied_model.schema.json   # JSON Schema draft-7 for the model file format

src/ws61850/protocol/
  types.py              # DataAttributeType, FunctionalConstraint, TrgOps, OptFlds
```

`protocol/types.py` is the canonical authority for every type that appears in **both** the data model and the wire
format. Import from there — not from `ied_model.py`.

---

## The three-role problem

The data model tree simultaneously plays three roles:

| Role                    | Who uses it                                                            | What they need                                                                  |
|-------------------------|------------------------------------------------------------------------|---------------------------------------------------------------------------------|
| **Model description**   | Directory services (`getDataDefinition`, `getLogicalNodeDirectory`, …) | CDC names, DA names, FC strings                                                 |
| **Runtime value store** | `update_value()`, `setDataValues`, reports                             | `da.mms_value` mutated in place                                                 |
| **Encoding proxy**      | ASN1 encode/decode layer                                               | DA type names as `Data ::= CHOICE` discriminators; FC names as `FC` enum values |

These three roles pull in opposite directions: a clean description tree would have no mutable values; a clean value
store would not care about wire names. The refactoring keeps all three roles in the same classes but makes the protocol
coupling **explicit** via `protocol/types.py`.

---

## Protocol coupling

The ASN1 layer (`ws61850.asn1.encode_decode`) uses `asn1tools` to encode Python tuples/dicts into BER/JSON. Several
parts of the data model are used directly as ASN1 field values:

### `da.attr_type.name` is the `Data ::= CHOICE` discriminator

```python
# ASN1: Data ::= CHOICE { boolean [1], float32 [12], quality [23], … }
value_tuple = (da.attr_type.name, da.mms_value)
# → ("float32", 12.34) or ("quality", {"validity": "good", …})
```

`DataAttributeType` enum member names must therefore match the ASN1 `Data` alternative names exactly.

### `da.fc.wire_name` is the `FC` enumerated value

Use `.wire_name`, **not** `.name`. The Python identifier for functional constraint `or` is `or_` (because `or` is a
reserved keyword), but the ASN1 enum name is `or`. All other FCs have identical Python and ASN1 names.

```python
# WRONG — returns "or_" for the 'or' FC:
fc_string = da.fc.name

# CORRECT:
fc_string = da.fc.wire_name
```

### `da.mms_value` dict keys ARE ASN1 field names

For structured types (`quality`, `timeStamp`, `check`), `mms_value` is a dict whose keys must match the ASN1 field names
exactly:

```python
# quality — keys match Quality ::= SEQUENCE in the ASN1 schema
{"validity": "good", "source": "process", "test": False, "operatorBlock": False}

# timeStamp — keys match TimeStamp ::= SEQUENCE
{"secondSinceEpoch": 1720458123, "fractionOfSecond": 1234567,
 "timeQuality": {"leapSecondsKnown": False, "clockFailure": False,
                 "clockNotSynchronized": False, "timeAccuracy": 3}}

# check — keys match CheckConditions ::= SEQUENCE
{"synchroCheck": False, "interlockCheck": False}
```

Note: older code used `"leapSecondsKown"` (typo, missing 'n'). This has been corrected to `"leapSecondsKnown"`
throughout.

### `rcb.trg_ops` and `rcb.opt_flds` are wire-format dicts

`ReportControl.trg_ops` and `ReportControl.opt_flds` are stored as plain dicts that map directly to the ASN1 `TrgOps`and
`OptFldsRCB` field names. Build them via `TrgOps(...).to_wire()` and `OptFlds(...).to_wire()`.

---

## Class reference

### `IedModel`

Root of the tree. Holds `logical_devices: list[LogicalDevice]`.

```python
ied = IedModel("MyIED")
ied.add_logical_device(ld)
```

### `LogicalDevice`

```python
ld = LogicalDevice(name="LD0", ldName="LD0")
ld.add_logical_node(ln)
```

### `LogicalNode`

Holds `data_objects`, `data_sets`, and `rcbs`.

```python
ln = LogicalNode("DWMX1")
ln.add_data_object(do)
ln.add_data_set(ds)
ln.add_report_control(rcb)  # sets rcb.ln and rcb.obj_ref
```

### `DataObject`

```python
do = DataObject("TotW", cdc="mv")
do.add_do_or_da(da)  # child DataAttribute or nested DataObject
```

`cdc` is a lowercase string like `"mv"`, `"asg"`, `"apc"` returned verbatim in `getDataDefinition` responses.
`elementCount` is always 0 and is an internal wire-format constant.

### `DataAttribute`

```python
da = DataAttribute(
    "mag",
    attr_type=DataAttributeType.structure,
    fc=FunctionalConstraint.mx,
    mms_value=[],
    parent=do,
)
da.add_data_attribute(child_da)
```

Key attributes:

| Attribute   | Type                   | Wire role                           |
|-------------|------------------------|-------------------------------------|
| `attr_type` | `DataAttributeType`    | `.name` → ASN1 `Data` discriminator |
| `fc`        | `FunctionalConstraint` | `.wire_name` → ASN1 `FC` enum value |
| `mms_value` | varies                 | Direct ASN1 field value             |

### `DataSet` / `DataSetEntry`

```python
ds = DataSet(ln, "LD0", "DataSet1", [
    DataSetEntry("LD0", "DWMX1.TotW.mag.f", FunctionalConstraint.mx),
])
```

`DataSetEntry` stores the variable name relative to the LD (e.g. `"DWMX1.TotW.mag.f"`) plus the FC.

### `ReportControl`

All parameters after `name` are keyword-only:

```python
rcb = ReportControl(
    "brcb01",
    buffered=True,
    dataset_name="LD0/LLN0.DataSet1",  # must be full three-part ref
    trg_ops=TrgOps(dchg=True, integrity=True).to_wire(),
    opt_flds=OptFlds(timeStamp=True, dataSet=True).to_wire(),
    int_period=1000,
)
ln.add_report_control(rcb)  # sets rcb.ln and rcb.obj_ref
```

`dataset_name` must be the full `LD/LN.DataSetName` path — `find_ds_in_tree` splits on `[/.]` and expects exactly three
segments.

---

## Builder pattern

`IedModelBuilder` provides a fluent API for constructing model trees without manually wiring parent references:

```python
from ws61850.iec61850.data_model.builder import IedModelBuilder
from ws61850.protocol.types import TrgOps, OptFlds

model = (
    IedModelBuilder("MyIED")
    .logical_device("LD0", ld_name="LD0")
    .logical_node("LLN0")
    .data_object("NamPlt", cdc="lpl")
    .data_set("DataSet1")
    .entry("DWMX1.TotW.mag.f", FunctionalConstraint.mx)
    .end_data_set()
    .brcb("brcb01", dataset_name="LD0/LLN0.DataSet1")
    .trg_ops(dchg=True, integrity=True)
    .opt_flds(timeStamp=True, dataSet=True)
    .int_period(1000)
    .end_report_control()
    .end_logical_node()
    .logical_node("DWMX1")
    .data_object("TotW", cdc="mv")
    .data_object("WMaxSpt", cdc="asg")
    .end_logical_node()
    .end_logical_device()
    .build()
)
```

The builder calls CDC factory functions automatically from `CdcRegistry`, so you only need the CDC name string.

---

## JSON model loading

Models can be defined in JSON and loaded at startup via `IedModelLoader`:

```python
from ws61850.iec61850.data_model.loader import IedModelLoader

model = IedModelLoader.from_file("config/my_ied.json")
# or from a dict already parsed elsewhere:
model = IedModelLoader.from_dict(data)
```

JSON format (conforms to `schema/ied_model.schema.json`):

```json
{
  "name": "MyIED",
  "logical_devices": [
    {
      "name": "LD0",
      "ld_name": "LD0",
      "logical_nodes": [
        {
          "name": "DWMX1",
          "data_objects": [
            {
              "name": "TotW",
              "cdc": "mv"
            },
            {
              "name": "WMaxSpt",
              "cdc": "asg"
            }
          ],
          "data_sets": [
            {
              "name": "DataSet1",
              "entries": [
                {
                  "variable_name": "DWMX1.TotW.mag.f",
                  "fc": "mx"
                }
              ]
            }
          ],
          "report_controls": [
            {
              "name": "brcb01",
              "buffered": true,
              "dataset_name": "LD0/DWMX1.DataSet1",
              "trg_ops": {
                "dchg": true,
                "integrity": true
              },
              "opt_flds": {
                "timeStamp": true,
                "dataSet": true
              },
              "int_period": 1000
            }
          ]
        }
      ]
    }
  ]
}
```

The JSON stays at **CDC granularity** — you specify `{"name": "TotW", "cdc": "mv"}` and the CDC factory function expands
this into the full `mag/f`, `q`, `t`, `units` DataAttribute subtree. Individual DA values are not part of the schema;
they are always set programmatically after loading.

---

## CDC registry

`CdcRegistry` maps lowercase CDC name strings to their factory functions:

```python
from ws61850.iec61850.data_model.cdc_registry import CdcRegistry

factory = CdcRegistry.get_factory("mv")  # → create_mv_do
do = factory("TotW", parent_ln)

# Register a custom CDC:
CdcRegistry.register("xyz", my_xyz_factory)

# List all known CDCs:
CdcRegistry.known_cdcs()
# → ['apc', 'asg', 'cmv', 'del', 'dpl', 'enc', 'ens', 'inc', 'ing', 'lpl', 'mv', 'sps', 'wye']
```

---

## Known bugs fixed
