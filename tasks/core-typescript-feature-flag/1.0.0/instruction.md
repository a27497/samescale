# Repair feature-flag parsing

Implement `parseFeatureFlag`: accept case-insensitive true/1/yes/on and false/0/no/off with
surrounding whitespace, return the supplied default for `undefined`, and throw `TypeError` for any
other value. Preserve the typed API and `contract.txt`.
