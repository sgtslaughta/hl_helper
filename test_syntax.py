#!/usr/bin/env python3
"""Quick syntax check for refactored files."""
import sys

files_to_check = [
    "server/app/api/app.py",
    "server/app/api/v1/audit.py",
    "server/app/api/v1/settings.py",
    "server/app/api/v1/roles.py",
    "server/app/api/v1/approvals.py",
    "server/app/api/v1/tokens.py",
    "server/app/api/v1/bindings.py",
    "server/app/api/v1/policies.py",
    "server/app/api/v1/groups.py",
    "server/app/api/v1/users.py",
    "server/tests/e2e/test_c2_user_story.py",
]

try:
    for fpath in files_to_check:
        print(f"Checking {fpath}...", end=" ")
        with open(fpath) as f:
            compile(f.read(), fpath, "exec")
        print("OK")
    print("\nAll files have valid syntax!")
    sys.exit(0)
except SyntaxError as e:
    print(f"SYNTAX ERROR: {e}")
    sys.exit(1)
except Exception as e:
    print(f"ERROR: {e}")
    sys.exit(1)
