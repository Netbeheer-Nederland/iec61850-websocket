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

from dataclasses import dataclass
from enum import Enum


class IedModel:
    """
    This class is used to represent and IED and the objects inside it
    """

    def __init__(
        self,
        name: str = None,
        logical_devices=None,
        data_sets=None,
        rcbs=None,
        gse_cbs=None,
        sv_cbs=None,
        sgcbs=None,
        lcbs=None,
        logs=None,
        initializer=None,
    ):
        """
        This function Initializes the IedModel instance.
        :param name:
        :param logical_devices:
        :param data_sets:
        :param rcbs:
        :param gse_cbs:
        :param sv_cbs:
        :param sgcbs:
        :param lcbs:
        :param logs:
        :param initializer:
        """
        self.name = name
        self.logical_devices = logical_devices if logical_devices is not None else []
        self.data_sets = data_sets if data_sets is not None else []
        self.rcbs = rcbs if rcbs is not None else []
        self.gse_cbs = gse_cbs if gse_cbs is not None else []
        self.sv_cbs = sv_cbs if sv_cbs is not None else []
        self.sgcbs = sgcbs if sgcbs is not None else []
        self.lcbs = lcbs if lcbs is not None else []
        self.logs = logs if logs is not None else []
        self.initializer = initializer

    def add_logicalDevice(self, logical_device):
        """
        Adds logical devices to IED
        """
        logical_device.parent = self
        self.logical_devices.append(logical_device)

    def add_dataSet(self, data_set):
        """
        Adds datasets to IED
        """
        # data_set.parent = self
        self.data_sets.append(data_set)

    def add_reportControl(self, report_control):
        """
        Adds report controls to IED
        """
        self.rcbs.append(report_control)


class ModelNode:
    """
    Represents a node in the IED model structure
    """

    def __init__(self, model_type, name, parent=None):
        self.model_type = model_type  # corresponds to ModelNodeType enum
        self.name = name  # string
        self.parent = parent  # reference to another ModelNode or None
        # self.sibling = sibling         # reference to another ModelNode or None
        # self.first_child = first_child # reference to another ModelNode or None


class LogicalDevice(ModelNode):
    """
    Represents a Logical Device
    """

    def __init__(self, name, ldName, parent=None):
        # Pass the correct model type constant for LogicalDevice
        super().__init__(
            model_type=ModelNodeType.LogicalDeviceModelType,
            name=name,
            parent=parent,
            # sibling=sibling,
            # first_child=firstChild
        )
        self.ldName = ldName  # ldName when using functional naming
        self.logical_nodes = []

    def add_logical_node(self, ln):
        """
        Adds Logical Nodes to Logical Devices
        """
        ln.parent = self  # set parent reference
        self.logical_nodes.append(ln)


class LogicalNode(ModelNode):  # Corresponds to sLogicalNode
    """
    Represents a Logical Node
    """

    def __init__(self, name, parent=None):
        super().__init__(
            model_type=ModelNodeType.LogicalNodeModelType,
            name=name,
            parent=parent,
            # sibling=sibling,
            # first_child=firstChild
        )
        """
        Initializes the Logical Node instance
        """
        self.data_objects = []
        self.data_sets = []
        self.rcbs = []
        self.data_sets = []

    def add_dataObject(self, data_object):
        """
        Adds Data Objects to a Logical Node
        """
        data_object.parent = self  # set parent reference
        self.data_objects.append(data_object)

    def add_reportControl(self, rcb):
        """
        Adds Report Controls to a Logical Node
        """
        rcb.ln = self
        self.rcbs.append(rcb)

    def add_dataSet(self, data_set):
        """
        Adds Data Sets to a Logical Node
        """
        self.data_sets.append(data_set)

    def get_ref_until_ln(self):
        """
        Get the logical node item using an object reference
        """
        return_ref = self.name
        obj = self.parent
        while not isinstance(obj.parent, LogicalNode):
            return_ref = "." + obj.name + return_ref
            obj = obj.parent

        ln = obj.parent
        return_ref = ln.name + "." + return_ref
        ld = ln.parent
        return_ref = ld.name + "/" + return_ref
        return return_ref

    def get_objRef(self):
        """
        Function used for getting the object reference of a logical node
        """
        return self.get_ref_until_ln()


class DataObject(ModelNode):
    """
    Represents a Data Object
    """

    def __init__(self, name, elementCount=0, arrayIndex=-1, type_=None, parent=None, cdc=None):
        super().__init__(
            model_type=ModelNodeType.DataObjectModelType,
            name=name,
            parent=parent,
        )
        self.elementCount = elementCount  # > 0 if this is an array
        self.arrayIndex = arrayIndex  # > -1 if this is an array element
        self.type_ = type_
        self.cdc = cdc
        self.do_or_da = do_or_da = []

    def get_ref_until_ln(self):
        """
        Internal Function used for creating the object reference
        """
        return_ref = ""
        obj = self
        while not isinstance(obj, LogicalNode):
            return_ref = "." + obj.name + return_ref
            obj = obj.parent

        ln = obj
        return_ref = ln.name + return_ref
        ld = ln.parent
        return_ref = ld.name + "/" + return_ref
        return return_ref

    def get_objRef(self):
        """
        Function used for getting the object reference
        """
        return self.get_ref_until_ln()

    def add_do_or_da(self, item):
        """
        Function used for adding data object or attribute to a Data Object
        """
        self.do_or_da.append(item)

    def get_da_from_do_or_da_list(self):
        """
        Getting the list of Data Attributes from the list of data object or attributes
        """
        return [da for da in self.do_or_da if isinstance(da, DataAttribute)]

    def get_do_from_do_or_da_list(self):
        """
        Getting the list of Data Objects from the list of data object or attributes
        """
        return [do for do in self.do_or_da if isinstance(do, DataObject)]


class DataAttribute(ModelNode):
    """
    Class used for representing Data Attributes
    """

    def __init__(
        self,
        name,
        elementCount=0,
        arrayIndex=-1,
        type_=None,
        fc=None,
        triggerOptions=0,
        mmsValue=None,
        sAddr=0,
        parent=None,
    ):
        super().__init__(
            model_type=ModelNodeType.DataAttributeModelType,
            name=name,
            parent=parent,
            # sibling=sibling,
            # first_child=firstChild
        )
        """
        Function used for initializing Data Attributes
        """
        self.elementCount = elementCount  # > 0 if this is an array
        self.arrayIndex = arrayIndex  # > -1 if this is an array element
        self.fc = fc  # FunctionalConstraint
        self.type = type_  # DataAttributeType
        self.triggerOptions = triggerOptions  # Bit flags
        self.mmsValue = mmsValue  # Reference to an MmsValue object
        self.sAddr = sAddr  # Deprecated field
        self.data_attributes = []

    def add_dataAttribute(self, data_attribute):
        """
        Function for adding data attributes to a data attribute object
        """
        data_attribute.parent = self
        self.data_attributes.append(data_attribute)

    def get_ref_until_ln(self):
        """
        Function used for creating the object reference
        """
        return_ref = ""
        obj = self
        while not isinstance(obj, LogicalNode):
            return_ref = "." + obj.name + return_ref
            obj = obj.parent

        ln = obj
        return_ref = ln.name + return_ref
        ld = ln.parent
        return_ref = ld.name + "/" + return_ref
        return return_ref

    def get_objRef(self):
        """
        function used for getting the object reference of the data attribute
        """
        return self.get_ref_until_ln()


class FunctionalConstraint(Enum):
    """
    Class to represent the Functional Constraints
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
    or_ = 9
    bl = 10
    ex = 11
    lg = 12
    co = 13


class DataAttributeType(Enum):
    """
    Class used for representing data attribute type
    """

    boolean = 1
    int8 = 2
    int16 = 3
    int24 = 4
    int32 = 5
    int64 = 6
    int8u = 7
    # 8 is reserved
    int16u = 9
    int24u = 10
    int32u = 11
    float32 = 12
    octetString = 13  # expects Integer32 (size in bytes)
    visString64 = 14
    visString129 = 15
    visString255 = 16
    array = 17  # SEQUENCE { numberOfElements, elementType }
    structure = 18  # SEQUENCE OF StructComponent
    bitstring = 19  # expects Integer32 (size in bits)
    generalizedtime = 21
    binaryTime = 22
    quality = 23
    timeStamp = 24
    enumerated = 25
    check = 26


class ModelNodeType(Enum):
    """
    Class used for representing Model Node
    """

    LogicalDeviceModelType = 0
    LogicalNodeModelType = 1
    DataObjectModelType = 2
    DataAttributeModelType = 3


class ACSIClassKind(Enum):
    """
    Class used for representing ASCI Class Kind
    """

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


class DataSet:
    """
    Class used to represent data sets
    """

    def __init__(self, parent, logical_device_name, name, element_count=0, fcdas=None):
        """
        Function used for initializing Data Sets
        :param logical_device_name:
        :param name:
        :param element_count:
        :param fcdas:
        """
        self.logical_device_name = logical_device_name  # logical device instance name (string)
        self.name = name  # dataset name (string)
        self.element_count = element_count  # integer
        self.fcdas = fcdas if fcdas is not None else []
        self.parent = parent  # reference to LogicalNode

    def dataSet_addEntry(self, dataEntry):
        """
        Function used for adding entries to data set instance
        """
        self.fcdas.append(dataEntry)

    def get_objRef(self):
        """
        Function used for getting the object reference of Data Sets
        :return:
        """
        ln = self.parent
        return self.logical_device_name + "/" + ln.name + "." + self.name


class DataSetEntry:
    """
    Class representing data set entry
    """

    def __init__(
        self,
        logical_device_name,
        is_ld_name_dynamically_allocated=False,
        variable_name=None,
        index=-1,
        component_name=None,
        value=None,
        # sibling=None
        fc=None,
    ):
        """
        Function used for initializing Data Set Entry
        :param logical_device_name:
        :param is_ld_name_dynamically_allocated:
        :param variable_name:
        :param index:
        :param component_name:
        :param value:
        :param fc:
        """
        self.logical_device_name = logical_device_name  # string
        self.is_ld_name_dynamically_allocated = is_ld_name_dynamically_allocated  # bool
        self.variable_name = variable_name  # string
        self.index = index  # int
        self.component_name = component_name  # string
        self.value = value  # MmsValue instance or None
        self.fc = fc


@dataclass
class TrgOps:
    """
    Class used to represent trigger options
    """

    dchg: bool = False
    qchg: bool = False
    dupd: bool = False
    integrity: bool = False
    gi: bool = False


@dataclass
class OptFldsRCB:
    """
    Class used for representing optional fields
    """

    seqNum: bool
    timeStamp: bool
    dataSet: bool
    bufOvfl: bool
    configRef: bool
    entryID: bool
    dataRef: bool
    reasonCode: bool


class ReportControl:
    """
    Class used for representing report controls
    """

    def __init__(
        self,
        obj_ref: str,
        ln: LogicalNode,
        name: str,
        rptId: str,
        # rptEna : bool,
        buffered: bool,
        datasetName: str,
        confRev,
        trgOps,
        options,
        bufferedTime,
        intPeriod,
        client_reservation: bytearray,
        indexed,
    ):
        """
        function used for initializing Report Control Instance
        :param ln:
        :param name:
        :param rptId:
        :param rptEna:
        :param buffered:
        :param datasetName:
        :param confRev:
        :param trgOps:
        :param options:
        :param bufferedTime:
        :param intPeriod:
        :param client_reservation:
        """
        self.ln = ln
        self.name = name
        self.rptId = rptId
        self.buffered = buffered
        self.datasetName = datasetName
        self.confRev = confRev
        self.trgOps = trgOps
        self.options = options
        self.bufferedTime = bufferedTime
        self.intPeriod = intPeriod
        self.client_reservation = client_reservation
        self.indexed = indexed
        self.obj_ref = obj_ref
        # self.RCBTrkInst : RCBTrkInst = RCBTrkInst()
        self.client_connection = None
        self.gi: bool = False

    def get_objRef(self):
        ld = self.ln.parent
        obj_ref = ld.name + "/" + self.ln.name + "." + self.name

        return obj_ref


@dataclass
class RCBReportOptions:
    """
    Representation of ASN.1 RCBReportOptions ::= SEQUENCE {
        sequenceNumber     BOOLEAN,
        reportTimeStamp    BOOLEAN,
        reasonForInclusion BOOLEAN,
        dataSetName        BOOLEAN,
        dataReference      BOOLEAN,
        bufferOverFlow     BOOLEAN,
        entryID            BOOLEAN,
        confRevision       BOOLEAN,
        segmentation       BOOLEAN
    }
    """

    sequenceNumber: bool = False
    reportTimeStamp: bool = False
    reasonForInclusion: bool = False
    dataSetName: bool = False
    dataReference: bool = False
    bufferOverFlow: bool = False
    entryID: bool = False
    confRevision: bool = False
    segmentation: bool = False


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
