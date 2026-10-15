import sys
import unittest
from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path

_SRC = Path(__file__).resolve().parents[1] / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

from harness_ccm_python.cli import main


class CliTest(unittest.TestCase):
    def test_help_without_command(self):
        output = StringIO()
        with redirect_stdout(output):
            code = main([])
        self.assertEqual(code, 2)
        self.assertIn("generate", output.getvalue())

    def test_generate_forwards_limit_validation(self):
        with self.assertRaises(SystemExit) as caught:
            main(
                [
                    "generate",
                    "examples/account-budgets.yaml",
                    "--limit",
                    "0",
                ]
            )
        self.assertIn("positive", str(caught.exception))


if __name__ == "__main__":
    unittest.main()
