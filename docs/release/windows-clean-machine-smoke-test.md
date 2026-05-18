# Windows Clean-Machine Smoke Test

## Test Environment

- [ ] Use a Windows machine, VM, or Windows Sandbox without system Python installed.
- [ ] Before testing, check whether AI Memory Card is already installed or `%LOCALAPPDATA%\AIMemoryCard\stable\` already exists.
- [ ] Start from a fresh environment, or explicitly remove or note the pre-existing install/data before continuing.
- [ ] Start from release artifacts under `apps/local-web/desktop/.release-output/<version>/`.
- [ ] Do not launch from the source tree.

## MSI Path

- [ ] Confirm `apps/local-web/desktop/.release-output/<version>/AIMemoryCard-<version>-x64-setup.msi` is the installer being tested.
- [ ] Install the MSI.
- [ ] Launch AI Memory Card from the Start Menu or desktop shortcut.
- [ ] Confirm the app opens without a missing-Python error.
- [ ] Create a card or other small piece of test data.
- [ ] Close the app and relaunch it.
- [ ] Confirm the test data is still present.
- [ ] Launch the app a second time and confirm the existing window is focused instead of opening a duplicate.
- [ ] Confirm data is stored under `%LOCALAPPDATA%\AIMemoryCard\stable\`.
- [ ] Confirm `%LOCALAPPDATA%\AIMemoryCard\stable\logs\app.log` exists.

## ZIP Path

- [ ] Confirm `apps/local-web/desktop/.release-output/<version>/AIMemoryCard-<version>-x64-portable.zip` is the archive being tested.
- [ ] Extract the ZIP to a temporary folder.
- [ ] Launch `AI Memory Card.exe` from the extracted folder.
- [ ] Confirm the app opens without a missing-Python error.
- [ ] Create a card or other small piece of test data.
- [ ] Close the app and relaunch it from the extracted folder.
- [ ] Confirm the test data is still present.
- [ ] Launch the app a second time and confirm the existing window is focused instead of opening a duplicate.
- [ ] Delete the extracted folder.
- [ ] Confirm `%LOCALAPPDATA%\AIMemoryCard\stable\` still contains the user data created during the test.
- [ ] Re-extract the ZIP, relaunch the app, and confirm the same persisted data is reused.

## Scheduler Mode Smoke

- [ ] Open Settings -> Study.
- [ ] Confirm Scheduler mode defaults to Traditional scheduling.
- [ ] Start a review session and submit one card. Confirm the review completes without AI provider configuration.
- [ ] Switch Scheduler mode to AI/RL personalized scheduling.
- [ ] Submit one card with the bundled plugin unavailable or unconfigured. Confirm the review still completes through the traditional fallback.
- [ ] Confirm logs mention either `ai_rl` or `fallback after ai_rl scheduler error` without crashing the app.
