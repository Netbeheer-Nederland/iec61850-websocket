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
    "secondSinceEpoch": 1720458123,
    "fractionOfSecond": 1234567,
    "timeQuality": {
        "leapSecondsKnown": False,
        "clockFailure": False,
        "clockNotSynchronized": False,
        "timeAccuracy": 3,
    },
}


def create_mv_do(name: str, parent):
    """
    Function used for creating a dataObject of type MV
    """
    do = DataObject(name, cdc="mv", parent=parent)

    da_mag = DataAttribute("mag", DataAttributeType.structure, FunctionalConstraint.mx, [], do)
    da_f = DataAttribute("f", DataAttributeType.float32, FunctionalConstraint.mx, 0.0, da_mag)
    da_quality = DataAttribute("q", DataAttributeType.quality, FunctionalConstraint.mx, default_quality, do)
    da_time_stamp = DataAttribute("t", DataAttributeType.timeStamp, FunctionalConstraint.mx, default_timestamp, do)

    da_units = DataAttribute("units", DataAttributeType.structure, FunctionalConstraint.cf, [], do)
    da_siUnit = DataAttribute("SIUnit", DataAttributeType.enumerated, FunctionalConstraint.cf, 0, da_units)
    da_multiplier = DataAttribute("multiplier", DataAttributeType.enumerated, FunctionalConstraint.cf, 0, da_units)
    da_units.add_data_attribute(da_siUnit)
    da_units.add_data_attribute(da_multiplier)

    da_mag.add_data_attribute(da_f)

    do.add_do_or_da(da_mag)
    do.add_do_or_da(da_quality)
    do.add_do_or_da(da_time_stamp)
    do.add_do_or_da(da_units)

    return do


def create_asg_do(name: str, parent):
    """
    Function used for creating a dataObject of type ASG
    """
    do = DataObject(name, cdc="asg", parent=parent)

    da_setMag = DataAttribute("setMag", DataAttributeType.structure, FunctionalConstraint.sp, [], do)
    da_f = DataAttribute("f", DataAttributeType.float32, FunctionalConstraint.sp, 0.0, da_setMag)

    da_units = DataAttribute("units", DataAttributeType.structure, FunctionalConstraint.cf, [], do)
    da_siUnit = DataAttribute("SIUnit", DataAttributeType.enumerated, FunctionalConstraint.cf, 0, da_units)
    da_multiplier = DataAttribute("multiplier", DataAttributeType.enumerated, FunctionalConstraint.cf, 0, da_units)
    da_units.add_data_attribute(da_siUnit)
    da_units.add_data_attribute(da_multiplier)

    da_setMag.add_data_attribute(da_f)

    da_dataNs = DataAttribute("dataNs", DataAttributeType.visString255, FunctionalConstraint.ex, "", do)

    do.add_do_or_da(da_setMag)
    do.add_do_or_da(da_dataNs)
    do.add_do_or_da(da_units)

    return do


def create_asg_do_custom(name: str, parent):
    """
    Function used for creating a dataObject of type ASG but not the standard
    """
    do = DataObject(name, cdc="asg", parent=parent)

    da_setMag = DataAttribute("setMag", DataAttributeType.structure, FunctionalConstraint.sp, [], do)
    da_f = DataAttribute("f", DataAttributeType.float32, FunctionalConstraint.sp, 0.0, da_setMag)
    da_val = DataAttribute("val", DataAttributeType.float32, FunctionalConstraint.sp, 0.0, da_setMag)

    da_units = DataAttribute("units", DataAttributeType.structure, FunctionalConstraint.cf, [], do)
    da_siUnit = DataAttribute("SIUnit", DataAttributeType.enumerated, FunctionalConstraint.cf, 0, da_units)
    da_multiplier = DataAttribute("multiplier", DataAttributeType.enumerated, FunctionalConstraint.cf, 0, da_units)
    da_units.add_data_attribute(da_siUnit)
    da_units.add_data_attribute(da_multiplier)

    da_setMag.add_data_attribute(da_f)
    da_setMag.add_data_attribute(da_val)

    da_dataNs = DataAttribute("dataNs", DataAttributeType.visString255, FunctionalConstraint.ex, "", do)

    do.add_do_or_da(da_setMag)
    do.add_do_or_da(da_dataNs)
    do.add_do_or_da(da_units)

    return do


def create_apc_do(name: str, parent):
    """
    Function used for creating a dataObject of type apc
    """
    do = DataObject(name, cdc="apc", parent=parent)

    # oper
    da_oper = DataAttribute("Oper", DataAttributeType.structure, FunctionalConstraint.co, [], do)

    da_cVal = DataAttribute("ctlVal", DataAttributeType.structure, FunctionalConstraint.co, [], da_oper)
    da_f = DataAttribute("f", DataAttributeType.float32, FunctionalConstraint.co, 0.0, da_cVal)

    da_cVal.add_data_attribute(da_f)
    da_oper.add_data_attribute(da_cVal)

    # origin
    da_origin = DataAttribute("origin", DataAttributeType.structure, FunctionalConstraint.co, [], da_oper)

    da_orCat = DataAttribute("orCat", DataAttributeType.enumerated, FunctionalConstraint.co, 0, da_origin)
    da_orIdent = DataAttribute("orIdent", DataAttributeType.octetString, FunctionalConstraint.co, bytes(), da_origin)

    da_origin.add_data_attribute(da_orCat)
    da_origin.add_data_attribute(da_orIdent)
    da_oper.add_data_attribute(da_origin)

    da_ctlNum = DataAttribute("ctlNum", DataAttributeType.int8u, FunctionalConstraint.co, 0, da_oper)
    da_T = DataAttribute("T", DataAttributeType.timeStamp, FunctionalConstraint.co, default_timestamp, da_oper)
    da_Test = DataAttribute("Test", DataAttributeType.boolean, FunctionalConstraint.co, False, da_oper)
    da_Check = DataAttribute(
        "Check",
        DataAttributeType.check,
        FunctionalConstraint.co,
        {"synchroCheck": False, "interlockCheck": False},
        da_oper,
    )

    da_syncroCheck = DataAttribute("synchroCheck", DataAttributeType.boolean, FunctionalConstraint.co, False, da_Check)
    da_interlockCheck = DataAttribute(
        "interlockCheck", DataAttributeType.boolean, FunctionalConstraint.co, False, da_Check
    )

    da_Check.add_data_attribute(da_syncroCheck)
    da_Check.add_data_attribute(da_interlockCheck)

    da_oper.add_data_attribute(da_ctlNum)
    da_oper.add_data_attribute(da_T)
    da_oper.add_data_attribute(da_Test)
    da_oper.add_data_attribute(da_Check)

    # mxVal
    da_mxVal = DataAttribute("mxVal", DataAttributeType.structure, FunctionalConstraint.mx, [], do)
    da_f = DataAttribute("f", DataAttributeType.float32, FunctionalConstraint.mx, 0.0, da_mxVal)
    da_mxVal.add_data_attribute(da_f)

    da_quality = DataAttribute("q", DataAttributeType.quality, FunctionalConstraint.mx, default_quality, do)
    da_quality.mms_value = copy.deepcopy(default_quality)
    da_time_stamp = DataAttribute("t", DataAttributeType.timeStamp, FunctionalConstraint.mx, default_timestamp, do)

    # units:
    da_units = DataAttribute("units", DataAttributeType.structure, FunctionalConstraint.cf, [], do)
    da_siUnit = DataAttribute("SIUnit", DataAttributeType.enumerated, FunctionalConstraint.cf, 0, da_units)
    da_multiplier = DataAttribute("multiplier", DataAttributeType.enumerated, FunctionalConstraint.cf, 0, da_units)

    da_units.add_data_attribute(da_siUnit)
    da_units.add_data_attribute(da_multiplier)

    da_ctlModel = DataAttribute("ctlModel", DataAttributeType.enumerated, FunctionalConstraint.cf, 1, do)

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
    do = DataObject(name, cdc="inc", parent=parent)

    # oper
    da_oper = DataAttribute("Oper", DataAttributeType.structure, FunctionalConstraint.co, [], do)

    da_cVal = DataAttribute("ctlVal", DataAttributeType.structure, FunctionalConstraint.co, [], da_oper)
    da_f = DataAttribute("f", DataAttributeType.float32, FunctionalConstraint.co, 0.0, da_cVal)

    da_cVal.add_data_attribute(da_f)
    da_oper.add_data_attribute(da_cVal)

    # origin
    da_origin = DataAttribute("origin", DataAttributeType.structure, FunctionalConstraint.co, [], da_oper)

    da_orCat = DataAttribute("orCat", DataAttributeType.enumerated, FunctionalConstraint.co, 0, da_origin)
    da_orIdent = DataAttribute("orIdent", DataAttributeType.octetString, FunctionalConstraint.co, bytes(), da_origin)

    da_origin.add_data_attribute(da_orCat)
    da_origin.add_data_attribute(da_orIdent)
    da_oper.add_data_attribute(da_origin)

    da_ctlNum = DataAttribute("ctlNum", DataAttributeType.int8u, FunctionalConstraint.co, 0, da_oper)
    da_T = DataAttribute("T", DataAttributeType.timeStamp, FunctionalConstraint.co, default_timestamp, da_oper)
    da_Test = DataAttribute("Test", DataAttributeType.boolean, FunctionalConstraint.co, False, da_oper)
    da_Check = DataAttribute(
        "Check",
        DataAttributeType.check,
        FunctionalConstraint.co,
        {"synchroCheck": False, "interlockCheck": False},
        da_oper,
    )

    da_syncroCheck = DataAttribute("synchroCheck", DataAttributeType.boolean, FunctionalConstraint.co, False, da_Check)
    da_interlockCheck = DataAttribute(
        "interlockCheck", DataAttributeType.boolean, FunctionalConstraint.co, False, da_Check
    )

    da_Check.add_data_attribute(da_syncroCheck)
    da_Check.add_data_attribute(da_interlockCheck)

    da_oper.add_data_attribute(da_ctlNum)
    da_oper.add_data_attribute(da_T)
    da_oper.add_data_attribute(da_Test)
    da_oper.add_data_attribute(da_Check)

    da_stVal = DataAttribute("stVal", DataAttributeType.int32, FunctionalConstraint.st, 0, do)

    da_quality = DataAttribute("q", DataAttributeType.quality, FunctionalConstraint.st, default_quality, do)
    da_time_stamp = DataAttribute("t", DataAttributeType.timeStamp, FunctionalConstraint.st, default_timestamp, do)
    da_ctlModel = DataAttribute("ctlModel", DataAttributeType.enumerated, FunctionalConstraint.cf, 1, do)
    da_dataNs = DataAttribute("dataNs", DataAttributeType.visString255, FunctionalConstraint.ex, "", do)

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
    do = DataObject(name, cdc="ens", parent=parent)
    da_stVal = DataAttribute("stVal", DataAttributeType.enumerated, FunctionalConstraint.st, 0, do)
    da_quality = DataAttribute("q", DataAttributeType.quality, FunctionalConstraint.st, default_quality, do)
    da_time_stamp = DataAttribute("t", DataAttributeType.timeStamp, FunctionalConstraint.st, default_timestamp, do)

    do.add_do_or_da(da_stVal)
    do.add_do_or_da(da_quality)
    do.add_do_or_da(da_time_stamp)

    return do


def create_sps_do(name: str, parent):
    """
    Function used for creating a dataObject of type SPS
    """
    do = DataObject(name, cdc="sps", parent=parent)
    da_stVal = DataAttribute("stVal", DataAttributeType.enumerated, FunctionalConstraint.st, 0, do)
    da_quality = DataAttribute("q", DataAttributeType.quality, FunctionalConstraint.st, default_quality, do)
    da_time_stamp = DataAttribute("t", DataAttributeType.timeStamp, FunctionalConstraint.st, default_timestamp, do)

    do.add_do_or_da(da_stVal)
    do.add_do_or_da(da_quality)
    do.add_do_or_da(da_time_stamp)

    return do


def create_enc_do(name: str, parent):
    """
    Function used for creating a dataObject of type ENC
    """
    do = DataObject(name, cdc="enc", parent=parent)
    da_stVal = DataAttribute("stVal", DataAttributeType.enumerated, FunctionalConstraint.st, 0, do)
    da_quality = DataAttribute("q", DataAttributeType.quality, FunctionalConstraint.st, default_quality, do)
    da_time_stamp = DataAttribute("t", DataAttributeType.timeStamp, FunctionalConstraint.st, default_timestamp, do)
    da_ctlModel = DataAttribute("ctlModel", DataAttributeType.enumerated, FunctionalConstraint.cf, 0, do)

    do.add_do_or_da(da_stVal)
    do.add_do_or_da(da_quality)
    do.add_do_or_da(da_time_stamp)
    do.add_do_or_da(da_ctlModel)

    return do


def create_lpl_do(name: str, parent):
    """
    Function used for creating a dataObject of type LPL
    """
    do = DataObject(name, cdc="lpl", parent=parent)
    da_vendor = DataAttribute("vendor", DataAttributeType.visString255, FunctionalConstraint.dc, "", do)
    da_swRev = DataAttribute("swRev", DataAttributeType.visString255, FunctionalConstraint.dc, "", do)
    da_configRev = DataAttribute("configRev", DataAttributeType.visString255, FunctionalConstraint.dc, "", do)
    da_lnNs = DataAttribute("lnNs", DataAttributeType.visString255, FunctionalConstraint.ex, "", do)

    do.add_do_or_da(da_vendor)
    do.add_do_or_da(da_swRev)
    do.add_do_or_da(da_configRev)
    do.add_do_or_da(da_lnNs)

    return do


def create_dpl_do(name: str, parent):
    """
    Function used for creating a dataObject of type DPL
    """
    do = DataObject(name, cdc="dpl", parent=parent)
    da_vendor = DataAttribute("vendor", DataAttributeType.visString255, FunctionalConstraint.dc, "", do)
    da_hwRev = DataAttribute("hwRev", DataAttributeType.visString255, FunctionalConstraint.dc, "", do)
    da_swRev = DataAttribute("swRev", DataAttributeType.visString255, FunctionalConstraint.dc, "", do)
    da_serNum = DataAttribute("serNum", DataAttributeType.visString255, FunctionalConstraint.dc, "", do)
    da_model = DataAttribute("model", DataAttributeType.visString255, FunctionalConstraint.dc, "", do)
    da_location = DataAttribute("location", DataAttributeType.visString255, FunctionalConstraint.dc, "", do)

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

    da_cVal = DataAttribute("cVal", DataAttributeType.structure, FunctionalConstraint.mx, [], do)
    da_mag = DataAttribute("mag", DataAttributeType.structure, FunctionalConstraint.mx, [], da_cVal)
    da_f = DataAttribute("f", DataAttributeType.float32, FunctionalConstraint.mx, 0.0, da_mag)
    da_quality = DataAttribute("q", DataAttributeType.quality, FunctionalConstraint.mx, default_quality, do)
    da_time_stamp = DataAttribute("t", DataAttributeType.timeStamp, FunctionalConstraint.mx, default_timestamp, do)

    da_units = DataAttribute("units", DataAttributeType.structure, FunctionalConstraint.cf, [], do)
    da_siUnit = DataAttribute("SIUnit", DataAttributeType.enumerated, FunctionalConstraint.cf, 0, da_units)
    da_multiplier = DataAttribute("multiplier", DataAttributeType.enumerated, FunctionalConstraint.cf, 0, da_units)

    da_units.add_data_attribute(da_siUnit)
    da_units.add_data_attribute(da_multiplier)

    da_mag.add_data_attribute(da_f)
    da_cVal.add_data_attribute(da_mag)

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

    da_setVal = DataAttribute("setVal", DataAttributeType.int32, FunctionalConstraint.sp, 0, do)

    da_units = DataAttribute("units", DataAttributeType.structure, FunctionalConstraint.cf, [], do)
    da_siUnit = DataAttribute("SIUnit", DataAttributeType.enumerated, FunctionalConstraint.cf, 0, da_units)
    da_multiplier = DataAttribute("multiplier", DataAttributeType.enumerated, FunctionalConstraint.cf, 0, da_units)

    da_units.add_data_attribute(da_siUnit)
    da_units.add_data_attribute(da_multiplier)

    da_dataNs = DataAttribute("dataNs", DataAttributeType.visString255, FunctionalConstraint.ex, "", do)

    do.add_do_or_da(da_setVal)
    do.add_do_or_da(da_units)
    do.add_do_or_da(da_dataNs)

    return do


def create_wye_do(name: str, parent):
    """
    Function used for creating a dataObject of type WYE
    """
    do = DataObject(name, cdc="wye", parent=parent)
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
    do = DataObject(name, cdc="del", parent=parent)
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
        "secondSinceEpoch": int(now.timestamp()),
        "fractionOfSecond": now.microsecond * 10,
        "timeQuality": {
            "leapSecondsKnown": False,
            "clockFailure": False,
            "clockNotSynchronized": False,
            "timeAccuracy": 3,
        },
    }
    return timestamp
