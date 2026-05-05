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
Fluent builders for the IEC 61850 data model.

Each builder follows the same pattern:
  1. Construct with required parameters.
  2. Call optional configuration methods (each returns ``self``).
  3. Call ``.build()`` to get the model node.

Example::

    model = (
        IedModelBuilder("TestIED")
        .logical_device("LD0", ld_name="LD0")
            .logical_node("LLN0")
                .data_object("NamPlt", cdc="lpl")
            .end_logical_node()
            .logical_node("DWMX1")
                .data_object("TotW", cdc="mv")
                .data_object("WMaxSpt", cdc="asg")
            .end_logical_node()
        .end_logical_device()
        .build()
    )
"""

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


class ReportControlBuilder:
    def __init__(
        self,
        name: str,
        *,
        buffered: bool,
        dataset_name: str,
        ln_builder: "LogicalNodeBuilder",
    ):
        self._name = name
        self._buffered = buffered
        self._dataset_name = dataset_name
        self._rpt_id = ""
        self._conf_rev = 1
        self._trg_ops = TrgOps()
        self._opt_flds = OptFlds()
        self._buffered_time: int | str = 0
        self._int_period = 1000
        self._indexed = False
        self._ln_builder = ln_builder

    def rpt_id(self, rpt_id: str) -> "ReportControlBuilder":
        self._rpt_id = rpt_id
        return self

    def conf_rev(self, conf_rev: int) -> "ReportControlBuilder":
        self._conf_rev = conf_rev
        return self

    def trg_ops(self, **kwargs) -> "ReportControlBuilder":
        self._trg_ops = TrgOps(**kwargs)
        return self

    def opt_flds(self, **kwargs) -> "ReportControlBuilder":
        self._opt_flds = OptFlds(**kwargs)
        return self

    def buffered_time(self, buffered_time: int | str) -> "ReportControlBuilder":
        self._buffered_time = buffered_time
        return self

    def int_period(self, int_period: int) -> "ReportControlBuilder":
        self._int_period = int_period
        return self

    def indexed(self, indexed: bool = True) -> "ReportControlBuilder":
        self._indexed = indexed
        return self

    def end_report_control(self) -> "LogicalNodeBuilder":
        rcb = ReportControl(
            self._name,
            buffered=self._buffered,
            dataset_name=self._dataset_name,
            rpt_id=self._rpt_id,
            conf_rev=self._conf_rev,
            trg_ops=self._trg_ops.to_wire(),
            opt_flds=self._opt_flds.to_wire(),
            buffered_time=self._buffered_time,
            int_period=self._int_period,
            indexed=self._indexed,
        )
        self._ln_builder._pending_rcbs.append(rcb)
        return self._ln_builder


class DataSetBuilder:
    def __init__(self, name: str, logical_device_name: str, ln_builder: "LogicalNodeBuilder"):
        self._name = name
        self._ld_name = logical_device_name
        self._ln_builder = ln_builder
        self._entries: list[DataSetEntry] = []

    def entry(self, variable_name: str, fc: FunctionalConstraint) -> "DataSetBuilder":
        self._entries.append(DataSetEntry(self._ld_name, variable_name, fc))
        return self

    def end_data_set(self) -> "LogicalNodeBuilder":
        self._ln_builder._pending_datasets.append((self._name, self._ld_name, self._entries))
        return self._ln_builder


class LogicalNodeBuilder:
    def __init__(self, name: str, ld_builder: "LogicalDeviceBuilder"):
        self._name = name
        self._ld_builder = ld_builder
        self._pending_dos: list[tuple[str, str]] = []  # (name, cdc)
        self._pending_datasets: list[tuple[str, str, list]] = []
        self._pending_rcbs: list[ReportControl] = []

    def data_object(self, name: str, *, cdc: str) -> "LogicalNodeBuilder":
        self._pending_dos.append((name, cdc))
        return self

    def data_set(self, name: str) -> "DataSetBuilder":
        return DataSetBuilder(name, self._ld_builder._name, self)

    def brcb(self, name: str, *, dataset_name: str) -> "ReportControlBuilder":
        return ReportControlBuilder(name, buffered=True, dataset_name=dataset_name, ln_builder=self)

    def urcb(self, name: str, *, dataset_name: str) -> "ReportControlBuilder":
        return ReportControlBuilder(name, buffered=False, dataset_name=dataset_name, ln_builder=self)

    def end_logical_node(self) -> "LogicalDeviceBuilder":
        self._ld_builder._pending_lns.append(self)
        return self._ld_builder

    def _build_into(self, ld: LogicalDevice) -> None:
        ln = LogicalNode(self._name)
        for do_name, cdc in self._pending_dos:
            factory = CdcRegistry.get_factory(cdc)
            do = factory(do_name, ln)
            ln.add_data_object(do)
        for ds_name, ld_name, entries in self._pending_datasets:
            ds = DataSet(ln, ld_name, ds_name, list(entries))
            ln.add_data_set(ds)
        for rcb in self._pending_rcbs:
            ln.add_report_control(rcb)
        ld.add_logical_node(ln)


class LogicalDeviceBuilder:
    def __init__(self, name: str, ld_name: str, model_builder: "IedModelBuilder"):
        self._name = name
        self._ld_name = ld_name
        self._model_builder = model_builder
        self._pending_lns: list[LogicalNodeBuilder] = []

    def logical_node(self, name: str) -> LogicalNodeBuilder:
        return LogicalNodeBuilder(name, self)

    def end_logical_device(self) -> "IedModelBuilder":
        self._model_builder._pending_lds.append(self)
        return self._model_builder

    def _build_into(self, model: IedModel) -> None:
        ld = LogicalDevice(self._name, self._ld_name)
        for ln_builder in self._pending_lns:
            ln_builder._build_into(ld)
        model.add_logical_device(ld)


class IedModelBuilder:
    def __init__(self, name: str):
        self._name = name
        self._pending_lds: list[LogicalDeviceBuilder] = []

    def logical_device(self, name: str, *, ld_name: str) -> LogicalDeviceBuilder:
        return LogicalDeviceBuilder(name, ld_name, self)

    def build(self) -> IedModel:
        model = IedModel(self._name)
        for ld_builder in self._pending_lds:
            ld_builder._build_into(model)
        return model
