"""Public requirement: Quantity(copy=True) preserves an existing float16 dtype."""

import numpy as np
from astropy import units as u

original = u.Quantity(np.array([1.0, 2.0], dtype=np.float16), u.m)
copied = u.Quantity(original, copy=True)
print("original_dtype=" + str(original.dtype) + "; copy_dtype=" + str(copied.dtype))
assert original.dtype == np.dtype("float16")
assert copied.dtype == original.dtype
assert copied is not original
assert copied.unit == original.unit
