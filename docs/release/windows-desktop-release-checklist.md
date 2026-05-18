# Windows Desktop Release Checklist

## Build-Time
- [ ] Confirm `<version>` matches `apps/local-web/desktop/package.json`.
- [ ] Verify `scheduler.plan_review` is present in the bundled `rag-core` manifest.
- [ ] Confirm release artifacts do not include `research/memory_rl/outputs*` directories.
- [ ] `npm run test:prepare-release`
- [ ] `npm run test:release-local`
- [ ] `npm run release:local`
- [ ] `apps/local-web/desktop/.release-output/<version>/` contains:
  - [ ] `AIMemoryCard-<version>-x64-setup.msi`
  - [ ] `AIMemoryCard-<version>-x64-portable.zip`
  - [ ] `AIMemoryCard-<version>-runtime-manifest.json`
  - [ ] `AIMemoryCard-<version>-SHA256SUMS.txt`

## Run-Time
- [ ] complete [windows-clean-machine-smoke-test.md](./windows-clean-machine-smoke-test.md)
- [ ] Verify traditional scheduling works with no AI provider configured.
- [ ] Verify AI/RL scheduler mode falls back to SM-2 v3 when the plugin runtime is unavailable.
- [ ] upload a GitHub draft release following [windows-github-release-manual.md](./windows-github-release-manual.md)
- [ ] publish only after smoke checks pass
