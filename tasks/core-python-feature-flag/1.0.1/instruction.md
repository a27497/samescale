# Repair bounded window parsing

Implement `parse_window(value, limit)` for `start:end` integer windows. Surrounding whitespace is
allowed around both numbers and the colon. Require `0 <= start <= end <= limit`; reject malformed
input, signed values, and a negative limit with `ValueError`. Do not modify `contract.txt`.
