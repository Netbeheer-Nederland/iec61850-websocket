# SPDX-FileCopyrightText: 2025 Netbeheer Nederland
# SPDX-License-Identifier: Apache-2.0
#
# Copyright 2025 Netbeheer Nederland
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""
IEC 61850 data model classes.

The model tree is:

    IedModel
      └── LogicalDevice  (1..*)
            └── LogicalNode  (1..*)
                  ├── DataObject  (0..*)
                  │     └── DataObject | DataAttribute  (0..*)  [do_or_da]
                  │                         └── DataAttribute  (0..*)  [data_attributes]
                  ├── DataSet  (0..*)
                  └── ReportControl  (0..*)

Protocol-level enumerations (DataAttributeType, FunctionalConstraint, …) live in
``ws61850.protocol.types`` — import from there, not from this module.
"""

from ws61850.protocol.types import DataAttributeType, FunctionalConstraint  # noqa: F401 — re-exported for callers


class IedModel:
    """Root of the IED model tree."""

    def __init__(self, name: str, logical_devices=None):
        self.name = name
        self.logical_devices = logical_devices if logical_devices is not None else []

    def add_logical_device(self, logical_device: "LogicalDevice") -> None:
        logical_device.parent = self
        self.logical_devices.append(logical_device)

    # Legacy name kept so existing server code compiles without change
    def add_logicalDevice(self, logical_device: "LogicalDevice") -> None:
        self.add_logical_device(logical_device)


class ModelNode:
    """Abstract base for all nodes in the model tree."""

    def __init__(self, name: str, parent=None):
        self.name = name
        self.parent = parent


class LogicalDevice(ModelNode):
    """Represents a Logical Device (LD)."""

    def __init__(self, name: str, ldName: str, parent=None):
        super().__init__(name=name, parent=parent)
        self.ldName = ldName
        self.logical_nodes: list["LogicalNode"] = []

    def add_logical_node(self, ln: "LogicalNode") -> None:
        ln.parent = self
        self.logical_nodes.append(ln)


class LogicalNode(ModelNode):
    """Represents a Logical Node (LN)."""

    def __init__(self, name: str, parent=None):
        super().__init__(name=name, parent=parent)
        self.data_objects: list["DataObject"] = []
        self.data_sets: list["DataSet"] = []
        self.rcbs: list["ReportControl"] = []

    def add_data_object(self, data_object: "DataObject") -> None:
        data_object.parent = self
        self.data_objects.append(data_object)

    def add_report_control(self, rcb: "ReportControl") -> None:
        rcb.ln = self
        rcb.obj_ref = rcb.get_obj_ref()
        self.rcbs.append(rcb)

    def add_data_set(self, data_set: "DataSet") -> None:
        self.data_sets.append(data_set)

    # Legacy names so existing server/test code compiles without change
    def add_dataObject(self, data_object: "DataObject") -> None:
        self.add_data_object(data_object)

    def add_reportControl(self, rcb: "ReportControl") -> None:
        self.add_report_control(rcb)

    def add_dataSet(self, data_set: "DataSet") -> None:
        self.add_data_set(data_set)

    def get_obj_ref(self) -> str:
        ld = self.parent
        return f"{ld.name}/{self.name}"

    def get_objRef(self) -> str:
        return self.get_obj_ref()


class DataObject(ModelNode):
    """
    Represents a Data Object (DO).

    ``cdc`` is a string like ``"mv"``, ``"asg"``, ``"apc"`` that names the
    Common Data Class.  It is returned verbatim in ``getDataDefinition`` wire
    responses, so it must match a value known to the remote client.

    ``elementCount`` is always 0 for scalar DOs and is included solely because
    the ``getDataDefinition`` response embeds it in the wire message.
    """

    def __init__(self, name: str, cdc: str, parent=None):
        super().__init__(name=name, parent=parent)
        self.cdc = cdc
        self.elementCount = 0  # wire field; always 0 for non-array DOs
        self.do_or_da: list = []  # List[DataObject | DataAttribute]

    def add_do_or_da(self, item) -> None:
        self.do_or_da.append(item)

    def get_da_from_do_or_da_list(self) -> list:
        return [da for da in self.do_or_da if isinstance(da, DataAttribute)]

    def get_do_from_do_or_da_list(self) -> list:
        return [do for do in self.do_or_da if isinstance(do, DataObject)]

    def get_obj_ref(self) -> str:
        parts = []
        obj = self
        while not isinstance(obj, LogicalNode):
            parts.append(obj.name)
            obj = obj.parent
        ln = obj
        ld = ln.parent
        return f"{ld.name}/{ln.name}." + ".".join(reversed(parts))

    def get_objRef(self) -> str:
        return self.get_obj_ref()


class DataAttribute(ModelNode):
    """
    Represents a Data Attribute (DA).

    ``attr_type`` is a :class:`DataAttributeType` whose ``.name`` is used
    directly as the ASN1 ``Data ::= CHOICE`` discriminator in wire encoding.

    ``fc`` is a :class:`FunctionalConstraint`; use ``fc.wire_name`` (not
    ``fc.name``) when building wire-format strings to avoid the ``or_`` edge case.

    ``mms_value`` is the live runtime value.  Its Python type depends on
    ``attr_type``:

    ========================  ========================
    attr_type                 mms_value Python type
    ========================  ========================
    float32                   float
    int8, int32, …            int
    boolean                   bool
    visString255, …           str
    enumerated                int
    octetString               bytes
    quality                   dict (keys: validity, source, test, operatorBlock)
    timeStamp                 dict (keys: secondSinceEpoch, fractionOfSecond, timeQuality)
    check                     dict (keys: synchroCheck, interlockCheck)
    structure                 [] (children accessed via data_attributes)
    ========================  ========================
    """

    def __init__(
        self,
        name: str,
        attr_type: DataAttributeType,
        fc: FunctionalConstraint,
        mms_value=None,
        parent=None,
    ):
        super().__init__(name=name, parent=parent)
        self.attr_type = attr_type
        self.fc = fc
        self.mms_value = mms_value
        self.data_attributes: list["DataAttribute"] = []

    def add_data_attribute(self, data_attribute: "DataAttribute") -> None:
        data_attribute.parent = self
        self.data_attributes.append(data_attribute)

    # Legacy name
    def addDataAttribute(self, data_attribute: "DataAttribute") -> None:
        self.add_data_attribute(data_attribute)

    def get_obj_ref(self) -> str:
        parts = []
        obj = self
        while not isinstance(obj, LogicalNode):
            parts.append(obj.name)
            obj = obj.parent
        ln = obj
        ld = ln.parent
        return f"{ld.name}/{ln.name}." + ".".join(reversed(parts))

    def get_objRef(self) -> str:
        return self.get_obj_ref()

    # ------------------------------------------------------------------
    # Legacy attribute aliases so server code that reads da.type and
    # da.mmsValue compiles without change during incremental migration.
    # ------------------------------------------------------------------

    @property
    def type(self):
        return self.attr_type

    @type.setter
    def type(self, value):
        self.attr_type = value

    @property
    def mmsValue(self):
        return self.mms_value

    @mmsValue.setter
    def mmsValue(self, value):
        self.mms_value = value


class DataSet:
    """Represents a DataSet belonging to a LogicalNode."""

    def __init__(self, parent: LogicalNode, logical_device_name: str, name: str, fcdas=None):
        self.parent = parent
        self.logical_device_name = logical_device_name
        self.name = name
        self.fcdas: list["DataSetEntry"] = fcdas if fcdas is not None else []

    def add_entry(self, entry: "DataSetEntry") -> None:
        self.fcdas.append(entry)

    # Legacy name
    def dataSet_addEntry(self, entry: "DataSetEntry") -> None:
        self.add_entry(entry)

    def get_obj_ref(self) -> str:
        ln = self.parent
        return f"{self.logical_device_name}/{ln.name}.{self.name}"

    def get_objRef(self) -> str:
        return self.get_obj_ref()


class DataSetEntry:
    """One FCDA (Functionally Constrained Data Attribute) reference in a DataSet."""

    def __init__(
        self,
        logical_device_name: str,
        variable_name: str,
        fc: FunctionalConstraint,
    ):
        self.logical_device_name = logical_device_name
        self.variable_name = variable_name
        self.fc = fc


class ReportControl:
    """
    Report Control Block (RCB) — buffered (BRCB) or unbuffered (URCB).

    All parameters after ``name`` are keyword-only with sensible defaults so
    that callers need not provide the full 13-positional-argument list.

    ``trg_ops`` and ``opt_flds`` must be plain dicts with keys matching the
    ASN1 ``TrgOps`` and ``OptFldsRCB`` field names respectively.  The easiest
    way to build them is via :meth:`ws61850.protocol.types.TrgOps.to_wire` and
    :meth:`ws61850.protocol.types.OptFlds.to_wire`.

    ``dataset_name`` must be the full three-part path ``LD/LN.DataSetName``.
    The server's ``find_ds_in_tree`` splits on ``[/.]`` and expects exactly
    three components; a short name will silently produce no dataset match.

    ``ln`` and ``obj_ref`` are set by :meth:`LogicalNode.add_report_control`
    and should not be supplied in the constructor.
    """

    def __init__(
        self,
        name: str,
        *,
        buffered: bool,
        dataset_name: str,
        rpt_id: str = "",
        conf_rev: int = 1,
        trg_ops: dict | None = None,
        opt_flds: dict | None = None,
        buffered_time: int | str = 0,
        int_period: int = 1000,
        indexed: bool = False,
    ):
        self.name = name
        self.buffered = buffered
        self.dataset_name = dataset_name
        self.rpt_id = rpt_id or name
        self.conf_rev = conf_rev
        self.trg_ops: dict = trg_ops if trg_ops is not None else {}
        self.opt_flds: dict = opt_flds if opt_flds is not None else {}
        self.buffered_time = buffered_time
        self.int_period = int_period
        self.indexed = indexed
        # set by LogicalNode.add_report_control:
        self.ln: LogicalNode | None = None
        self.obj_ref: str = ""
        # runtime state (set by server):
        self.client_connection = None
        self.gi: bool = False

    def get_obj_ref(self) -> str:
        if self.ln is None:
            return self.obj_ref
        ld = self.ln.parent
        return f"{ld.name}/{self.ln.name}.{self.name}"

    def get_objRef(self) -> str:
        return self.get_obj_ref()
