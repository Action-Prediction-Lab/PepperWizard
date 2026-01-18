import sys
import os
import unittest
from pathlib import Path

# Ensure we can import pepper_wizard no matter where we are
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from pepper_wizard.config import load_config, Config

class TestConfigLoading(unittest.TestCase):
    def test_config_loads_successfully(self):
        """Verify that the configuration loads without error and contains data."""
        print("\nTesting Config Loading...")
        try:
            c = load_config()
            self.assertIsInstance(c, Config)
            self.assertTrue(c.animations, "Animations dict should not be empty")
            self.assertTrue(c.quick_responses, "Quick responses dict should not be empty")
            self.assertTrue(c.emoticon_map, "Emoticon map should not be empty")
            print("Config loaded successfully with valid data.")
        except Exception as e:
            self.fail(f"Config loading failed with exception: {e}")

if __name__ == "__main__":
    unittest.main()
