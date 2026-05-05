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
JSON model loader for IEC 61850 IED models.

Reads a dict (or JSON file) that conforms to ``schema/ied_model.schema.json``
and produces a fully populated :class:`IedModel` tree.  CDC factory functions
(via :class:`CdcRegistry`) expand each ``{"name": ..., "cdc": ...}`` entry into
its complete DataAttribute subtree.

Example JSON file::

    {
      "name": "TestIED",
      "logical_devices": [
        {
          "name": "LD0",
          "ld_name": "LD0",
          "logical_nodes": [
            {
              "name": "LLN0",
              "data_objects": [{"name": "NamPlt", "cdc": "lpl"}]
            },
            {
              "name": "DWMX1",
              "data_objects": [
                {"name": "TotW",   "cdc": "mv"},
                {"name": "WMaxSpt","cdc": "asg"}
              ],
              "data_sets": [
                {
                  "name": "DataSet1",
                  "entries": [
                    {"variable_name": "DWMX1.TotW.mag.f", "fc": "mx"}
                  ]
                }
              ],
              "report_controls": [
                {
                  "name": "brcb01",
                  "buffered": true,
                  "dataset_name": "LD0/DWMX1.DataSet1",
                  "trg_ops": {"dchg": true, "integrity": true}
                }
              ]
            }
          ]
        }
      ]
    }

Usage::

    model = IedModelLoader.from_file("my_ied.json")
"""

import json
import pathlib

from ws61850.iec61850.data_model.cdc_registry import CdcRegistry
from ws61850.iec61850.data_model.ied_model import (
    DataSet,
    DataSetEntry,
    FunctionalConstraint,
    IedModel,
    LogicalDevice,
    LogicalNode,
    ReportControl,
)
from ws61850.protocol.types import OptFlds, TrgOps


class IedModelLoader:
    @staticmethod
    def from_file(path: str | pathlib.Path) -> IedModel:
        with open(path, encoding="utf-8") as fh:
            data = json.load(fh)
        return IedModelLoader.from_dict(data)

    @staticmethod
    def from_dict(data: dict) -> IedModel:
        model = IedModel(data["name"])
        for ld_data in data.get("logical_devices", []):
            ld = IedModelLoader._build_ld(ld_data)
            model.add_logical_device(ld)
        return model

    @staticmethod
    def _build_ld(data: dict) -> LogicalDevice:
        ld = LogicalDevice(data["name"], data["ld_name"])
        for ln_data in data.get("logical_nodes", []):
            IedModelLoader._build_ln(ln_data, ld)
        return ld

    @staticmethod
    def _build_ln(data: dict, ld: LogicalDevice) -> LogicalNode:
        ln = LogicalNode(data["name"])
        # Must attach to LD first so ln.parent is set before add_report_control
        # computes obj_ref (which walks ln.parent → ld.name).
        ld.add_logical_node(ln)
        for do_data in data.get("data_objects", []):
            factory = CdcRegistry.get_factory(do_data["cdc"])
            do = factory(do_data["name"], ln)
            ln.add_data_object(do)
        for ds_data in data.get("data_sets", []):
            ds = IedModelLoader._build_dataset(ds_data, ln, ld.name)
            ln.add_data_set(ds)
        for rcb_data in data.get("report_controls", []):
            rcb = IedModelLoader._build_rcb(rcb_data)
            ln.add_report_control(rcb)
        return ln

    @staticmethod
    def _build_dataset(data: dict, ln: LogicalNode, ld_name: str) -> DataSet:
        entries = []
        for e in data.get("entries", []):
            fc = FunctionalConstraint.from_wire(e["fc"])
            entries.append(DataSetEntry(ld_name, e["variable_name"], fc))
        return DataSet(ln, ld_name, data["name"], entries)

    @staticmethod
    def _build_rcb(data: dict) -> ReportControl:
        trg_ops = TrgOps.from_wire(data.get("trg_ops", {})).to_wire()
        opt_flds = OptFlds.from_wire(data.get("opt_flds", {})).to_wire()
        return ReportControl(
            data["name"],
            buffered=data["buffered"],
            dataset_name=data["dataset_name"],
            rpt_id=data.get("rpt_id", ""),
            conf_rev=data.get("conf_rev", 1),
            trg_ops=trg_ops,
            opt_flds=opt_flds,
            buffered_time=data.get("buffered_time", 0),
            int_period=data.get("int_period", 1000),
            indexed=data.get("indexed", False),
        )
