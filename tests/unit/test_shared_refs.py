# SPDX-FileCopyrightText: 2025 Netbeheer Nederland
# SPDX-License-Identifier: Apache-2.0
import pytest

from ws61850.shared.refs import build_fcd_ref


def test_returns_dict_with_ref_and_fc():
    result = build_fcd_ref("LD0/LLN0.HEALTH", "st")
    assert result == {"ref": "LD0/LLN0.HEALTH", "fc": "st"}


def test_ref_key_value():
    result = build_fcd_ref("LD0/MMXU1.TotW.mag.f", "mx")
    assert result["ref"] == "LD0/MMXU1.TotW.mag.f"


def test_fc_key_value():
    result = build_fcd_ref("LD0/LLN0.Mod", "cf")
    assert result["fc"] == "cf"


def test_arbitrary_fc():
    for fc in ("st", "mx", "cf", "dc", "co", "sp"):
        r = build_fcd_ref("LD0/LLN0.X", fc)
        assert r["fc"] == fc
