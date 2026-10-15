"""Related public invariant: generated xunit fixtures are hidden without -v.

This checks plain-module setup_module, beyond the issue's unittest.setUpClass example.
"""

import os
import subprocess
import sys
import tempfile
from pathlib import Path

with tempfile.TemporaryDirectory(prefix="public-fixture-probe-") as directory:
    source = Path(directory) / "test_public_module.py"
    source.write_text("def setup_module(): pass\ndef test_example(): pass\n")
    observed = subprocess.run(
        [
            sys.executable,
            "-m",
            "pytest",
            "--fixtures",
            "-q",
            "-p",
            "no:cacheprovider",
            "--confcutdir=" + directory,
            str(source),
        ],
        cwd="/tmp/repository",
        env=dict(os.environ, PYTEST_DISABLE_PLUGIN_AUTOLOAD="1"),
        capture_output=True,
        text=True,
        timeout=15,
        check=False,
    )
    assert observed.returncode == 0
    visible = any(
        line.startswith("xunit_setup_module_fixture_") for line in observed.stdout.splitlines()
    )
    print("generated_module_fixture_visible_without_verbose=" + str(visible))
    assert not visible
