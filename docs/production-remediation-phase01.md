# Phase 01 — Image upload filesystem containment

## Frozen requirement and design

Primary question: can an Image Processor upload write outside its server-created job directory?

Acceptance criteria:
1. Valid existing flat/folder payloads retain filenames, folder identity, owner, response and task arguments.
2. Parent traversal, absolute paths on either OS, unsafe components and normalized traversal return HTTP 400.
3. Every final destination resolves below a newly created server-generated directory.
4. Links, existing job directories, and colliding file/directory destinations cannot redirect or overwrite uploads.
5. Rejected uploads create no batch and dispatch no task; failed writes clean only the new job directory.

The user authorized the inspect/design/implement/test/commit/PR sequence for this phase. This is a local security repair, not a new architecture or API. No schema, dependency, frontend, worker, deployment or ZIP changes. Existing multiple-folder payloads are characterized, not expanded.

Keep `/tmp/batch_uploads/<uuid>` because the API, worker and cleanup task already share that root. Validate relative components before normalization, including Windows rules on Linux. Build the final flat-upload destination directly rather than moving files using unchecked `style`. Resolve containment before and after parent creation; use exclusive file creation. Preserve the existing filename normalizer and reject its collisions.

The server controls the staging root and its permissions. Fresh job directories use mode 0700; API and worker use the existing compatible container identity. Host administrators or a compromised process running as the application user remain outside this request-input boundary.

## Repository safety snapshot

- Original repository: `D:/Project/UQ_GU_Web_Summary`.
- Remote: `https://github.com/Forhath-Hosain-Ome/UQ_GU_Web_Summary.git`.
- Original branch / HEAD: `develop` / `3fb8aa87e40f537fedcaafccf4d69235a90d908e`.
- Base / verified remote SHA: `develop` / `3fb8aa87e40f537fedcaafccf4d69235a90d908e`.
- Task branch: `fix/image-upload-containment`, in a separate worktree.
- `main` is the default branch but diverges substantially from this application's audited `develop` state; this PR targets `develop` to avoid unrelated changes.
- Existing staged work: extractor analysis documents/scripts, `test_extractor.py`, and `backend/final_summary/extraction/fields/__init__.py`.
- Existing unstaged status: Dockerfiles, entrypoint, settings and Compose.
- Existing untracked work: `.codex/`, `ARCHITECTURE.md`, `PROJECT_CONTEXT.md`, backend environment example and rotated logs.
- None of that existing work is included or modified by this phase.
- No tracked GitHub Actions configuration or backend lint/typecheck command was found.
- Frontend declares `npm run lint` and `npm run build`; it is unchanged and outside this backend-only gate.
- The existing architecture document is proposed; the accepted user phase contract governs this bounded repair.

## Finding verification

On the unchanged base upload handler, the first three tests produced one pass and two failures: legitimate upload succeeded, while both `../escaped` and an absolute temporary destination returned HTTP 201 instead of 400. A separate replay loaded the serializer/view directly from base SHA `3fb8aa8` and confirmed both inputs wrote the synthetic bytes outside the generated job directory, entirely inside temporary sandboxes. The view joined unchecked `style` to the staging directory and moved uploaded bytes there.

The serializer also checked a normalized relative path while the view replaced its filename with another client filename. The fix validates both inputs and the exact final destination. Unsupported actual filename extensions cannot be hidden behind a `.jpg` metadata path.

## Verification commands and boundaries

From `backend`, with repository dependencies installed:

```sh
python -B -m django test image_processor.tests --settings=image_processor.tests.settings --verbosity=1
python -B -m django test image_processor mail_download.tests --settings=image_processor.tests.settings --verbosity=1
python -B -m django check --settings=image_processor.tests.settings
```

Tests use synthetic bytes, actual multipart requests/serializers/views, an in-memory SQLite database, temporary directories and a mocked Celery dispatch. They do not process images, contact Redis, or load deployment credentials. The test-only settings synchronize Image Processor tables because its committed migrations are absent; migration repair remains Phase 05. The existing shared imports require the Final Summary app to be registered.

Coverage includes traversal and absolute paths, mixed separators, Windows drive-relative/UNC/device names, invalid lengths/control characters, filename/type mismatch, case/normalization collisions, file-directory conflicts, existing root preservation, exclusive writes, link rejection, failed-write cleanup, owner-scoped batch detail/list, field aliases and unchanged upload size limits. Windows uses real directory junctions; Linux uses real symlinks.

| Check | Result / evidence |
| --- | --- |
| Base reproduction | PASS: 2 negative tests fail on base; legitimate upload passes |
| Windows module/sibling discovery | PASS: 27 tests; no skips; Python 3.12.14, Django 6.0.3, DRF 3.17.1 |
| Linux module/sibling discovery | PASS: 27 tests; no skips; Python 3.12.12, repository-constrained dependencies |
| Backend source syntax | PASS: all 267 Python files parse |
| Production heuristic scanner | PASS: no findings in Image Processor |
| Security heuristic scanner | Four existing broad-exception cleanup leads; reviewed below |
| Diff whitespace | PASS: `git diff --check` |
| Backend lint/typecheck | NOT APPLICABLE: no configured command |
| Frontend/container build | NOT APPLICABLE to this phase: no changes to those surfaces |
| Production DB/Redis/worker/UAT | NOT RUN: no production readiness claim; task dispatch is mocked |

Windows temporary dependencies pin direct framework versions; some transitives differ from deployment pins. The Linux run uses `requirements.txt` as a constraint for the full installed test dependency closure. No repository dependency declaration changed.

## Self-review and sibling harvest

Each runtime change belongs to the same upload boundary: serializer input validation, destination validation, and the final filesystem write. Tests/settings/URL mounting isolate that boundary without replacing its ORM or HTTP behavior.

- Worker `image_processor/tasks/process_image.py` discovers immediate staging directories and uses their names. Existing layout and task signature remain unchanged.
- Cleanup `image_processor/tasks/cleanup_task.py` enumerates `/tmp/batch_uploads`; the root layout remains unchanged.
- Batch detail/list consumers retain ownership and status behavior; covered by the new API regression.
- Puma upload uses a server-derived directory but its duplicate counter can collide with a separately submitted suffixed name (for example `a.pdf`, another `a.pdf`, then `a_1.pdf`). Record as a separate filename-collision follow-up; do not fix here.
- Final Summary upload uses a server-created temporary directory and Django-uploaded basenames. No equivalent unchecked `style` destination was found in that handler.
- Mail ZIP generation writes client names into an in-memory archive, not server directories. Archive-entry safety needs a separate review.
- Image batch-detail `_pdf_exists` uses string-prefix containment for an existence flag. This is a separate read-path follow-up, not an upload write sink.
- The scanner's four broad-exception leads are pre-existing cleanup handlers in the worker, two download views and upload view, verified on the base. They do not authorize an invalid upload; cleanup failure can retain staging data and is an operational follow-up.

No sibling implementation was changed. These follow-ups are not authorization to start another phase.

## Rollback and remaining limits

No migrations/configuration changes. Reverting the phase commit restores previous behavior, including the security defect; prefer a forward fix or disabling the upload endpoint if rollback is required. No production artifacts or data were touched.

This verifies the upload containment boundary, not document rendering, production storage/permissions, migration readiness, Redis delivery, browser UAT or dependency-advisory status. Those remain subject to the later authorized phases.

## Delivery gates (pre-publication snapshot)

| Gate | State |
| --- | --- |
| Requirement Freeze | PASS |
| Design | PASS |
| Implement | PASS |
| Self-review | PASS |
| Sibling Harvest | PASS |
| Adversarial Tests | PASS: Windows junctions and Linux symlinks |
| Full Regression | PASS: affected module/API/ownership checks on both platforms, source parse and diff audit |
| PR | NOT STARTED: next authorized action after this evidence commit |

## Phase queue

| Phase | Work | State |
| --- | --- | --- |
| 01 | Image upload filesystem containment | LOCALLY VERIFIED; PR next |
| 02 | Image Processor multi-folder + ZIP backend | NOT STARTED |
| 03 | Image Processor multi-folder + ZIP frontend | NOT STARTED |
| 04 | JWT refresh routing | NOT STARTED |
| 05 | Reproducible migrations/startup | NOT STARTED |
| 06 | Mail Download proxy routing | NOT STARTED |
| 07 | Final Summary transactional persistence | NOT STARTED |
| 08 | Lint scope/source remediation | NOT STARTED |
| 09 | Release qualification | NOT STARTED |

Stop after this phase's PR. No merge or deployment is authorized.
