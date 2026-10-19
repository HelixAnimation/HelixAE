#!/usr/bin/env python3
"""Run the HelixAE regression tests.

Uses only the Python standard library so it runs on any dev machine
without Prism, Qt, or the vendored dependencies.
"""

import os
import sys
import unittest


def main():
    here = os.path.dirname(os.path.abspath(__file__))
    suite = unittest.TestLoader().discover(here, pattern="test_*.py")
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    return 0 if result.wasSuccessful() else 1


if __name__ == "__main__":
    sys.exit(main())
