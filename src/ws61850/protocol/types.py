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
Protocol-level type definitions shared by the data model and the ASN1 encoding layer.

Every name and integer value in this module is normative: they appear directly in
the wire format produced by ``ws61850.asn1.encode_decode``.  Do not rename or
renumber anything here without simultaneously updating
``src/ws61850/asn1/schema/ws_iec61850_tpaa_full.asn``.
"""

from dataclasses import asdict, dataclass
from enum import Enum


class DataAttributeType(Enum):
    """
    Data-attribute type tag.

    The ``.name`` of each member is the ASN1 ``Data ::= CHOICE`` discriminator string
    passed to ``asn1tools`` during wire encoding.  The integer value is the ASN1
    context tag number and must match both ``TypeSpecification`` and ``Data`` in the
    ASN1 schema.
    """

    boolean = 1
    int8 = 2
    int16 = 3
    int24 = 4
    int32 = 5
    int64 = 6
    int8u = 7
    # 8 is reserved in the ASN1 schema
    int16u = 9
    int24u = 10
    int32u = 11
    float32 = 12
    octetString = 13
    visString64 = 14
    visString129 = 15
    visString255 = 16
    array = 17
    structure = 18
    bitstring = 19
    # 20 is reserved
    generalizedtime = 21
    binaryTime = 22
    quality = 23
    timeStamp = 24
    enumerated = 25
    check = 26


class FunctionalConstraint(Enum):
    """
    Functional constraint.

    Use ``.wire_name`` (not ``.name``) when building wire-format strings, because
    ``or_`` is the Python identifier but the ASN1 name is ``or``.  All other members
    have identical Python and ASN1 names.
    """

    st = 0
    mx = 1
    sp = 2
    sv = 3
    cf = 4
    dc = 5
    sg = 6
    se = 7
    sr = 8
    or_ = 9   # ASN1 name is "or"; Python reserves "or" as a keyword
    bl = 10
    ex = 11
    lg = 12
    co = 13

    @property
    def wire_name(self) -> str:
        """Return the ASN1 ``FC`` enum name used in wire encoding."""
        return "or" if self is FunctionalConstraint.or_ else self.name

    @classmethod
    def from_wire(cls, name: str) -> "FunctionalConstraint":
        """Look up an FC by its ASN1 wire name (handles 'or' → or_)."""
        if name == "or":
            return cls.or_
        return cls[name]


class ACSIClassKind(Enum):
    dataObject = 0
    dataset = 1
    brcb = 2
    urcb = 3
    lcb = 4
    log = 5
    sgcb = 6
    gocb = 7
    gscb = 8
    msvcb = 9
    usvcb = 10


class OriginatorCategoryKind(Enum):
    notSupported = 0
    bayControl = 1
    stationControl = 2
    remoteControl = 3
    automaticBay = 4
    automaticStation = 5
    automaticRemote = 6
    maintenance = 7
    process = 8


@dataclass
class TrgOps:
    """
    Trigger options for a report control block.

    Field names match ``TrgOps ::= SEQUENCE`` in the ASN1 schema.
    ``to_wire()`` returns the plain dict that ``asn1tools`` expects.
    ``from_wire()`` reconstructs from a decoded ASN1 dict.
    """

    dchg: bool = False
    qchg: bool = False
    dupd: bool = False
    integrity: bool = False
    gi: bool = False

    def to_wire(self) -> dict:
        return asdict(self)

    @classmethod
    def from_wire(cls, d: dict) -> "TrgOps":
        keys = ("dchg", "qchg", "dupd", "integrity", "gi")
        return cls(**{k: d.get(k, False) for k in keys})


@dataclass
class OptFlds:
    """
    Optional fields for a report control block.

    Field names match ``OptFldsRCB ::= SEQUENCE`` in the ASN1 schema.
    ``to_wire()`` returns the plain dict that ``asn1tools`` expects.
    ``from_wire()`` reconstructs from a decoded ASN1 dict.
    """

    seqNum: bool = False
    timeStamp: bool = False
    dataSet: bool = False
    bufOvfl: bool = False
    configRef: bool = False
    entryID: bool = False
    dataRef: bool = False
    reasonCode: bool = False

    def to_wire(self) -> dict:
        return asdict(self)

    @classmethod
    def from_wire(cls, d: dict) -> "OptFlds":
        keys = ("seqNum", "timeStamp", "dataSet", "bufOvfl", "configRef", "entryID", "dataRef", "reasonCode")
        return cls(**{k: d.get(k, False) for k in keys})
