"""
services/exceptions.py — Service-layer custom exceptions.
"""


class CollectionFailed(Exception):
    """Raised when cloud collector experiences a fatal credential, auth, or API listing failure."""

    pass
