# Repair HTTP header normalization

Implement `Settings.normalize`: return a new insertion-ordered map with lowercase trimmed names and
values whose spaces/tabs are collapsed and trimmed. Reject blank names, CR/LF in names or values,
and names that collide after normalization. Do not mutate the input; keep both classes and
`contract.txt`.
