"""Silence a spurious BLAS warning.

NumPy 2.x linked against Apple's Accelerate framework raises "divide by zero encountered
in matmul", "overflow encountered in matmul" and "invalid value encountered in matmul" on
matrix products whose inputs and outputs are entirely finite. It reproduces on
`numpy.random.randn(500000, 3) @ numpy.eye(3)`, so it is a property of the BLAS binding
rather than of any array this pipeline builds.

The filter is narrow on purpose: it names the three messages and the matmul origin, so a
genuine overflow anywhere else in the codebase still surfaces. `tests/test_numpy_compat.py`
asserts the warning is still spurious, and will fail loudly if a future NumPy starts
raising it for a real reason.
"""

from __future__ import annotations

import warnings

_MESSAGES = (
    "divide by zero encountered in matmul",
    "overflow encountered in matmul",
    "invalid value encountered in matmul",
)


def install() -> None:
    for message in _MESSAGES:
        warnings.filterwarnings("ignore", message=message, category=RuntimeWarning)
