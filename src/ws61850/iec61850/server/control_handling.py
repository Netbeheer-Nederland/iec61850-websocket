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

from enum import Enum


class ControlHandlerResult(Enum):
    FAILED = 0  # check or operation failed
    OK = 1  # check or operation was successful
    WAITING = 2  # check or operation is in progress


class ControlServiceStatusKind(Enum):
    unknown = 0
    notSupported = 1
    blockedBySwitchingHierarchy = 2
    selectFailed = 3
    invalidPosition = 4
    positionReached = 5
    parameterChangeInExecution = 6
    stepLimit = 7
    blockedByMode = 8
    blockedByProcess = 9
    blockedByInterlocking = 10
    blockedBySynchrocheck = 11
    commandAlreadyInExecution = 12
    blockedByHealth = 13
    oneOfNControl = 14
    abortionByCancel = 15
    timeLimitOver = 16
    abortionByTrip = 17
    objectNotSelected = 18
    objectAlreadySelected = 19
    noAccessAuthority = 20
    endedWithOvershoot = 21
    abortionDueToDeviation = 22
    abortionByCommunicationLoss = 23
    blockedByCommand = 24
    none = 25
    inconsistentParameters = 26
    lockedByOtherClient = 27
