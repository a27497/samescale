import sys
from calculator import inclusive_sum

if sys.argv[1] == "empty":
    passed = inclusive_sum(1, 0) == 0
elif sys.argv[1] == "boundary":
    passed = inclusive_sum(1, 3) == 6
else:
    raise ValueError("unsupported check")
print("SAMESCALE_HOOK_EXIT_PROBE_V1")
raise SystemExit(0 if passed else 7)
