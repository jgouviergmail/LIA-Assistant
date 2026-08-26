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
    /**
     * Where each deep-link host puts the user.
     *
     * <p>A map rather than one constant because two flows now come home this
     * way — provider sign-in and connector authorization — and a third would
     * otherwise be a third branch. The PATHS are fixed here on purpose: a link
     * that carried its own destination would let whoever claims the scheme
     * choose where the WebView goes next, and a custom scheme must be assumed
     * interceptable (App Links pin domains at build time, and one published app
     * serves every self-hosted server).
     */
    private static final java.util.Map<String, String> DEEP_LINK_PAGES = java.util.Map.of(
        "auth-callback",
        "/native-auth",
        "connector-callback",
        "/dashboard/settings",
        "mcp-callback",
        "/dashboard/settings"
    );

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
        String page = DEEP_LINK_PAGES.get(data.getHost());
        if (page == null) {
            // A host we do not serve. Navigating anywhere would be guessing.
            return;
        }

        String query = data.getEncodedQuery();
        String target = serverUrl + page + (query != null ? "?" + query : "");
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
