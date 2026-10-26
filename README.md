# Verity classroom attendance

Verity is being transformed from a facility attendance prototype into classroom attendance software. Its workflow is organized around students, courses, class sections, lecturer-led attendance sessions, and auditable attendance records—not building operations.

## Application audit

The previous application was a React/Vite frontend and FastAPI/PostgreSQL backend. It included signed-cookie authentication, administrator/staff authorization, append-only audit events, cursor-based repositories, a room/people/check-in schema, and a Siamese image-pair verifier. Its dashboards and sample provider were facility-oriented and contained fictional people, events, rooms, occupancy, mock recognition, and browser-only role switching. The Siamese verifier only compared two supplied images; it did not identify a face from a camera or safely make attendance decisions. No identification model artifact was bundled.

### Feature disposition

| Remove | Retain | Replace or add |
| --- | --- | --- |
| Facility map, building occupancy, room-location events, maintenance/work-order/asset/inspection/energy workflows, corporate people directory, mock recognition feed, mock check-in terminal | Signed HttpOnly sessions, server-side role authorization, PostgreSQL/Alembic, append-only audit foundation, request IDs, reusable layout primitives, Vite/Render/Vercel deployment configuration | Student records, courses, semesters, class sections and schedules, enrollment, attendance sessions, manual attendance records, class reports, academic dashboard |
| Facility-specific frontend providers and sample data | Password hashing and session revocation | Explicit states for unavailable recognition, offline synchronization, and unsupported device readings |
| Legacy facility API routes | Existing database history during migration/rollback window | A later validated CNN identification pipeline, encrypted template service, offline queue/sync, correction workflow, PDF reports, retention operations |

The prior facility API routes and frontend modules have been removed from the active application. Existing facility tables are retained by the migration chain for rollback and controlled data disposition; they are not queried by the new classroom dashboard.

## Verity architecture

```text
React/Vite classroom UI
  ├─ signed-in dashboard and academic management
  ├─ explicit single-image recognition review and consent-based enrollment
  └─ same-origin authenticated API calls
          │
FastAPI
  ├─ HttpOnly session authentication + admin/staff authorization
  ├─ academic API: students, courses, semesters, sections, sessions, records
  ├─ YuNet detection → face-region quality gate → SFace alignment/embedding
  ├─ encrypted templates, session-scoped matching, audit metadata
  ├─ transactional attendance/outbox writes and idempotent HTTPS sync receiver
  └─ PostgreSQL via async SQLAlchemy/Alembic
```

The schema includes student, course, semester, section, enrollment, session, attendance-record, facial-template, recognition-attempt, and sync-outbox tables. Embeddings are authenticated-encrypted before storage. Enrollment and recognition images are processed in memory and not persisted. Encryption keys are supplied outside PostgreSQL and are never returned by an API.

Dashboard counts are returned by the authenticated `/api/v1/dashboard/summary` API and computed from stored students, explicit weekly schedules, active sessions, enrollments, and recorded marks. `Absent` means explicitly marked absent; `Not yet verified` means an enrolled roster entry in an open session has no mark. Both are unavailable (`—`) when there is no active session. No mock/demo attendance is loaded.

The earlier browser preview remains opt-in and local. The recognition page now sends a user-selected image to the authenticated API, where it is processed in memory and not retained. Automatic attendance is disabled unless a model-hash-matched validation report has sufficient representative coverage and explicit institutional approval, and a separate deployment flag is enabled. The UI always offers manual verification.

## Recognition prototype and model/dependency assessment

| Component | Selection | Provenance / license | Runtime / constraints |
| --- | --- | --- | --- |
| Face detector | OpenCV Zoo YuNet `face_detection_yunet_2023mar.onnx` (232,589 bytes) | OpenCV Zoo commit `48b10fa505aeb51fbd127fc60a5c660040e823b7`, MIT | `cv2.FaceDetectorYN`, OpenCV CPU DNN, five landmarks; documented for faces approximately 10–300 pixels |
| Embedding | OpenCV Zoo SFace `face_recognition_sface_2021dec.onnx` (38,696,353 bytes), a MobileFaceNet model trained with SFace loss | Same pinned OpenCV Zoo commit, model directory Apache-2.0; SFace paper/original implementation linked from OpenCV Zoo | `cv2.FaceRecognizerSF`, CPU DNN; landmark `alignCrop`, normalized 128-element feature |
| Existing verifier | Siamese verifier remains for its original pairwise use only | Existing local artifact/configuration | TensorFlow remains installed; it is not used for student identification or attendance matching |
| ONNX Runtime | Not added | Both model files already run as ONNX through OpenCV DNN | OpenCV CPU avoids a second inference runtime; compare ONNX Runtime only if target-device benchmarks justify its dependency and resource cost |

From `backend/`, run `python -m scripts.download_face_models` to fetch only the pinned models. The downloader checks exact Git LFS sizes and SHA-256 digests before atomically installing to the ignored `model-artifacts/` directory. Configure `VERITY_YUNET_MODEL_PATH` and `VERITY_SFACE_MODEL_PATH`; missing/corrupt/incompatible artifacts fail closed. Weights are not committed.

Components are separated as `YuNetFaceDetector.detect`, `assess_quality`, `SFaceEmbedder.extract` (alignment and embedding), `match_embedding`, template cryptography, and the session recognition API. Quality checks use brightness, contrast, Laplacian blur, face dimensions, and image bounds on the detected face region. Defaults are engineering heuristics, not classroom-calibrated thresholds; low-quality input is rejected and sent to manual roll call. No synthetic brightness enhancement is applied.

| Endpoint | Purpose |
| --- | --- |
| `GET /api/v1/recognition/status` | Authenticated model, key, retention, and threshold-manifest readiness |
| `POST /api/v1/students/{id}/face-template` | Admin-only image enrollment; requires explicit consent confirmation and an opaque institutional consent reference |
| `DELETE /api/v1/students/{id}/face-template` | Admin-only hard deletion/withdrawal |
| `POST /api/v1/attendance-sessions/{id}/recognize` | Admin/staff/assigned lecturer inference for an open session |
| `POST /api/v1/sync/attendance` | HTTPS central receiver with shared bearer-token authentication and event idempotency |

No student validation set exists, so there is no accuracy claim or calibrated threshold. Without an approved validation manifest, each inference returns `uncertain` without assigning an identity. Automatic attendance requires a report matching the detector and embedder hashes, at least 30 enrolled identities and 30 evaluation images, low/medium/high lighting data, selected measured error-rate metrics, a time-stamped institutional approval reference, an HMAC signature from an external approval key, and `VERITY_AUTO_ATTENDANCE_ENABLED=true`. The benchmark tool itself always writes approval as false. After institutional review, sign a report with `python -m scripts.sign_validation_manifest --manifest /secure/local/verity-validation-report.json --minimum-similarity <measured-value> --minimum-margin <measured-value> --approved-by <reviewer> --approval-reference <institution-reference>` while `VERITY_RECOGNITION_APPROVAL_KEY_ID` and a base64 32-byte `VERITY_RECOGNITION_APPROVAL_KEY` are securely provisioned. These coverage checks do not guarantee statistical sufficiency, demographic fairness, or classroom performance. A standard USB RGB webcam has no validated liveness/PAD signal; replay/spoof prevention is not implemented.

### Validation, benchmarking, and performance

Do not use public example images as student-validation data. Prepare an institution-approved local CSV with columns `path,identity,split,has_face,lighting`: `split` is `enrollment` or `evaluation`; `identity` is stable pseudonymous identity for known students and blank for non-enrolled/impostor examples; `has_face` is the ground-truth detection label; `lighting` is `low`, `medium`, or `high`. Keep images on the institution's device.

```bash
cd backend
python -m scripts.benchmark_face_pipeline \
  --manifest /secure/local/validation.csv \
  --detector ../model-artifacts/face_detection_yunet_2023mar.onnx \
  --embedder ../model-artifacts/face_recognition_sface_2021dec.onnx \
  --similarity-thresholds 0.25,0.35,0.45,0.55 \
  --minimum-margin 0.08 \
  --output /secure/local/verity-validation-report.json
```

The threshold list above is only a command example, not a recommendation. Select thresholds using measured false-accept/false-reject curves and a documented institutional risk decision. The script reports per-lighting detection rate, quality rejection, false acceptance/rejection, misidentification, inference latency percentiles, model load time, process CPU, and peak RSS. The current target description (8-GB-or-better laptop/desktop, USB webcam, 30–100 students) does not identify CPU, OS, camera resolution, lux range, or power profile. No target performance numbers are claimed. Benchmark each supported hardware class before establishing p95 latency/RAM/CPU/energy limits. OpenCV CPU DNN defaults to one thread; tune `VERITY_OPENCV_THREADS` only after measurement. One image must contain exactly one face; group-frame recognition is not supported.

### Biometric keys, consent, retention, deletion

Configure `VERITY_TEMPLATE_KEYS` as a JSON object mapping key IDs to base64-encoded 32-byte AES keys, `VERITY_TEMPLATE_ACTIVE_KEY_ID` as the write-key ID, and `VERITY_FACE_TEMPLATE_RETENTION_DAYS` as a positive institutional policy value (1–3650). No default retention is chosen. Store key material in an OS keychain, protected secret file, or secret manager, never in the database/source/logs. Keep previous key IDs configured while templates use them, then run `python scripts/rotate_template_keys.py` after securely provisioning the new active key. Key loss without a backup makes templates unrecoverable.

Enrollment requires an admin, explicit confirmation, an opaque consent-record reference, a configured retention period and keys, one acceptable face, and available model weights. A checkbox is not a substitute for lawful consent or guardian authorization; the application does not collect consent documents. `DELETE` erases the template and writes an audit event. Schedule `python -m scripts.purge_expired_templates`; recognition excludes expired templates even before physical purge. Also define deletion/expiry for backups and snapshots. Rotate keys with `python -m scripts.rotate_template_keys`.

### Local/offline attendance and synchronization

For disconnected classroom operation, run FastAPI and PostgreSQL on the classroom laptop/local network. `DATABASE_URL` must reference that local database; the existing Render web service is not itself an offline classroom deployment. Attendance and its outbox event are committed in one database transaction. The outbox uses deterministic event IDs and persists `pending`, `synced`, or `conflict`. Run `python -m app.sync_outbox` when connectivity returns (or schedule it with the OS), configuring `VERITY_SYNC_URL` and `VERITY_SYNC_TOKEN`; non-local remote URLs must use HTTPS, and the receiving server must have the same secret. Replays are idempotent. A conflicting mark for the same student/session is held in `conflict` for human reconciliation rather than overwritten.

Outbox entries contain attendance identifiers/marks, not images or embeddings. Protect local PostgreSQL and backups with disk/database encryption and OS access controls. A powered-off device cannot record scans; use the laptop battery/approved UPS and test PostgreSQL crash recovery. Unit tests cover retry after connectivity returns; end-to-end synchronization against a second deployment and actual power-loss recovery remain acceptance tests.

### Migration and rollback

Revision `20261026_0008` adds consent/model metadata, recognition-attempt audit records (outcome, model hashes, duration, non-image quality metrics), and the attendance outbox. It does not rewrite existing attendance or facility data. Take a PostgreSQL backup and test on a restored copy before applying migrations. Downgrade of `0008` refuses to discard non-empty recognition/outbox data or newly populated consent metadata; export/reconcile data before separately approving rollback. Earlier migrations' downgrade behavior must also be reviewed.

### Implemented API surface

All classroom API routes require authentication. Admins, staff, and lecturers can read academic data; lecturers see only their assigned classes and rosters. Only admins can create student, course, semester, section, and enrollment records. Admins, staff, and lecturers can open/close sessions and manually record attendance, with lecturer writes limited to assigned classes.

| Endpoint | Purpose |
| --- | --- |
| `GET /api/v1/dashboard/summary?local_date=YYYY-MM-DD` | Current registered-student, schedule, session, attendance, and recent-activity metrics |
| `GET, POST /api/v1/students` | List/search or register a student |
| `GET, POST /api/v1/courses` | List or create courses |
| `GET, POST /api/v1/semesters` | List or create semesters |
| `GET, POST /api/v1/class-sections` | List or create course sections, lecturer assignments, and weekly schedules |
| `GET /api/v1/lecturers` | Admin list of active lecturer accounts for class assignment |
| `POST /api/v1/class-sections/{id}/enrollments` | Enroll a student |
| `GET /api/v1/attendance-sessions` and `POST /api/v1/class-sections/{id}/attendance-sessions` | List, schedule, or open sessions |
| `POST /api/v1/attendance-sessions/{id}/start` | Start a scheduled session |
| `POST /api/v1/attendance-sessions/{id}/records` | Manually record a student's mark; supports idempotency keys |
| `GET /api/v1/attendance-sessions/{id}/records` | Read session attendance |
| `PATCH /api/v1/attendance-sessions/{id}/records/{record_id}` | Correct a mark with a required reason and audit event |
| `GET /api/v1/attendance-sessions/{id}/records.csv` | Export a session to CSV |
| `POST /api/v1/attendance-sessions/{id}/close` | Close a session |
| `GET /api/v1/recognition/status` | Report recognition and safety-gate readiness |
| `POST /api/v1/students/{id}/face-template` / `DELETE .../face-template` | Consented encrypted enrollment and hard deletion |
| `POST /api/v1/attendance-sessions/{id}/recognize` | Single-face detection, quality gate, embedding match, and review-first attendance |
| `POST /api/v1/sync/attendance` | Token-authenticated, idempotent offline attendance receipt |

Manual attendance and academic creation emit audit events. Recognition attempts store model hashes, outcome, duration, and non-image quality metrics. PDF export, user invitations/role editing, and audit-log browsing are not yet implemented. Retention purge is an OS-scheduled command, not a database scheduler.

## Database migration plan

The new Alembic migrations are additive and preserve existing authentication, audit, and historical facility tables:

1. Take a verified PostgreSQL backup and review the current Alembic revision.
2. Run `alembic upgrade head`; revisions `20261026_0004` through `20261026_0008` add the classroom domain, schedules, lecturer role, recognition metadata, and sync outbox without dropping legacy tables.
3. Populate the new student/course/semester/section/enrollment tables from institution-approved source records. Do not automatically reinterpret corporate people or rooms as students or classrooms.
4. Only migrate historical attendance if the institution approves a source-to-student and source-to-course mapping. Preserve source IDs/timestamps and audit provenance; reject ambiguous rows rather than guessing.
5. Keep old facility tables read-only during the rollback and reconciliation period. Drop them only in a separately reviewed migration after backup, retention, legal, and rollback requirements are approved.
6. Do not enroll real templates until lawful consent, external AES keys, configured retention, model validation, institutional threshold approval, and deletion procedures are ready. Recognition is review-first by default.

The forward migration intentionally does not copy facility records into the academic schema: the current source data has no reliable student/course/semester semantics. Back up before applying migrations. Revision `0008` protects new data on downgrade; original classroom migration `0004` removes classroom tables and their contents on downgrade. PostgreSQL retains the added `lecturer` enum value on downgrade; do not run older application code against lecturer accounts.

## Run locally

### Frontend

```bash
cd frontend
npm install
npm run dev
npm run build
```

### Backend

```bash
cd backend
python -m pip install -r requirements.txt
python -m pip install -r requirements-dev.txt
export DATABASE_URL='postgresql+asyncpg://user:password@localhost:5432/verity'
uvicorn app.main:app --reload
```

Apply migrations from `backend/` with `alembic upgrade head`. Authentication also requires the Ed25519 JWT environment configuration described in deployment settings; create an administrator with `python -m app.cli create-user --email admin@example.edu --role admin`, and provision lecturers with `--role lecturer`.

## Production checklist and known gaps

- [ ] Select CPU/camera/OS combinations; benchmark warm/cold latency, RAM, CPU, and power on each supported classroom device.
- [ ] Collect approved, consented validation data across lighting and target demographics; review false accept/reject tradeoffs and approve exact model hashes/thresholds.
- [ ] Confirm jurisdiction-specific student/guardian consent, withdrawal, retention, lawful basis, and non-biometric alternative.
- [ ] Provision and recovery-test AES keys, key rotation, filesystem encryption, and backup/snapshot deletion policy.
- [ ] Validate local-to-central sync and conflict reconciliation on two deployments; rotate the shared sync token.
- [ ] Evaluate liveness/PAD separately; a standard USB RGB webcam is not a validated liveness sensor.
- [ ] Test correction, duplicates, disk-full/database failure, power loss, network recovery, and restart on the target laptop.
- [ ] Apply Alembic migrations from a verified backup; retain the `0008` downgrade data guards.

Actual YuNet/SFace inference, face alignment, embedding extraction, quality rejection, encrypted template primitives, enrollment/deletion APIs, validation-manifest gating, manual-review UX, and transactional attendance outbox are implemented. A smoke test on one OpenCV Zoo sample exercised detection, alignment, and a normalized 128-element embedding; it is not an accuracy or classroom-robustness result. No student validation data, calibrated thresholds, demographic evaluation, or target-hardware benchmark exists. Automatic attendance remains disabled by default. Automated report signing/approval, browser camera capture, central user/class synchronization, conflict-resolution UI, PAD, and end-to-end power-loss testing remain incomplete.

The prior user change to `render.yaml` is preserved. Review deployment environment variables, database backups, and key management for the target environment before deploying.
