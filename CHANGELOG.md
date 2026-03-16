# Changelog

All notable changes to DocuElevate will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

> **This CHANGELOG is automatically generated and maintained by [python-semantic-release](https://github.com/python-semantic-release/python-semantic-release). Do not edit it manually.**
> New entries are prepended automatically on every merge to `main` that triggers a version bump.

<!-- version list -->

## v0.150.7 (2026-03-16)

### Bug Fixes

- Resolve conflicts in mobile app config
  ([`89b3a6a`](https://github.com/christianlouis/DocuElevate/commit/89b3a6a3c05dfcd72c523db011e1b5a72f82aa74))

### Chores

- **i18n**: Auto-update translations via LLM
  ([`3cd895d`](https://github.com/christianlouis/DocuElevate/commit/3cd895d57ce70cd160c3085d2c30481187f7e2f8))

- **i18n**: Auto-update translations via LLM
  ([`872ff6c`](https://github.com/christianlouis/DocuElevate/commit/872ff6c53b874e1ca04a3009b4933cfc06365401))


## v0.150.6 (2026-03-16)

### Bug Fixes

- **mobile**: Handle iOS share sheet custom scheme URLs and add photo library picker
  ([`acfba4b`](https://github.com/christianlouis/DocuElevate/commit/acfba4b58cced43a939765692a1cd1798f1abe7f))

### Refactoring

- **mobile**: Address code review feedback
  ([`b6af39c`](https://github.com/christianlouis/DocuElevate/commit/b6af39c56700250a8a9d3118729df876e64142ab))


## v0.150.5 (2026-03-16)

### Bug Fixes

- **mobile**: Switch to remote appVersionSource for auto-incrementing build numbers
  ([`4c8926a`](https://github.com/christianlouis/DocuElevate/commit/4c8926a1fa32082a0e7aeb7d84bd667652695dab))


## v0.150.4 (2026-03-16)

### Bug Fixes

- **mobile**: Sync package-lock.json with package.json to fix npm ci failure
  ([`0e14471`](https://github.com/christianlouis/DocuElevate/commit/0e144710b56fd14a42e0089c1bcfdd9f3a7c5901))


## v0.150.3 (2026-03-16)

### Bug Fixes

- **tasks**: Dispatch per-user notifications on document processed/failed events
  ([`195c3c3`](https://github.com/christianlouis/DocuElevate/commit/195c3c344672357e09554996a1071e983fa92f8c))

### Refactoring

- **tasks**: Address code review feedback for notification dispatch
  ([`803331d`](https://github.com/christianlouis/DocuElevate/commit/803331d61f95b315efc880fb6964094c903be9b8))


## v0.150.2 (2026-03-16)

### Bug Fixes

- **mobile**: Rename notification sound for Android, add LSSupportsOpeningDocumentsInPlace, update
  deps
  ([`04c6823`](https://github.com/christianlouis/DocuElevate/commit/04c6823079ef544294205dba840676370f0cad22))

### Continuous Integration

- **mobile**: Add path filter and auto-submit to Apple for EAS workflow
  ([`bebeab3`](https://github.com/christianlouis/DocuElevate/commit/bebeab319139dc22e1ccaff5f284bbb80942138e))

### Documentation

- **changelog**: Update changelog [skip ci]
  ([`1c81678`](https://github.com/christianlouis/DocuElevate/commit/1c81678c9f09d8b3fa1b37c1c4a9805518498db5))


## Unreleased

### Continuous Integration

- **mobile**: Add path filter and auto-submit to Apple for EAS workflow
  ([`bebeab3`](https://github.com/christianlouis/DocuElevate/commit/bebeab319139dc22e1ccaff5f284bbb80942138e))


## v0.150.1 (2026-03-16)

### Bug Fixes

- **mobile**: IOS share sheet, empty files tab, and stuck upload status
  ([`4de6b43`](https://github.com/christianlouis/DocuElevate/commit/4de6b439ceddee2cb047771af594851fa2b10244))


## v0.150.0 (2026-03-16)

### Chores

- **docker**: Optimize image size with venv, slim builder, and dockerignore
  ([`718d82c`](https://github.com/christianlouis/DocuElevate/commit/718d82c815c693436708944b4396939f329a1ca7))

### Documentation

- **changelog**: Update changelog [skip ci]
  ([`b8df5ba`](https://github.com/christianlouis/DocuElevate/commit/b8df5ba253cea4ed51f3c36be7c5b1fda37c65b9))

### Features

- **ui**: Add View Document link from file detail page back to file view page
  ([`036210d`](https://github.com/christianlouis/DocuElevate/commit/036210dd454c21b1fa54ddd1c253aaf48687b35a))


## Unreleased

### Chores

- **docker**: Optimize image size with venv, slim builder, and dockerignore
  ([`718d82c`](https://github.com/christianlouis/DocuElevate/commit/718d82c815c693436708944b4396939f329a1ca7))


## v0.149.4 (2026-03-16)

### Bug Fixes

- **translation**: Fix apply_owner_filter called with wrong arguments
  ([`825f3cc`](https://github.com/christianlouis/DocuElevate/commit/825f3cc3a80305cd5ab31d0b61cf97a117b3c633))


## v0.149.3 (2026-03-16)

### Bug Fixes

- **migrations**: Guard migration 036 against missing user_profiles table
  ([`77df962`](https://github.com/christianlouis/DocuElevate/commit/77df9628c33ccff8756735a819911aeb7d32977b))


## v0.149.2 (2026-03-16)

### Bug Fixes

- **ui**: Replace emoji flags with cross-platform flag-icons CSS library
  ([`4619e6b`](https://github.com/christianlouis/DocuElevate/commit/4619e6b8a67ab4976ce4adf4a4b63e4475a32a78))


## v0.149.1 (2026-03-16)

### Bug Fixes

- **auth**: Address review comments - improve debug logging, use SimpleNamespace, fix session
  cleanup
  ([`9a25674`](https://github.com/christianlouis/DocuElevate/commit/9a256741d5a0fe3e9c52860a8f5ea9e1b30408d3))

- **auth**: Resolve Bearer token in get_current_owner_id for mobile API auth
  ([`15a9ed9`](https://github.com/christianlouis/DocuElevate/commit/15a9ed94357f72c59010d7773321cfb361bbf278))

- **security**: Clarify billing log message wording
  ([`7bd667e`](https://github.com/christianlouis/DocuElevate/commit/7bd667e271050db4d2e8db1935e51902268fbc08))

- **security**: Remove clear-text logging of sensitive data and fix Annotated+Depends pattern
  ([`b7a3b30`](https://github.com/christianlouis/DocuElevate/commit/b7a3b301a3883e90050d5b15f49f4d2bd69390fc))

- **test**: Update url_upload test mocks from requests to httpx
  ([`0444b14`](https://github.com/christianlouis/DocuElevate/commit/0444b14d874c6307e050a348232d8476cfdc774e))


## v0.149.0 (2026-03-16)

### Bug Fixes

- Register translate task in celery_worker and add setting metadata
  ([`0c10fcb`](https://github.com/christianlouis/DocuElevate/commit/0c10fcbafc5b6b708ac983d664384a42e0b0d456))

### Features

- **profile**: Expose default_document_language in profile API and UI
  ([`075a505`](https://github.com/christianlouis/DocuElevate/commit/075a5050855840e10155503517a239639f43a68d))

- **translation**: Add model, config, task, API, and UI for default document language translation
  ([`3a221a6`](https://github.com/christianlouis/DocuElevate/commit/3a221a62cd30900f4b0808cbda9c0bf37dbccdf4))


## v0.148.0 (2026-03-16)

### Documentation

- Improve docstring and comment clarity in extract_metadata_from_file
  ([`f2255f9`](https://github.com/christianlouis/DocuElevate/commit/f2255f9a1c28f138eae7836e9cf2df97f03b7b17))

### Features

- **tasks**: Extract and map embedded PDF metadata in upload_to_email
  ([`9d6bfde`](https://github.com/christianlouis/DocuElevate/commit/9d6bfde2882fe74356bef8b64fb79bfa99870f56))


## v0.147.3 (2026-03-16)

### Code Style

- Apply ruff auto-fix
  ([`ca2d023`](https://github.com/christianlouis/DocuElevate/commit/ca2d023d8130000fb82482fb8fbe0d7e218c94fb))

### Performance Improvements

- **onedrive**: Use async httpx for token refresh
  ([`8279795`](https://github.com/christianlouis/DocuElevate/commit/827979598eaeab765a1d24e6011deb26fc804b95))

- **onedrive**: Use async httpx for token refresh
  ([`2471921`](https://github.com/christianlouis/DocuElevate/commit/24719212042a65ed4a0d99776c6b3974ef97f0e8))

- **onedrive**: Use async httpx for token refresh
  ([`d1f64eb`](https://github.com/christianlouis/DocuElevate/commit/d1f64ebfba6bb353ea6f75e1535a42fd26a8fe0a))

- **onedrive**: Use async httpx for token refresh
  ([`7242f3c`](https://github.com/christianlouis/DocuElevate/commit/7242f3c168396aa5400fd46ad531ede93024b467))


## v0.147.2 (2026-03-16)

### Code Style

- Apply ruff auto-fix
  ([`46c4031`](https://github.com/christianlouis/DocuElevate/commit/46c403127641c1b5c729ff69ab5505efa5c9b54d))

### Documentation

- **changelog**: Update changelog [skip ci]
  ([`66fdb11`](https://github.com/christianlouis/DocuElevate/commit/66fdb11e39bc63f5a1d2b652649fd39d2a7e7469))

- **changelog**: Update changelog [skip ci]
  ([`0f31216`](https://github.com/christianlouis/DocuElevate/commit/0f312160bcb2e46e29c90dd055c4ebc9aaf01ad4))

- **changelog**: Update changelog [skip ci]
  ([`5734df2`](https://github.com/christianlouis/DocuElevate/commit/5734df2d5046158a23b987fdc4235d3f3f6b4042))


## Unreleased

### Code Style

- Apply ruff auto-fix
  ([`46c4031`](https://github.com/christianlouis/DocuElevate/commit/46c403127641c1b5c729ff69ab5505efa5c9b54d))

### Documentation

- **changelog**: Update changelog [skip ci]
  ([`0f31216`](https://github.com/christianlouis/DocuElevate/commit/0f312160bcb2e46e29c90dd055c4ebc9aaf01ad4))

- **changelog**: Update changelog [skip ci]
  ([`5734df2`](https://github.com/christianlouis/DocuElevate/commit/5734df2d5046158a23b987fdc4235d3f3f6b4042))


## Unreleased

### Code Style

- Apply ruff auto-fix
  ([`46c4031`](https://github.com/christianlouis/DocuElevate/commit/46c403127641c1b5c729ff69ab5505efa5c9b54d))

### Documentation

- **changelog**: Update changelog [skip ci]
  ([`5734df2`](https://github.com/christianlouis/DocuElevate/commit/5734df2d5046158a23b987fdc4235d3f3f6b4042))


## Unreleased


## v0.147.1 (2026-03-16)

### Bug Fixes

- Resolve test failures and mypy errors on main
  ([`c7ff177`](https://github.com/christianlouis/DocuElevate/commit/c7ff177e179b60a4b6adba7f5296522e6da4391f))

### Documentation

- **changelog**: Update changelog [skip ci]
  ([`dd7c8f0`](https://github.com/christianlouis/DocuElevate/commit/dd7c8f0342f00b80e83394d146e6bc51a3688687))

- **changelog**: Update changelog [skip ci]
  ([`4d4706e`](https://github.com/christianlouis/DocuElevate/commit/4d4706e078d661682326262000e70d7e56fb6d23))


## Unreleased

### Documentation

- **changelog**: Update changelog [skip ci]
  ([`4d4706e`](https://github.com/christianlouis/DocuElevate/commit/4d4706e078d661682326262000e70d7e56fb6d23))


## Unreleased


## v0.147.0 (2026-03-16)

### Code Style

- Apply ruff auto-fix
  ([`80a0ddc`](https://github.com/christianlouis/DocuElevate/commit/80a0ddcbfcd89c156d6cce65bb6275bdf35c061e))

### Documentation

- **changelog**: Update changelog [skip ci]
  ([`5e986cb`](https://github.com/christianlouis/DocuElevate/commit/5e986cb6d66c313753c7ce9cf69137c36b354ae8))

- **changelog**: Update changelog [skip ci]
  ([`8f8e11c`](https://github.com/christianlouis/DocuElevate/commit/8f8e11cffe5a6aaae47c9111bc6a95cb88ef6cd8))

### Features

- **config**: Add JSON structured logging and syslog forwarding for application logs
  ([`6da1e6f`](https://github.com/christianlouis/DocuElevate/commit/6da1e6fd816fea1dc0fa37c9ad42ce8cafed8c73))

- **config**: Add LOG_LEVEL setting and configure root logging at startup
  ([`18c49c6`](https://github.com/christianlouis/DocuElevate/commit/18c49c6b2d214fddefa2f954d57b0358fb4b5f72))

### Refactoring

- **main**: Move JSON formatter imports to module level per code review
  ([`df1fa51`](https://github.com/christianlouis/DocuElevate/commit/df1fa51800fb62862271fce4e0fff691f62c3333))

### Testing

- Add 500 error test for saved search deletion
  ([`ae9ed6e`](https://github.com/christianlouis/DocuElevate/commit/ae9ed6e9a703f8a80880d0b1cb421de3cf024cd3))


## Unreleased

### Code Style

- Apply ruff auto-fix
  ([`80a0ddc`](https://github.com/christianlouis/DocuElevate/commit/80a0ddcbfcd89c156d6cce65bb6275bdf35c061e))

### Documentation

- **changelog**: Update changelog [skip ci]
  ([`8f8e11c`](https://github.com/christianlouis/DocuElevate/commit/8f8e11cffe5a6aaae47c9111bc6a95cb88ef6cd8))

### Testing

- Add 500 error test for saved search deletion
  ([`ae9ed6e`](https://github.com/christianlouis/DocuElevate/commit/ae9ed6e9a703f8a80880d0b1cb421de3cf024cd3))


## Unreleased

### Code Style

- Apply ruff auto-fix
  ([`80a0ddc`](https://github.com/christianlouis/DocuElevate/commit/80a0ddcbfcd89c156d6cce65bb6275bdf35c061e))

### Testing

- Add 500 error test for saved search deletion
  ([`ae9ed6e`](https://github.com/christianlouis/DocuElevate/commit/ae9ed6e9a703f8a80880d0b1cb421de3cf024cd3))


## v0.146.0 (2026-03-16)

### Code Style

- Apply ruff auto-fix
  ([`522cefa`](https://github.com/christianlouis/DocuElevate/commit/522cefad935508fed32e194984726b0a10c99654))

- Apply ruff auto-fix
  ([`c76e513`](https://github.com/christianlouis/DocuElevate/commit/c76e51391b14eccbbe74f34ffadc89a477b58a64))

- Apply ruff auto-fix
  ([`cc2a07b`](https://github.com/christianlouis/DocuElevate/commit/cc2a07b090883f3cf2affea8a5e254a4163ce966))

- Apply ruff auto-fix
  ([`8bb6457`](https://github.com/christianlouis/DocuElevate/commit/8bb6457c65c177a13fd15de7a7b55e24eb39477e))

- Apply ruff auto-fix
  ([`275a5ad`](https://github.com/christianlouis/DocuElevate/commit/275a5ad6fa887ce3aa05d50787bd5da435735f26))

- Apply ruff auto-fix
  ([`ac35c5e`](https://github.com/christianlouis/DocuElevate/commit/ac35c5e6fa84f2b38cd333de75f202f13bf4c461))

- Apply ruff auto-fix
  ([`705c801`](https://github.com/christianlouis/DocuElevate/commit/705c801158394e7d6466f82485f8d872860653bb))

- Apply ruff auto-fix
  ([`0425d46`](https://github.com/christianlouis/DocuElevate/commit/0425d46c4440191cd410434ba64c1bc9cdb53cbb))

- Apply ruff auto-fix
  ([`b4118f6`](https://github.com/christianlouis/DocuElevate/commit/b4118f61622a35461af2c220d8a948ecb795e65b))

- Format app/database.py to fix CI failure
  ([`fbd4f83`](https://github.com/christianlouis/DocuElevate/commit/fbd4f837301deb208c7303553bca8facbae85ba6))

### Features

- Extract embedded PDF metadata using pypdf in upload_to_email
  ([`726e4df`](https://github.com/christianlouis/DocuElevate/commit/726e4dfdc47507dd08047a27f02c137ed3e7ecaf))

- Extract embedded PDF metadata using pypdf in upload_to_email
  ([`df64aec`](https://github.com/christianlouis/DocuElevate/commit/df64aece2c19215cf762b2ac62d476888cd21527))

### Performance Improvements

- Optimize dropbox token refresh by replacing blocking requests with httpx
  ([`84c6e1c`](https://github.com/christianlouis/DocuElevate/commit/84c6e1c5dd1a427c7f015e7461df59b889e66154))

- **api**: Optimize reorder_plans to prevent N+1 queries
  ([`d8372c6`](https://github.com/christianlouis/DocuElevate/commit/d8372c6fb83b09ce8d61bc8a870c921372a9d27a))

- **duplicates**: Fix N+1 query in group listing
  ([`e4e3ac4`](https://github.com/christianlouis/DocuElevate/commit/e4e3ac40771bdd8459cc0876d9d49be441df51a4))

### Testing

- Add missing error tests for updating saved searches
  ([`d18c05c`](https://github.com/christianlouis/DocuElevate/commit/d18c05c36dc4324dd24e20e5344bca9c038bbf73))

- Improve coverage for notify_settings_updated error handling
  ([`d8906ae`](https://github.com/christianlouis/DocuElevate/commit/d8906aece0045aed9dcd0f0cf1891970c7cb00e8))


## v0.145.3 (2026-03-16)

### Bug Fixes

- **tests**: Resolve ruff import sorting issue in benchmark test
  ([`fa9b037`](https://github.com/christianlouis/DocuElevate/commit/fa9b037d5a2a67f9115a1bddf0f98ba9020cefd6))

### Code Style

- Apply ruff auto-fix
  ([`c1657a0`](https://github.com/christianlouis/DocuElevate/commit/c1657a01a77ca6b914bc21a20a42aeb924de8254))

- Apply ruff auto-fix
  ([`6f5f4d9`](https://github.com/christianlouis/DocuElevate/commit/6f5f4d9d4948208f65fc5572c86a08642efe54b6))

- Apply ruff auto-fix
  ([`2cfbea2`](https://github.com/christianlouis/DocuElevate/commit/2cfbea29a9211abfc13b74dea0a841fe5a2546b9))

### Documentation

- **changelog**: Update changelog [skip ci]
  ([`fa36ec6`](https://github.com/christianlouis/DocuElevate/commit/fa36ec69876b919a33a7471bb837c2a6b69c2a50))

### Performance Improvements

- **api**: Fix n+1 query issue in user notification preferences update
  ([`fe20e02`](https://github.com/christianlouis/DocuElevate/commit/fe20e02f78c3c6236b07f50edb66599b8a9c7ed2))


## Unreleased

### Code Style

- Apply ruff auto-fix
  ([`2cfbea2`](https://github.com/christianlouis/DocuElevate/commit/2cfbea29a9211abfc13b74dea0a841fe5a2546b9))


## v0.145.2 (2026-03-15)

### Bug Fixes

- **auth**: Case-insensitive login + mobile auth debug logging
  ([`f58b894`](https://github.com/christianlouis/DocuElevate/commit/f58b8943fbec892ebcc612b28e301605a72232b4))


## v0.145.1 (2026-03-15)

### Bug Fixes

- **mobile**: Suppress Node.js url.parse() deprecation and document Apple session fix
  ([`dd02ff5`](https://github.com/christianlouis/DocuElevate/commit/dd02ff5677fdd9704da4bacdaf2850882e9f6743))

### Documentation

- **changelog**: Update changelog [skip ci]
  ([`4de5743`](https://github.com/christianlouis/DocuElevate/commit/4de574370c700708915c4241c1b0ac91e4478707))

### Testing

- Fix webdav localhost assertion to match actual error message
  ([`fe48e2a`](https://github.com/christianlouis/DocuElevate/commit/fe48e2aedc6cae822cd06a85293833ce103ebcce))


## Unreleased

### Testing

- Fix webdav localhost assertion to match actual error message
  ([`fe48e2a`](https://github.com/christianlouis/DocuElevate/commit/fe48e2aedc6cae822cd06a85293833ce103ebcce))


## v0.145.0 (2026-03-15)

### Features

- **i18n**: Localize admin files page (filemanager.html)
  ([`2bb47e7`](https://github.com/christianlouis/DocuElevate/commit/2bb47e7631836880873e51b131455ff8a500d2a6))


## v0.144.0 (2026-03-15)

### Bug Fixes

- **i18n**: Fix overage buffer sentence spacing in admin_plans template
  ([`de8922b`](https://github.com/christianlouis/DocuElevate/commit/de8922bb8e1e837ffc1ff29cbbeb1a2cd10d8d20))

### Documentation

- Rewrite README.md and update UserGuide and Troubleshooting docs
  ([`fcf2452`](https://github.com/christianlouis/DocuElevate/commit/fcf2452b625109dbd7f7464929d5482b94db4a32))

### Features

- **i18n**: Localize admin plans page
  ([`36aef73`](https://github.com/christianlouis/DocuElevate/commit/36aef7396951ff2b91677f877415b8bce4fd1fc3))


## v0.143.1 (2026-03-15)

### Bug Fixes

- **auth**: Expo Go support via Linking.createURL; safe token URL construction; clean up return type
  annotation
  ([`1428556`](https://github.com/christianlouis/DocuElevate/commit/14285567d5bbf30200bd56ca30c75c906d09a376))

- **auth**: Store mobile_redirect_uri in session and redirect to deep-link after SSO; fix
  SafeAreaView deprecation
  ([`5c373e7`](https://github.com/christianlouis/DocuElevate/commit/5c373e72243ab18a4bb0f25bb23379ef6ccfa6fc))


## v0.143.0 (2026-03-15)

### Features

- **i18n**: Localize admin users page
  ([`3fc0d52`](https://github.com/christianlouis/DocuElevate/commit/3fc0d5212675a3a54ee32ecaede8a0494f309c40))


## v0.142.0 (2026-03-15)

### Features

- **i18n**: Localize terms and conditions page
  ([`8c18f0d`](https://github.com/christianlouis/DocuElevate/commit/8c18f0da1718c53ab6ba5bf70ad2679cc287f0d1))


## v0.141.2 (2026-03-15)

### Bug Fixes

- **mobile**: Align React version with react-native-renderer to fix version mismatch crash
  ([`0736278`](https://github.com/christianlouis/DocuElevate/commit/073627884ca08ddb1b7838ce95815fc20f6ca5a0))

### Chores

- Initial plan placeholder
  ([`c5b08e7`](https://github.com/christianlouis/DocuElevate/commit/c5b08e778d99d9a5a677f38a3ff5ba60cc657981))


## v0.141.1 (2026-03-15)

### Bug Fixes

- **mobile**: Correct asset logo path depth and add expo-router app/ routes for web support
  ([`82d90b4`](https://github.com/christianlouis/DocuElevate/commit/82d90b48e24320734f6b602044d2845efbbead05))

- **mobile**: Update Node.js minimum requirement to 20.19.4
  ([`b4b50e8`](https://github.com/christianlouis/DocuElevate/commit/b4b50e834088045510b3c235464862789d31c646))


## v0.141.0 (2026-03-15)

### Features

- **ui**: Localize status page with i18n translations
  ([`e46dadb`](https://github.com/christianlouis/DocuElevate/commit/e46dadbf45bc91f1c14f544538bf143a438b1c0a))


## v0.140.0 (2026-03-15)

### Features

- **i18n**: Localize attribution page
  ([`246ef70`](https://github.com/christianlouis/DocuElevate/commit/246ef702453fdfbca240b2bf0d1aa410abd9f179))


## v0.139.0 (2026-03-15)

### Features

- **ui**: Localize license page with i18n translation keys
  ([`9c73ab8`](https://github.com/christianlouis/DocuElevate/commit/9c73ab8e5963ae061c5ca3b494efb5620d4c8468))


## v0.138.0 (2026-03-15)

### Features

- **i18n**: Localize cookies policy page
  ([`182868c`](https://github.com/christianlouis/DocuElevate/commit/182868c0d71f7accfd801c7c41864c639aca5149))


## v0.137.1 (2026-03-15)

### Bug Fixes

- **mobile**: Add missing react@19.2.4 integrity hash to package-lock.json
  ([`ca962f8`](https://github.com/christianlouis/DocuElevate/commit/ca962f8040c4f6fb5f7e20cf4bf04f4c4532c100))

- **mobile**: Fix iOS TurboModule crash and npm install peer dep conflict
  ([`f983b20`](https://github.com/christianlouis/DocuElevate/commit/f983b20a8f0424353cbda5e876428fe97459e303))

### Chores

- Initial plan for npm install lockfile fix
  ([`0181143`](https://github.com/christianlouis/DocuElevate/commit/01811438dcc46b5b335dc6054cbde6b229ccd332))


## v0.137.0 (2026-03-15)

### Chores

- **mobile**: Update iOS build image to Xcode 26 for iOS 26 SDK compliance
  ([`69664ec`](https://github.com/christianlouis/DocuElevate/commit/69664ec6cdb0bcfc3742fa9d75eed2125ed9ca12))

### Documentation

- **changelog**: Update changelog [skip ci]
  ([`8a1dc2a`](https://github.com/christianlouis/DocuElevate/commit/8a1dc2aa0e6b03408501ee8964ba60f9385c552b))

- **changelog**: Update changelog [skip ci]
  ([`02c3992`](https://github.com/christianlouis/DocuElevate/commit/02c399239c8260cb0ba217128bb2c62271a847f7))

### Features

- **ui**: Localize imprint page
  ([`1f6a3a5`](https://github.com/christianlouis/DocuElevate/commit/1f6a3a58037f24fc838b2d4471afa01c68f4178d))


## Unreleased

### Chores

- **mobile**: Update iOS build image to Xcode 26 for iOS 26 SDK compliance
  ([`69664ec`](https://github.com/christianlouis/DocuElevate/commit/69664ec6cdb0bcfc3742fa9d75eed2125ed9ca12))

### Documentation

- **changelog**: Update changelog [skip ci]
  ([`02c3992`](https://github.com/christianlouis/DocuElevate/commit/02c399239c8260cb0ba217128bb2c62271a847f7))


## Unreleased


## v0.136.1 (2026-03-15)

### Bug Fixes

- **mobile**: Resolve iOS build errors by enabling buildReactNativeFromSource for Expo SDK 54
  ([`3372a93`](https://github.com/christianlouis/DocuElevate/commit/3372a93f71f76d0dacb9c41458240b4146e33d9f))

### Code Style

- Apply ruff auto-fix
  ([`b7a195d`](https://github.com/christianlouis/DocuElevate/commit/b7a195d3bced215bf4d197c867883c2277940b56))


## v0.136.0 (2026-03-14)

### Features

- **mobile**: Update DocuElevate mobile app branding with original logo and UX
  ([`971e578`](https://github.com/christianlouis/DocuElevate/commit/971e578dd7f356d5a7cf2d2dfbb8c7a168f334d0))


## v0.135.4 (2026-03-14)

### Bug Fixes

- **mobile**: Fix expo doctor dependency version mismatches for SDK 54
  ([`f6e955a`](https://github.com/christianlouis/DocuElevate/commit/f6e955acce84366cab4138634dbc8b258bb10f3d))


## v0.135.3 (2026-03-14)

### Bug Fixes

- **mobile**: Update iOS build image from macos-sequoia-15.1-xcode-16.2 to
  macos-sequoia-15.3-xcode-16.2
  ([`fe66e51`](https://github.com/christianlouis/DocuElevate/commit/fe66e519966c983cee9b8867cc33261459a085df))


## v0.135.2 (2026-03-14)

### Bug Fixes

- **mobile**: Add missing assets and EAS workflow for automatic builds
  ([`1aa02ae`](https://github.com/christianlouis/DocuElevate/commit/1aa02aea24fbfdc40cc5cf92a5907616f4d9c706))

- **mobile**: Sync app.json and eas.json to expo.dev project credentials
  ([`5f3d134`](https://github.com/christianlouis/DocuElevate/commit/5f3d134d7ef42380b6f99fa70f8fdf71bed9391b))

- **mobile**: Sync app.json slug and owner to expo.dev project
  ([`7633cdf`](https://github.com/christianlouis/DocuElevate/commit/7633cdf4e49277612a830ef9c6aaf9c5ed783648))

- **mobile**: Use org.docuelevate.mobile as app identifier
  ([`4f38075`](https://github.com/christianlouis/DocuElevate/commit/4f38075de4b6647b41f776517ff6499fb616b6e6))


## v0.135.1 (2026-03-14)

### Bug Fixes

- **mobile**: Resolve EAS CI build failures – wrap app.json, update deps, pin Xcode image
  ([`3bf9589`](https://github.com/christianlouis/DocuElevate/commit/3bf9589462ffb2cff80ef3d73b38be879869f157))


## v0.135.0 (2026-03-14)

### Features

- **ui**: Add i18n support to privacy page
  ([`e1941ad`](https://github.com/christianlouis/DocuElevate/commit/e1941adfc9aa59301de9f3114a7c2370c26b547b))


## v0.134.5 (2026-03-14)

### Bug Fixes

- **mobile**: Update react to 19.2.4 and add package-lock.json to fix npm ERESOLVE build failure
  ([`8653247`](https://github.com/christianlouis/DocuElevate/commit/8653247e442b64d1d8456f716d7baa2b3f61d73a))

### Chores

- Initial plan for mobile npm peer dep fix
  ([`0cb2f6c`](https://github.com/christianlouis/DocuElevate/commit/0cb2f6c36263616b68f8c7799fd4c967fb1cf3bd))

- **i18n**: Auto-update translations via LLM
  ([`c664220`](https://github.com/christianlouis/DocuElevate/commit/c6642203c095c59329d6ce460c31a0bdb53dc948))

- **i18n**: Auto-update translations via LLM
  ([`31218c8`](https://github.com/christianlouis/DocuElevate/commit/31218c886021aced8f74881e6015d7d660cc99c2))

### Documentation

- **changelog**: Update changelog [skip ci]
  ([`ef4c513`](https://github.com/christianlouis/DocuElevate/commit/ef4c513908eee9fbc40f8c3bcae8cbfc072415bc))


## Unreleased

### Chores

- **i18n**: Auto-update translations via LLM
  ([`c664220`](https://github.com/christianlouis/DocuElevate/commit/c6642203c095c59329d6ce460c31a0bdb53dc948))

- **i18n**: Auto-update translations via LLM
  ([`31218c8`](https://github.com/christianlouis/DocuElevate/commit/31218c886021aced8f74881e6015d7d660cc99c2))


## v0.134.4 (2026-03-14)

### Bug Fixes

- **mobile**: Bump Node to 20.19.4 and fix react-navigation peer dependency
  ([`4c6596b`](https://github.com/christianlouis/DocuElevate/commit/4c6596b56192341f2be4bb14a8a9ace1182bd38e))


## v0.134.3 (2026-03-14)

### Bug Fixes

- **mobile**: Add expo-dev-client, pin Node version, and fix EAS build config
  ([`6834f3e`](https://github.com/christianlouis/DocuElevate/commit/6834f3ef1b3bce099e4f8f9f76cee94a2a635f64))

- **mobile**: Add owner field to app.json to match EAS project owner
  ([`492b2c6`](https://github.com/christianlouis/DocuElevate/commit/492b2c643c42686c950f871bd284a4e702af52d5))


## v0.134.2 (2026-03-14)

### Bug Fixes

- **mobile**: Upgrade Expo SDK from 51 to 54 and fix EAS project ID
  ([`f148785`](https://github.com/christianlouis/DocuElevate/commit/f148785079b220530ff4ba8a41ca4258727c9f2d))


## v0.134.1 (2026-03-14)

### Bug Fixes

- **mobile**: Relax Node.js engine constraint to >=18.0.0
  ([`fb5d494`](https://github.com/christianlouis/DocuElevate/commit/fb5d494e42e1d4caf8b5d62480e38a168118de21))

- **mobile**: Remove expo-sharing from plugins and align .nvmrc with Node 18 LTS
  ([`8f9405b`](https://github.com/christianlouis/DocuElevate/commit/8f9405b5ac33df9a0f211061038814aac3d57286))


## v0.134.0 (2026-03-14)

### Bug Fixes

- **i18n**: Replace fragment translation keys with placeholder-based complete sentences
  ([`eaa5337`](https://github.com/christianlouis/DocuElevate/commit/eaa533760dbb8e143fadfece808d1a229e29940b))

- **ui**: Restore missing template x-if tag and fix Nextcloud URL label key
  ([`08853e8`](https://github.com/christianlouis/DocuElevate/commit/08853e823c949d9b220d02004a9ac1196b15bb23))

### Features

- **ui**: Internationalize profile, subscription, integrations templates and user menu JS
  ([`5a02557`](https://github.com/christianlouis/DocuElevate/commit/5a025576c42107ac01caa3d8fcf9ffe5b35223f8))


## v0.133.7 (2026-03-14)

### Bug Fixes

- **mobile**: Fix EAS build Node.js version incompatibility for iOS and Android
  ([`8717538`](https://github.com/christianlouis/DocuElevate/commit/8717538967a8d8b141984abf8c070e19728f07f8))


## v0.133.6 (2026-03-14)

### Bug Fixes

- **database**: Quote identifiers in index management queries to prevent SQL injection
  ([`120002b`](https://github.com/christianlouis/DocuElevate/commit/120002b39408fb610d06c7555abdd40ab40c2ae4))

### Code Style

- Apply ruff auto-fix
  ([`0b064b9`](https://github.com/christianlouis/DocuElevate/commit/0b064b9d20f600b0a6ca140d590bc93cf6148491))

- Use Annotated pattern in audit_logs.py to resolve Ruff B008
  ([`f96fcbe`](https://github.com/christianlouis/DocuElevate/commit/f96fcbe6c9d1b306e1b40c0485da8c4c97062f9b))

### Testing

- Add error path tests for API token revocation
  ([`fdf5053`](https://github.com/christianlouis/DocuElevate/commit/fdf5053acedae711fc8b1f874e6057141fd4cd6d))

- Clarify caller cleanup responsibility in _make_unauthenticated_client docstring
  ([`751b16d`](https://github.com/christianlouis/DocuElevate/commit/751b16d804b0659514ac682b6b5d6c66a4e83e94))

- Exercise real auth path in test_revoke_token_unauthenticated
  ([`96ef7d4`](https://github.com/christianlouis/DocuElevate/commit/96ef7d4769fc5cdfbd552cd49a13778f8717a4d9))

- Strengthen test_revoke_token_database_error to verify rollback is called
  ([`9e9b1fb`](https://github.com/christianlouis/DocuElevate/commit/9e9b1fb158cf906de47b61997436104d924b45d6))

- **database**: Add unit test for quoted identifier in filehash index drop
  ([`33eded0`](https://github.com/christianlouis/DocuElevate/commit/33eded02b1a4a603136a41b46dcd3ec6a5356489))


## v0.133.5 (2026-03-14)

### Bug Fixes

- **ui**: Add 22 missing help page translation keys to en.json
  ([`48a9303`](https://github.com/christianlouis/DocuElevate/commit/48a93036ca94cf910eb854c210382884911502c2))


## v0.133.4 (2026-03-14)

### Bug Fixes

- **i18n**: Add noqa comment to intentionally broad exception in hydration helper
  ([`f41ecc9`](https://github.com/christianlouis/DocuElevate/commit/f41ecc9b2c234062d5d5565380c3c409011e3883))

- **i18n**: Persist language preference server-side, fix dropdown rendering and avatar 404
  ([`1416d90`](https://github.com/christianlouis/DocuElevate/commit/1416d901d0615adf0c77551d1678207ae3308b3a))

### Chores

- **i18n**: Auto-update translations via LLM
  ([`d09227b`](https://github.com/christianlouis/DocuElevate/commit/d09227b61cad3fc77396b86834da9849a222e8a0))

### Documentation

- **changelog**: Update changelog [skip ci]
  ([`01739e8`](https://github.com/christianlouis/DocuElevate/commit/01739e8c228f1bd1278cb472998eb7c05e851a51))


## Unreleased

### Chores

- **i18n**: Auto-update translations via LLM
  ([`d09227b`](https://github.com/christianlouis/DocuElevate/commit/d09227b61cad3fc77396b86834da9849a222e8a0))


## v0.133.3 (2026-03-14)

### Bug Fixes

- **i18n**: Add missing index page translation keys to en.json
  ([`1f24b1b`](https://github.com/christianlouis/DocuElevate/commit/1f24b1b95be512c0f9a09b54001ae5bf71b47e37))


## v0.133.2 (2026-03-14)

### Bug Fixes

- **ui**: Add missing suggested_languages global to error templates
  ([`0592c59`](https://github.com/christianlouis/DocuElevate/commit/0592c59174bfb2cbb2b96f62297963c9a6c1bb60))

### Code Style

- Apply ruff auto-fix
  ([`de0b674`](https://github.com/christianlouis/DocuElevate/commit/de0b674025943dcc6aa21edc9e8027512964a605))


## v0.133.1 (2026-03-14)

### Bug Fixes

- **test**: Remove tests that check specific translation content
  ([`08fabe1`](https://github.com/christianlouis/DocuElevate/commit/08fabe154a35e9f8def21f86178b3619e021a595))

### Chores

- **i18n**: Auto-update translations via LLM
  ([`0cb6017`](https://github.com/christianlouis/DocuElevate/commit/0cb6017b50c7e2bb06a39a41a17d504b68bcb09f))

### Documentation

- **changelog**: Update changelog [skip ci]
  ([`971d450`](https://github.com/christianlouis/DocuElevate/commit/971d4501282790c73fa43823039d5d4cea0111f4))


## Unreleased

### Chores

- **i18n**: Auto-update translations via LLM
  ([`0cb6017`](https://github.com/christianlouis/DocuElevate/commit/0cb6017b50c7e2bb06a39a41a17d504b68bcb09f))


## v0.133.0 (2026-03-14)

### Features

- **ui**: Smart compact language selector with search and flags
  ([`3557590`](https://github.com/christianlouis/DocuElevate/commit/3557590679f17ad88fe7cf91b5665fd669ba0447))


## v0.132.1 (2026-03-14)

### Bug Fixes

- **security**: Prevent potential SQL injection in database migration
  ([`82b1f89`](https://github.com/christianlouis/DocuElevate/commit/82b1f89332d7bb3e7d8a16651b17a060e8ae4d0f))

### Chores

- **i18n**: Auto-update translations via LLM
  ([`8e86518`](https://github.com/christianlouis/DocuElevate/commit/8e865180a5e751566ea3312bef916efc9dc7cdb1))

- **i18n**: Auto-update translations via LLM
  ([`9a480e3`](https://github.com/christianlouis/DocuElevate/commit/9a480e3d68e2e162c73cb526b2887dbcae0cedac))

### Documentation

- **changelog**: Update changelog [skip ci]
  ([`4a46f37`](https://github.com/christianlouis/DocuElevate/commit/4a46f372b97f89a3c0059ce8c451424e9c121c7a))

### Testing

- **i18n**: Remove translation content assertion from test_translate_with_kwargs_german
  ([`9b32cbc`](https://github.com/christianlouis/DocuElevate/commit/9b32cbc91b26f83cd451d0c5d369b0692dd7edf7))


## Unreleased

### Chores

- **i18n**: Auto-update translations via LLM
  ([`8e86518`](https://github.com/christianlouis/DocuElevate/commit/8e865180a5e751566ea3312bef916efc9dc7cdb1))

- **i18n**: Auto-update translations via LLM
  ([`9a480e3`](https://github.com/christianlouis/DocuElevate/commit/9a480e3d68e2e162c73cb526b2887dbcae0cedac))


## v0.132.0 (2026-03-13)

### Features

- **i18n**: Update language support to 77 languages
  ([`59d8512`](https://github.com/christianlouis/DocuElevate/commit/59d851272dccd0213c4b718a9a07e98d9fed1be8))


## v0.131.0 (2026-03-13)

### Documentation

- **changelog**: Update changelog [skip ci]
  ([`bd35cdd`](https://github.com/christianlouis/DocuElevate/commit/bd35cdd268b796cefa257e395d9ef3039c2fc63f))

- **changelog**: Update changelog [skip ci]
  ([`bb71f0a`](https://github.com/christianlouis/DocuElevate/commit/bb71f0aab8d4375c02553eb93d8c5c6cb71cde09))

- **i18n**: Add comment on Welsh subdivision flag Unicode representation
  ([`ce4e797`](https://github.com/christianlouis/DocuElevate/commit/ce4e797bd10f0cde5268a2a335510c5bd08b41e3))

### Features

- **i18n**: Expand supported languages from 31 to 49 with flags and locale formats
  ([`87d8562`](https://github.com/christianlouis/DocuElevate/commit/87d85624be78b2c97faec27745e7c896480a4438))


## Unreleased

### Documentation

- **changelog**: Update changelog [skip ci]
  ([`bb71f0a`](https://github.com/christianlouis/DocuElevate/commit/bb71f0aab8d4375c02553eb93d8c5c6cb71cde09))


## Unreleased


## v0.130.0 (2026-03-13)

### Features

- **i18n**: Add complete Catalan (ca) translation
  ([`217217d`](https://github.com/christianlouis/DocuElevate/commit/217217dd01eaa29eeb2510f953438240fb8fc235))


## v0.129.0 (2026-03-13)

### Bug Fixes

- **i18n**: Use plain plural form for files.files_selected in fr.json
  ([`bb2c3ac`](https://github.com/christianlouis/DocuElevate/commit/bb2c3ac7595d1668cae5d9ff5d5668f10670be24))

### Features

- **i18n**: Add complete French translations to fr.json
  ([`5de7e01`](https://github.com/christianlouis/DocuElevate/commit/5de7e01a8677902b3f249c68b96692bdc42eb623))


## v0.128.0 (2026-03-13)

### Features

- **i18n**: Add missing Polish translations to pl.json
  ([`f737f29`](https://github.com/christianlouis/DocuElevate/commit/f737f2903a8ecfe204f4ca9a40f4eb143545609b))


## v0.127.0 (2026-03-13)


## v0.126.0 (2026-03-13)

### Documentation

- **changelog**: Update changelog [skip ci]
  ([`fd4ea5c`](https://github.com/christianlouis/DocuElevate/commit/fd4ea5c71b4ac3204bb9cf21b115333c0db24927))

- **changelog**: Update changelog [skip ci]
  ([`95af9ff`](https://github.com/christianlouis/DocuElevate/commit/95af9ffe5e493470caaf09dc784ba12f5d19a8e7))

- **changelog**: Update changelog [skip ci]
  ([`ca88d7d`](https://github.com/christianlouis/DocuElevate/commit/ca88d7d4250b3b9ee384d05b53d854056c5eccb4))

- **routing**: Add routing rules documentation to API.md and UserGuide.md
  ([`e95693d`](https://github.com/christianlouis/DocuElevate/commit/e95693d684076ef87c436840caf2c5aa4581456d))

### Features

- **routing**: Add conditional routing rules for document-to-pipeline assignment
  ([`40d56f0`](https://github.com/christianlouis/DocuElevate/commit/40d56f0396b42754954cea03e4efa2e442121313))

### Refactoring

- **routing**: Address code review feedback - simplify list filter, fix docs example
  ([`1e5e35a`](https://github.com/christianlouis/DocuElevate/commit/1e5e35a26af47db925f77514a3bfdbccf417c0f5))


## Unreleased

### Documentation

- **changelog**: Update changelog [skip ci]
  ([`95af9ff`](https://github.com/christianlouis/DocuElevate/commit/95af9ffe5e493470caaf09dc784ba12f5d19a8e7))

- **changelog**: Update changelog [skip ci]
  ([`ca88d7d`](https://github.com/christianlouis/DocuElevate/commit/ca88d7d4250b3b9ee384d05b53d854056c5eccb4))


## Unreleased

### Documentation

- **changelog**: Update changelog [skip ci]
  ([`ca88d7d`](https://github.com/christianlouis/DocuElevate/commit/ca88d7d4250b3b9ee384d05b53d854056c5eccb4))


## Unreleased


## v0.125.1 (2026-03-12)

### Bug Fixes

- **i18n**: Sync de.json keys with en.json — add 26 missing keys to en.json and all language files
  ([`d3349e6`](https://github.com/christianlouis/DocuElevate/commit/d3349e649ea1ef01d8afc62d9a92d00ba4aac3f8))


## v0.125.0 (2026-03-12)

### Bug Fixes

- **profile**: Address code review feedback - early size check, CSRF helper, test constants
  ([`9583d6d`](https://github.com/christianlouis/DocuElevate/commit/9583d6d96f02d3ee105c73a47084661feef3e811))

- **tests**: Pass mock db to whoami_handler in test_api_auth_enabled.py
  ([`270e1a5`](https://github.com/christianlouis/DocuElevate/commit/270e1a56b51148651ed499780ba9dec5af68b33e))

### Features

- **profile**: Add user self-service profile settings page and API
  ([`b0d6f1a`](https://github.com/christianlouis/DocuElevate/commit/b0d6f1ab609d5676b71eab20fee8c5cce9201614))


## v0.124.0 (2026-03-12)

### Bug Fixes

- **i18n**: Register _ in all Jinja2 template instances, sync translation files, fix pipelines.html
  ([`b483ed1`](https://github.com/christianlouis/DocuElevate/commit/b483ed16fc01e474468356b3af8c2abaa8f22af6))


## v0.123.1 (2026-03-12)

### Bug Fixes

- **tests**: Fix two failing tests - missing DB table and MagicMock IP address
  ([`be6b49c`](https://github.com/christianlouis/DocuElevate/commit/be6b49c8721445dc8ea870afda87f311acb192e3))

### Code Style

- Fix ruff formatting in tests/test_imap_profiles.py
  ([`8060a79`](https://github.com/christianlouis/DocuElevate/commit/8060a79b9c5172c40edff87bdcf0e095e177560e))


## v0.123.0 (2026-03-12)

### Bug Fixes

- **imap**: Address code review feedback on ingestion profiles
  ([`2e08773`](https://github.com/christianlouis/DocuElevate/commit/2e087731b92fe554e54955c97166d61fe644bafc))

### Features

- **imap**: Add attachment type filter for IMAP ingestion
  ([`554bb21`](https://github.com/christianlouis/DocuElevate/commit/554bb21d329ca2cca868a61adf337e29e4284ca4))

- **imap**: Add ImapIngestionProfile model, API, migration and UI
  ([`c9f5544`](https://github.com/christianlouis/DocuElevate/commit/c9f554465d5bf027a92bb4aa56db244aad4a6ff6))


## v0.122.0 (2026-03-12)

### Documentation

- **storage**: Document explicit enable/disable flags in ConfigurationGuide and .env.demo
  ([`fd75961`](https://github.com/christianlouis/DocuElevate/commit/fd7596158064b68a23df4a89201f456df8f28b38))

### Features

- **storage**: Add explicit enable/disable flag for each global storage destination
  ([`b72ab3b`](https://github.com/christianlouis/DocuElevate/commit/b72ab3b31835ab6ab574067499544427c4101231))


## v0.121.1 (2026-03-12)

### Bug Fixes

- Remove duplicate Audit Logs nav entry and add login/logout audit log events
  ([`1e8f433`](https://github.com/christianlouis/DocuElevate/commit/1e8f433419c5c7b0c551dffe05f107d2bb5a35a1))

### Documentation

- **changelog**: Update changelog [skip ci]
  ([`50ef607`](https://github.com/christianlouis/DocuElevate/commit/50ef6072935083554dd52a11cc6438891f177a8b))

### Testing

- **notifications**: Improve coverage for user_notification.py to 100%
  ([`78204c2`](https://github.com/christianlouis/DocuElevate/commit/78204c2490ffd9ed0bcb62154c3da54fa9614450))


## Unreleased

### Testing

- **notifications**: Improve coverage for user_notification.py to 100%
  ([`78204c2`](https://github.com/christianlouis/DocuElevate/commit/78204c2490ffd9ed0bcb62154c3da54fa9614450))


## v0.121.0 (2026-03-12)

### Bug Fixes

- **auth**: Address code review feedback - sanitize error messages, remove unused import
  ([`5d716ad`](https://github.com/christianlouis/DocuElevate/commit/5d716ad78fdcd92cafa0a7765580ef290cc842fc))

### Documentation

- **changelog**: Update changelog [skip ci]
  ([`04cde33`](https://github.com/christianlouis/DocuElevate/commit/04cde33d01d53877fc34a60b887c6978d167a97e))

### Features

- **auth**: Add social login support for Google, Microsoft, Apple, and Dropbox
  ([`ac6e052`](https://github.com/christianlouis/DocuElevate/commit/ac6e05278896986ca234e6109e225c599eb982c7))

### Testing

- Improve coverage for app/utils/audit_service.py from 59% to 100%
  ([`7438551`](https://github.com/christianlouis/DocuElevate/commit/7438551080dfec645a9e9c9ea8ee059764430e90))

- **auth**: Add tests for social login and fix existing config validator tests
  ([`9c26d41`](https://github.com/christianlouis/DocuElevate/commit/9c26d412d7710dce47d06969270f184411cd6898))


## Unreleased

### Testing

- Improve coverage for app/utils/audit_service.py from 59% to 100%
  ([`7438551`](https://github.com/christianlouis/DocuElevate/commit/7438551080dfec645a9e9c9ea8ee059764430e90))


## v0.120.0 (2026-03-12)

### Bug Fixes

- Remove accidental pip artifact file and update docs for iCloud Drive
  ([`ca84a11`](https://github.com/christianlouis/DocuElevate/commit/ca84a11284a979409db186b20b0381f5025d4fdf))

- Remove accidental pip artifact file and update docs for iCloud Drive
  ([`528f0a6`](https://github.com/christianlouis/DocuElevate/commit/528f0a624de335b21125b8b86700eb4d85dfed86))

- **tests**: Add iCloud mocks to all test files and address code review feedback
  ([`50af0ea`](https://github.com/christianlouis/DocuElevate/commit/50af0ea67942e545849bbd745258cbed7822af45))

### Features

- **storage**: Add Apple iCloud Drive storage provider
  ([`82d67c5`](https://github.com/christianlouis/DocuElevate/commit/82d67c56b34ec5a849bb3fa46aba0182c7f51dcd))

- **storage**: Add Apple iCloud Drive storage provider
  ([`30f06e0`](https://github.com/christianlouis/DocuElevate/commit/30f06e0b3292d9b01428fc945913ab91888644a3))

### Testing

- **tasks**: Add _should_upload_to_icloud mock to send_to_all tests
  ([`6e50c61`](https://github.com/christianlouis/DocuElevate/commit/6e50c6197082bbf2de2935cca1b74602789383f4))

- **tasks**: Add _should_upload_to_icloud mock to send_to_all tests
  ([`9bc23aa`](https://github.com/christianlouis/DocuElevate/commit/9bc23aa40b9c8a9c943cf75f1051fac9e38c24fc))


## v0.119.0 (2026-03-12)


## v0.118.0 (2026-03-11)

### Features

- **api**: Add GraphQL endpoint at /graphql with Strawberry
  ([`a41ded5`](https://github.com/christianlouis/DocuElevate/commit/a41ded535f32d4892199208e1cab54cc189fde13))


## v0.117.1 (2026-03-11)

### Bug Fixes

- Resolve all 47 failing tests in main
  ([`df4c91a`](https://github.com/christianlouis/DocuElevate/commit/df4c91a58661e2ecf9fda15500e4ba1259674168))


## v0.117.0 (2026-03-11)

### Continuous Integration

- Opt into Node.js 24 for all GitHub Actions workflows
  ([`c306d80`](https://github.com/christianlouis/DocuElevate/commit/c306d80755193e4b12222c73ed4da442a2d5e23c))

### Documentation

- **changelog**: Update changelog [skip ci]
  ([`ab19ae5`](https://github.com/christianlouis/DocuElevate/commit/ab19ae57060ff2be8e9172714c5e3b308c45334d))

- **changelog**: Update changelog [skip ci]
  ([`c5b67fe`](https://github.com/christianlouis/DocuElevate/commit/c5b67fe36464b0756553cc54614d0f77273772ec))

- **changelog**: Update changelog [skip ci]
  ([`eb22a58`](https://github.com/christianlouis/DocuElevate/commit/eb22a580651b4de477b3b5cc945581776a6775fa))


## Unreleased

### Continuous Integration

- Opt into Node.js 24 for all GitHub Actions workflows
  ([`c306d80`](https://github.com/christianlouis/DocuElevate/commit/c306d80755193e4b12222c73ed4da442a2d5e23c))

### Documentation

- **changelog**: Update changelog [skip ci]
  ([`c5b67fe`](https://github.com/christianlouis/DocuElevate/commit/c5b67fe36464b0756553cc54614d0f77273772ec))

- **changelog**: Update changelog [skip ci]
  ([`eb22a58`](https://github.com/christianlouis/DocuElevate/commit/eb22a580651b4de477b3b5cc945581776a6775fa))


## Unreleased

### Continuous Integration

- Opt into Node.js 24 for all GitHub Actions workflows
  ([`c306d80`](https://github.com/christianlouis/DocuElevate/commit/c306d80755193e4b12222c73ed4da442a2d5e23c))

### Documentation

- **changelog**: Update changelog [skip ci]
  ([`eb22a58`](https://github.com/christianlouis/DocuElevate/commit/eb22a580651b4de477b3b5cc945581776a6775fa))


## Unreleased

### Continuous Integration

- Opt into Node.js 24 for all GitHub Actions workflows
  ([`c306d80`](https://github.com/christianlouis/DocuElevate/commit/c306d80755193e4b12222c73ed4da442a2d5e23c))


## v0.116.0 (2026-03-11)

### Documentation

- **changelog**: Update changelog [skip ci]
  ([`d6fb787`](https://github.com/christianlouis/DocuElevate/commit/d6fb78715ae550f25a925bdc629eb2945f455009))

### Testing

- **views**: Add comprehensive coverage tests for 11 view modules
  ([`c8987d9`](https://github.com/christianlouis/DocuElevate/commit/c8987d966bd949634d222a7809ec52c3ed258f81))

- **views**: Boost coverage for 11 view modules toward 100%
  ([`6fb1df1`](https://github.com/christianlouis/DocuElevate/commit/6fb1df1aade8a8c98c27fe50dbe44045cba1724d))


## Unreleased

### Testing

- **views**: Add comprehensive coverage tests for 11 view modules
  ([`c8987d9`](https://github.com/christianlouis/DocuElevate/commit/c8987d966bd949634d222a7809ec52c3ed258f81))

- **views**: Boost coverage for 11 view modules toward 100%
  ([`6fb1df1`](https://github.com/christianlouis/DocuElevate/commit/6fb1df1aade8a8c98c27fe50dbe44045cba1724d))


## v0.115.0 (2026-03-10)


## v0.114.1 (2026-03-10)

### Bug Fixes

- **db**: Add migration to create shared_links table for databases that skipped 025
  ([`289dcc3`](https://github.com/christianlouis/DocuElevate/commit/289dcc375c111c8d71bd04ef31f184a0e6a3f6f2))


## v0.114.0 (2026-03-09)

### Bug Fixes

- 100% coverage, WCAG accessibility fixes, and documentation updates for per-user OAuth wizards
  ([`0529ae5`](https://github.com/christianlouis/DocuElevate/commit/0529ae53ff9367dc5390c1137896b2eea33ceb64))

- **templates**: Remove orphan </div> in google_drive.html causing HTML accessibility lint failure
  ([`256d9cb`](https://github.com/christianlouis/DocuElevate/commit/256d9cb674429bd7beebacd320d4701dafec6831))

### Features

- **integrations**: Add per-user OAuth wizard with user-mode for Dropbox, OneDrive, Google Drive
  ([`c71f33a`](https://github.com/christianlouis/DocuElevate/commit/c71f33a214272badb5c719f7a91d46a352caa2d0))

### Testing

- **views**: Add user-mode coverage tests and fix dashboard helper duplication
  ([`2d01e71`](https://github.com/christianlouis/DocuElevate/commit/2d01e71afd1a5f86ca47bc326216bc73d94095fb))


## v0.113.0 (2026-03-09)

### Bug Fixes

- Code standards audit — 100% coverage, Pydantic v2 model_config, asyncio.run(), targeted edge-case
  tests
  ([`ec77c51`](https://github.com/christianlouis/DocuElevate/commit/ec77c51cb5ed538d346eebe809cc4e8cf580c94c))

### Features

- **tasks**: Add 5 additional scheduled jobs (expire_shared_links, prune_processing_logs,
  prune_old_notifications, backfill_missing_metadata, sync_search_index)
  ([`5bc1fac`](https://github.com/christianlouis/DocuElevate/commit/5bc1fac79cd1f4079df76e565c366c461457cb1a))

- **tasks**: Add scheduled batch processing infrastructure (model, migration, tasks, API, view,
  template)
  ([`c2d56d7`](https://github.com/christianlouis/DocuElevate/commit/c2d56d74754703e2f6cff71161f0bfd33eec20a8))


## v0.112.0 (2026-03-09)

### Bug Fixes

- Address code review feedback - fix type hint and rename test
  ([`4acad71`](https://github.com/christianlouis/DocuElevate/commit/4acad71c8f9179bb93226bf1aff778d3a3ff5178))

- **imap**: Normalize CRLF line endings to LF in imap_tasks.py
  ([`9a342af`](https://github.com/christianlouis/DocuElevate/commit/9a342af609b27caeb021f782d4c6e3febdd56623))

### Documentation

- **integrations**: Update UserGuide and ConfigurationGuide for new IMAP and Watch Folder features
  ([`8c62a6b`](https://github.com/christianlouis/DocuElevate/commit/8c62a6b714d6de8516b748c1b52282c2a1f6cfa8))

### Features

- **integrations**: Add IMAP Gmail labels/delete and Watch Folder cloud source support
  ([`e7d1289`](https://github.com/christianlouis/DocuElevate/commit/e7d1289f1b96168460e60612d23bb9e0b644d6e4))

### Testing

- Add tests for gmail_apply_labels=False and cloud source type dispatching
  ([`79fc11b`](https://github.com/christianlouis/DocuElevate/commit/79fc11b45203ade500a35e58a7f2ffd1f6f64c7a))

- **integrations**: Add tests for gmail_apply_labels and cloud watch folder dispatch
  ([`8c62a6b`](https://github.com/christianlouis/DocuElevate/commit/8c62a6b714d6de8516b748c1b52282c2a1f6cfa8))

- **tasks**: Add comprehensive tests for per-user cloud scan functions and gmail_apply_labels
  ([`1741ab1`](https://github.com/christianlouis/DocuElevate/commit/1741ab1011866e7ec2131d7504c41dbcb1b52fb6))


## v0.111.1 (2026-03-09)

### Bug Fixes

- **migrations**: Resolve duplicate Alembic heads causing test failures
  ([`c374ba3`](https://github.com/christianlouis/DocuElevate/commit/c374ba3ae973a4472968247d7d3b66d13b32f254))


## v0.111.0 (2026-03-09)

### Bug Fixes

- **tasks**: Address code review - SMTP TLS cert validation, rclone input validation, consolidated
  test fixture
  ([`01a9511`](https://github.com/christianlouis/DocuElevate/commit/01a9511dcfc4a5753722df944d231954b8bf2f43))

- **tasks**: Register upload_to_user_integration in celery_worker and add handler tests
  ([`5fb11b9`](https://github.com/christianlouis/DocuElevate/commit/5fb11b978c5b05992bb0647da42bfc7e7889a71a))

### Features

- **tasks**: Dynamic routing to user-specific destination integrations
  ([`89bf07d`](https://github.com/christianlouis/DocuElevate/commit/89bf07d2eff9a09bd758e882c27c8f9e31d04240))


## v0.110.1 (2026-03-08)

### Bug Fixes

- **sentry**: Initialize Sentry after DB settings are loaded in lifespan
  ([`5864a4e`](https://github.com/christianlouis/DocuElevate/commit/5864a4ed0630b87469c49232653062f286297953))

### Code Style

- Apply ruff auto-fix
  ([`b22f9a6`](https://github.com/christianlouis/DocuElevate/commit/b22f9a6af6856ed2cafa79dfb2909e20b554f2f9))


## v0.110.0 (2026-03-08)

### Code Style

- Apply ruff auto-fix
  ([`e5d4f8b`](https://github.com/christianlouis/DocuElevate/commit/e5d4f8b58f4f3ef81cac604a9f2d2a83e3766b30))


## v0.109.0 (2026-03-08)

### Bug Fixes

- **ocr**: Address code review feedback on multi-language OCR
  ([`0b29199`](https://github.com/christianlouis/DocuElevate/commit/0b291995b90fe3141128f19542dd3c7308f0c7c3))

### Features

- **ocr**: Add multi-language OCR support with per-pipeline language override
  ([`a2a4c6f`](https://github.com/christianlouis/DocuElevate/commit/a2a4c6fc9a077a80d1877a441f61f72c5e611e58))


## v0.108.0 (2026-03-08)

### Chores

- Remove accidentally committed =8.0.0 file
  ([`a92bf8e`](https://github.com/christianlouis/DocuElevate/commit/a92bf8ec8f938a493e8992bdd71f655e5f266759))

### Features

- **cli**: Add docuelevate CLI tool for power users
  ([`a3fd74f`](https://github.com/christianlouis/DocuElevate/commit/a3fd74f117e96b9693cbfc0f76abbd0a3d526b00))


## v0.107.0 (2026-03-08)

### Documentation

- Add per-user notification system documentation to ConfigurationGuide.md
  ([`ae07590`](https://github.com/christianlouis/DocuElevate/commit/ae075908d1256ad728f4b992c020de2ef978fb65))

### Features

- **notifications**: Add per-user notification system with inbox, email, and webhook targets
  ([`fcefd09`](https://github.com/christianlouis/DocuElevate/commit/fcefd0978f36fc66ec2a34c9ab26021e38b1fcfb))

- **notifications**: Build per-user notification system (email, webhook, in-app)
  ([`d48e368`](https://github.com/christianlouis/DocuElevate/commit/d48e36813e37d3db220a04044f319698ecb48056))


## v0.106.0 (2026-03-08)

### Features

- **observability**: Add Sentry error and performance monitoring integration
  ([`58af9e5`](https://github.com/christianlouis/DocuElevate/commit/58af9e5a29e01332c8d6a5886bf09b87d8fa2e9b))


## v0.105.0 (2026-03-08)

### Continuous Integration

- Restore javascript-typescript CodeQL config alongside javascript
  ([`1fe6f86`](https://github.com/christianlouis/DocuElevate/commit/1fe6f86cc0d10047349825122d2582304a03beee))

### Documentation

- **changelog**: Update changelog [skip ci]
  ([`289eb42`](https://github.com/christianlouis/DocuElevate/commit/289eb422f317932b72c913b2dc88f39fbb871381))

### Features

- **ci**: Integrate Codecov for test coverage analysis and reporting
  ([`6d533aa`](https://github.com/christianlouis/DocuElevate/commit/6d533aae337b765e97c36a0d79f091bac2a639ba))


## Unreleased

### Continuous Integration

- Restore javascript-typescript CodeQL config alongside javascript
  ([`1fe6f86`](https://github.com/christianlouis/DocuElevate/commit/1fe6f86cc0d10047349825122d2582304a03beee))


## v0.104.0 (2026-03-08)

### Bug Fixes

- Correct token_prefix comment to match implementation (12 chars)
  ([`2f95feb`](https://github.com/christianlouis/DocuElevate/commit/2f95febf71881d8e4b86aca29f931a5a6c2665c8))

- **security**: Address CodeQL clear-text logging and weak hashing alerts
  ([`a7eff2c`](https://github.com/christianlouis/DocuElevate/commit/a7eff2c0331119f7b04ba4d6d39a864590621222))

### Code Style

- Apply ruff auto-fix
  ([`fc9caf4`](https://github.com/christianlouis/DocuElevate/commit/fc9caf4f9b35c666c1a03b8c1857c5dea5ff6484))

### Documentation

- Add API tokens and webhook ingestion documentation
  ([`a982959`](https://github.com/christianlouis/DocuElevate/commit/a9829598c509a230672daf53bb8656eb20f1a902))

### Features

- **api**: Add personal API tokens and enhance webhook integration UI
  ([`c3bb93c`](https://github.com/christianlouis/DocuElevate/commit/c3bb93c1971b51ca2ef09b733e273a569604e85a))


## v0.103.0 (2026-03-08)

### Bug Fixes

- **ui**: Correct OAuth setup page links in integrations dashboard
  ([`ba387b8`](https://github.com/christianlouis/DocuElevate/commit/ba387b8e8bdf8f8732ae237397083072d280977e))

### Documentation

- **config**: Document per-user IMAP and watch folder integration polling
  ([`fc453be`](https://github.com/christianlouis/DocuElevate/commit/fc453be71fe650e091ebd819c09735a9cdb8af43))

### Features

- **auth**: Make OAuth credentials user-specific via UserIntegration records
  ([`cfc52fd`](https://github.com/christianlouis/DocuElevate/commit/cfc52fd355c54655a7a2619a97f01206b3c7820a))

- **auth**: Save OAuth credentials per-user to UserIntegration records
  ([`73119e0`](https://github.com/christianlouis/DocuElevate/commit/73119e0cef6a50e23784267e8d68ec965a5bc70d))

- **tasks**: Refactor IMAP and watch folder polling to support multi-tenant user attribution
  ([`019807d`](https://github.com/christianlouis/DocuElevate/commit/019807d0f551da3a8f99609a6d5a662d02df6966))

### Testing

- **tasks**: Add comprehensive tests for multi-tenant polling functions
  ([`4f9f458`](https://github.com/christianlouis/DocuElevate/commit/4f9f458151b8d2aa0b1fcea33fa80d9b9226c099))


## v0.102.0 (2026-03-08)

### Features

- **support**: Auto-fill Zammad chat and ticket widgets with user context
  ([`209e82f`](https://github.com/christianlouis/DocuElevate/commit/209e82f7e5435773a6ed34d58632c9295b65c772))

### Testing

- **support**: Improve Zammad user context tests with meaningful assertions
  ([`8098856`](https://github.com/christianlouis/DocuElevate/commit/80988561860f14403436355979e4a48c10115999))


## v0.101.0 (2026-03-08)

### Features

- **ui**: Add unified Sources & Destinations integrations dashboard
  ([`2c652dc`](https://github.com/christianlouis/DocuElevate/commit/2c652dcc3e3b7bf5b959de8d0a1fe3cd6635763c))

- **ui**: Replace Email Ingestion nav with unified Integrations link
  ([`0edb941`](https://github.com/christianlouis/DocuElevate/commit/0edb94158d6956dcbd19a29751c3c89ac7980a87))

### Refactoring

- **ui**: Address code review - optimize queries, extract helpers, improve error handling
  ([`e27bace`](https://github.com/christianlouis/DocuElevate/commit/e27bacee3bbd84384ca3e87a540da3a721cdc0c3))


## v0.100.0 (2026-03-08)

### Bug Fixes

- Update docs endpoint test and add Zammad settings metadata
  ([`351d6f3`](https://github.com/christianlouis/DocuElevate/commit/351d6f3f4fc7d4128230b357fc0b4662c539645c))

- **security**: Add SRI to jQuery CDN, escape chat ID, use server-side hostname
  ([`883f123`](https://github.com/christianlouis/DocuElevate/commit/883f1231387a511e046c56484961267e32517939))

### Features

- **help**: Restructure /help as user-facing Help Center with Zammad integration
  ([`af3eed4`](https://github.com/christianlouis/DocuElevate/commit/af3eed4040b9513a5331be9c5163a505940dda9d))


## v0.99.0 (2026-03-08)

### Bug Fixes

- **billing**: Address code review - remove duplicate mode logic, accessibility improvements, robust
  test assertions
  ([`002cdf3`](https://github.com/christianlouis/DocuElevate/commit/002cdf312b6ef45864d89d9bdbf3030ef18e3ba6))

- **billing**: Cast plan.name to str to fix mypy typeddict-item error
  ([`9627667`](https://github.com/christianlouis/DocuElevate/commit/9627667d82aa4d9c5130aa1cf755a0a00fe08b1e))

### Features

- **billing**: Expose Stripe price IDs in plan API, add Stripe Setup Wizard and sync endpoints
  ([`223539b`](https://github.com/christianlouis/DocuElevate/commit/223539bebb7c7fa928bd4437796397c8ec19f99e))


## v0.98.0 (2026-03-08)

### Bug Fixes

- **integrations**: Sanitize error messages and add SSRF protection for WebDAV test
  ([`c4b4643`](https://github.com/christianlouis/DocuElevate/commit/c4b4643f6ee700ea080dd3de3148dfdf0eb83839))

### Documentation

- **api**: Add integrations quota enforcement and test endpoint documentation
  ([`71350f2`](https://github.com/christianlouis/DocuElevate/commit/71350f2ad6182b3fbc711740fe0669bf2985279e))

### Features

- **integrations**: Add quota enforcement, connection test, and quota endpoint
  ([`35abdb0`](https://github.com/christianlouis/DocuElevate/commit/35abdb0e6970ef1ee72a2235d050f2a3fdfc161b))


## v0.97.0 (2026-03-08)

### Features

- **status**: Restrict status page to admin-only and move to admin menu
  ([`feea051`](https://github.com/christianlouis/DocuElevate/commit/feea051c4f90c26c3d59894ee259e2d75c5eb073))


## v0.96.0 (2026-03-08)

### Bug Fixes

- **ui**: Move IMAP modals inside Alpine.js x-data scope so create/edit/delete buttons work
  ([`8aa8a93`](https://github.com/christianlouis/DocuElevate/commit/8aa8a93a6a49aa344be47285f9447abf4502f1f3))

### Features

- **models**: Add UserIntegration model, encrypt IMAP passwords, add integrations API
  ([`743627e`](https://github.com/christianlouis/DocuElevate/commit/743627ecc2155864ecaabde9cac8de43c3b81b30))


## v0.95.0 (2026-03-08)

### Bug Fixes

- **auth**: Cache request body in CSRF middleware to prevent login failures
  ([`087f3c1`](https://github.com/christianlouis/DocuElevate/commit/087f3c10e9e09d2953f30c9e362ae1017a5ca272))

- **imap**: Address code review feedback - named constants, error context in JS, security docs
  ([`73727dc`](https://github.com/christianlouis/DocuElevate/commit/73727dc56a9a5dc46d49c9f96065dd4bec7681b7))

### Features

- **imap**: Add per-user IMAP ingestion accounts with quota enforcement
  ([`43bcfe5`](https://github.com/christianlouis/DocuElevate/commit/43bcfe56539929ebd91a5a43be7c4f79d1a262a2))


## v0.94.0 (2026-03-08)

### Documentation

- **changelog**: Update changelog [skip ci]
  ([`e68bf13`](https://github.com/christianlouis/DocuElevate/commit/e68bf139492f17480fd66bfaaacac973faf0e3eb))

- **changelog**: Update changelog [skip ci]
  ([`195febf`](https://github.com/christianlouis/DocuElevate/commit/195febfb097162ba53f60108289853d52e58f54e))

- **changelog**: Update changelog [skip ci]
  ([`cc6acc1`](https://github.com/christianlouis/DocuElevate/commit/cc6acc1f03e5f31a15c092d7376be6be6eba7ddd))

### Features

- **auth**: Add comprehensive debug logging for local login failures
  ([`c5b330c`](https://github.com/christianlouis/DocuElevate/commit/c5b330cb4e8e86d1098ec049c7944fa6818bb107))

### Testing

- Increase backup_tasks.py coverage to 99.79%
  ([`9a95d5c`](https://github.com/christianlouis/DocuElevate/commit/9a95d5cfd55a766d0d8e1d71c03c5c845c6a3293))

- Increase watch_folder_tasks coverage from 37% to 98%
  ([`3ac5a97`](https://github.com/christianlouis/DocuElevate/commit/3ac5a97467d3ebae703b31d689bde2c4ca18468d))

- **backup**: Add comprehensive unit tests for app/views/backup.py
  ([`19b4ea4`](https://github.com/christianlouis/DocuElevate/commit/19b4ea4f6b0ff6c5ebcf2b560fb533f0aabe8a34))


## Unreleased

### Documentation

- **changelog**: Update changelog [skip ci]
  ([`195febf`](https://github.com/christianlouis/DocuElevate/commit/195febfb097162ba53f60108289853d52e58f54e))

- **changelog**: Update changelog [skip ci]
  ([`cc6acc1`](https://github.com/christianlouis/DocuElevate/commit/cc6acc1f03e5f31a15c092d7376be6be6eba7ddd))

### Testing

- Increase backup_tasks.py coverage to 99.79%
  ([`9a95d5c`](https://github.com/christianlouis/DocuElevate/commit/9a95d5cfd55a766d0d8e1d71c03c5c845c6a3293))

- Increase watch_folder_tasks coverage from 37% to 98%
  ([`3ac5a97`](https://github.com/christianlouis/DocuElevate/commit/3ac5a97467d3ebae703b31d689bde2c4ca18468d))

- **backup**: Add comprehensive unit tests for app/views/backup.py
  ([`19b4ea4`](https://github.com/christianlouis/DocuElevate/commit/19b4ea4f6b0ff6c5ebcf2b560fb533f0aabe8a34))


## Unreleased

### Documentation

- **changelog**: Update changelog [skip ci]
  ([`cc6acc1`](https://github.com/christianlouis/DocuElevate/commit/cc6acc1f03e5f31a15c092d7376be6be6eba7ddd))

### Testing

- Increase backup_tasks.py coverage to 99.79%
  ([`9a95d5c`](https://github.com/christianlouis/DocuElevate/commit/9a95d5cfd55a766d0d8e1d71c03c5c845c6a3293))

- **backup**: Add comprehensive unit tests for app/views/backup.py
  ([`19b4ea4`](https://github.com/christianlouis/DocuElevate/commit/19b4ea4f6b0ff6c5ebcf2b560fb533f0aabe8a34))


## Unreleased

### Testing

- Increase backup_tasks.py coverage to 99.79%
  ([`9a95d5c`](https://github.com/christianlouis/DocuElevate/commit/9a95d5cfd55a766d0d8e1d71c03c5c845c6a3293))


## v0.93.1 (2026-03-08)

### Bug Fixes

- **auth**: Activate account on password reset and fix is_active check order
  ([`86f9f5f`](https://github.com/christianlouis/DocuElevate/commit/86f9f5f9b1025c9270f342cc9ea77622c27781c9))

### Documentation

- **changelog**: Update changelog [skip ci]
  ([`be0a092`](https://github.com/christianlouis/DocuElevate/commit/be0a0922dc754cd97568e70ff73fbb724f84ea9b))

- **changelog**: Update changelog [skip ci]
  ([`5a11f14`](https://github.com/christianlouis/DocuElevate/commit/5a11f14681c7c22f0d4e1587f782e1c40a046d0a))

- **changelog**: Update changelog [skip ci]
  ([`53f7ab3`](https://github.com/christianlouis/DocuElevate/commit/53f7ab37d5e0242dd5b45b4327026c2dbca3c46d))

- **changelog**: Update changelog [skip ci]
  ([`754ea99`](https://github.com/christianlouis/DocuElevate/commit/754ea99092670b125ee9e689391b1decc085e007))

- **changelog**: Update changelog [skip ci]
  ([`8db0093`](https://github.com/christianlouis/DocuElevate/commit/8db0093562789925bb460300e83f2bd7c02753a2))

- **changelog**: Update changelog [skip ci]
  ([`2be09ef`](https://github.com/christianlouis/DocuElevate/commit/2be09efd99020b295a05da2c49a1611a70616579))

### Testing

- Increase app/api/google_drive.py coverage to 100%
  ([`14c9432`](https://github.com/christianlouis/DocuElevate/commit/14c94326402aed375a8178198ccd045f91765d74))

- Increase coverage for app/tasks/subscription_tasks.py to 100%
  ([`a580527`](https://github.com/christianlouis/DocuElevate/commit/a580527de454323f49b158929ceadb0c760bae33))

- Increase coverage for app/views/pipelines.py to 100%
  ([`344d20e`](https://github.com/christianlouis/DocuElevate/commit/344d20e4e63260e671118375ddfa811937b52c0c))

- Increase coverage for app/views/subscriptions.py to 100%
  ([`e96ddc7`](https://github.com/christianlouis/DocuElevate/commit/e96ddc78654ccc2f327f49eee587f6d62973532d))

- Increase url_upload.py test coverage to 100%
  ([`afe4227`](https://github.com/christianlouis/DocuElevate/commit/afe42270bb7dcbc23b4a8d7994899a18b0127d61))

- **subscriptions**: Add comprehensive API tests reaching 100% coverage
  ([`cd19ac6`](https://github.com/christianlouis/DocuElevate/commit/cd19ac661e84ff902bbbb3cc6a6fc78f3afb24c5))


## Unreleased

### Documentation

- **changelog**: Update changelog [skip ci]
  ([`5a11f14`](https://github.com/christianlouis/DocuElevate/commit/5a11f14681c7c22f0d4e1587f782e1c40a046d0a))

- **changelog**: Update changelog [skip ci]
  ([`53f7ab3`](https://github.com/christianlouis/DocuElevate/commit/53f7ab37d5e0242dd5b45b4327026c2dbca3c46d))

- **changelog**: Update changelog [skip ci]
  ([`754ea99`](https://github.com/christianlouis/DocuElevate/commit/754ea99092670b125ee9e689391b1decc085e007))

- **changelog**: Update changelog [skip ci]
  ([`8db0093`](https://github.com/christianlouis/DocuElevate/commit/8db0093562789925bb460300e83f2bd7c02753a2))

- **changelog**: Update changelog [skip ci]
  ([`2be09ef`](https://github.com/christianlouis/DocuElevate/commit/2be09efd99020b295a05da2c49a1611a70616579))

### Testing

- Increase app/api/google_drive.py coverage to 100%
  ([`14c9432`](https://github.com/christianlouis/DocuElevate/commit/14c94326402aed375a8178198ccd045f91765d74))

- Increase coverage for app/tasks/subscription_tasks.py to 100%
  ([`a580527`](https://github.com/christianlouis/DocuElevate/commit/a580527de454323f49b158929ceadb0c760bae33))

- Increase coverage for app/views/pipelines.py to 100%
  ([`344d20e`](https://github.com/christianlouis/DocuElevate/commit/344d20e4e63260e671118375ddfa811937b52c0c))

- Increase coverage for app/views/subscriptions.py to 100%
  ([`e96ddc7`](https://github.com/christianlouis/DocuElevate/commit/e96ddc78654ccc2f327f49eee587f6d62973532d))

- Increase url_upload.py test coverage to 100%
  ([`afe4227`](https://github.com/christianlouis/DocuElevate/commit/afe42270bb7dcbc23b4a8d7994899a18b0127d61))

- **subscriptions**: Add comprehensive API tests reaching 100% coverage
  ([`cd19ac6`](https://github.com/christianlouis/DocuElevate/commit/cd19ac661e84ff902bbbb3cc6a6fc78f3afb24c5))


## Unreleased

### Documentation

- **changelog**: Update changelog [skip ci]
  ([`53f7ab3`](https://github.com/christianlouis/DocuElevate/commit/53f7ab37d5e0242dd5b45b4327026c2dbca3c46d))

- **changelog**: Update changelog [skip ci]
  ([`754ea99`](https://github.com/christianlouis/DocuElevate/commit/754ea99092670b125ee9e689391b1decc085e007))

- **changelog**: Update changelog [skip ci]
  ([`8db0093`](https://github.com/christianlouis/DocuElevate/commit/8db0093562789925bb460300e83f2bd7c02753a2))

- **changelog**: Update changelog [skip ci]
  ([`2be09ef`](https://github.com/christianlouis/DocuElevate/commit/2be09efd99020b295a05da2c49a1611a70616579))

### Testing

- Increase app/api/google_drive.py coverage to 100%
  ([`14c9432`](https://github.com/christianlouis/DocuElevate/commit/14c94326402aed375a8178198ccd045f91765d74))

- Increase coverage for app/views/pipelines.py to 100%
  ([`344d20e`](https://github.com/christianlouis/DocuElevate/commit/344d20e4e63260e671118375ddfa811937b52c0c))

- Increase coverage for app/views/subscriptions.py to 100%
  ([`e96ddc7`](https://github.com/christianlouis/DocuElevate/commit/e96ddc78654ccc2f327f49eee587f6d62973532d))

- Increase url_upload.py test coverage to 100%
  ([`afe4227`](https://github.com/christianlouis/DocuElevate/commit/afe42270bb7dcbc23b4a8d7994899a18b0127d61))

- **subscriptions**: Add comprehensive API tests reaching 100% coverage
  ([`cd19ac6`](https://github.com/christianlouis/DocuElevate/commit/cd19ac661e84ff902bbbb3cc6a6fc78f3afb24c5))


## Unreleased

### Documentation

- **changelog**: Update changelog [skip ci]
  ([`754ea99`](https://github.com/christianlouis/DocuElevate/commit/754ea99092670b125ee9e689391b1decc085e007))

- **changelog**: Update changelog [skip ci]
  ([`8db0093`](https://github.com/christianlouis/DocuElevate/commit/8db0093562789925bb460300e83f2bd7c02753a2))

- **changelog**: Update changelog [skip ci]
  ([`2be09ef`](https://github.com/christianlouis/DocuElevate/commit/2be09efd99020b295a05da2c49a1611a70616579))

### Testing

- Increase app/api/google_drive.py coverage to 100%
  ([`14c9432`](https://github.com/christianlouis/DocuElevate/commit/14c94326402aed375a8178198ccd045f91765d74))

- Increase coverage for app/views/pipelines.py to 100%
  ([`344d20e`](https://github.com/christianlouis/DocuElevate/commit/344d20e4e63260e671118375ddfa811937b52c0c))

- Increase url_upload.py test coverage to 100%
  ([`afe4227`](https://github.com/christianlouis/DocuElevate/commit/afe42270bb7dcbc23b4a8d7994899a18b0127d61))

- **subscriptions**: Add comprehensive API tests reaching 100% coverage
  ([`cd19ac6`](https://github.com/christianlouis/DocuElevate/commit/cd19ac661e84ff902bbbb3cc6a6fc78f3afb24c5))


## Unreleased

### Documentation

- **changelog**: Update changelog [skip ci]
  ([`8db0093`](https://github.com/christianlouis/DocuElevate/commit/8db0093562789925bb460300e83f2bd7c02753a2))

- **changelog**: Update changelog [skip ci]
  ([`2be09ef`](https://github.com/christianlouis/DocuElevate/commit/2be09efd99020b295a05da2c49a1611a70616579))

### Testing

- Increase app/api/google_drive.py coverage to 100%
  ([`14c9432`](https://github.com/christianlouis/DocuElevate/commit/14c94326402aed375a8178198ccd045f91765d74))

- Increase coverage for app/views/pipelines.py to 100%
  ([`344d20e`](https://github.com/christianlouis/DocuElevate/commit/344d20e4e63260e671118375ddfa811937b52c0c))

- Increase url_upload.py test coverage to 100%
  ([`afe4227`](https://github.com/christianlouis/DocuElevate/commit/afe42270bb7dcbc23b4a8d7994899a18b0127d61))


## Unreleased

### Documentation

- **changelog**: Update changelog [skip ci]
  ([`2be09ef`](https://github.com/christianlouis/DocuElevate/commit/2be09efd99020b295a05da2c49a1611a70616579))

### Testing

- Increase app/api/google_drive.py coverage to 100%
  ([`14c9432`](https://github.com/christianlouis/DocuElevate/commit/14c94326402aed375a8178198ccd045f91765d74))

- Increase coverage for app/views/pipelines.py to 100%
  ([`344d20e`](https://github.com/christianlouis/DocuElevate/commit/344d20e4e63260e671118375ddfa811937b52c0c))


## Unreleased

### Testing

- Increase app/api/google_drive.py coverage to 100%
  ([`14c9432`](https://github.com/christianlouis/DocuElevate/commit/14c94326402aed375a8178198ccd045f91765d74))

- Increase coverage for app/views/pipelines.py to 100%
  ([`344d20e`](https://github.com/christianlouis/DocuElevate/commit/344d20e4e63260e671118375ddfa811937b52c0c))


## v0.93.0 (2026-03-08)

### Features

- **tests**: Increase test coverage for app/views/onboarding.py to 100%
  ([`ade7c9a`](https://github.com/christianlouis/DocuElevate/commit/ade7c9a86554be2bfbddb28b385c9769a9c91c88))

### Testing

- **local_auth**: Increase coverage for app/utils/local_auth.py to 100%
  ([`25c31a6`](https://github.com/christianlouis/DocuElevate/commit/25c31a63ff0a2682f0326174e1cd5276512983b8))


## v0.92.1 (2026-03-08)


## v0.92.0 (2026-03-08)

### Bug Fixes

- **admin-users**: Restore missing @router.get decorator on get_user endpoint
  ([`9b8eb91`](https://github.com/christianlouis/DocuElevate/commit/9b8eb911c3bf2b0be84a73030e82cff12151d4ba))

### Chores

- Update plan to include forgot-username and login label clarification
  ([`44ea43f`](https://github.com/christianlouis/DocuElevate/commit/44ea43f9cf948aabe8f8ae98744cd41061ab8770))

### Continuous Integration

- Fix CodeQL javascript language identifier mismatch
  ([`3f8a95d`](https://github.com/christianlouis/DocuElevate/commit/3f8a95d8081c4ce3ad380e6391afa3bebb57bbb7))

### Documentation

- **changelog**: Update changelog [skip ci]
  ([`f2d2aaa`](https://github.com/christianlouis/DocuElevate/commit/f2d2aaa3545081de1ff7317672199085daa3c3c0))

### Features

- **auth**: Password reset, forgot username, and admin user management for local accounts
  ([`d36ba88`](https://github.com/christianlouis/DocuElevate/commit/d36ba88de765b688888c6e661256f8508da86d89))


## v0.91.0 (2026-03-08)

### Features

- **backup**: Extend backup and restore to PostgreSQL and MySQL/MariaDB
  ([`a0f5ba1`](https://github.com/christianlouis/DocuElevate/commit/a0f5ba179978d7c63bbdb8c564a32eaf3f78e5ad))


## v0.90.3 (2026-03-08)

### Bug Fixes

- **email**: Create missing email template and decouple email destination settings
  ([`58c9b5d`](https://github.com/christianlouis/DocuElevate/commit/58c9b5d7f01941949db71b2816678ac6464d9d0f))


## v0.90.2 (2026-03-08)

### Bug Fixes

- **tasks**: Remove erroneous in_progress log that regressed finalize_document_storage status when
  PDF/A archival is enabled
  ([`ff1310c`](https://github.com/christianlouis/DocuElevate/commit/ff1310c23ed6080f95957bf19fdb7cc179d10ecb))


## v0.90.1 (2026-03-08)

### Bug Fixes

- **auth**: Return 401 for API paths in require_login to prevent wrong post-login redirect
  ([`3aa5364`](https://github.com/christianlouis/DocuElevate/commit/3aa5364e0ca3eaceb37616bb9b3a9a55fc08b223))


## v0.90.0 (2026-03-08)

### Features

- **watch-folders**: Add cloud provider watch folders (Dropbox, Drive, OneDrive, Nextcloud, S3,
  WebDAV)
  ([`9a9efae`](https://github.com/christianlouis/DocuElevate/commit/9a9efae19e9a8e6e4e43ced3426aa0b6a873597a))

- **watch-folders**: Add local/FTP/SFTP watch folder ingest with settings, tasks, tests, docs
  ([`bdb67de`](https://github.com/christianlouis/DocuElevate/commit/bdb67de5cbe2fb4832065c2958c41eba708ac8db))


## v0.89.1 (2026-03-08)

### Bug Fixes

- **ui**: Replace Tailwind v3-only peer toggles with Alpine.js-driven toggles in admin users modal
  ([`56f346a`](https://github.com/christianlouis/DocuElevate/commit/56f346ac20ea2146b281430a03c60bd8445b3bf1))


## v0.89.0 (2026-03-08)

### Bug Fixes

- **backup**: Address code review feedback - accessibility, CSRF, docs, imports
  ([`1877fc0`](https://github.com/christianlouis/DocuElevate/commit/1877fc0000490340e5d53e8654ba3116f545c444))

### Features

- **backup**: Add database backup/restore with scheduled retention and admin dashboard
  ([`2dd1ca0`](https://github.com/christianlouis/DocuElevate/commit/2dd1ca0197eaba2c9b6ca9b7083f8814401a8d0f))


## v0.88.2 (2026-03-08)

### Bug Fixes

- **auth**: Prevent None==None admin credential bypass creating phantom admin user
  ([`b95f552`](https://github.com/christianlouis/DocuElevate/commit/b95f552ed231d660303116b608b8f07b6a89fdc4))


## v0.88.1 (2026-03-08)

### Bug Fixes

- **ui**: Make pricing page CTAs link to /signup when local signup is enabled
  ([`db5f3d5`](https://github.com/christianlouis/DocuElevate/commit/db5f3d51d9f81b643f9c864c44d0dcc99df49963))


## v0.88.0 (2026-03-07)

### Bug Fixes

- **subscriptions**: Address code review feedback
  ([`72f96e3`](https://github.com/christianlouis/DocuElevate/commit/72f96e3c02256bce32031dd230e8fbff50269b9f))

### Features

- **notifications**: Admin push notifications and webhooks for user signup, plan changes, and
  payment issues
  ([`fdc48c7`](https://github.com/christianlouis/DocuElevate/commit/fdc48c7fe9825cf703624c7bba01fbc32b17ee66))

- **subscriptions**: Add subscription change management with upgrade/downgrade scheduling
  ([`231f983`](https://github.com/christianlouis/DocuElevate/commit/231f983429336046348bf98699dbcd808adf6b89))


## v0.87.0 (2026-03-07)

### Bug Fixes

- **docs**: Improve security and accessibility in help section
  ([`fe8e1c4`](https://github.com/christianlouis/DocuElevate/commit/fe8e1c41cc8ddb72d1130fa4d58a6b6ed3447704))

- **ui**: Move Help nav link outside auth conditional so it shows for all visitors
  ([`6390584`](https://github.com/christianlouis/DocuElevate/commit/63905842fde797a16c92c16a85fc291a15410ff9))

### Features

- **docs**: Add built-in help section with How-To guides embedded in app
  ([`46b2f17`](https://github.com/christianlouis/DocuElevate/commit/46b2f17acc4553b9b22856e254e6d50cdfc047f1))


## v0.86.0 (2026-03-07)

### Bug Fixes

- **ui**: Address code review feedback on complimentary badge and aria attributes
  ([`064ba72`](https://github.com/christianlouis/DocuElevate/commit/064ba72d361215c1370f0d3fd81ac04ff1624d2e))

### Features

- **auth**: Auto-create admin user profiles with highest tier and complimentary flag
  ([`97f85ce`](https://github.com/christianlouis/DocuElevate/commit/97f85ce74ed5d7970f330c923c7ae60ec299b7fd))


## v0.85.0 (2026-03-07)

### Bug Fixes

- **auth**: Restore get_user function body lost in refactor; fix button period placement
  ([`19c1ccb`](https://github.com/christianlouis/DocuElevate/commit/19c1ccb11c10698259fa01b408979b4fac158cd5))

- **ui**: Update plan descriptions to reflect per-user pricing
  ([`9d11d74`](https://github.com/christianlouis/DocuElevate/commit/9d11d741f4e6c0f29529d7dafc93980eea955aeb))

### Features

- **auth**: Enable local user signup without SMTP, add admin user creation
  ([`aa6e2fe`](https://github.com/christianlouis/DocuElevate/commit/aa6e2fe00157ed924d42ae305c932b04ad2c1a81))


## v0.84.0 (2026-03-07)

### Features

- **ui**: Show marketing landing page for unauthenticated multi-user visitors
  ([`68e8af9`](https://github.com/christianlouis/DocuElevate/commit/68e8af95545b3cda94e1b84383fc42ae584705b7))


## v0.83.0 (2026-03-07)

### Bug Fixes

- **tests**: Correct OCR subtask retry test to patch process_with_ocr instead of azure module
  ([`c485d44`](https://github.com/christianlouis/DocuElevate/commit/c485d4410d014d479230804ed7c51150a26ceab2))

### Code Style

- Apply ruff auto-fix
  ([`650a992`](https://github.com/christianlouis/DocuElevate/commit/650a9925c4d3754d553937a6eedd6e0ede8feb5c))

### Features

- **ui**: Redesign navigation for multi-user SaaS UX with pre/post-login visibility
  ([`dc1ee0e`](https://github.com/christianlouis/DocuElevate/commit/dc1ee0e2e5b5e4328783bc0f9c92ac8af546fd88))


## v0.82.0 (2026-03-07)

### Bug Fixes

- Address code review feedback
  ([`6a96705`](https://github.com/christianlouis/DocuElevate/commit/6a967051bada88cf66cf2df4edbabc215d41b588))

- Gate LocalUser machinery on multi_user_enabled for single-user backward compat
  ([`b5b285e`](https://github.com/christianlouis/DocuElevate/commit/b5b285ebe6c5c69a8b7557a045e40aa611e6e45a))

- Pricing page toggle and user auto-creation on OAuth login
  ([`dd207ee`](https://github.com/christianlouis/DocuElevate/commit/dd207eef9bdf738d6d6764df4ab6e8f5929801b5))

- Resolve merge conflict with main, fix test failures
  ([`b1ce28f`](https://github.com/christianlouis/DocuElevate/commit/b1ce28f804085df0f0e8211662deb6816484f14d))

- **auth**: Add WCAG 2.5.8 min-height to signup form inputs
  ([`43f3f6b`](https://github.com/christianlouis/DocuElevate/commit/43f3f6bdbe489f9018489dc3d6796a3f84567ab2))

- **tests**: Set multi_user_enabled=False in auth module tests that call auth() directly
  ([`6f197e6`](https://github.com/christianlouis/DocuElevate/commit/6f197e69fc04f3d5d00cf44ceb4cf5fd4c72a3d6))

### Documentation

- **changelog**: Update changelog [skip ci]
  ([`2317595`](https://github.com/christianlouis/DocuElevate/commit/2317595829b37f0c004d0a9d10809a5b6f9af77f))

- **changelog**: Update changelog [skip ci]
  ([`fa78a71`](https://github.com/christianlouis/DocuElevate/commit/fa78a714928e24cde6e0d66f8f2bf997d42efae3))

### Features

- Add multi-step user onboarding wizard
  ([`e0de0fd`](https://github.com/christianlouis/DocuElevate/commit/e0de0fd6fbd441ac45c4ad2483dd64565174958a))

- **auth**: Add local user signup, email verification, and Stripe billing
  ([`52e3852`](https://github.com/christianlouis/DocuElevate/commit/52e3852129f4b64a9813c3a4041c8826eece9e8c))

- **onboarding**: Add multi-step user onboarding wizard
  ([`99df081`](https://github.com/christianlouis/DocuElevate/commit/99df0816b06ef6a36bad8e38c4551b76ec00997c))

### Testing

- Improve coverage for app/api/plans.py from 38% to 100%
  ([`ac10ada`](https://github.com/christianlouis/DocuElevate/commit/ac10adac84811481ddafc8b596ff3dc84cd13351))

- **views**: Add 100% coverage tests for app/views/admin_users.py
  ([`7cebb82`](https://github.com/christianlouis/DocuElevate/commit/7cebb824122d9f69843ba6117e1d1efea878e65b))


## Unreleased

### Documentation

- **changelog**: Update changelog [skip ci]
  ([`fa78a71`](https://github.com/christianlouis/DocuElevate/commit/fa78a714928e24cde6e0d66f8f2bf997d42efae3))

### Testing

- Improve coverage for app/api/plans.py from 38% to 100%
  ([`ac10ada`](https://github.com/christianlouis/DocuElevate/commit/ac10adac84811481ddafc8b596ff3dc84cd13351))

- **views**: Add 100% coverage tests for app/views/admin_users.py
  ([`7cebb82`](https://github.com/christianlouis/DocuElevate/commit/7cebb824122d9f69843ba6117e1d1efea878e65b))


## Unreleased

### Testing

- **views**: Add 100% coverage tests for app/views/admin_users.py
  ([`7cebb82`](https://github.com/christianlouis/DocuElevate/commit/7cebb824122d9f69843ba6117e1d1efea878e65b))


## v0.81.0 (2026-03-07)

### Bug Fixes

- **pipelines**: Seed standard processing pipeline as system default on startup
  ([`d318110`](https://github.com/christianlouis/DocuElevate/commit/d318110bbe133e75a9cc3852d86295e6f682e2a4))

### Features

- **files**: Show assigned pipeline info on file status and detail views
  ([`a644efe`](https://github.com/christianlouis/DocuElevate/commit/a644efe016220af088654e6448b9429881bcc27b))

- **pipelines**: Add custom processing pipeline engine
  ([`89e0c2f`](https://github.com/christianlouis/DocuElevate/commit/89e0c2fb5055298aad40b9b493d37b95a7c0c480))

### Refactoring

- **pipelines**: Address code review - shared get_current_user_id, aria-live, deduplicate user ID
  logic
  ([`1203a4b`](https://github.com/christianlouis/DocuElevate/commit/1203a4b75fa56e80a8781700763ea3cb94943895))


## v0.80.0 (2026-03-07)

### Bug Fixes

- Add subscription_overage_percent to SETTING_METADATA and docs
  ([`9853a27`](https://github.com/christianlouis/DocuElevate/commit/9853a27d82a5c68ca01b9350365589837b0f8911))

- Resolve mypy and djlint CI failures
  ([`ab532b5`](https://github.com/christianlouis/DocuElevate/commit/ab532b55dcdf5bface2ac617db034c3d96b6a3ab))

- **api**: Move quota check before file write in ui-upload endpoint
  ([`45949f3`](https://github.com/christianlouis/DocuElevate/commit/45949f34c67696aa9cd453bfcb489d86c0392eba))

- **subscriptions**: Address code review feedback
  ([`7f521eb`](https://github.com/christianlouis/DocuElevate/commit/7f521eb755d92b306d84a612a5b74ee4ecf77dc2))

### Chores

- Plan dynamic plan designer feature
  ([`d439d9a`](https://github.com/christianlouis/DocuElevate/commit/d439d9afdd6e54a7a65a0b62b09a0a7db39cba3b))

- Plan pricing/limits overhaul with cost analysis
  ([`5351d82`](https://github.com/christianlouis/DocuElevate/commit/5351d822759636a9f4e1fcbfd5e126e4183dea91))

### Continuous Integration

- Merge quick and integration tests into a single test step
  ([`9670e84`](https://github.com/christianlouis/DocuElevate/commit/9670e8486251de8f83d4faefb4ca370ced7cd8f9))

### Documentation

- **changelog**: Update changelog [skip ci]
  ([`4277e5e`](https://github.com/christianlouis/DocuElevate/commit/4277e5ed5dee914ff555f2bfba90dc848dc81784))

### Features

- **subscriptions**: Add SaaS subscription tiers, pricing page, and enforced upload quotas
  ([`179f612`](https://github.com/christianlouis/DocuElevate/commit/179f6125e80d8abc5818eb1f4c32fd1c1538f3f1))

- **subscriptions**: Database-backed plan designer with admin CRUD and overage buffer
  ([`ea7fffa`](https://github.com/christianlouis/DocuElevate/commit/ea7fffa3a126ba819261be36052b8f609743df98))


## Unreleased

### Continuous Integration

- Merge quick and integration tests into a single test step
  ([`9670e84`](https://github.com/christianlouis/DocuElevate/commit/9670e8486251de8f83d4faefb4ca370ced7cd8f9))


## v0.79.0 (2026-03-06)

### Bug Fixes

- **ui**: Apply code review feedback on admin_users template accessibility
  ([`a00e67b`](https://github.com/christianlouis/DocuElevate/commit/a00e67b01f8174e1edb944ee9cb366a184c6c2bd))

### Documentation

- **changelog**: Update changelog [skip ci]
  ([`17b0f37`](https://github.com/christianlouis/DocuElevate/commit/17b0f3762c7424e967095049c080ecaeaa21d3a3))

- **changelog**: Update changelog [skip ci]
  ([`299ae98`](https://github.com/christianlouis/DocuElevate/commit/299ae98ebdfa25c2c2b6cfc0dbebc36f82ecaedf))

- **changelog**: Update changelog [skip ci]
  ([`158b113`](https://github.com/christianlouis/DocuElevate/commit/158b113ac9b1ef7dae013d59e02a6e83682d9c0a))

### Features

- **auth**: Add admin user management dashboard
  ([`56f7f23`](https://github.com/christianlouis/DocuElevate/commit/56f7f2351f38e4423ffe2e3f5814064aa189c56e))

### Testing

- Improve coverage for app/views/files.py from 59.67% to 99.35%
  ([`aab1c5f`](https://github.com/christianlouis/DocuElevate/commit/aab1c5fda96e3e6be37f23094d722ba4079c388f))

- Improve coverage for extract_metadata_with_gpt to 100%
  ([`b901576`](https://github.com/christianlouis/DocuElevate/commit/b9015764c5cd72954755ec7e77d54eba82d04c7e))

- Improve test coverage for app/utils/step_manager.py
  ([`ed404b4`](https://github.com/christianlouis/DocuElevate/commit/ed404b46610929eb750764a98c4f0b7361cb0903))

- **similarity**: Improve test coverage for app/utils/similarity.py to 100%
  ([`7acac42`](https://github.com/christianlouis/DocuElevate/commit/7acac4225bc4383a943d9da644b44e83484249d2))


## Unreleased

### Documentation

- **changelog**: Update changelog [skip ci]
  ([`299ae98`](https://github.com/christianlouis/DocuElevate/commit/299ae98ebdfa25c2c2b6cfc0dbebc36f82ecaedf))

- **changelog**: Update changelog [skip ci]
  ([`158b113`](https://github.com/christianlouis/DocuElevate/commit/158b113ac9b1ef7dae013d59e02a6e83682d9c0a))

### Testing

- Improve coverage for app/views/files.py from 59.67% to 99.35%
  ([`aab1c5f`](https://github.com/christianlouis/DocuElevate/commit/aab1c5fda96e3e6be37f23094d722ba4079c388f))

- Improve coverage for extract_metadata_with_gpt to 100%
  ([`b901576`](https://github.com/christianlouis/DocuElevate/commit/b9015764c5cd72954755ec7e77d54eba82d04c7e))

- Improve test coverage for app/utils/step_manager.py
  ([`ed404b4`](https://github.com/christianlouis/DocuElevate/commit/ed404b46610929eb750764a98c4f0b7361cb0903))

- **similarity**: Improve test coverage for app/utils/similarity.py to 100%
  ([`7acac42`](https://github.com/christianlouis/DocuElevate/commit/7acac4225bc4383a943d9da644b44e83484249d2))


## Unreleased

### Documentation

- **changelog**: Update changelog [skip ci]
  ([`158b113`](https://github.com/christianlouis/DocuElevate/commit/158b113ac9b1ef7dae013d59e02a6e83682d9c0a))

### Testing

- Improve coverage for app/views/files.py from 59.67% to 99.35%
  ([`aab1c5f`](https://github.com/christianlouis/DocuElevate/commit/aab1c5fda96e3e6be37f23094d722ba4079c388f))

- Improve coverage for extract_metadata_with_gpt to 100%
  ([`b901576`](https://github.com/christianlouis/DocuElevate/commit/b9015764c5cd72954755ec7e77d54eba82d04c7e))

- Improve test coverage for app/utils/step_manager.py
  ([`ed404b4`](https://github.com/christianlouis/DocuElevate/commit/ed404b46610929eb750764a98c4f0b7361cb0903))

- **similarity**: Improve test coverage for app/utils/similarity.py to 100%
  ([`7acac42`](https://github.com/christianlouis/DocuElevate/commit/7acac4225bc4383a943d9da644b44e83484249d2))


## Unreleased

### Testing

- Improve coverage for extract_metadata_with_gpt to 100%
  ([`b901576`](https://github.com/christianlouis/DocuElevate/commit/b9015764c5cd72954755ec7e77d54eba82d04c7e))


## v0.78.1 (2026-03-06)

### Bug Fixes

- **views**: Resolve mypy TemplateResponse typing and owner fallback
  ([`575b4e0`](https://github.com/christianlouis/DocuElevate/commit/575b4e088e77513468ffd1742f684a2623576d02))


## v0.78.0 (2026-03-06)

### Bug Fixes

- Address code review feedback
  ([`507c333`](https://github.com/christianlouis/DocuElevate/commit/507c333c15daa6e2bc5c1cce10d916dc82894b8e))

- Address code review — use modern type hints and Callable annotation
  ([`c8bc4af`](https://github.com/christianlouis/DocuElevate/commit/c8bc4afc9381a4d49455da5eefaf49d84c02ed3d))

- **tests**: Add missing mock settings attrs in test_original_filename_preservation
  ([`f4b793e`](https://github.com/christianlouis/DocuElevate/commit/f4b793e9b8eae37f5917ed8a057e90ad0a36ade2))

### Chores

- Plan general autocomplete widget for settings
  ([`3fd2bb3`](https://github.com/christianlouis/DocuElevate/commit/3fd2bb3c5f50148a5e668c9c648dd272c5167e1f))

### Code Style

- Apply ruff auto-fix
  ([`330c3ae`](https://github.com/christianlouis/DocuElevate/commit/330c3aedb6c2207c717415be86b3544d12c94d01))

### Documentation

- **database**: Add wizard and migration tool documentation
  ([`cb3bf80`](https://github.com/christianlouis/DocuElevate/commit/cb3bf809ccf75b77d9db9295b6a33c16af9a3e78))

- **database**: Update configuration guides with wizard cross-references, clean up review feedback
  ([`7dae15f`](https://github.com/christianlouis/DocuElevate/commit/7dae15fd29823a9d2a1843613c14d81cf1eedebd))

### Features

- **database**: Add database configuration wizard and migration tool
  ([`f6fcaae`](https://github.com/christianlouis/DocuElevate/commit/f6fcaaecccf885203ef76add850de424233de9b4))

- **database**: Integrate wizard into settings page, improve accessibility and test coverage
  ([`174e489`](https://github.com/christianlouis/DocuElevate/commit/174e4890dd22b69ef39cfeeaf2421c409e096878))

- **multi-user**: Add multi-user feature flag, owner_id model field, and user-scoped queries
  ([`71f437e`](https://github.com/christianlouis/DocuElevate/commit/71f437e43aa95788d2dc8c57725fa3842816ad96))

- **multi-user**: Add unclaimed doc visibility, claim/assign-owner endpoints, default_owner_id
  ([`5722252`](https://github.com/christianlouis/DocuElevate/commit/5722252dcb46b498f402bef17361f4741a9698ef))

- **settings**: Add dynamic autocomplete for AWS/Azure regions, OCR langs, and embedding models
  ([`62d7ad7`](https://github.com/christianlouis/DocuElevate/commit/62d7ad7e9ec8ff6f8239199bc5b69a737cfba49a))

- **ui**: Add user autocomplete widget for default_owner_id, user search API, and documentation
  ([`3601e2c`](https://github.com/christianlouis/DocuElevate/commit/3601e2ca5ccb475b47aa5a18fd9c0a6b8de012bc))

### Refactoring

- **multi-user**: Address code review - module imports, explicit false(), string length
  ([`a8d44b1`](https://github.com/christianlouis/DocuElevate/commit/a8d44b189c4212144fe5f772f89e2a6f8f05501c))

### Testing

- **multi-user**: Add comprehensive tests for multi-user isolation and feature flag
  ([`d7b7f14`](https://github.com/christianlouis/DocuElevate/commit/d7b7f1478f971c25e795e4beaa291042bea5a592))


## v0.77.2 (2026-03-02)

### Bug Fixes

- **upload**: Fix upload progress counter showing done count always as 0
  ([`3be1fa5`](https://github.com/christianlouis/DocuElevate/commit/3be1fa504023e15b38cdfe60da2b1c99b35bef42))


## v0.77.1 (2026-03-02)

### Bug Fixes

- **tasks**: Register missing Celery tasks in celery_worker.py
  ([`14adbee`](https://github.com/christianlouis/DocuElevate/commit/14adbeeabb2e37937fe2b46c71a6cfb75cce4320))


## v0.77.0 (2026-03-02)

### Bug Fixes

- **ui**: Address code review feedback for settings page
  ([`b8bd049`](https://github.com/christianlouis/DocuElevate/commit/b8bd049dffdf49495c76d1cda45d74a8f8be6f12))

### Features

- **ui**: Redesign settings page with modern UX improvements
  ([`6ff1da2`](https://github.com/christianlouis/DocuElevate/commit/6ff1da2496e3448b3ba1644d3edc71251b3d3e6b))


## v0.76.0 (2026-03-02)

### Documentation

- **settings**: Update SettingsManagement.md with new categories and setting types
  ([`3080e37`](https://github.com/christianlouis/DocuElevate/commit/3080e37ddf3d93f75584f488fa84e87d7028797c))

### Features

- **settings**: Add all missing config settings to settings page with enhanced UX
  ([`a259262`](https://github.com/christianlouis/DocuElevate/commit/a2592629dbe07226097a34f4c1794554c7ce3f23))


## v0.75.0 (2026-03-02)

### Code Style

- Apply ruff auto-fix
  ([`fea8f5c`](https://github.com/christianlouis/DocuElevate/commit/fea8f5c0de6fcc6a050bbcd5c9bfb3f6b1268e64))


## v0.74.0 (2026-03-02)

### Bug Fixes

- **similarity**: Address code review - column-only queries, configurable batch size, WCAG touch
  targets
  ([`55543be`](https://github.com/christianlouis/DocuElevate/commit/55543be3b0918160ec437d5ddae760af7f074c8a))

- **similarity**: Truncate text to fit embedding model context window, fix step tracking
  ([`8e955f3`](https://github.com/christianlouis/DocuElevate/commit/8e955f3c81764708053f34a57557664f8b356c2a))

### Features

- **similarity**: Add embedding pipeline, debug endpoints, backfill task, and scalable similarity
  search
  ([`8d7c8e7`](https://github.com/christianlouis/DocuElevate/commit/8d7c8e7c4ebeb6bb233d681e31f9bfb08ac32775))

- **similarity**: Add similarity pairs dashboard, step tracking, and fix tests for pre-computed
  embeddings
  ([`c724b8d`](https://github.com/christianlouis/DocuElevate/commit/c724b8d83a063619aaa0af50156e872b3a205a28))


## v0.73.0 (2026-03-02)

### Features

- **duplicates**: Add duplicate document detection and management
  ([`ebea83a`](https://github.com/christianlouis/DocuElevate/commit/ebea83a750022f9722e548ba8a6ecea179ac2d8b))


## v0.72.1 (2026-03-02)

### Bug Fixes

- **database**: Skip create_all for Alembic-tracked databases to prevent OperationalError on
  webhook_configs
  ([`b87dd60`](https://github.com/christianlouis/DocuElevate/commit/b87dd6083cdf43835e435cf6d2fa32f9ca7ca60d))


## v0.72.0 (2026-03-02)

### Bug Fixes

- **migrations**: Resolve multiple Alembic heads causing CI test crash
  ([`f7cf7e2`](https://github.com/christianlouis/DocuElevate/commit/f7cf7e2a4c47e02658831e84acd20ce659c209d6))

### Continuous Integration

- Optimize pipeline for fail-fast feedback loop
  ([`ea0f7fb`](https://github.com/christianlouis/DocuElevate/commit/ea0f7fb54fd081d2e2a8e0b97a2a82accfe1bc52))

### Documentation

- **changelog**: Update changelog [skip ci]
  ([`744a433`](https://github.com/christianlouis/DocuElevate/commit/744a433cc97a341cd431fd79def7e7ba2e62ca75))

- **changelog**: Update changelog [skip ci]
  ([`fe9f84a`](https://github.com/christianlouis/DocuElevate/commit/fe9f84ac05da73f764c6972ff1b32b8b4d0b5c5f))

- **changelog**: Update changelog [skip ci]
  ([`3d38813`](https://github.com/christianlouis/DocuElevate/commit/3d38813da5c2c911e379303aa8e58449479962f8))

- **changelog**: Update changelog [skip ci]
  ([`ed85797`](https://github.com/christianlouis/DocuElevate/commit/ed8579757cf17b696e70505fefb543ee26837aaa))

- **similarity**: Add API documentation and fix template accessibility
  ([`b7c7817`](https://github.com/christianlouis/DocuElevate/commit/b7c78177e9d02714a46c328ca99f8820dcb27b18))

### Features

- **similarity**: Add document similarity detection with embeddings and cosine similarity
  ([`9748103`](https://github.com/christianlouis/DocuElevate/commit/974810378251a8ca33aa2d43c34e7567cdf1a574))


## Unreleased

### Continuous Integration

- Optimize pipeline for fail-fast feedback loop
  ([`ea0f7fb`](https://github.com/christianlouis/DocuElevate/commit/ea0f7fb54fd081d2e2a8e0b97a2a82accfe1bc52))

### Documentation

- **changelog**: Update changelog [skip ci]
  ([`fe9f84a`](https://github.com/christianlouis/DocuElevate/commit/fe9f84ac05da73f764c6972ff1b32b8b4d0b5c5f))

- **changelog**: Update changelog [skip ci]
  ([`3d38813`](https://github.com/christianlouis/DocuElevate/commit/3d38813da5c2c911e379303aa8e58449479962f8))

- **changelog**: Update changelog [skip ci]
  ([`ed85797`](https://github.com/christianlouis/DocuElevate/commit/ed8579757cf17b696e70505fefb543ee26837aaa))


## Unreleased

### Continuous Integration

- Optimize pipeline for fail-fast feedback loop
  ([`ea0f7fb`](https://github.com/christianlouis/DocuElevate/commit/ea0f7fb54fd081d2e2a8e0b97a2a82accfe1bc52))

### Documentation

- **changelog**: Update changelog [skip ci]
  ([`3d38813`](https://github.com/christianlouis/DocuElevate/commit/3d38813da5c2c911e379303aa8e58449479962f8))

- **changelog**: Update changelog [skip ci]
  ([`ed85797`](https://github.com/christianlouis/DocuElevate/commit/ed8579757cf17b696e70505fefb543ee26837aaa))


## Unreleased

### Continuous Integration

- Optimize pipeline for fail-fast feedback loop
  ([`ea0f7fb`](https://github.com/christianlouis/DocuElevate/commit/ea0f7fb54fd081d2e2a8e0b97a2a82accfe1bc52))

### Documentation

- **changelog**: Update changelog [skip ci]
  ([`ed85797`](https://github.com/christianlouis/DocuElevate/commit/ed8579757cf17b696e70505fefb543ee26837aaa))


## Unreleased


## v0.71.0 (2026-03-01)

### Documentation

- **webhooks**: Add webhook API and configuration documentation
  ([`a953b72`](https://github.com/christianlouis/DocuElevate/commit/a953b726fcd9da1738e6b90fdd913556457c37a7))

- **webhooks**: Fix spelling - Behaviour to Behavior
  ([`a85992e`](https://github.com/christianlouis/DocuElevate/commit/a85992ee79e2bbe3177fe0126b49e99b932508fc))

### Features

- **webhooks**: Add webhook support for external integrations
  ([`e609141`](https://github.com/christianlouis/DocuElevate/commit/e60914127c62dfb294c3cda968492893f5051228))


## v0.70.0 (2026-03-01)

### Features

- **release**: Add named release anchors with codenames and roadmap integration
  ([`d18c109`](https://github.com/christianlouis/DocuElevate/commit/d18c10996aa922d12d1bc1807ec18ca7974a4e5e))

### Refactoring

- **test**: Simplify test patches per code review feedback
  ([`61d7639`](https://github.com/christianlouis/DocuElevate/commit/61d7639129e1db8416226fc3a5b41c83299489ee))


## v0.69.0 (2026-03-01)

### Documentation

- **changelog**: Update changelog [skip ci]
  ([`32ea0c8`](https://github.com/christianlouis/DocuElevate/commit/32ea0c89494f9b558b513efda2f47505ebebce2b))

- **changelog**: Update changelog [skip ci]
  ([`1775c4e`](https://github.com/christianlouis/DocuElevate/commit/1775c4e0ddb678cabfd80d04acc4ad1b08761e17))

### Features

- **api**: Add GET /api/diagnostic/health endpoint for monitoring
  ([`85da309`](https://github.com/christianlouis/DocuElevate/commit/85da30974020efabcd2bab525e74bc846ddd7edd))

- **tasks**: Add retry logic with exponential backoff and jitter
  ([`5ff7b72`](https://github.com/christianlouis/DocuElevate/commit/5ff7b72a800011bb3ea676994ac0326a3acf93e3))

### Testing

- Increase code coverage for app/views/wizard.py to 100%
  ([`bf337a1`](https://github.com/christianlouis/DocuElevate/commit/bf337a15609d7aac008d68de7ca7398554b954ab))

- **status**: Increase code coverage for app/views/status.py to 100%
  ([`1095b41`](https://github.com/christianlouis/DocuElevate/commit/1095b415797583f52fd49c94c9d6b652e173f5ef))


## Unreleased

### Documentation

- **changelog**: Update changelog [skip ci]
  ([`1775c4e`](https://github.com/christianlouis/DocuElevate/commit/1775c4e0ddb678cabfd80d04acc4ad1b08761e17))

### Testing

- Increase code coverage for app/views/wizard.py to 100%
  ([`bf337a1`](https://github.com/christianlouis/DocuElevate/commit/bf337a15609d7aac008d68de7ca7398554b954ab))

- **status**: Increase code coverage for app/views/status.py to 100%
  ([`1095b41`](https://github.com/christianlouis/DocuElevate/commit/1095b415797583f52fd49c94c9d6b652e173f5ef))


## Unreleased


## v0.68.0 (2026-03-01)

### Features

- **api**: Implement proper pagination for file list API
  ([`af34ce8`](https://github.com/christianlouis/DocuElevate/commit/af34ce88dfadb0c288120995356605a3e70d3ec4))


## v0.67.3 (2026-03-01)

### Bug Fixes

- **docker**: Copy migrations directory and alembic.ini into Docker image
  ([`3d71d2b`](https://github.com/christianlouis/DocuElevate/commit/3d71d2b36275386f60edba1d132da1d73a18756d))


## v0.67.2 (2026-03-01)

### Bug Fixes

- Address code review feedback - use specific exceptions, dynamic revision IDs in tests
  ([`8d81ed6`](https://github.com/christianlouis/DocuElevate/commit/8d81ed6c745a7eefe890c5dbfa5ba826a8357cee))

- **ci**: Add pytest-timeout, fix hanging test, split CI into quick + integration stages
  ([`6c643e9`](https://github.com/christianlouis/DocuElevate/commit/6c643e99624b113a040f92d2f2881736e496f287))

- **ci**: Increase quick test job timeout to 15 minutes for CI runner headroom
  ([`6a21adc`](https://github.com/christianlouis/DocuElevate/commit/6a21adcdd47c38e0b1e9a9cc67a0b730de75936c))

### Documentation

- Update CI workflow and integration test documentation for two-stage pipeline
  ([`c100250`](https://github.com/christianlouis/DocuElevate/commit/c100250b23390e9f85ab8231ff5cfa6eac9274f6))

### Refactoring

- **database**: Enforce Alembic-only database migrations, deprecate manual schema migrations
  ([`87d1b9d`](https://github.com/christianlouis/DocuElevate/commit/87d1b9d93503b4f8b54f7556fa4e01fd58a92be5))


## v0.67.1 (2026-03-01)

### Bug Fixes

- Add type: ignore for redis.scan() mypy false positive in cache.py
  ([`d45d0a4`](https://github.com/christianlouis/DocuElevate/commit/d45d0a424e01297c5eb2f9f40b262081f40c7876))

- **db**: Check column existence before creating performance indexes
  ([`febdf41`](https://github.com/christianlouis/DocuElevate/commit/febdf414694e65080b51feac0aecfb48ec8023df))

### Code Style

- Fix spelling (British to American English)
  ([`ce87b53`](https://github.com/christianlouis/DocuElevate/commit/ce87b533314a73297195652ff0d6bc01ec3b880b))

### Documentation

- Add Performance & Caching section to ConfigurationGuide
  ([`d5a95e9`](https://github.com/christianlouis/DocuElevate/commit/d5a95e92704cc86e10318cb6cd33c8641b8aa553))

### Performance Improvements

- **db**: Add indexes on query-hot columns and Redis caching layer
  ([`b79ba81`](https://github.com/christianlouis/DocuElevate/commit/b79ba81e050df79d6df39390f63120deffe499de))


## v0.67.0 (2026-03-01)

### Features

- **imap**: Add IMAP_READONLY_MODE feature flag to safeguard shared mailboxes
  ([`f8c5dd5`](https://github.com/christianlouis/DocuElevate/commit/f8c5dd539d627569231bbed828acab96be9aa485))


## v0.66.0 (2026-03-01)

### Code Style

- **search**: Address code review - use const/let, fix date timezone, deduplicate filter keys
  ([`68857c1`](https://github.com/christianlouis/DocuElevate/commit/68857c1785d068e3716ea40c18f54d8ada296c97))

### Documentation

- Update API and User Guide with search filters and saved searches
  ([`de09dba`](https://github.com/christianlouis/DocuElevate/commit/de09dba28532af549b25dfdc35384a71aa1c223c))

### Features

- **search**: Add content-finding filters, saved searches, and text quality to Search view
  ([`5bf0a4c`](https://github.com/christianlouis/DocuElevate/commit/5bf0a4c0b990c3c4915696ae01448bf1ca12f87b))


## v0.65.0 (2026-03-01)

### Features

- Add bulk download, cloud OCR, and basic OCR quality filter
  ([`705b970`](https://github.com/christianlouis/DocuElevate/commit/705b9705222e37c28a0ae235c23e9f0ac80ccf38))

- Persist ocr_quality_score and use it for numeric filtering
  ([`83c3405`](https://github.com/christianlouis/DocuElevate/commit/83c3405c986700b079a1f8167ebbebfe23e7aa7f))


## v0.64.1 (2026-03-01)

### Bug Fixes

- Append new drops to upload queue instead of overwriting it
  ([`81c08ed`](https://github.com/christianlouis/DocuElevate/commit/81c08ed9d0c016f4fe9603c74c969c0c85468d82))


## v0.64.0 (2026-03-01)

### Features

- **api**: Default download endpoint to processed file version
  ([`7b5494b`](https://github.com/christianlouis/DocuElevate/commit/7b5494bafbb354eb457a393682d9686de4a6af98))


## v0.63.0 (2026-03-01)

### Bug Fixes

- **api**: Address code review feedback - logging, wildcard escaping, UX
  ([`d5884f6`](https://github.com/christianlouis/DocuElevate/commit/d5884f6d2cf98b6419fcc38e7fcdec7988195ec8))

- **db**: Add saved_searches table to runtime schema migrations
  ([`82f7113`](https://github.com/christianlouis/DocuElevate/commit/82f7113d39986e773afd66184af4001491d2b05d))

### Documentation

- **api**: Document advanced filtering and saved searches endpoints
  ([`cc9fd1a`](https://github.com/christianlouis/DocuElevate/commit/cc9fd1a7fe78d05f6effb324f8bcc5377e11fe9f))

### Features

- **api**: Add advanced filtering and saved searches
  ([`e5a4c6c`](https://github.com/christianlouis/DocuElevate/commit/e5a4c6c64ada140f64980b74cabb3bd5ed0bb895))


## v0.62.0 (2026-03-01)

### Bug Fixes

- Address code review feedback on tests and placeholder messages
  ([`d095e30`](https://github.com/christianlouis/DocuElevate/commit/d095e3046768ba908775b4d09c9b957fd89ccd42))

- **ui**: Preview modal falls back to original version when processed unavailable
  ([`c814af1`](https://github.com/christianlouis/DocuElevate/commit/c814af11450d880ea4b6ce634dfde099b74664ca))

### Features

- **ui**: Add pdf.js viewer, image zoom/pan, text preview, and preview modal
  ([`372e8cd`](https://github.com/christianlouis/DocuElevate/commit/372e8cdff1a43892e82b485e6e4e7a6248010a1f))

### Testing

- **preview**: Add 23 tests for document preview features
  ([`7a8ccba`](https://github.com/christianlouis/DocuElevate/commit/7a8ccba9be7bc119ec10169737f0b37767bcbf68))


## v0.61.0 (2026-02-28)

### Continuous Integration

- **a11y**: Add djlint HTML accessibility lint to CI pipeline
  ([`1968a0e`](https://github.com/christianlouis/DocuElevate/commit/1968a0e481635c6dc91cae6fc76247291b18dee5))

### Documentation

- **a11y**: Add comprehensive AccessibilityGuide.md
  ([`1f48503`](https://github.com/christianlouis/DocuElevate/commit/1f48503217ca7d5108c4f5409553a4226b372493))

### Features

- **ui**: Add accessibility foundations to base.html and styles.css
  ([`364ff93`](https://github.com/christianlouis/DocuElevate/commit/364ff9375a90f4f5f719cb5a931a4c15efc090e3))

- **ui**: Add ARIA attributes for accessibility improvements
  ([`0969436`](https://github.com/christianlouis/DocuElevate/commit/0969436abda8edd691f759e9cf00cce257571357))

- **ui**: Fix accessibility in upload, search, files, and login templates
  ([`bf6bbe3`](https://github.com/christianlouis/DocuElevate/commit/bf6bbe35126266fb8375b3098d86d7df15692573))


## v0.60.4 (2026-02-28)

### Bug Fixes

- **api**: Use processed_file_path from DB in upload retry path resolution
  ([`bb98afa`](https://github.com/christianlouis/DocuElevate/commit/bb98afac826a955770744c93141e22a671f08d94))

### Testing

- Improve upload retry tests with legacy path assertions and priority verification
  ([`2f442b0`](https://github.com/christianlouis/DocuElevate/commit/2f442b0906b4f2befed18795f798789228eac8d3))


## v0.60.3 (2026-02-28)

### Bug Fixes

- Address code review feedback - restrict terminal step check to success only, add test assertions
  ([`4fdb1b8`](https://github.com/christianlouis/DocuElevate/commit/4fdb1b8d85c43d51d7a703675e199fba4e121626))

- **tasks**: Resolve files stuck in Pending status despite completed processing
  ([`2c55f07`](https://github.com/christianlouis/DocuElevate/commit/2c55f076be6ffe167f54d1e660bb2448385f090b))


## v0.60.2 (2026-02-27)

### Bug Fixes

- **upload**: Fix multi-file drag-and-drop only uploading one file
  ([`dc9aec2`](https://github.com/christianlouis/DocuElevate/commit/dc9aec2bab43e7b6ef2f85205a1d9742109aa78d))


## v0.60.1 (2026-02-27)

### Bug Fixes

- **status**: Prevent false Completed status when mandatory pipeline steps have not run
  ([`e6dd39c`](https://github.com/christianlouis/DocuElevate/commit/e6dd39c27d4b8e77a9c546c911eace2783b47068))

- **status**: Simplify terminal step guard condition in get_step_summary
  ([`baa412b`](https://github.com/christianlouis/DocuElevate/commit/baa412b172b5fb19292481fb4155442bf6f4296e))

### Testing

- Add send_to_all_destinations step to test_status_filter_completed
  ([`aba47af`](https://github.com/christianlouis/DocuElevate/commit/aba47af30a180126035752f7026f1b33ff07e72d))

- Update 3 tests broken by terminal-step completed guard
  ([`9795ca0`](https://github.com/christianlouis/DocuElevate/commit/9795ca0d52675c15ef7c7ff8f6a93421dc89c6c4))


## v0.60.0 (2026-02-27)

### Features

- **queue**: Add queue monitoring dashboard and pending banner on files page
  ([`c7c5718`](https://github.com/christianlouis/DocuElevate/commit/c7c5718f78ce89466fffdc9ce2f1fdbe88f7ab9e))

### Refactoring

- **queue**: Address code review feedback — extract constants and sync refresh interval
  ([`4dd018f`](https://github.com/christianlouis/DocuElevate/commit/4dd018f21011b16be66b22b35a877e6f97959eae))


## v0.59.1 (2026-02-27)

### Bug Fixes

- **api**: Use stored file paths for preview and download endpoints
  ([`cded734`](https://github.com/christianlouis/DocuElevate/commit/cded73481efcdce3359b71ec474cf7105ebef717))


## v0.59.0 (2026-02-26)

### Bug Fixes

- **test**: Update drop overlay text assertion to match new directory-upload message
  ([`4a251fd`](https://github.com/christianlouis/DocuElevate/commit/4a251fd3ca11100df21f6ace5ffb3496c7125d71))

### Features

- **upload**: Adaptive 429 backoff, full Gotenberg file types, directory traversal
  ([`a05690b`](https://github.com/christianlouis/DocuElevate/commit/a05690bd5fb6f79818ccf88079e96ae44b5b99d9))

- **upload**: Add directory traversal, queue throttling, and upload config settings
  ([`35d2ed0`](https://github.com/christianlouis/DocuElevate/commit/35d2ed05e9ed589cc70ced4d1b76dc3b9a85ca41))


## v0.58.0 (2026-02-26)

### Bug Fixes

- **search**: Correct file detail page URL in search results
  ([`da865b5`](https://github.com/christianlouis/DocuElevate/commit/da865b5f7aa5f51b69432c060d04018381970a23))

### Features

- **views**: Add document-centric view at /files/{id}
  ([`c540dd4`](https://github.com/christianlouis/DocuElevate/commit/c540dd4f5209644b4d450c006c78e85c4c5d422e))


## v0.57.4 (2026-02-26)

### Bug Fixes

- **tests**: Fix OAuth integration tests failing due to Docker registry timeout
  ([`36b6680`](https://github.com/christianlouis/DocuElevate/commit/36b668020bfe32531250d390b3b69f2934c0bcad))

- **tests**: Fix test_save_settings_outer_exception in OneDrive coverage tests
  ([`b4e93c0`](https://github.com/christianlouis/DocuElevate/commit/b4e93c00b47f085b6c86c8de2c8dfe8774789ea1))

- **tests**: Fix TestGetFullConfigException using PropertyMock on module-level settings
  ([`44dcabd`](https://github.com/christianlouis/DocuElevate/commit/44dcabd1f3781dfe363884314a4f4c25b1173e1a))


## v0.57.3 (2026-02-26)

### Bug Fixes

- **tests**: Correct mock patch targets in google_drive coverage tests
  ([`096aedb`](https://github.com/christianlouis/DocuElevate/commit/096aedb8a0ea3988a8072634647cfc3b1def0309))

- **tests**: Use targeted settings mock instead of broad getattr patch
  ([`c6ac6b5`](https://github.com/christianlouis/DocuElevate/commit/c6ac6b50e998876543a2f167f126ff064c29ec16))

### Testing

- **coverage**: Add celery_worker coverage and remove dead config_validator.py
  ([`ffa0e1e`](https://github.com/christianlouis/DocuElevate/commit/ffa0e1eb7bf9a945fee63b7c6623ac45e733e4c6))


## v0.57.2 (2026-02-26)

### Bug Fixes

- **ui**: Prevent search input from clearing on each keystroke and add dedicated /search page
  ([`09a6337`](https://github.com/christianlouis/DocuElevate/commit/09a6337c6f6957f49a0b72be50d660f6119a81e3))

- **ui**: Sanitize Meilisearch HTML output, use event delegation, improve error messages
  ([`483a5b7`](https://github.com/christianlouis/DocuElevate/commit/483a5b71a1303acec165b971105e4a76dfbcfdfa))

### Documentation

- **search**: Update UserGuide with search page documentation and fix import order
  ([`e9dd3ef`](https://github.com/christianlouis/DocuElevate/commit/e9dd3ef1c283dd9d8c626b285313f0cece5909e2))


## v0.57.1 (2026-02-26)

### Bug Fixes

- Regenerate logo PNGs from SVG to fix DocuNova → DocuElevate branding
  ([`d83dfb1`](https://github.com/christianlouis/DocuElevate/commit/d83dfb12c69b56c2fb7d37c11588a13bbdc82441))

### Code Style

- Apply ruff auto-fix
  ([`69cb16c`](https://github.com/christianlouis/DocuElevate/commit/69cb16c522f4571f6171a7352aff3fa7efe94de4))

### Documentation

- **changelog**: Update changelog [skip ci]
  ([`d86dda9`](https://github.com/christianlouis/DocuElevate/commit/d86dda94317d09d285a4da1c7a1cffc34288beab))

- **changelog**: Update changelog [skip ci]
  ([`62e4521`](https://github.com/christianlouis/DocuElevate/commit/62e4521f3cc90d09c8977ce77d78e5978b0eaa71))

### Testing

- Improve coverage for process_with_ocr, api/settings, and settings_service to 90%+
  ([`d9abbc1`](https://github.com/christianlouis/DocuElevate/commit/d9abbc1c998668ffae485493f27e82aed4fd1527))

- **coverage**: Add coverage tests for app/api/onedrive.py and app/api/google_drive.py
  ([`e3cd687`](https://github.com/christianlouis/DocuElevate/commit/e3cd687757bfa97f688880787ff33960259146cd))

- **coverage**: Add tests to push coverage above 95% for 11 target files
  ([`759647f`](https://github.com/christianlouis/DocuElevate/commit/759647f9577e9afd57313cefe8731b6502bcca77))


## Unreleased

### Code Style

- Apply ruff auto-fix
  ([`69cb16c`](https://github.com/christianlouis/DocuElevate/commit/69cb16c522f4571f6171a7352aff3fa7efe94de4))

### Documentation

- **changelog**: Update changelog [skip ci]
  ([`62e4521`](https://github.com/christianlouis/DocuElevate/commit/62e4521f3cc90d09c8977ce77d78e5978b0eaa71))

### Testing

- Improve coverage for process_with_ocr, api/settings, and settings_service to 90%+
  ([`d9abbc1`](https://github.com/christianlouis/DocuElevate/commit/d9abbc1c998668ffae485493f27e82aed4fd1527))

- **coverage**: Add coverage tests for app/api/onedrive.py and app/api/google_drive.py
  ([`e3cd687`](https://github.com/christianlouis/DocuElevate/commit/e3cd687757bfa97f688880787ff33960259146cd))

- **coverage**: Add tests to push coverage above 95% for 11 target files
  ([`759647f`](https://github.com/christianlouis/DocuElevate/commit/759647f9577e9afd57313cefe8731b6502bcca77))


## Unreleased

### Testing

- Improve coverage for process_with_ocr, api/settings, and settings_service to 90%+
  ([`d9abbc1`](https://github.com/christianlouis/DocuElevate/commit/d9abbc1c998668ffae485493f27e82aed4fd1527))

- **coverage**: Add tests to push coverage above 95% for 11 target files
  ([`759647f`](https://github.com/christianlouis/DocuElevate/commit/759647f9577e9afd57313cefe8731b6502bcca77))


## v0.57.0 (2026-02-25)

### Features

- **privacy**: Implement GDPR and global privacy compliance
  ([`0821e2f`](https://github.com/christianlouis/DocuElevate/commit/0821e2f989416f596f62620bed1b160f5b35bd19))


## v0.56.2 (2026-02-25)

### Bug Fixes

- **database**: Add runtime migrations for ocr_text, ai_metadata, document_title columns
  ([`db581ba`](https://github.com/christianlouis/DocuElevate/commit/db581ba355834a514606717fb5f8f9673fc0dce6))

### Documentation

- Add missing docs to mkdocs nav and README index
  ([`6e78e9e`](https://github.com/christianlouis/DocuElevate/commit/6e78e9e7cf37ce53700bd4b0ce5b599c8c5ac029))

- **changelog**: Update changelog [skip ci]
  ([`3dced5e`](https://github.com/christianlouis/DocuElevate/commit/3dced5eba42ef39144695003924dcf9425532ed8))


## Unreleased

### Documentation

- Add missing docs to mkdocs nav and README index
  ([`6e78e9e`](https://github.com/christianlouis/DocuElevate/commit/6e78e9e7cf37ce53700bd4b0ce5b599c8c5ac029))


## v0.56.1 (2026-02-25)

### Bug Fixes

- **mypy**: Add missing type annotations in meilisearch_client.py
  ([`07e7b49`](https://github.com/christianlouis/DocuElevate/commit/07e7b49ac83604e9bac5ca53266d7475b9f8a45d))

### Documentation

- Add Setup Wizard, Production Readiness, Database, K8s, and Licensing guides
  ([`139e23c`](https://github.com/christianlouis/DocuElevate/commit/139e23c9e48a872e1d4f6c16443053489273b661))


## v0.56.0 (2026-02-25)

### Features

- **ui**: Add dark mode support with system preference detection and localStorage persistence
  ([`c428a7e`](https://github.com/christianlouis/DocuElevate/commit/c428a7ec00e3b600cd2ecbb8edfdd9112ebf5d31))


## v0.55.0 (2026-02-25)

### Bug Fixes

- **config**: Default meilisearch_url to http://meilisearch:7700 for Docker/K8s service discovery
  ([`ff96340`](https://github.com/christianlouis/DocuElevate/commit/ff963401549eabeee6de6bc1421949e5df2213e2))

### Code Style

- Apply ruff auto-fix
  ([`0930765`](https://github.com/christianlouis/DocuElevate/commit/093076515e7686b94af31dd6a3f9ca9d393dc01a))

### Features

- **helm**: Add Helm chart for Kubernetes deployment and update DeploymentGuide
  ([`a08bfb9`](https://github.com/christianlouis/DocuElevate/commit/a08bfb9f1a21105c48356655e7bb5e129b7d8b43))


## v0.54.0 (2026-02-25)

### Features

- **ocr**: Fine-tune OCR quality criteria with stricter threshold and head-to-head comparison
  ([`89d5df7`](https://github.com/christianlouis/DocuElevate/commit/89d5df71c837f07111ad691ce455f7d253a14584))


## v0.53.1 (2026-02-25)

### Bug Fixes

- **ocr**: Sync workflow steps with process_with_ocr replacing legacy azure step
  ([`37a3f7a`](https://github.com/christianlouis/DocuElevate/commit/37a3f7aae7b1691915c65c481dbca061061d610a))

### Testing

- Fix test_retry_azure_ocr_success to patch process_with_ocr instead of legacy azure task
  ([`44c9f6d`](https://github.com/christianlouis/DocuElevate/commit/44c9f6dc3811ef82c16fee25575ea66fe8ba7929))


## v0.53.0 (2026-02-24)

### Bug Fixes

- **ocr**: Address code review: add model fallback default, remove unused variable
  ([`0c500e1`](https://github.com/christianlouis/DocuElevate/commit/0c500e1ec659e88b7b638380e338c4f2f7985308))

### Documentation

- **changelog**: Update changelog [skip ci]
  ([`b5fb7da`](https://github.com/christianlouis/DocuElevate/commit/b5fb7da18c21753bcdd44fc8b95a736030fae98e))

### Features

- **ocr**: Add AI-based embedded text quality check with automatic OCR fallback
  ([`b03bfb5`](https://github.com/christianlouis/DocuElevate/commit/b03bfb5e026abd02b9284537c4c6257a5da418f3))

### Testing

- Achieve 90%+ code coverage across codebase
  ([`02ad558`](https://github.com/christianlouis/DocuElevate/commit/02ad558330382679e5ed60f53dc4fdb3d2aeae15))


## Unreleased

### Testing

- Achieve 90%+ code coverage across codebase
  ([`02ad558`](https://github.com/christianlouis/DocuElevate/commit/02ad558330382679e5ed60f53dc4fdb3d2aeae15))


## v0.52.2 (2026-02-24)

### Bug Fixes

- **ocr**: Ensure Tesseract language data for embed_text_layer regardless of active OCR provider
  ([`2b2a97c`](https://github.com/christianlouis/DocuElevate/commit/2b2a97c2fa32e3aaaf7a02ed3856dbd927b8b856))


## v0.52.1 (2026-02-24)

### Bug Fixes

- **ui**: Resolve merge conflict markers in settings.html and add CI guard
  ([`66a4570`](https://github.com/christianlouis/DocuElevate/commit/66a45703cf4a625c01a6d381296fc95d6d51f4cb))


## v0.52.0 (2026-02-24)

### Features

- **ocr**: Auto-install Tesseract/EasyOCR languages from settings
  ([`8a2a4dc`](https://github.com/christianlouis/DocuElevate/commit/8a2a4dc2b3b6535fe1b6e3821e7f80fb41fe61c4))


## v0.51.0 (2026-02-24)

### Bug Fixes

- **ocr**: Address code review - add subprocess security comment and type hints in tests
  ([`50573ec`](https://github.com/christianlouis/DocuElevate/commit/50573ec7be67a9d7d337960b9a0206d9acb1d1b8))

### Features

- **ocr**: Embed searchable text layer for providers without native PDF output
  ([`fec0326`](https://github.com/christianlouis/DocuElevate/commit/fec032643beda655c96585a7be79ba74f6357bf3))


## v0.50.1 (2026-02-24)

### Bug Fixes

- **ocr**: Rewrite MistralOCRProvider to use native Mistral OCR API
  ([`c742383`](https://github.com/christianlouis/DocuElevate/commit/c7423834d51a2e4231b55520fc04a49ce38563c1))


## v0.50.0 (2026-02-24)

### Code Style

- **tests**: Rename _SESSION_SECRET to TEST_SESSION_SECRET; tighten non-admin redirect assertions to
  == 302
  ([`1f080a8`](https://github.com/christianlouis/DocuElevate/commit/1f080a8a431746d2750bc8101912f52aae7a76c3))

### Features

- **tests**: Increase code coverage from 89.28% to 92.15%
  ([`a1b9ac1`](https://github.com/christianlouis/DocuElevate/commit/a1b9ac1db6e07f2858c8bdc2c539b8d3935aeb7c))


## v0.49.0 (2026-02-24)

### Code Style

- Apply ruff auto-fix
  ([`0827b6e`](https://github.com/christianlouis/DocuElevate/commit/0827b6eaa97783b6ec2a11191d4089dcfa36210c))

### Features

- **api**: Remove redundant /env and /api/diagnostic/settings endpoints
  ([`f9d849f`](https://github.com/christianlouis/DocuElevate/commit/f9d849f7eb49426c1b945df158aa553460519673))


## v0.48.0 (2026-02-23)

### Bug Fixes

- **tests**: Update process_document test patches to use process_with_ocr
  ([`8828b71`](https://github.com/christianlouis/DocuElevate/commit/8828b710315ba0c5add8546842c05c3f46cb98ca))

- **tests**: Update process_with_azure patch target in test_storage_reorganization
  ([`7fdd8a4`](https://github.com/christianlouis/DocuElevate/commit/7fdd8a4d3fa3af3633e7c58862a5e26aa18050d4))


## v0.47.0 (2026-02-23)

### Documentation

- **changelog**: Update changelog [skip ci]
  ([`d70fffd`](https://github.com/christianlouis/DocuElevate/commit/d70fffd4d21214900fdb018066f10a60019b5706))

- **copilot**: Checkpoint before comprehensive instructions overhaul
  ([`dbea61d`](https://github.com/christianlouis/DocuElevate/commit/dbea61dc0b5808cb25db15553a950ca849a3228d))

- **copilot**: Overhaul instructions — Ruff toolchain, 100% coverage, agent workflow, modern Python
  ([`156e0ba`](https://github.com/christianlouis/DocuElevate/commit/156e0ba524000a1063c0cb316063f1e28e5f0182))

### Features

- **ai**: Handle temperature incompatibility for gpt-5 and o-series models, add model picker UI
  ([`a94b52e`](https://github.com/christianlouis/DocuElevate/commit/a94b52ee144e6e1f5a54ebc85d548bf5f860626b))


## Unreleased

### Documentation

- **copilot**: Checkpoint before comprehensive instructions overhaul
  ([`dbea61d`](https://github.com/christianlouis/DocuElevate/commit/dbea61dc0b5808cb25db15553a950ca849a3228d))

- **copilot**: Overhaul instructions — Ruff toolchain, 100% coverage, agent workflow, modern Python
  ([`156e0ba`](https://github.com/christianlouis/DocuElevate/commit/156e0ba524000a1063c0cb316063f1e28e5f0182))


## v0.46.0 (2026-02-23)

### Bug Fixes

- **api**: Swap parameter order in test_ai_extraction to fix 500 error
  ([`ce4700a`](https://github.com/christianlouis/DocuElevate/commit/ce4700ae44abf55a87bc94b83c4d41e4cac2278e))

### Features

- **ui**: Add copy button to text modals in file detail view
  ([`219e03e`](https://github.com/christianlouis/DocuElevate/commit/219e03ed3dc5cd80c1ed073167669db49dc01512))


## v0.45.0 (2026-02-23)

### Chores

- Add example.com and smtp.example.com to copilot agent network allowlist
  ([`d93cd96`](https://github.com/christianlouis/DocuElevate/commit/d93cd96b6205021c4739765090fa55641e23e2ee))

### Documentation

- **changelog**: Update changelog [skip ci]
  ([`d5e4a74`](https://github.com/christianlouis/DocuElevate/commit/d5e4a74f693b6a458dcdc2978d834d41c5b4cb4d))

### Features

- **api**: Add POST /api/ai/test-extraction endpoint and Test Extraction UI button
  ([`ce73f23`](https://github.com/christianlouis/DocuElevate/commit/ce73f23a8981ffae94594461362df3834481ced7))

### Testing

- **api**: Add comprehensive tests for AI extraction endpoint reaching 100% coverage
  ([`3262d65`](https://github.com/christianlouis/DocuElevate/commit/3262d65bfe38d0669ba7eb6c0c51961ff6817976))


## Unreleased

### Chores

- Add example.com and smtp.example.com to copilot agent network allowlist
  ([`d93cd96`](https://github.com/christianlouis/DocuElevate/commit/d93cd96b6205021c4739765090fa55641e23e2ee))


## v0.44.0 (2026-02-23)

### Code Style

- Apply ruff auto-fix
  ([`724d7d8`](https://github.com/christianlouis/DocuElevate/commit/724d7d870f5804fe6254809af488155a4c68be79))

### Features

- Add AI provider abstraction layer with OpenAI, Azure, Anthropic, Gemini, Ollama, OpenRouter,
  LiteLLM support
  ([`d4c7fb2`](https://github.com/christianlouis/DocuElevate/commit/d4c7fb26ac6a8365843310979ee83f7e1538cf95))

- Add Portkey provider support and null-content guard to AI abstraction layer
  ([`dcdef44`](https://github.com/christianlouis/DocuElevate/commit/dcdef443032e5c43202566b3545560c3464f3848))

- Update all OpenAI/ChatGPT refs + settings dropdown for fixed-value fields
  ([`044da0f`](https://github.com/christianlouis/DocuElevate/commit/044da0ff471d59ffaa483ee0ed108238b6000835))


## v0.43.0 (2026-02-23)

### Features

- **ui**: Implement responsive mobile interface
  ([`d08e175`](https://github.com/christianlouis/DocuElevate/commit/d08e175352bae477e657cbd7ab27839de406cbc3))


## v0.42.2 (2026-02-23)

### Bug Fixes

- **api**: Pass base_url to OpenAI client in test endpoint to prevent UnsupportedProtocol error
  ([`d885b63`](https://github.com/christianlouis/DocuElevate/commit/d885b63d38ff151c5dc3e70ad51fbf1d56a5f7df))


## v0.42.1 (2026-02-23)

### Bug Fixes

- Fix automatic changelog creation with PSR v10
  ([`7f3e831`](https://github.com/christianlouis/DocuElevate/commit/7f3e8312de33b44eba3c021ac4cf58e504528b85))


## [0.40.0] - 2026-02-23

> **Retroactive summary.** Releases v0.6.0 through v0.40.0 were cut automatically by
> `python-semantic-release` from conventional commits, but the CHANGELOG was not updated
> at the time due to a configuration bug (`autoescape = true`). This section documents all
> known changes made after v0.5.0.

### Added

#### Security Middleware Stack
- **CSRF Protection** (`app/middleware/csrf.py`): Per-session cryptographic tokens validated on all state-changing requests (POST/PUT/DELETE/PATCH). Token delivered via `X-CSRF-Token` header or `csrf_token` form field. No-op when `AUTH_ENABLED=False`.
- **Rate Limiting** (`app/middleware/rate_limit.py`): SlowAPI + Redis-backed rate limiting. Configurable defaults: 100 req/min (API), 600 req/min (uploads), 10 req/min (auth). Falls back to in-memory for development.
- **Rate Limit Decorators** (`app/middleware/rate_limit_decorators.py`): Convenience `@limit("N/period")` decorators for per-endpoint overrides.
- **Security Headers** (`app/middleware/security_headers.py`): Configurable HSTS, CSP, `X-Frame-Options`, and `X-Content-Type-Options` headers. Each header individually togglable for reverse-proxy deployments.
- **Audit Logging** (`app/middleware/audit_log.py`): Per-request structured log entries with sensitive-value masking. Elevated `[SECURITY]` log level for 401/403/login/5xx events.
- **Request Size Limiting** (`app/middleware/request_size_limit.py`): Separate limits for JSON/form bodies (`MAX_REQUEST_BODY_SIZE`, default 1 MB) and file upload multipart bodies (`MAX_UPLOAD_SIZE`, default 1 GB). Returns HTTP 413 immediately without reading the full body.
- **CORS** (`main.py`): Configurable CORS policy via `CORS_ENABLED`, `CORS_ALLOWED_ORIGINS`, `CORS_ALLOW_CREDENTIALS`, `CORS_ALLOWED_METHODS`, and `CORS_ALLOWED_HEADERS`.

#### New Storage Providers
- **Amazon S3** (`app/tasks/upload_to_s3.py`): Upload to S3-compatible buckets. Configured via `AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY`, `AWS_REGION`, and `S3_BUCKET_NAME`.
- **SFTP** (`app/tasks/upload_to_sftp.py`): Secure file transfer with password or private-key authentication. Supports `SFTP_DISABLE_HOST_KEY_VERIFICATION` flag.
- **FTP/FTPS** (`app/tasks/upload_to_ftp.py`): FTP with automatic FTPS upgrade attempt; plaintext fallback configurable via `FTP_ALLOW_PLAINTEXT`.
- **WebDAV** (`app/tasks/upload_to_webdav.py`): HTTP Basic auth, configurable SSL verification (`WEBDAV_VERIFY_SSL`).
- **Email/SMTP** (`app/tasks/upload_to_email.py`): Send processed documents as email attachments. Supports TLS, configurable sender, and default recipient.
- **rclone** (`app/tasks/upload_with_rclone.py`): Delegate uploads to a locally configured `rclone` binary, enabling support for any of rclone's 40+ cloud providers.

#### File Processing Improvements
- **PDF Page Rotation** (`app/tasks/rotate_pdf_pages.py`): Detects and corrects skewed pages using Azure Document Intelligence angle metadata.
- **Metadata Embedding** (`app/tasks/embed_metadata_into_pdf.py`): Writes GPT-extracted metadata as PDF document properties using pypdf.
- **PDF Splitting** (`app/utils/file_splitting.py`): Splits oversized PDFs at page boundaries into chunks ≤ `MAX_SINGLE_FILE_SIZE` bytes. Each chunk is a valid, readable PDF.
- **Document Deduplication**: SHA-256 hash-based duplicate detection. Controlled by `ENABLE_DEDUPLICATION` and `SHOW_DEDUPLICATION_STEP` settings.
- **Forced Cloud OCR**: `force_cloud_ocr` flag on `process_document` task to bypass local text extraction and always use Azure Document Intelligence. Useful for reprocessing.
- **pypdf migration**: Replaced PyPDF2 with pypdf (actively maintained fork); fixes CVE-2023-36464.

#### Processing Status Tracking (Dual-Table Architecture)
- **`FileProcessingStep` model**: New DB table; single row per (file, step) pair tracking current state (`pending`, `in_progress`, `success`, `failure`, `skipped`). Replaces log-scanning for status queries.
- **Step Manager** (`app/utils/step_manager.py`): Initialises, updates, and queries processing steps. Supports `ENABLE_DEDUPLICATION` conditional step inclusion.
- **Step Timeout Detection** (`app/utils/step_timeout.py`): Marks steps stuck in `in_progress` as `failure` after configurable `STEP_TIMEOUT` seconds (default 600).
- **Stalled Step Monitor** (`app/tasks/monitor_stalled_steps.py`): Periodic Celery task (runs every minute) that calls the timeout detection logic.
- **Log Migration Utility** (`app/utils/migrate_logs_to_steps.py`): Back-fills `FileProcessingStep` from existing `ProcessingLog` entries for files processed before the new table existed.

#### New API Endpoints
- **`POST /api/upload-from-url`** (`app/api/url_upload.py`): Upload a document from a remote URL. Includes SSRF protection (blocks private IPs and loopback addresses).
- **`GET /api/logs`** (`app/api/logs.py`): Paginated, filterable list of `ProcessingLog` entries; filterable by `file_id` and `task_name`.
- **`GET /api/diagnostic/settings`** (`app/api/diagnostic.py`): Admin-only endpoint that dumps non-sensitive configuration to logs and returns summary info.
- **`GET /api/whoami`** (`app/api/user.py`): Returns session user info including a Gravatar URL derived from the authenticated user's email.

#### Notification System
- **Apprise integration** (`app/utils/notification.py`): Multi-channel notifications via the Apprise library (70+ services: Slack, email, Telegram, PushOver, etc.). Configured via `NOTIFICATION_URLS`.
- **Configurable triggers**: `NOTIFY_ON_TASK_FAILURE`, `NOTIFY_ON_CREDENTIAL_FAILURE`, `NOTIFY_ON_STARTUP`, `NOTIFY_ON_SHUTDOWN`, `NOTIFY_ON_FILE_PROCESSED`.
- **Uptime Kuma integration** (`app/tasks/uptime_kuma_tasks.py`): Periodic heartbeat ping to a configured Uptime Kuma push URL (`UPTIME_KUMA_URL`, `UPTIME_KUMA_PING_INTERVAL`).

#### Admin & Operations
- **Admin File Manager** (`app/views/filemanager.py`): Three-pane admin view at `/filemanager`:
  - *Filesystem view*: Browse `workdir` tree with DB cross-reference per file.
  - *Database view*: List all `FileRecord` rows with on-disk existence flag.
  - *Reconcile view*: Delta view showing orphan disk files and ghost DB records.
- **Credential Checker Task** (`app/tasks/check_credentials.py`): Periodic Celery task that validates all configured provider credentials (OpenAI, Azure, Dropbox, Google Drive, OneDrive) and sends a notification on failure.
- **Settings Audit Log** (`ApplicationSettings` + `SettingsAuditLog` models): Every settings change is recorded with timestamp, user, and before/after values.
- **ProcessAll Throttling**: Configurable `PROCESSALL_THROTTLE_THRESHOLD` and `PROCESSALL_THROTTLE_DELAY` to prevent flooding the task queue during bulk reprocessing.
- **Worker Settings Sync** (`app/utils/settings_sync.py`): Publishes a version token to Redis whenever settings change; Celery workers reload settings from DB before each task, ensuring config changes propagate without a restart.

#### Browser Extension (v1.1.0)
- Send files and web pages from the browser directly to DocuElevate with one click.
- Context menu integration on links, images, and pages.
- Manifest v3 compatible; works with Chrome, Firefox, Edge, and Chromium-based browsers.
- In-browser notifications for upload status.

#### OpenAI Customization
- `OPENAI_BASE_URL` setting (default `https://api.openai.com/v1`): Enables use of OpenAI-compatible endpoints (Azure OpenAI, local models, etc.).
- `OPENAI_MODEL` setting (default `gpt-4o-mini`): Model selection without code changes.

#### Configuration & Developer Experience
- **Config Loader** (`app/utils/config_loader.py`): Hot-reload of settings from DB without service restart.
- **Config Validator** (`app/utils/config_validator/`): Modular validation with provider status, masked display, and per-provider readiness checks.
- **Input Validation** (`app/utils/input_validation.py`): Centralised validators for sort fields, sort order, search query length, task ID format (UUID v4), and settings key format.
- **Filename Utilities** (`app/utils/filename_utils.py`): `sanitize_filename`, `get_unique_filename`, and `extract_remote_path` helpers shared across upload tasks.
- **OAuth Helper** (`app/utils/oauth_helper.py`): Shared token-exchange logic reused by Dropbox, Google Drive, and OneDrive OAuth flows.
- **Retry Configuration** (`app/tasks/retry_config.py`): `BaseTaskWithRetry` base class with auto-retry (3 attempts, 10 s initial delay, exponential backoff) shared by all upload tasks.
- **HTTP Request Timeout**: Configurable `HTTP_REQUEST_TIMEOUT` (default 120 s) to handle large file operations gracefully.
- **File Deletion Toggle**: `ALLOW_FILE_DELETE` setting to prevent accidental deletions in production.

### Changed
- Docker image renamed from `christianlouis/document-processor` to `christianlouis/docuelevate`
- `app/routes/` deprecated; all endpoints migrated to `app/api/` and `app/views/`
- `FileRecord` status now derived from `FileProcessingStep` rows instead of scanning `ProcessingLog`
- Settings changes now propagated to Celery workers via Redis version key (no restart required)
- Dependency scanner switched from `safety` to `pip-audit` in CI pipeline
- CI pipeline streamlined: removed redundant DeepSource integration (40–50% faster CI runs)
- `app/utils/logging.py` introduced as canonical import point for `log_task_progress`

### Fixed
- **Critical: Path Traversal via GPT Metadata Filename** — GPT-extracted `filename` metadata was used directly in file path construction. Fixed by running all GPT-suggested filenames through `sanitize_filename` before use.
- **Medium: Path Traversal in File API** — `file_path` query parameters sanitised to block `../` sequences.
- **Medium: Unvalidated Sort Parameters** — sort field and order inputs in file list endpoint now validated against an allowlist.
- OAuth admin group detection now correctly handles groups list from Authentik userinfo response.
- Session secret validation raises a clear error at startup instead of silently using an insecure default.
- Redirect loop for logged-in non-admin users on `/settings` route resolved.

### Security
- CSRF protection added to all state-changing endpoints
- Rate limiting prevents brute-force and DoS attacks on auth and upload endpoints
- Security response headers (HSTS, CSP, X-Frame-Options, X-Content-Type-Options) enabled by default
- Audit log records all HTTP requests with sensitive-value masking
- Request body size limits prevent memory-exhaustion attacks
- Path traversal vulnerabilities in file path handling remediated (see security audit `docs/security/PATH_TRAVERSAL_AUDIT_2026-02-10.md`)
- Host key verification enforced for SFTP by default (`SFTP_DISABLE_HOST_KEY_VERIFICATION=False`)
- FTPS attempted by default for FTP connections; plaintext requires explicit opt-in
- SSRF protection on URL-upload endpoint (blocks private IP ranges and loopback)
- Input validation on all user-controlled sort/search/key parameters

### Documentation
- Added `docs/RateLimitingStrategy.md` — rate limiting configuration guide
- Added `docs/FileProcessingStatusArchitecture.md` — dual-table architecture explanation
- Added `docs/NotificationsSetup.md` — Apprise notification setup guide
- Added `docs/StorageArchitecture.md` — document storage directory layout
- Added `docs/AuthenticationSetup.md` — OAuth2 / Basic Auth configuration
- Added `docs/AmazonS3Setup.md`, `docs/DropboxSetup.md`, `docs/GoogleDriveSetup.md`, `docs/OneDriveSetup.md` — per-provider setup guides
- Added `docs/CredentialRotationGuide.md` — how to rotate API keys and credentials
- Added `docs/ConfigurationTroubleshooting.md` — common configuration problems
- Added `docs/security/PATH_TRAVERSAL_AUDIT_2026-02-10.md` — security audit findings
- Added `docs/BrowserExtension.md` — browser extension installation and usage
- Added `docs/CIToolsGuide.md` and `docs/CIWorkflow.md` — CI pipeline documentation
- Added `docs/BuildMetadata.md` — build metadata file documentation
- CI de-duplication summary archived in `docs/CI_DEDUPLICATION_SUMMARY.md`
- OAuth testing summary archived in `OAUTH_IMPLEMENTATION_SUMMARY.md`
- WebDAV testing summary archived in `WEBDAV_TESTING_SUMMARY.md`

---

## [0.5.0] - 2026-02-08

### Added
- **Settings Management System**: Database-backed configuration management with web UI
  - Admin-only settings page at `/settings` with 102 settings across 10 categories
  - REST API endpoints: `GET/POST /api/settings/{key}`, `POST /api/settings/bulk-update`, `DELETE /api/settings/{key}`
  - Settings organized by category: Core, Authentication, AI Services, Storage Providers, Email, IMAP, Monitoring, Processing, Notifications, Feature Flags
  - Form pre-filled with current values, all fields optional for flexible editing
  - Bulk update support for changing multiple settings at once
- **Encryption for Sensitive Settings**: Fernet symmetric encryption for database storage
  - Automatic encryption/decryption for passwords, API keys, tokens, and secrets
  - Encryption key derived from `SESSION_SECRET` via SHA256
  - Values prefixed with `enc:` in database to identify encrypted data
  - Graceful fallback if cryptography library unavailable (logs warning)
  - Lock icon (🔒) in UI indicates encrypted fields
- **Setup Wizard**: First-time configuration wizard for fresh installations
  - 3-step wizard: Infrastructure → Security → AI Services
  - Auto-detects missing critical settings and redirects from homepage
  - Beautiful UI with progress indicators and step navigation
  - Auto-generate option for session secrets
  - Skippable for advanced users
  - Settings saved encrypted to database
- **Settings Precedence System**: Clear resolution order with visual indicators
  - Precedence: Database > Environment Variables > Defaults
  - Color-coded badges in UI: 🟢 DB (green), 🔵 ENV (blue), ⚪ DEFAULT (gray)
  - Source detection for each setting shows where value originates
  - Info section explaining precedence order
- **OAuth Admin Support**: Enhanced authentication for settings access
  - Admin flag set from OAuth group membership (`admin` or `administrators`)
  - Proper decorator pattern for admin access control
  - Session-based authorization with redirect on unauthorized access

### Changed
- Updated `requirements.txt` to include `cryptography>=41.0.0` for encryption
- Enhanced settings service to auto-encrypt/decrypt sensitive values transparently
- Improved `/settings` route with proper admin decorator (fixes redirect loop)
- Updated settings template with enhanced UI: source badges, encryption indicators, show/hide toggles
- Modified `app/views/general.py` to redirect to wizard when setup required

### Fixed
- Fixed `/settings` endpoint returning 301 redirect to `/` (converted to proper decorator)
- Resolved redirect loop for logged-in non-admin users
- Fixed OAuth users not receiving admin privileges from group membership

### Documentation
- Added [docs/SettingsManagement.md](docs/SettingsManagement.md) - Comprehensive user guide
- Added [SETTINGS_IMPLEMENTATION.md](SETTINGS_IMPLEMENTATION.md) - Technical documentation
- Added [FRAMEWORK_ANALYSIS.md](FRAMEWORK_ANALYSIS.md) - Research on existing frameworks
- Added [IMPLEMENTATION_CHECKLIST.md](IMPLEMENTATION_CHECKLIST.md) - Feature tracking
- Updated TODO.md with completed features
- Updated MILESTONES.md with release details

### Technical Details
- New files:
  - `app/utils/encryption.py` - Fernet encryption utilities
  - `app/utils/setup_wizard.py` - Wizard detection and logic
  - `app/views/wizard.py` - Wizard routes (GET/POST /setup)
  - `frontend/templates/setup_wizard.html` - Wizard UI
  - `frontend/templates/settings.html` - Enhanced settings page
- Modified files:
  - `app/utils/settings_service.py` - Encryption integration, 102 setting metadata
  - `app/views/settings.py` - Fixed decorator, source detection
  - `app/auth.py` - OAuth admin support
  - `app/api/settings.py` - Enhanced admin checks
  - `tests/test_settings.py` - Comprehensive test coverage

### Security
- Sensitive settings encrypted at rest in database using Fernet (AES-128-CBC + HMAC)
- Encryption key derived from `SESSION_SECRET` (minimum 32 characters required)
- Admin-only access enforced on all settings operations
- Visual masking of sensitive values in UI by default
- CodeQL security scan: 0 alerts

## [0.3.3] - 2026-02-08

### Added
- **Drag-and-drop file upload on Files page**: You can now drag and drop files anywhere on the Files view (`/files`) to upload them, making it more convenient to add documents without navigating to the dedicated Upload page
- Visual drop overlay that appears when dragging files over the Files page
- Upload progress modal in bottom-right corner showing real-time upload status
- Reusable `upload.js` module extracted from upload page for better code maintainability
- Tests for drag-and-drop functionality presence in Files view
- Enhanced visual feedback with animations and improved styling

### Changed
- Refactored upload functionality into a shared JavaScript module (`/static/js/upload.js`)
- Updated Upload page to use the new shared upload module
- Improved drop zone visual styling with better colors and animations

### Security
- Continued security improvements from v0.3.2 (authlib, starlette updates)

## [0.3.2] - 2026-02-06

### Added
- Comprehensive test infrastructure with pytest
- Security scanning workflows (CodeQL, Bandit)
- SECURITY_AUDIT.md documentation
- ROADMAP.md and MILESTONES.md planning documents
- API integration tests and configuration validation tests
- Pre-commit hooks configuration

### Changed
- Updated authlib to 1.6.5+ (security fix)
- Updated starlette to 0.49.1+ (DoS vulnerability fix)
- Improved SESSION_SECRET validation and handling
- Enhanced .gitignore for security
- Updated README with improved documentation structure

### Fixed
- Critical security vulnerabilities in dependencies
- Session security issues

## [0.3.1] - 2026-01-15

### Added
- Files view with sorting and filtering capabilities
- Bulk operations (delete, reprocess) for multiple files
- File detail view with processing history
- Processing flow visualization

### Changed
- Improved UI responsiveness
- Enhanced error handling and user feedback

### Fixed
- Various bug fixes in file processing pipeline

## [0.3.0] - 2025-12-20

### Added
- OAuth2 authentication support with Authentik
- Multi-provider storage support (Dropbox, Google Drive, OneDrive, S3, Nextcloud)
- Azure Document Intelligence integration for OCR
- OpenAI metadata extraction
- Gotenberg PDF conversion service integration
- IMAP integration for email attachment processing
- REST API with FastAPI
- Web UI for document management
- Celery task queue for asynchronous processing

### Changed
- Major architectural improvements
- Database schema optimizations

## [0.2.0] - 2025-11-01

### Added
- Basic document upload functionality
- Simple storage integration
- Basic metadata extraction

## [0.1.0] - 2025-10-01

### Added
- Initial release
- Core document processing framework
- Basic file handling

---

## Historical Release Links

**Note**: Tags v0.3.1, v0.3.2, v0.3.3, v0.5.0, and the retroactive v0.40.0 summary do not correspond
one-to-one with formal GitHub Releases from that period. Going forward all releases have corresponding
GitHub Releases and tags created automatically by `python-semantic-release`.

[Unreleased]: https://github.com/christianlouis/DocuElevate/compare/v0.40.0...HEAD
[0.40.0]: https://github.com/christianlouis/DocuElevate/compare/v0.5.0...v0.40.0
[0.5.0]: https://github.com/christianlouis/DocuElevate/compare/v0.3.3...v0.5.0
[0.3.3]: https://github.com/christianlouis/DocuElevate/compare/v0.3.2...v0.3.3
[0.3.2]: https://github.com/christianlouis/DocuElevate/compare/v0.3.1...v0.3.2
[0.3.1]: https://github.com/christianlouis/DocuElevate/compare/v0.3.0...v0.3.1
[0.3.0]: https://github.com/christianlouis/DocuElevate/compare/0.2...0.3
[0.2.0]: https://github.com/christianlouis/DocuElevate/compare/0.1...0.2
[0.1.0]: https://github.com/christianlouis/DocuElevate/releases/tag/0.1
