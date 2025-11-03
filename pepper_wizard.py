#!/usr/bin/env python

import sys

# This allows us to run the script from the root of the project
# while keeping the modular structure.
from pepper_wizard.main import main

if __name__ == "__main__":
    # We need to add the current directory to the path to allow the import to work
    sys.path.insert(0, '.')
    main()