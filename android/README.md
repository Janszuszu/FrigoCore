# FrigoCore Service (Android)

Native Android client for FrigoCore technicians — receives and acts on
critical service alarms dispatched by the existing FastAPI backend
(`backend/app/api/routes.py`, `backend/app/services/dispatch_service.py`).

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
