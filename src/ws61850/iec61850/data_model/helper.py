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

import copy
import datetime

from ws61850.iec61850.data_model.ied_model import (
    DataAttribute,
    DataAttributeType,
    DataObject,
    FunctionalConstraint,
)

default_quality = {
    # 'detailQual' omitted (OPTIONAL)
    "validity": "good",  # must provide a value; choose from: 'good', 'invalid', 'questionable'
    "source": "process",  # choose from: 'process', 'substituted'
    "test": False,
    "operatorBlock": False,
}

default_timestamp = {
    "secondSinceEpoch": 1720458123,  # Example: some UTC time in seconds
    "fractionOfSecond": 1234567,  # Example: partial seconds (e.g., microseconds * 10)
    "timeQuality": {
        "leapSecondsKown": False,
        "clockFailure": False,
        "clockNotSynchronized": False,
        "timeAccuracy": 3,  # e.g., ±1 ms, depending on definition
    },
}


def create_mv_do(name: str, parent):
    """
    Function used for creating a dataObject of type MV
    """
    do = DataObject(name, 0, -1, cdc="mv", parent=parent)

    da_mag = DataAttribute("mag", 0, -1, DataAttributeType.structure, FunctionalConstraint.mx, 0, [], 0, do)
    da_f = DataAttribute("f", 0, -1, DataAttributeType.float32, FunctionalConstraint.mx, 0, 0.0, 0, da_mag)
    da_quality = DataAttribute(
        "q", 0, -1, DataAttributeType.quality, FunctionalConstraint.mx, 0, default_quality, 0, do
    )
    da_time_stamp = DataAttribute(
        "t", 0, -1, DataAttributeType.timeStamp, FunctionalConstraint.mx, 0, default_timestamp, 0, do
    )

    da_units = DataAttribute("units", 0, -1, DataAttributeType.structure, FunctionalConstraint.cf, 0, [], 0, do)
    da_siUnit = DataAttribute("SIUnit", 0, -1, DataAttributeType.enumerated, FunctionalConstraint.cf, 0, 0, 0, da_units)
    da_multiplier = DataAttribute(
        "multiplier", 0, -1, DataAttributeType.enumerated, FunctionalConstraint.cf, 0, 0, 0, da_units
    )
    da_units.add_dataAttribute(da_siUnit)
    da_units.add_dataAttribute(da_multiplier)

    da_mag.add_dataAttribute(da_f)

    do.add_do_or_da(da_mag)
    do.add_do_or_da(da_quality)
    do.add_do_or_da(da_time_stamp)
    do.add_do_or_da(da_units)

    return do


def create_asg_do(name: str, parent):
    """
    Function used for creating a dataObject of type ASG
    """
    do = DataObject(name, 0, -1, cdc="asg", parent=parent)

    da_setMag = DataAttribute("setMag", 0, -1, DataAttributeType.structure, FunctionalConstraint.sp, 0, [], 0, do)
    da_f = DataAttribute("f", 0, -1, DataAttributeType.float32, FunctionalConstraint.sp, 0, 0.0, 0, da_setMag)

    da_units = DataAttribute("units", 0, -1, DataAttributeType.structure, FunctionalConstraint.cf, 0, [], 0, do)
    da_siUnit = DataAttribute("SIUnit", 0, -1, DataAttributeType.enumerated, FunctionalConstraint.cf, 0, 0, 0, da_units)
    da_multiplier = DataAttribute(
        "multiplier", 0, -1, DataAttributeType.enumerated, FunctionalConstraint.cf, 0, 0, 0, da_units
    )
    da_units.add_dataAttribute(da_siUnit)
    da_units.add_dataAttribute(da_multiplier)

    da_setMag.add_dataAttribute(da_f)

    da_dataNs = DataAttribute("dataNs", 0, -1, DataAttributeType.visString255, FunctionalConstraint.ex, 0, "", 0, do)

    do.add_do_or_da(da_setMag)
    do.add_do_or_da(da_dataNs)
    do.add_do_or_da(da_units)

    return do


def create_asg_do_custom(name: str, parent):
    """
    Function used for creating a dataObject of type ASG but not the standard
    """
    do = DataObject(name, 0, -1, cdc="asg", parent=parent)

    da_setMag = DataAttribute("setMag", 0, -1, DataAttributeType.structure, FunctionalConstraint.sp, 0, [], 0, do)
    da_f = DataAttribute("f", 0, -1, DataAttributeType.float32, FunctionalConstraint.sp, 0, 0.0, 0, da_setMag)
    da_val = DataAttribute("val", 0, -1, DataAttributeType.float32, FunctionalConstraint.sp, 0, 0.0, 0, da_setMag)

    da_units = DataAttribute("units", 0, -1, DataAttributeType.structure, FunctionalConstraint.cf, 0, [], 0, do)
    da_siUnit = DataAttribute("SIUnit", 0, -1, DataAttributeType.enumerated, FunctionalConstraint.cf, 0, 0, 0, da_units)
    da_multiplier = DataAttribute(
        "multiplier", 0, -1, DataAttributeType.enumerated, FunctionalConstraint.cf, 0, 0, 0, da_units
    )
    da_units.add_dataAttribute(da_siUnit)
    da_units.add_dataAttribute(da_multiplier)

    da_setMag.add_dataAttribute(da_f)
    da_setMag.add_dataAttribute(da_val)

    da_dataNs = DataAttribute("dataNs", 0, -1, DataAttributeType.visString255, FunctionalConstraint.ex, 0, "", 0, do)

    do.add_do_or_da(da_setMag)
    do.add_do_or_da(da_dataNs)
    do.add_do_or_da(da_units)

    return do


def create_apc_do(name: str, parent):
    """
    Function used for creating a dataObject of type apc
    """
    do = DataObject(name, 0, -1, cdc="apc", parent=parent)

    # oper
    da_oper = DataAttribute("Oper", 0, -1, DataAttributeType.structure, FunctionalConstraint.co, 0, [], 0, do)

    da_cVal = DataAttribute("ctlVal", 0, -1, DataAttributeType.structure, FunctionalConstraint.co, 0, [], 0, da_oper)
    da_f = DataAttribute("f", 0, -1, DataAttributeType.float32, FunctionalConstraint.co, 0, 0.0, 0, da_cVal)

    da_cVal.add_dataAttribute(da_f)
    da_oper.add_dataAttribute(da_cVal)

    # origin
    da_origin = DataAttribute("origin", 0, -1, DataAttributeType.structure, FunctionalConstraint.co, 0, [], 0, da_oper)

    da_orCat = DataAttribute("orCat", 0, -1, DataAttributeType.enumerated, FunctionalConstraint.co, 0, 0, 0, da_origin)
    da_orIdent = DataAttribute(
        "orIdent", 0, -1, DataAttributeType.octetString, FunctionalConstraint.co, 0, bytes(), 0, da_origin
    )

    da_origin.add_dataAttribute(da_orCat)
    da_origin.add_dataAttribute(da_orIdent)
    da_oper.add_dataAttribute(da_origin)

    da_ctlNum = DataAttribute("ctlNum", 0, -1, DataAttributeType.int8u, FunctionalConstraint.co, 0, 0, 0, da_oper)
    da_T = DataAttribute(
        "T", 0, -1, DataAttributeType.timeStamp, FunctionalConstraint.co, 0, default_timestamp, 0, da_oper
    )
    da_Test = DataAttribute("Test", 0, -1, DataAttributeType.boolean, FunctionalConstraint.co, 0, False, 0, da_oper)
    da_Check = DataAttribute(
        "Check",
        0,
        -1,
        DataAttributeType.check,
        FunctionalConstraint.co,
        0,
        {"synchroCheck": False, "interlockCheck": False},
        0,
        da_oper,
    )

    da_syncroCheck = DataAttribute(
        "synchroCheck", 0, -1, DataAttributeType.boolean, FunctionalConstraint.co, 0, False, 0, da_Check
    )
    da_interlockCheck = DataAttribute(
        "interlockCheck", 0, -1, DataAttributeType.boolean, FunctionalConstraint.co, 0, False, 0, da_Check
    )

    da_Check.add_dataAttribute(da_syncroCheck)
    da_Check.add_dataAttribute(da_interlockCheck)

    da_oper.add_dataAttribute(da_ctlNum)
    da_oper.add_dataAttribute(da_T)
    da_oper.add_dataAttribute(da_Test)
    da_oper.add_dataAttribute(da_Check)

    # mxVal
    da_mxVal = DataAttribute("mxVal", 0, -1, DataAttributeType.structure, FunctionalConstraint.mx, 0, [], 0, do)
    da_f = DataAttribute("f", 0, -1, DataAttributeType.float32, FunctionalConstraint.mx, 0, 0.0, 0, da_mxVal)
    da_mxVal.add_dataAttribute(da_f)

    da_quality = DataAttribute(
        "q", 0, -1, DataAttributeType.quality, FunctionalConstraint.mx, 0, default_quality, 0, do
    )
    da_quality.mmsValue = copy.deepcopy(default_quality)
    da_time_stamp = DataAttribute(
        "t", 0, -1, DataAttributeType.timeStamp, FunctionalConstraint.mx, 0, default_timestamp, 0, do
    )
    # units:
    da_units = DataAttribute("units", 0, -1, DataAttributeType.structure, FunctionalConstraint.cf, 0, [], 0, do)
    da_siUnit = DataAttribute("SIUnit", 0, -1, DataAttributeType.enumerated, FunctionalConstraint.cf, 0, 0, 0, da_units)
    da_multiplier = DataAttribute(
        "multiplier", 0, -1, DataAttributeType.enumerated, FunctionalConstraint.cf, 0, 0, 0, da_units
    )

    da_units.add_dataAttribute(da_siUnit)
    da_units.add_dataAttribute(da_multiplier)

    da_ctlModel = DataAttribute("ctlModel", 0, -1, DataAttributeType.enumerated, FunctionalConstraint.cf, 0, 1, 0, do)

    do.add_do_or_da(da_oper)
    do.add_do_or_da(da_mxVal)
    do.add_do_or_da(da_quality)
    do.add_do_or_da(da_time_stamp)
    do.add_do_or_da(da_units)
    do.add_do_or_da(da_ctlModel)

    return do


def create_inc_do(name: str, parent):
    """
    Function used for creating a dataObject of type inc
    """
    do = DataObject(name, 0, -1, cdc="inc", parent=parent)

    # oper
    da_oper = DataAttribute("Oper", 0, -1, DataAttributeType.structure, FunctionalConstraint.co, 0, [], 0, do)

    da_cVal = DataAttribute("ctlVal", 0, -1, DataAttributeType.structure, FunctionalConstraint.co, 0, [], 0, da_oper)
    da_f = DataAttribute("f", 0, -1, DataAttributeType.float32, FunctionalConstraint.co, 0, 0.0, 0, da_cVal)

    da_cVal.add_dataAttribute(da_f)
    da_oper.add_dataAttribute(da_cVal)

    # origin
    da_origin = DataAttribute("origin", 0, -1, DataAttributeType.structure, FunctionalConstraint.co, 0, [], 0, da_oper)

    da_orCat = DataAttribute("orCat", 0, -1, DataAttributeType.enumerated, FunctionalConstraint.co, 0, 0, 0, da_origin)
    da_orIdent = DataAttribute(
        "orIdent", 0, -1, DataAttributeType.octetString, FunctionalConstraint.co, 0, bytes(), 0, da_origin
    )

    da_origin.add_dataAttribute(da_orCat)
    da_origin.add_dataAttribute(da_orIdent)
    da_oper.add_dataAttribute(da_origin)

    da_ctlNum = DataAttribute("ctlNum", 0, -1, DataAttributeType.int8u, FunctionalConstraint.co, 0, 0, 0, da_oper)
    da_T = DataAttribute(
        "T", 0, -1, DataAttributeType.timeStamp, FunctionalConstraint.co, 0, default_timestamp, 0, da_oper
    )
    da_Test = DataAttribute("Test", 0, -1, DataAttributeType.boolean, FunctionalConstraint.co, 0, False, 0, da_oper)
    da_Check = DataAttribute(
        "Check",
        0,
        -1,
        DataAttributeType.check,
        FunctionalConstraint.co,
        0,
        {"synchroCheck": False, "interlockCheck": False},
        0,
        da_oper,
    )

    da_syncroCheck = DataAttribute(
        "synchroCheck", 0, -1, DataAttributeType.boolean, FunctionalConstraint.co, 0, False, 0, da_Check
    )
    da_interlockCheck = DataAttribute(
        "interlockCheck", 0, -1, DataAttributeType.boolean, FunctionalConstraint.co, 0, False, 0, da_Check
    )

    da_Check.add_dataAttribute(da_syncroCheck)
    da_Check.add_dataAttribute(da_interlockCheck)

    da_oper.add_dataAttribute(da_ctlNum)
    da_oper.add_dataAttribute(da_T)
    da_oper.add_dataAttribute(da_Test)
    da_oper.add_dataAttribute(da_Check)

    # mxVal
    da_stVal = DataAttribute("stVal", 0, -1, DataAttributeType.int32, FunctionalConstraint.st, 0, 0, 0, do)

    da_quality = DataAttribute(
        "q", 0, -1, DataAttributeType.quality, FunctionalConstraint.st, 0, default_quality, 0, do
    )
    da_time_stamp = DataAttribute(
        "t", 0, -1, DataAttributeType.timeStamp, FunctionalConstraint.st, 0, default_timestamp, 0, do
    )
    da_ctlModel = DataAttribute("ctlModel", 0, -1, DataAttributeType.enumerated, FunctionalConstraint.cf, 0, 1, 0, do)
    da_dataNs = DataAttribute("dataNs", 0, -1, DataAttributeType.visString255, FunctionalConstraint.ex, 0, "", 0, do)

    do.add_do_or_da(da_oper)
    do.add_do_or_da(da_stVal)
    do.add_do_or_da(da_quality)
    do.add_do_or_da(da_time_stamp)
    do.add_do_or_da(da_ctlModel)
    do.add_do_or_da(da_dataNs)

    return do


def create_ens_do(name: str, parent):
    """
    Function used for creating a dataObject of type ENS
    """
    do = DataObject(name, 0, -1, cdc="ens", parent=parent)
    da_stVal = DataAttribute("stVal", 0, -1, DataAttributeType.enumerated, FunctionalConstraint.st, 0, 0, 0, do)
    da_quality = DataAttribute(
        "q", 0, -1, DataAttributeType.quality, FunctionalConstraint.st, 0, default_quality, 0, do
    )
    da_time_stamp = DataAttribute(
        "t", 0, -1, DataAttributeType.timeStamp, FunctionalConstraint.st, 0, default_timestamp, 0, do
    )

    do.add_do_or_da(da_stVal)
    do.add_do_or_da(da_quality)
    do.add_do_or_da(da_time_stamp)

    return do


def create_sps_do(name: str, parent):
    """
    Function used for creating a dataObject of type SPS
    """
    do = DataObject(name, 0, -1, cdc="sps", parent=parent)
    da_stVal = DataAttribute("stVal", 0, -1, DataAttributeType.enumerated, FunctionalConstraint.st, 0, 0, 0, do)
    da_quality = DataAttribute(
        "q", 0, -1, DataAttributeType.quality, FunctionalConstraint.st, 0, default_quality, 0, do
    )
    da_time_stamp = DataAttribute(
        "t", 0, -1, DataAttributeType.timeStamp, FunctionalConstraint.st, 0, default_timestamp, 0, do
    )
    # do.add_dataAttribute(da_stVal)
    # do.add_dataAttribute(da_quality)
    # do.add_dataAttribute(da_time_stamp)

    do.add_do_or_da(da_stVal)
    do.add_do_or_da(da_quality)
    do.add_do_or_da(da_time_stamp)

    return do


def create_enc_do(name: str, parent):
    """
    Function used for creating a dataObject of type ENC
    """
    do = DataObject(name, 0, -1, cdc="enc", parent=parent)
    da_stVal = DataAttribute("stVal", 0, -1, DataAttributeType.enumerated, FunctionalConstraint.st, 0, 0, 0, do)
    da_quality = DataAttribute(
        "q", 0, -1, DataAttributeType.quality, FunctionalConstraint.st, 0, default_quality, 0, do
    )
    da_time_stamp = DataAttribute(
        "t", 0, -1, DataAttributeType.timeStamp, FunctionalConstraint.st, 0, default_timestamp, 0, do
    )
    da_ctlModel = DataAttribute("ctlModel", 0, -1, DataAttributeType.enumerated, FunctionalConstraint.cf, 0, 0, 0, do)

    do.add_do_or_da(da_stVal)
    do.add_do_or_da(da_quality)
    do.add_do_or_da(da_time_stamp)
    do.add_do_or_da(da_ctlModel)

    return do


def create_lpl_do(name: str, parent):
    """
    Function used for creating a dataObject of type LPL
    """
    do = DataObject(name, 0, -1, cdc="lpl", parent=parent)
    da_vendor = DataAttribute("vendor", 0, -1, DataAttributeType.visString255, FunctionalConstraint.dc, 0, "", 0, do)
    da_swRev = DataAttribute("swRev", 0, -1, DataAttributeType.visString255, FunctionalConstraint.dc, 0, "", 0, do)
    da_configRev = DataAttribute(
        "configRev", 0, -1, DataAttributeType.visString255, FunctionalConstraint.dc, 0, "", 0, do
    )
    da_lnNs = DataAttribute("lnNs", 0, -1, DataAttributeType.visString255, FunctionalConstraint.ex, 0, "", 0, do)

    do.add_do_or_da(da_vendor)
    do.add_do_or_da(da_swRev)
    do.add_do_or_da(da_configRev)
    do.add_do_or_da(da_lnNs)

    return do


def create_dpl_do(name: str, parent):
    """
    Function used for creating a dataObject of type DPL
    """
    do = DataObject(name, 0, -1, cdc="dpl", parent=parent)
    da_vendor = DataAttribute("vendor", 0, -1, DataAttributeType.visString255, FunctionalConstraint.dc, 0, "", 0, do)
    da_hwRev = DataAttribute("hwRev", 0, -1, DataAttributeType.visString255, FunctionalConstraint.dc, 0, "", 0, do)
    da_swRev = DataAttribute("swRev", 0, -1, DataAttributeType.visString255, FunctionalConstraint.dc, 0, "", 0, do)
    da_serNum = DataAttribute("serNum", 0, -1, DataAttributeType.visString255, FunctionalConstraint.dc, 0, "", 0, do)
    da_model = DataAttribute("model", 0, -1, DataAttributeType.visString255, FunctionalConstraint.dc, 0, "", 0, do)
    da_location = DataAttribute(
        "location", 0, -1, DataAttributeType.visString255, FunctionalConstraint.dc, 0, "", 0, do
    )

    do.add_do_or_da(da_vendor)
    do.add_do_or_da(da_hwRev)
    do.add_do_or_da(da_swRev)
    do.add_do_or_da(da_serNum)
    do.add_do_or_da(da_model)
    do.add_do_or_da(da_location)

    return do


def create_cmv_do(name: str, parent):
    """
    Function used for creating a dataObject of type CMV
    """
    do = DataObject(name=name, parent=parent, cdc="cmv")

    da_cVal = DataAttribute("cVal", 0, -1, DataAttributeType.structure, FunctionalConstraint.mx, 0, [], 0, do)
    da_mag = DataAttribute("mag", 0, -1, DataAttributeType.structure, FunctionalConstraint.mx, 0, [], 0, da_cVal)
    da_f = DataAttribute("f", 0, -1, DataAttributeType.float32, FunctionalConstraint.mx, 0, 0.0, 0, da_mag)
    da_quality = DataAttribute(
        "q", 0, -1, DataAttributeType.quality, FunctionalConstraint.mx, 0, default_quality, 0, do
    )
    da_time_stamp = DataAttribute(
        "t", 0, -1, DataAttributeType.timeStamp, FunctionalConstraint.mx, 0, default_timestamp, 0, do
    )

    da_units = DataAttribute("units", 0, -1, DataAttributeType.structure, FunctionalConstraint.cf, 0, [], 0, do)
    da_siUnit = DataAttribute("SIUnit", 0, -1, DataAttributeType.enumerated, FunctionalConstraint.cf, 0, 0, 0, da_units)
    da_multiplier = DataAttribute(
        "multiplier", 0, -1, DataAttributeType.enumerated, FunctionalConstraint.cf, 0, 0, 0, da_units
    )

    da_units.add_dataAttribute(da_siUnit)
    da_units.add_dataAttribute(da_multiplier)

    da_mag.add_dataAttribute(da_f)
    da_cVal.add_dataAttribute(da_mag)

    do.add_do_or_da(da_cVal)
    do.add_do_or_da(da_quality)
    do.add_do_or_da(da_time_stamp)
    do.add_do_or_da(da_units)

    return do


def create_ing_do(name: str, parent):
    """
    Function used for creating a dataObject of type ING
    """
    do = DataObject(name=name, parent=parent, cdc="ing")

    da_setVal = DataAttribute("setVal", 0, -1, DataAttributeType.int32, FunctionalConstraint.sp, 0, 0, 0, do)

    da_units = DataAttribute("units", 0, -1, DataAttributeType.structure, FunctionalConstraint.cf, 0, [], 0, do)
    da_siUnit = DataAttribute("SIUnit", 0, -1, DataAttributeType.enumerated, FunctionalConstraint.cf, 0, 0, 0, da_units)
    da_multiplier = DataAttribute(
        "multiplier", 0, -1, DataAttributeType.enumerated, FunctionalConstraint.cf, 0, 0, 0, da_units
    )

    da_units.add_dataAttribute(da_siUnit)
    da_units.add_dataAttribute(da_multiplier)

    da_dataNs = DataAttribute("dataNs", 0, -1, DataAttributeType.visString255, FunctionalConstraint.ex, 0, "", 0, do)

    do.add_do_or_da(da_setVal)
    do.add_do_or_da(da_units)
    do.add_do_or_da(da_dataNs)

    return do


def create_wye_do(name: str, parent):
    """
    Function used for creating a dataObject of type WYE
    """
    do = DataObject(name, 0, -1, cdc="wye", parent=parent)
    do_phsA = create_cmv_do("phsA", do)
    do.add_do_or_da(do_phsA)

    do_phsB = create_cmv_do("phsB", do)
    do.add_do_or_da(do_phsB)

    do_phsC = create_cmv_do("phsC", do)
    do.add_do_or_da(do_phsC)

    return do


def create_del_do(name: str, parent):
    """
    Function used for creating a dataObject of type DEL
    """
    do = DataObject(name, 0, -1, cdc="del", parent=parent)
    do_phsAB = create_cmv_do("phsAB", do)
    do.add_do_or_da(do_phsAB)

    do_phsBC = create_cmv_do("phsBC", do)
    do.add_do_or_da(do_phsBC)

    do_phsCA = create_cmv_do("phsCA", do)
    do.add_do_or_da(do_phsCA)

    return do


def get_now_time():
    now = datetime.datetime.now()

    timestamp = {
        "secondSinceEpoch": int(now.timestamp()),  # UTC seconds since Unix epoch
        "fractionOfSecond": now.microsecond * 10,  # microseconds × 10
        "timeQuality": {
            "leapSecondsKown": False,
            "clockFailure": False,
            "clockNotSynchronized": False,
            "timeAccuracy": 3,  # Example value: ±1 ms
        },
    }
    return timestamp
