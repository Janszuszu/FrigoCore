# FrigoCore (Android)

Native Android client for FrigoCore, for two audiences selected by the
logged-in user's role:

- **Technicians** (`serwisant`, `kierownik`, `admin`) — receive and act on
  critical SERVICE_ALARM pushes (full-screen alarm, accept / en route /
  resolve) and can browse every object.
- **Object owners** (`user`) — see only their assigned objects: live sensor
  temperatures, 6 h / 24 h / 7 d charts, open alarms, and get informational
  CLIENT_ALARM pushes (alarm raised, service en route, alarm closed).

Backend contract: `backend/app/api/routes.py`,
`backend/app/services/dispatch_service.py:notify_object_owners`,
`backend/app/services/notification_engine.py`.

## applicationId

- Release and debug both use `pl.frigocore.service`.

Only one Firebase Android app (`pl.frigocore.service`) is registered. Debug
builds intentionally do not use an `applicationIdSuffix` — the Google
Services Gradle plugin requires an exact applicationId match against every
client entry in `google-services.json`, and it hard-fails the build (not
just FCM init) for any variant whose applicationId isn't registered. If a
separate `pl.frigocore.service.debug` Firebase app is added later for
side-by-side install with release, `applicationIdSuffix = ".debug"` can be
restored once that app is registered in the Firebase console.

## First-time setup

1. In the Firebase console, add an Android app for `pl.frigocore.service`
   (and optionally `pl.frigocore.service.debug`), download
   `google-services.json`, and place it at `app/google-services.json`.
   This file is intentionally not committed (see `.gitignore`) and is not
   fabricated here — the build compiles and unit-tests without it, but FCM
   won't actually initialize until it's present.
2. `local.properties` already points `sdk.dir` at the local SDK and sets
   `API_BASE_URL=https://frigocore.pl/api/v1/`. Change `API_BASE_URL` if
   pointing at a different backend (e.g. a local dev server).
3. Build: `./gradlew assembleDebug`

## Release build (Google Play)

1. Create the upload key once and keep it backed up outside the repo —
   losing it means Play support has to reset the upload key:
   `keytool -genkeypair -v -keystore frigocore-upload.jks -keyalg RSA -keysize 2048 -validity 10000 -alias upload`
2. Create `android/keystore.properties` (gitignored):
   ```
   storeFile=frigocore-upload.jks
   storePassword=...
   keyAlias=upload
   keyPassword=...
   ```
3. Bump `versionCode` in `app/build.gradle.kts`, then `./gradlew :app:bundleRelease`
   → `app/build/outputs/bundle/release/app-release.aab`.
4. Enrol in Play App Signing when uploading the first bundle.

Privacy policy for the store listing: `https://frigocore.pl/privacy.html`
(`frontend/public/privacy.html`).

## Architecture

- `data/api` — Retrofit interface mirroring `backend/app/api/routes.py`
  exactly, `AuthInterceptor` (bearer token + 401 detection).
- `data/model` — DTOs matching `backend/app/schemas.py`, plus
  `ServiceAlarmPayload` for the SERVICE_ALARM FCM data payload
  (`backend/app/services/notification_engine.py:build_service_alarm_payload`).
- `data/local` — `SessionStore` (EncryptedSharedPreferences-backed token +
  user), `SessionExpiredNotifier` (fan-out on 401).
- `data/repository` — `AuthRepository`, `AlarmRepository`,
  `DeviceRepository`; every call returns a confirmed `ApiResult`, never an
  optimistic success.
- `fcm` — `FrigoFcmService` (token refresh + message receipt),
  `AlarmNotificationHelper` (full-screen-intent critical notification),
  `AlarmDedupStore` (redelivery dedup by assignment_id),
  `AlarmActionReceiver` (notification action buttons → AlarmActivity).
- `ui/alarm` — `AlarmActivity` (dedicated full-screen alarm screen,
  `setShowWhenLocked`/`setTurnScreenOn`), `AlarmViewModel`.
- `ui/login`, `ui/dashboard` — Compose screens + Hilt ViewModels.

## Verification performed in this environment

- `./gradlew :app:compileDebugKotlin` — success
- `./gradlew :app:assembleDebug` — success (`app/build/outputs/apk/debug/app-debug.apk`)
- `./gradlew :app:testDebugUnitTest` — 37/37 unit tests pass
- `./gradlew :app:lintDebug` — 0 errors (warnings only)

No instrumentation/emulator run was performed — no emulator/device was
available in this environment.
