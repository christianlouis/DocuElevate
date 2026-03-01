# Changelog

All notable changes to DocuElevate will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

> **This CHANGELOG is automatically generated and maintained by [python-semantic-release](https://github.com/python-semantic-release/python-semantic-release). Do not edit it manually.**
> New entries are prepended automatically on every merge to `main` that triggers a version bump.

<!-- version list -->

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
