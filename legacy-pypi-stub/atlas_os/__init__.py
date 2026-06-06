"""Deprecated redirect package — ``atlas-os`` was renamed to ``eidetic-os``.

This package contains no functionality. It exists only so that
``pip install atlas-os`` keeps working: it depends on ``eidetic-os`` (the
renamed package) and raises a :class:`DeprecationWarning` on import to point
users at the new name. Install and use ``eidetic-os`` directly instead.
"""

import warnings

warnings.warn(
    "The 'atlas-os' package has been renamed to 'eidetic-os'. "
    "Please run 'pip install eidetic-os' as this legacy package is deprecated.",
    DeprecationWarning,
    stacklevel=2,
)

__all__: list[str] = []
