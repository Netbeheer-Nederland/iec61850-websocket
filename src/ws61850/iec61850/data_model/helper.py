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

    da_mag = DataAttribute(
        "mag", DataAttributeType.structure, FunctionalConstraint.mx, [], do
    )
    da_f = DataAttribute(
        "f", DataAttributeType.float32, FunctionalConstraint.mx, 0.0, da_mag
    )
    da_quality = DataAttribute(
        "q", DataAttributeType.quality, FunctionalConstraint.mx, default_quality, do
    )
    da_time_stamp = DataAttribute(
        "t", DataAttributeType.timeStamp, FunctionalConstraint.mx, default_timestamp, do
    )

    da_units = DataAttribute(
        "units", DataAttributeType.structure, FunctionalConstraint.cf, [], do
    )
    da_si_unit = DataAttribute(
        "SIUnit", DataAttributeType.enumerated, FunctionalConstraint.cf, 0, da_units
    )
    da_multiplier = DataAttribute(
        "multiplier", DataAttributeType.enumerated, FunctionalConstraint.cf, 0, da_units
    )
    da_units.add_data_attribute(da_si_unit)
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

    da_set_mag = DataAttribute(
        "setMag", DataAttributeType.structure, FunctionalConstraint.sp, [], do
    )
    da_f = DataAttribute(
        "f", DataAttributeType.float32, FunctionalConstraint.sp, 0.0, da_set_mag
    )

    da_units = DataAttribute(
        "units", DataAttributeType.structure, FunctionalConstraint.cf, [], do
    )
    da_si_unit = DataAttribute(
        "SIUnit", DataAttributeType.enumerated, FunctionalConstraint.cf, 0, da_units
    )
    da_multiplier = DataAttribute(
        "multiplier", DataAttributeType.enumerated, FunctionalConstraint.cf, 0, da_units
    )
    da_units.add_data_attribute(da_si_unit)
    da_units.add_data_attribute(da_multiplier)

    da_set_mag.add_data_attribute(da_f)

    da_data_ns = DataAttribute(
        "dataNs", DataAttributeType.visString255, FunctionalConstraint.ex, "", do
    )

    do.add_do_or_da(da_set_mag)
    do.add_do_or_da(da_data_ns)
    do.add_do_or_da(da_units)

    return do


def create_asg_do_custom(name: str, parent):
    """
    Function used for creating a dataObject of type ASG but not the standard
    """
    do = DataObject(name, cdc="asg", parent=parent)

    da_set_mag = DataAttribute(
        "setMag", DataAttributeType.structure, FunctionalConstraint.sp, [], do
    )
    da_f = DataAttribute(
        "f", DataAttributeType.float32, FunctionalConstraint.sp, 0.0, da_set_mag
    )
    da_val = DataAttribute(
        "val", DataAttributeType.float32, FunctionalConstraint.sp, 0.0, da_set_mag
    )

    da_units = DataAttribute(
        "units", DataAttributeType.structure, FunctionalConstraint.cf, [], do
    )
    da_si_unit = DataAttribute(
        "SIUnit", DataAttributeType.enumerated, FunctionalConstraint.cf, 0, da_units
    )
    da_multiplier = DataAttribute(
        "multiplier", DataAttributeType.enumerated, FunctionalConstraint.cf, 0, da_units
    )
    da_units.add_data_attribute(da_si_unit)
    da_units.add_data_attribute(da_multiplier)

    da_set_mag.add_data_attribute(da_f)
    da_set_mag.add_data_attribute(da_val)

    da_data_ns = DataAttribute(
        "dataNs", DataAttributeType.visString255, FunctionalConstraint.ex, "", do
    )

    do.add_do_or_da(da_set_mag)
    do.add_do_or_da(da_data_ns)
    do.add_do_or_da(da_units)

    return do


def create_apc_do(name: str, parent):
    """
    Function used for creating a dataObject of type apc
    """
    do = DataObject(name, cdc="apc", parent=parent)

    # oper
    da_oper = DataAttribute(
        "Oper", DataAttributeType.structure, FunctionalConstraint.co, [], do
    )

    da_c_val = DataAttribute(
        "ctlVal", DataAttributeType.structure, FunctionalConstraint.co, [], da_oper
    )
    da_f = DataAttribute(
        "f", DataAttributeType.float32, FunctionalConstraint.co, 0.0, da_c_val
    )

    da_c_val.add_data_attribute(da_f)
    da_oper.add_data_attribute(da_c_val)

    # origin
    da_origin = DataAttribute(
        "origin", DataAttributeType.structure, FunctionalConstraint.co, [], da_oper
    )

    da_or_cat = DataAttribute(
        "orCat", DataAttributeType.enumerated, FunctionalConstraint.co, 0, da_origin
    )
    da_or_ident = DataAttribute(
        "orIdent",
        DataAttributeType.octetString,
        FunctionalConstraint.co,
        b"",
        da_origin,
    )

    da_origin.add_data_attribute(da_or_cat)
    da_origin.add_data_attribute(da_or_ident)
    da_oper.add_data_attribute(da_origin)

    da_ctl_num = DataAttribute(
        "ctlNum", DataAttributeType.int8u, FunctionalConstraint.co, 0, da_oper
    )
    da_t = DataAttribute(
        "T",
        DataAttributeType.timeStamp,
        FunctionalConstraint.co,
        default_timestamp,
        da_oper,
    )
    da_test = DataAttribute(
        "Test", DataAttributeType.boolean, FunctionalConstraint.co, False, da_oper
    )
    da_check = DataAttribute(
        "Check",
        DataAttributeType.check,
        FunctionalConstraint.co,
        {"synchroCheck": False, "interlockCheck": False},
        da_oper,
    )

    da_syncro_check = DataAttribute(
        "synchroCheck",
        DataAttributeType.boolean,
        FunctionalConstraint.co,
        False,
        da_check,
    )
    da_interlock_check = DataAttribute(
        "interlockCheck",
        DataAttributeType.boolean,
        FunctionalConstraint.co,
        False,
        da_check,
    )

    da_check.add_data_attribute(da_syncro_check)
    da_check.add_data_attribute(da_interlock_check)

    da_oper.add_data_attribute(da_ctl_num)
    da_oper.add_data_attribute(da_t)
    da_oper.add_data_attribute(da_test)
    da_oper.add_data_attribute(da_check)

    # mxVal
    da_mx_val = DataAttribute(
        "mxVal", DataAttributeType.structure, FunctionalConstraint.mx, [], do
    )
    da_f = DataAttribute(
        "f", DataAttributeType.float32, FunctionalConstraint.mx, 0.0, da_mx_val
    )
    da_mx_val.add_data_attribute(da_f)

    da_quality = DataAttribute(
        "q", DataAttributeType.quality, FunctionalConstraint.mx, default_quality, do
    )
    da_quality.mms_value = copy.deepcopy(default_quality)
    da_time_stamp = DataAttribute(
        "t", DataAttributeType.timeStamp, FunctionalConstraint.mx, default_timestamp, do
    )

    # units:
    da_units = DataAttribute(
        "units", DataAttributeType.structure, FunctionalConstraint.cf, [], do
    )
    da_si_unit = DataAttribute(
        "SIUnit", DataAttributeType.enumerated, FunctionalConstraint.cf, 0, da_units
    )
    da_multiplier = DataAttribute(
        "multiplier", DataAttributeType.enumerated, FunctionalConstraint.cf, 0, da_units
    )

    da_units.add_data_attribute(da_si_unit)
    da_units.add_data_attribute(da_multiplier)

    da_ctl_model = DataAttribute(
        "ctlModel", DataAttributeType.enumerated, FunctionalConstraint.cf, 1, do
    )

    do.add_do_or_da(da_oper)
    do.add_do_or_da(da_mx_val)
    do.add_do_or_da(da_quality)
    do.add_do_or_da(da_time_stamp)
    do.add_do_or_da(da_units)
    do.add_do_or_da(da_ctl_model)

    return do


def create_inc_do(name: str, parent):
    """
    Function used for creating a dataObject of type inc
    """
    do = DataObject(name, cdc="inc", parent=parent)

    # oper
    da_oper = DataAttribute(
        "Oper", DataAttributeType.structure, FunctionalConstraint.co, [], do
    )

    da_c_val = DataAttribute(
        "ctlVal", DataAttributeType.structure, FunctionalConstraint.co, [], da_oper
    )
    da_f = DataAttribute(
        "f", DataAttributeType.float32, FunctionalConstraint.co, 0.0, da_c_val
    )

    da_c_val.add_data_attribute(da_f)
    da_oper.add_data_attribute(da_c_val)

    # origin
    da_origin = DataAttribute(
        "origin", DataAttributeType.structure, FunctionalConstraint.co, [], da_oper
    )

    da_or_cat = DataAttribute(
        "orCat", DataAttributeType.enumerated, FunctionalConstraint.co, 0, da_origin
    )
    da_or_ident = DataAttribute(
        "orIdent",
        DataAttributeType.octetString,
        FunctionalConstraint.co,
        b"",
        da_origin,
    )

    da_origin.add_data_attribute(da_or_cat)
    da_origin.add_data_attribute(da_or_ident)
    da_oper.add_data_attribute(da_origin)

    da_ctl_num = DataAttribute(
        "ctlNum", DataAttributeType.int8u, FunctionalConstraint.co, 0, da_oper
    )
    da_t = DataAttribute(
        "T",
        DataAttributeType.timeStamp,
        FunctionalConstraint.co,
        default_timestamp,
        da_oper,
    )
    da_test = DataAttribute(
        "Test", DataAttributeType.boolean, FunctionalConstraint.co, False, da_oper
    )
    da_check = DataAttribute(
        "Check",
        DataAttributeType.check,
        FunctionalConstraint.co,
        {"synchroCheck": False, "interlockCheck": False},
        da_oper,
    )

    da_syncro_check = DataAttribute(
        "synchroCheck",
        DataAttributeType.boolean,
        FunctionalConstraint.co,
        False,
        da_check,
    )
    da_interlock_check = DataAttribute(
        "interlockCheck",
        DataAttributeType.boolean,
        FunctionalConstraint.co,
        False,
        da_check,
    )

    da_check.add_data_attribute(da_syncro_check)
    da_check.add_data_attribute(da_interlock_check)

    da_oper.add_data_attribute(da_ctl_num)
    da_oper.add_data_attribute(da_t)
    da_oper.add_data_attribute(da_test)
    da_oper.add_data_attribute(da_check)

    da_st_val = DataAttribute(
        "stVal", DataAttributeType.int32, FunctionalConstraint.st, 0, do
    )

    da_quality = DataAttribute(
        "q", DataAttributeType.quality, FunctionalConstraint.st, default_quality, do
    )
    da_time_stamp = DataAttribute(
        "t", DataAttributeType.timeStamp, FunctionalConstraint.st, default_timestamp, do
    )
    da_ctl_model = DataAttribute(
        "ctlModel", DataAttributeType.enumerated, FunctionalConstraint.cf, 1, do
    )
    da_data_ns = DataAttribute(
        "dataNs", DataAttributeType.visString255, FunctionalConstraint.ex, "", do
    )

    do.add_do_or_da(da_oper)
    do.add_do_or_da(da_st_val)
    do.add_do_or_da(da_quality)
    do.add_do_or_da(da_time_stamp)
    do.add_do_or_da(da_ctl_model)
    do.add_do_or_da(da_data_ns)

    return do


def create_ens_do(name: str, parent):
    """
    Function used for creating a dataObject of type ENS
    """
    do = DataObject(name, cdc="ens", parent=parent)
    da_st_val = DataAttribute(
        "stVal", DataAttributeType.enumerated, FunctionalConstraint.st, 0, do
    )
    da_quality = DataAttribute(
        "q", DataAttributeType.quality, FunctionalConstraint.st, default_quality, do
    )
    da_time_stamp = DataAttribute(
        "t", DataAttributeType.timeStamp, FunctionalConstraint.st, default_timestamp, do
    )

    do.add_do_or_da(da_st_val)
    do.add_do_or_da(da_quality)
    do.add_do_or_da(da_time_stamp)

    return do


def create_sps_do(name: str, parent):
    """
    Function used for creating a dataObject of type SPS
    """
    do = DataObject(name, cdc="sps", parent=parent)
    da_st_val = DataAttribute(
        "stVal", DataAttributeType.enumerated, FunctionalConstraint.st, 0, do
    )
    da_quality = DataAttribute(
        "q", DataAttributeType.quality, FunctionalConstraint.st, default_quality, do
    )
    da_time_stamp = DataAttribute(
        "t", DataAttributeType.timeStamp, FunctionalConstraint.st, default_timestamp, do
    )

    do.add_do_or_da(da_st_val)
    do.add_do_or_da(da_quality)
    do.add_do_or_da(da_time_stamp)

    return do


def create_enc_do(name: str, parent):
    """
    Function used for creating a dataObject of type ENC
    """
    do = DataObject(name, cdc="enc", parent=parent)
    da_st_val = DataAttribute(
        "stVal", DataAttributeType.enumerated, FunctionalConstraint.st, 0, do
    )
    da_quality = DataAttribute(
        "q", DataAttributeType.quality, FunctionalConstraint.st, default_quality, do
    )
    da_time_stamp = DataAttribute(
        "t", DataAttributeType.timeStamp, FunctionalConstraint.st, default_timestamp, do
    )
    da_ctl_model = DataAttribute(
        "ctlModel", DataAttributeType.enumerated, FunctionalConstraint.cf, 0, do
    )

    do.add_do_or_da(da_st_val)
    do.add_do_or_da(da_quality)
    do.add_do_or_da(da_time_stamp)
    do.add_do_or_da(da_ctl_model)

    return do


def create_lpl_do(name: str, parent):
    """
    Function used for creating a dataObject of type LPL
    """
    do = DataObject(name, cdc="lpl", parent=parent)
    da_vendor = DataAttribute(
        "vendor", DataAttributeType.visString255, FunctionalConstraint.dc, "", do
    )
    da_sw_rev = DataAttribute(
        "swRev", DataAttributeType.visString255, FunctionalConstraint.dc, "", do
    )
    da_config_rev = DataAttribute(
        "configRev", DataAttributeType.visString255, FunctionalConstraint.dc, "", do
    )
    da_ln_ns = DataAttribute(
        "lnNs", DataAttributeType.visString255, FunctionalConstraint.ex, "", do
    )

    do.add_do_or_da(da_vendor)
    do.add_do_or_da(da_sw_rev)
    do.add_do_or_da(da_config_rev)
    do.add_do_or_da(da_ln_ns)

    return do


def create_dpl_do(name: str, parent):
    """
    Function used for creating a dataObject of type DPL
    """
    do = DataObject(name, cdc="dpl", parent=parent)
    da_vendor = DataAttribute(
        "vendor", DataAttributeType.visString255, FunctionalConstraint.dc, "", do
    )
    da_hw_rev = DataAttribute(
        "hwRev", DataAttributeType.visString255, FunctionalConstraint.dc, "", do
    )
    da_sw_rev = DataAttribute(
        "swRev", DataAttributeType.visString255, FunctionalConstraint.dc, "", do
    )
    da_ser_num = DataAttribute(
        "serNum", DataAttributeType.visString255, FunctionalConstraint.dc, "", do
    )
    da_model = DataAttribute(
        "model", DataAttributeType.visString255, FunctionalConstraint.dc, "", do
    )
    da_location = DataAttribute(
        "location", DataAttributeType.visString255, FunctionalConstraint.dc, "", do
    )

    do.add_do_or_da(da_vendor)
    do.add_do_or_da(da_hw_rev)
    do.add_do_or_da(da_sw_rev)
    do.add_do_or_da(da_ser_num)
    do.add_do_or_da(da_model)
    do.add_do_or_da(da_location)

    return do


def create_cmv_do(name: str, parent):
    """
    Function used for creating a dataObject of type CMV
    """
    do = DataObject(name=name, parent=parent, cdc="cmv")

    da_c_val = DataAttribute(
        "cVal", DataAttributeType.structure, FunctionalConstraint.mx, [], do
    )
    da_mag = DataAttribute(
        "mag", DataAttributeType.structure, FunctionalConstraint.mx, [], da_c_val
    )
    da_f = DataAttribute(
        "f", DataAttributeType.float32, FunctionalConstraint.mx, 0.0, da_mag
    )
    da_quality = DataAttribute(
        "q", DataAttributeType.quality, FunctionalConstraint.mx, default_quality, do
    )
    da_time_stamp = DataAttribute(
        "t", DataAttributeType.timeStamp, FunctionalConstraint.mx, default_timestamp, do
    )

    da_units = DataAttribute(
        "units", DataAttributeType.structure, FunctionalConstraint.cf, [], do
    )
    da_si_unit = DataAttribute(
        "SIUnit", DataAttributeType.enumerated, FunctionalConstraint.cf, 0, da_units
    )
    da_multiplier = DataAttribute(
        "multiplier", DataAttributeType.enumerated, FunctionalConstraint.cf, 0, da_units
    )

    da_units.add_data_attribute(da_si_unit)
    da_units.add_data_attribute(da_multiplier)

    da_mag.add_data_attribute(da_f)
    da_c_val.add_data_attribute(da_mag)

    do.add_do_or_da(da_c_val)
    do.add_do_or_da(da_quality)
    do.add_do_or_da(da_time_stamp)
    do.add_do_or_da(da_units)

    return do


def create_ing_do(name: str, parent):
    """
    Function used for creating a dataObject of type ING
    """
    do = DataObject(name=name, parent=parent, cdc="ing")

    da_set_val = DataAttribute(
        "setVal", DataAttributeType.int32, FunctionalConstraint.sp, 0, do
    )

    da_units = DataAttribute(
        "units", DataAttributeType.structure, FunctionalConstraint.cf, [], do
    )
    da_si_unit = DataAttribute(
        "SIUnit", DataAttributeType.enumerated, FunctionalConstraint.cf, 0, da_units
    )
    da_multiplier = DataAttribute(
        "multiplier", DataAttributeType.enumerated, FunctionalConstraint.cf, 0, da_units
    )

    da_units.add_data_attribute(da_si_unit)
    da_units.add_data_attribute(da_multiplier)

    da_data_ns = DataAttribute(
        "dataNs", DataAttributeType.visString255, FunctionalConstraint.ex, "", do
    )

    do.add_do_or_da(da_set_val)
    do.add_do_or_da(da_units)
    do.add_do_or_da(da_data_ns)

    return do


def create_wye_do(name: str, parent):
    """
    Function used for creating a dataObject of type WYE
    """
    do = DataObject(name, cdc="wye", parent=parent)
    do_phs_a = create_cmv_do("phsA", do)
    do.add_do_or_da(do_phs_a)

    do_phs_b = create_cmv_do("phsB", do)
    do.add_do_or_da(do_phs_b)

    do_phs_c = create_cmv_do("phsC", do)
    do.add_do_or_da(do_phs_c)

    return do


def create_del_do(name: str, parent):
    """
    Function used for creating a dataObject of type DEL
    """
    do = DataObject(name, cdc="del", parent=parent)
    do_phs_ab = create_cmv_do("phsAB", do)
    do.add_do_or_da(do_phs_ab)

    do_phs_bc = create_cmv_do("phsBC", do)
    do.add_do_or_da(do_phs_bc)

    do_phs_ca = create_cmv_do("phsCA", do)
    do.add_do_or_da(do_phs_ca)

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
