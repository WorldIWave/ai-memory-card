# Windows GitHub Release Manual

## Release Ritual

1. Confirm `<version>` from `apps/local-web/desktop/package.json`.
2. Create a GitHub draft release.
3. Choose the tag `vX.Y.Z`.
4. Set the release title to `AI Memory Card vX.Y.Z`.
5. Paste the release notes template below.
6. Attach these four files from `apps/local-web/desktop/.release-output/<version>/`:
   - `AIMemoryCard-<version>-x64-setup.msi`
   - `AIMemoryCard-<version>-x64-portable.zip`
   - `AIMemoryCard-<version>-runtime-manifest.json`
   - `AIMemoryCard-<version>-SHA256SUMS.txt`
7. Leave the release as a draft until [windows-clean-machine-smoke-test.md](./windows-clean-machine-smoke-test.md) passes.
8. Publish the release only after the smoke checks pass.

## Release Notes Template

```md
## Windows Downloads

- `AIMemoryCard-<version>-x64-setup.msi` - recommended for most Windows users
- `AIMemoryCard-<version>-x64-portable.zip` - portable build for users who do not want an installer

## Notes

- Data is stored under `%LOCALAPPDATA%\AIMemoryCard\stable\`
- MSI and ZIP share the same data directory
- Runtime manifest and checksums are attached for operator verification
```
