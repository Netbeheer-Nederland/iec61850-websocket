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

from dataclasses import dataclass, asdict

from ws61850.iec61850.data_model.ied_model import IedModel


@dataclass
class ReasonForInclusionInLog:
    """
    Class to represent why a report is generated
    """
    dataChange: bool = False
    qualityChange: bool = False
    dataUpdate: bool = False
    integrity: bool = False
    generalInterrogation: bool = False
    applicationTrigger: bool = False

    def get_true_values_dict(self):
        return {k: v for k, v in asdict(self).items() if v is True}


timestamp_zero = {
    "secondSinceEpoch": 0,  # Example: some UTC time in seconds
    "fractionOfSecond": 0,  # Example: partial seconds (e.g., microseconds * 10)
    "timeQuality": {
        "leapSecondKnown": False,
        "clockFailure": False,
        "clockNotSynchronized": False,
        "timeAccuracy": 0  # e.g., ±1 ms, depending on definition
    }
}


class ServerReportControl:
    """
    Class used to represent a report control and its runtime variables
    """

    def __init__(self, rcb):
        self.rcb = rcb
        self.purge_buff = False
        self.entry_id = bytearray()
        self.resv = False
        self.seq_num = 0
        self.rsvdTimeSec = 0
        self.time_of_entry = timestamp_zero
        self.owner = None
        self.rptEna: bool = False


def create_server_report_controls_list(ied: IedModel):
    """
    Function used for creating the list of serverReportControls when the ied tree is being created
    """
    return_list = []

    for ld in ied.logical_devices:
        for ln in ld.logical_nodes:
            for rcb in ln.rcbs:
                return_list.append(ServerReportControl(rcb))

    return return_list
