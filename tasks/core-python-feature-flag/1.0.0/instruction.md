# Repair feature-flag parsing

Implement the documented `parse_feature_flag` contract. Accept case-insensitive `true`, `1`,
`yes`, `on` and `false`, `0`, `no`, `off`, including surrounding whitespace. Return the supplied
default for `None`; raise `ValueError` for every other value. Do not modify `contract.txt`.
