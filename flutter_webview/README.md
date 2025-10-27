Flutter WebView Shell (Hybrid Frontend)

Goal
- Wrap the existing web UI in a minimal Flutter app using WebView so it can be shipped as an APK. The app simply loads your deployed backend URL (same as the browser version).

How to set up
1) Create a Flutter app skeleton:
   flutter create flutter_webview
   cd flutter_webview

2) Add WebView dependency:
   flutter pub add webview_flutter

3) Replace lib/main.dart with the one in this repo at flutter_webview/lib/main.dart

4) For HTTP during development (non-HTTPS), enable cleartext on Android:
   - Edit android/app/src/main/AndroidManifest.xml, within <application ...> add:
     android:usesCleartextTraffic="true"

5) Run on a device/emulator:
   flutter run -d android

Configure the URL
- By default it loads http://127.0.0.1:5231. For production, pass --dart-define:
  flutter run -d android \
    --dart-define=INITIAL_URL=https://yourapp.onrender.com

Build APK
  flutter build apk --release \
    --dart-define=INITIAL_URL=https://yourapp.onrender.com

Notes
- The backend must be reachable (0.0.0.0 and CORS enabled). This project already sets host=0.0.0.0 and enables CORS.
- If you require in-app navigation back/forward or pull-to-refresh, extend the example in main.dart.

