import pytest
from datetime import datetime, timezone
from backend.models import Tilt, Device

def test_tilt_model_has_paired_field():
    """Test that Tilt model includes paired field with default False."""
    tilt = Tilt(
        id="tilt-red",
        color="RED",
        beer_name="Test Beer",
        paired=False
    )
    assert hasattr(tilt, 'paired')
    assert tilt.paired is False

def test_device_model_has_paired_field():
    """Test that Device model includes paired field with default False."""
    device = Device(
        id="tilt-blue",
        device_type="tilt",
        name="Blue Tilt",
        paired=False
    )
    assert hasattr(device, 'paired')
    assert device.paired is False
