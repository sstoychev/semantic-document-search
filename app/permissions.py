# Permission bitmask constants.
#
# Checking: (user_permissions & PERM_X) == PERM_X
#
# PERM_UPDATE intentionally equals (PERM_READ | PERM_CREATE) so that the
# update operation requires a user to have both read and create capabilities.

PERM_READ = 1    # 0b0001  — always granted to every authenticated user
PERM_CREATE = 2  # 0b0010
PERM_UPDATE = 3  # 0b0011  — requires PERM_READ + PERM_CREATE
PERM_DELETE = 4  # 0b0100

PERM_ALL = 0xFF  # admin shorthand — covers every present and future bit


def check_permission(user_permissions: int, required: int) -> bool:
    """Return True if *user_permissions* satisfies *required* (bitmask AND)."""
    return (user_permissions & required) == required
