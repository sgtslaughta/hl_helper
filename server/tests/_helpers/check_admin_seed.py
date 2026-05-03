"""CI helper: assert bootstrap-admin migration created the expected user + binding."""
from __future__ import annotations

import argparse
import sys
from typing import Any

from sqlalchemy import create_engine, text


def main() -> int:
    """Check that admin user and global binding exist in the database."""
    parser = argparse.ArgumentParser(
        description="Verify bootstrap-admin migration seeded correctly"
    )
    parser.add_argument("--db-url", required=True, help="Database URL")
    parser.add_argument("--email", required=True, help="Expected admin email")
    args = parser.parse_args()

    # Create engine for the given DB URL
    engine = create_engine(args.db_url)

    try:
        with engine.connect() as conn:
            # Check user exists with the given email
            user_rows: Any = conn.execute(
                text("SELECT id FROM users WHERE email = :email"),
                {"email": args.email},
            ).fetchall()

            if len(user_rows) != 1:
                print(
                    f"FAIL: expected 1 user with email={args.email}, "
                    f"found {len(user_rows)}",
                    file=sys.stderr,
                )
                return 1

            user_id = user_rows[0][0]

            # Get admin role ID
            admin_role_result: Any = conn.execute(
                text("SELECT id FROM roles WHERE name = 'admin'")
            ).scalar()

            if not admin_role_result:
                print(
                    "FAIL: admin role not found in database",
                    file=sys.stderr,
                )
                return 1

            admin_role_id = admin_role_result

            # Check binding exists for this user with admin role and global scope
            binding_rows: Any = conn.execute(
                text(
                    """
                    SELECT id FROM bindings
                    WHERE principal_id = :pid
                      AND principal_type = 'user'
                      AND role_id = :rid
                      AND scope_kind = 'global'
                    """
                ),
                {"pid": user_id, "rid": admin_role_id},
            ).fetchall()

            if len(binding_rows) != 1:
                print(
                    f"FAIL: expected 1 admin binding for user, "
                    f"found {len(binding_rows)}",
                    file=sys.stderr,
                )
                return 1

            binding_id = binding_rows[0][0]
            print(
                f"PASS: admin {args.email} seeded with global binding {binding_id}"
            )
            return 0
    finally:
        engine.dispose()


if __name__ == "__main__":
    sys.exit(main())
