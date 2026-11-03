# Invite All for Android

A [Trusted Web Activity](https://developer.chrome.com/docs/android/trusted-web-activity): the app opens
https://invite-all.com full screen in Chrome, so every website update reaches the app instantly.

**Builds** run on GitHub Actions (`.github/workflows/android.yml`) on every push that changes `android/`, or by hand
from the Actions tab. Each run uploads:

- `invite-all-<version>.apk`: install directly on a phone (Settings → allow installing from this source)
- `invite-all-<version>.aab`: upload to Google Play Console

**Signing:** the upload key lives only on the owner's PC and in the repository secrets
`ANDROID_KEYSTORE_B64` and `ANDROID_KEYSTORE_PASSWORD`. Without them the workflow builds a debug APK for testing.

**Full screen (no browser bar)** needs the key's SHA-256 fingerprint in the server's `ANDROID_SHA256` setting,
which publishes https://invite-all.com/.well-known/assetlinks.json. After uploading to Google Play, add Play's
"App signing key certificate" SHA-256 (Play Console → Setup → App integrity) to `ANDROID_SHA256` too,
separated by a comma.
