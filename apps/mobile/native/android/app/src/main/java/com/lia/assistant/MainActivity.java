package com.lia.assistant;

import android.content.Intent;
import android.net.Uri;
import android.os.Bundle;
import android.webkit.CookieManager;
import com.getcapacitor.BridgeActivity;
import com.getcapacitor.CapConfig;

/**
 * The shell's entry point: which server to show, and not losing the session.
 */
public class MainActivity extends BridgeActivity {

    /** Scheme the manifest registers for the sign-in return trip. */
    private static final String DEEP_LINK_SCHEME = "lia";

    /** Web route that spends a handoff code; localisation is the app's own job. */
    private static final String NATIVE_AUTH_PATH = "/native-auth";

    @Override
    public void onCreate(Bundle savedInstanceState) {
        // Before super: onCreate builds the bridge, and a plugin registered
        // afterwards would never be part of it.
        registerPlugin(LiaShellPlugin.class);
        super.onCreate(savedInstanceState);
    }

    /**
     * Point the WebView at this installation's server, when it has one.
     *
     * <p>Without a stored origin the bridge falls back to the bundled assets —
     * the setup screen — because `capacitor.config.json` names `www` as its
     * webDir and supplies no server URL.
     */
    @Override
    protected void load() {
        String serverUrl = ServerUrlStore.read(this);
        if (serverUrl != null && !serverUrl.isEmpty()) {
            this.config = new CapConfig.Builder(this).setServerUrl(serverUrl).create();
        }
        super.load();
    }

    /**
     * Bring a provider sign-in back into the WebView.
     *
     * <p>The system browser finished the flow and the operating system handed
     * us {@code lia://auth-callback?code=…}. That code is not a session: it is
     * spent by the web layer, from the WebView, against the verifier it kept —
     * so all this does is put the WebView on the page that knows how.
     *
     * <p>The activity is {@code singleTask}, so a running shell receives this
     * here rather than being started afresh.
     *
     * @param intent The intent that resumed us.
     */
    @Override
    public void onNewIntent(Intent intent) {
        super.onNewIntent(intent);

        Uri data = intent != null ? intent.getData() : null;
        if (data == null || !DEEP_LINK_SCHEME.equals(data.getScheme())) {
            return;
        }

        String serverUrl = ServerUrlStore.read(this);
        if (serverUrl == null || serverUrl.isEmpty()) {
            // No server yet: a sign-in cannot have started, so this link is not
            // ours to act on.
            return;
        }

        // The query is carried across verbatim — the code and any error the
        // provider reported. Building the target here rather than in the page
        // keeps the WebView from ever seeing the custom-scheme URL itself.
        String query = data.getEncodedQuery();
        String target = serverUrl + NATIVE_AUTH_PATH + (query != null ? "?" + query : "");
        if (bridge != null && bridge.getWebView() != null) {
            bridge.getWebView().post(() -> bridge.getWebView().loadUrl(target));
        }
    }

    /**
     * Write the cookie store to disk before this app can be reclaimed.
     *
     * <p>Measured on Android 16 / WebView 133: Chromium flushes its cookie jar
     * on a ~30 s timer and Capacitor calls {@code flush()} nowhere. A restart 28
     * seconds after sign-in LOST the session; the same restart at 60 seconds
     * kept it. Without this line a user who signs in and leaves is signed out —
     * which is exactly when someone backgrounds an app.
     *
     * <p>Reproduce the hazard with
     * {@code task mobile:probe:android -- --settle 25000}.
     */
    @Override
    public void onPause() {
        super.onPause();
        CookieManager.getInstance().flush();
    }
}
