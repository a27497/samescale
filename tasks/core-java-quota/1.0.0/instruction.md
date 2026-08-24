# Repair reservation transitions

Implement the `Quota` reservation state machine. A new reservation may be reserved once, then
either committed or cancelled. A cancelled or committed reservation is terminal. Invalid
transitions throw `IllegalStateException` without changing state. Preserve `contract.txt`.
