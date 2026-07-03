import os
import subprocess
import sys


def test_seed_script_importability_and_helpers() -> None:
    code = """
from types import SimpleNamespace
from scripts import seed_dev_data

assert seed_dev_data.DEMO_USER_EMAIL == "demo@leafletpilot.com"
assert seed_dev_data.DEMO_MARKET_SLUG == "anadolu-market"

barcodes = [product.barcode for product in seed_dev_data.DEMO_PRODUCTS]
assert len(barcodes) == len(set(barcodes))

instance = SimpleNamespace(name="Old Name", is_active=True)
assert seed_dev_data.update_fields(instance, name="Old Name", is_active=True) is False
assert seed_dev_data.update_fields(instance, name="New Name", is_active=True) is True
assert instance.name == "New Name"
"""
    env = os.environ.copy()
    env["PYTHONDONTWRITEBYTECODE"] = "1"

    result = subprocess.run(
        [sys.executable, "-c", code],
        env=env,
        capture_output=True,
        text=True,
        timeout=15,
        check=False,
    )

    assert result.returncode == 0, result.stderr
