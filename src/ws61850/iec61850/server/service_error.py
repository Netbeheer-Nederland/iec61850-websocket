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


class ServiceStatusKind(Enum):
    noError = 0
    instanceNotAvailable = 1
    instanceInUse = 2
    accessViolation = 3
    accessNotAllowedInCurrentState = 4
    parameterValueInappropriate = 5
    parameterValueInconsistent = 6
    classNotSupported = 7
    instanceLockedByOtherClient = 8
    controlMustBeSelected = 9
    typeConflict = 10
    failedDueToCommunicationsConstraint = 11
    failedDueToServerConstraint = 12
