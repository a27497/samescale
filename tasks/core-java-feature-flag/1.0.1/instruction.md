# Preserve repository failure causes

Fix `FeatureFlag.fetch`: reject a null or blank key before calling the repository. Return repository
values unchanged. Wrap `RepositoryException` in `ServiceException` with the original exception as
the direct cause, while allowing unrelated runtime exceptions to propagate unchanged. Preserve
`contract.txt`.
