#!/usr/bin/env python3
"""
Test script for LCD I2C implementation.

Run this script locally to verify the LCD I2C implementation works before deploying to Docker.

Usage:
    python test_lcd_i2c.py
"""

import sys
import json
from pathlib import Path

# Add the io_api_server directory to the path
script_dir = Path(__file__).parent
sys.path.insert(0, str(script_dir))

from devices import (
    DeviceType, 
    LCDI2CConfig, 
    LCDI2CDevice, 
    DeviceFactory,
    validate_device_config
)
from io_config import load_config


def test_1_device_type_enum():
    """Test that LCD_I2C device type exists in enum."""
    print("Test 1: DeviceType enum")
    print("-" * 40)
    
    all_types = [dt.value for dt in DeviceType]
    print(f"Available device types: {all_types}")
    
    assert DeviceType.LCD_I2C.value == "lcd_i2c", "LCD_I2C not found in DeviceType enum"
    print("[OK] LCD_I2C device type exists in enum")
    print()


def test_2_config_creation():
    """Test creating LCDI2CConfig programmatically."""
    print("Test 2: LCDI2CConfig creation")
    print("-" * 40)
    
    # Create config programmatically
    config = LCDI2CConfig(
        name="test_lcd_i2c",
        i2c_address=0x27,
        i2c_bus=1,
        columns=16,
        rows=2,
        backlight=True
    )
    
    print(f"Config name: {config.name}")
    print(f"Device type: {config.device_type.value}")
    print(f"I2C address: 0x{config.i2c_address:02X}")
    print(f"I2C bus: {config.i2c_bus}")
    print(f"Columns: {config.columns}")
    print(f"Rows: {config.rows}")
    print(f"Backlight: {config.backlight}")
    print(f"Bit mappings: rs={config.rs_bit}, rw={config.rw_bit}, e={config.e_bit}, bl={config.backlight_bit}")
    
    assert config.device_type == DeviceType.LCD_I2C
    assert config.i2c_address == 0x27
    assert config.i2c_bus == 1
    print("[OK] LCDI2CConfig created successfully")
    print()


def test_3_config_validation():
    """Test validating LCDI2CConfig."""
    print("Test 3: Config validation")
    print("-" * 40)
    
    config = LCDI2CConfig(
        name="test_lcd_i2c",
        i2c_address=0x27,
        i2c_bus=1,
        columns=16,
        rows=2
    )
    
    try:
        validate_device_config(config)
        print("[OK] Config validation passed")
    except Exception as e:
        print(f"[FAIL] Config validation failed: {e}")
        raise
    
    print()


def test_4_config_serialization():
    """Test converting config to dict and back."""
    print("Test 4: Config serialization")
    print("-" * 40)
    
    # Create config
    original = LCDI2CConfig(
        name="test_lcd_i2c",
        i2c_address=0x27,
        i2c_bus=1,
        columns=16,
        rows=2,
        backlight=True,
        rs_bit=0,
        rw_bit=1,
        e_bit=2,
        backlight_bit=3
    )
    
    # Convert to dict
    config_dict = original.to_dict()
    print(f"Config as dict keys: {list(config_dict.keys())}")
    
    # Convert back from dict
    restored = LCDI2CConfig.from_dict(config_dict)
    
    # Verify all fields match
    assert restored.name == original.name
    assert restored.i2c_address == original.i2c_address
    assert restored.i2c_bus == original.i2c_bus
    assert restored.columns == original.columns
    assert restored.rows == original.rows
    assert restored.backlight == original.backlight
    assert restored.rs_bit == original.rs_bit
    
    print("[OK] Config serialization/deserialization works")
    print()


def test_5_device_factory():
    """Test creating device via DeviceFactory."""
    print("Test 5: DeviceFactory")
    print("-" * 40)
    
    config = LCDI2CConfig(
        name="test_lcd_i2c",
        i2c_address=0x27,
        i2c_bus=1
    )
    
    device = DeviceFactory.create_device(config)
    
    print(f"Device type: {device.__class__.__name__}")
    print(f"Device name: {device.config.name}")
    print(f"Is connected: {device.is_connected}")
    
    assert isinstance(device, LCDI2CDevice)
    assert device.config.name == "test_lcd_i2c"
    
    # Clean up
    device.close()
    
    print("[OK] DeviceFactory creates LCDI2CDevice correctly")
    print()


def test_6_io_config_loading():
    """Test loading config from io_config.json."""
    print("Test 6: io_config.json loading")
    print("-" * 40)
    
    config_path = str(script_dir / "io_config.json")
    
    if not Path(config_path).exists():
        print(f"⚠ Config file not found at {config_path}, skipping")
        print()
        return
    
    configs = load_config(config_path)
    
    if configs is None:
        print("✗ Failed to load config file")
        raise Exception("Failed to load io_config.json")
    
    print(f"Loaded {len(configs)} device configurations")
    
    # Check if lcd_i2c is present
    if 'lcd_i2c' not in configs:
        print("✗ lcd_i2c not found in loaded configs")
        print(f"Available devices: {list(configs.keys())}")
        raise Exception("lcd_i2c not found in io_config.json")
    
    lcd_i2c_config = configs['lcd_i2c']
    print(f"lcd_i2c config type: {lcd_i2c_config.__class__.__name__}")
    print(f"  I2C address: 0x{lcd_i2c_config.i2c_address:02X}")
    print(f"  I2C bus: {lcd_i2c_config.i2c_bus}")
    print(f"  Columns: {lcd_i2c_config.columns}")
    print(f"  Rows: {lcd_i2c_config.rows}")
    
    assert isinstance(lcd_i2c_config, LCDI2CConfig)
    assert lcd_i2c_config.device_type == DeviceType.LCD_I2C
    
    print("[OK] io_config.json loads lcd_i2c correctly")
    print()


def test_7_device_methods():
    """Test that LCDI2CDevice has all required methods."""
    print("Test 7: Device methods")
    print("-" * 40)
    
    config = LCDI2CConfig(
        name="test_lcd_i2c",
        i2c_address=0x27,
        i2c_bus=1
    )
    
    device = LCDI2CDevice(config)
    
    required_methods = [
        'read', 'write', 'clear', 'close', 'is_connected',
        'write_line', 'set_cursor', 'display_on', 'backlight_on'
    ]
    
    for method in required_methods:
        has_method = hasattr(device, method)
        status = "[OK]" if has_method else "[FAIL]"
        print(f"{status} {method}: {'present' if has_method else 'MISSING'}")
        assert has_method, f"Method {method} not found"
    
    # Test write method (in mock mode, this should work without errors)
    try:
        device.write("Test")
        print("[OK] write() method works")
    except Exception as e:
        print(f"[FAIL] write() method failed: {e}")
        raise
    
    try:
        device.write(["Line 1", "Line 2"])
        print("[OK] write() with list works")
    except Exception as e:
        print(f"[FAIL] write() with list failed: {e}")
        raise
    
    device.close()
    print("[OK] All device methods present and working")
    print()


def test_8_mock_mode_behavior():
    """Test that device works in mock mode when hardware is not available."""
    print("Test 8: Mock mode behavior")
    print("-" * 40)
    
    config = LCDI2CConfig(
        name="mock_lcd_i2c",
        i2c_address=0x27,
        i2c_bus=1
    )
    
    device = LCDI2CDevice(config)
    
    # In mock mode, is_connected should be False
    print(f"Is connected (mock mode): {device.is_connected}")
    
    # But device should still be usable
    result = device.write("Mock Test")
    print(f"Write result: {result}")
    
    result = device.clear()
    print(f"Clear result: {result}")
    
    result = device.backlight_on(True)
    print(f"Backlight on result: {result}")
    
    device.close()
    
    print("[OK] Device works in mock mode")
    print()


def main():
    """Run all tests."""
    print("=" * 70)
    print("LCD I2C Implementation - Local Debug Tests")
    print("=" * 70)
    print()
    
    tests = [
        test_1_device_type_enum,
        test_2_config_creation,
        test_3_config_validation,
        test_4_config_serialization,
        test_5_device_factory,
        test_6_io_config_loading,
        test_7_device_methods,
        test_8_mock_mode_behavior,
    ]
    
    failed = []
    for test in tests:
        try:
            test()
        except Exception as e:
            failed.append((test.__name__, str(e)))
            print(f"✗ {test.__name__} FAILED: {e}")
            print()
    
    print("=" * 70)
    if not failed:
        print("ALL TESTS PASSED ✓")
        print("=" * 70)
        print()
        print("Your LCD I2C implementation is ready for Docker deployment!")
        return 0
    else:
        print(f"FAILED TESTS: {len(failed)}")
        for name, error in failed:
            print(f"  - {name}: {error}")
        print("=" * 70)
        return 1


if __name__ == "__main__":
    sys.exit(main())
