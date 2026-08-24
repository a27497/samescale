# Repair feature-flag parsing

Implement `FeatureFlag.parse`: accept case-insensitive true/1/yes/on and false/0/no/off with
surrounding whitespace, return the supplied default for `null`, and throw
`IllegalArgumentException` for any other value. Preserve `contract.txt`.
