package com.lia.assistant;

import android.content.Intent;
import android.net.Uri;
import android.os.Bundle;
import android.util.Log;
import android.webkit.CookieManager;
import android.webkit.JavascriptInterface;
import android.webkit.WebView;
import com.getcapacitor.BridgeActivity;
import com.getcapacitor.CapConfig;

/**
 * The shell's entry point: which server to show, and not losing the session.
 */
public class MainActivity extends BridgeActivity {

    /** Scheme the manifest registers for the sign-in return trip. */
    private static final String DEEP_LINK_SCHEME = "lia";

    /**
     * Bundled page shown when a navigation to the server fails.
     *
     * <p>Must match {@code server.errorPath} in capacitor.config.json: the JSON
     * governs the unconfigured state (bridge built from the file), this
     * constant governs the configured one (bridge built from the Builder).
     */
    private static final String OFFLINE_ERROR_PATH = "offline.html";

    /**
     * Where each deep-link host puts the user.
     *
     * <p>A map rather than one constant because three flows come home this way
     * — provider sign-in, connector authorization, MCP authorization — and a
     * fourth would otherwise be a fourth branch. The PATHS are fixed here on
     * purpose: a link that carried its own destination would let whoever claims
     * the scheme choose where the WebView goes next, and a custom scheme must
     * be assumed interceptable (App Links pin domains at build time, and one
     * published app serves every self-hosted server).
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
            // The Builder starts from NOTHING — it does not read
            // capacitor.config.json. Every server.* value the JSON declares has
            // to be carried across by hand here, or it silently disappears in
            // exactly the state where the app is actually used. Found the hard
            // way: errorPath was dropped, so the offline screen never loaded
            // once a server was configured — the only state where it matters.
            // (iOS is immune: instanceDescriptor() starts from the PARSED
            // config and only overrides serverURL.) Guarded by
            // apps/api/tests/unit/test_mobile_shell_pages_guard.py.
            this.config = new CapConfig.Builder(this)
                .setServerUrl(serverUrl)
                .setErrorPath(OFFLINE_ERROR_PATH)
                .create();
        }
        super.load();

        // The offline screen cannot use the Capacitor bridge: with a REMOTE
        // server configured, Android injects the bridge only into that
        // origin's documents, never into the local errorPath page — measured
        // by the shell bench, whose first real run found both buttons dead
        // (`window.Capacitor` undefined; iOS is immune, WKUserScript injects
        // on every navigation). A JavascriptInterface is the platform's own
        // mechanism for exactly this, and it survives navigations.
        if (bridge != null && bridge.getWebView() != null) {
            bridge.getWebView().addJavascriptInterface(new OfflineActions(), "LiaOffline");
        }

        // A deep link can also be what STARTED the app: the system browser may
        // have reclaimed the shell during the OAuth dance (low memory), and the
        // return trip then arrives on the LAUNCH intent, not onNewIntent. iOS
        // has this covered upstream — Capacitor's SceneDelegateProxy defers the
        // cold-start URL until plugins are registered — Android does not, and
        // without this the sign-in code was silently dropped exactly when the
        // device was under pressure.
        handleDeepLink(getIntent());
    }

    /**
     * The two actions the offline screen needs, without the bridge.
     *
     * <p>An added interface is visible to EVERY page this WebView loads — the
     * user's own server included — so each method re-checks, on the UI thread,
     * that the caller IS the bundled offline page. Without that guard, any
     * script on the remote origin could silently un-configure the app.
     */
    private class OfflineActions {

        /** Rebuild the bridge, which retries the configured server. */
        @JavascriptInterface
        public void retry() {
            runOnUiThread(() -> {
                if (isOnOfflinePage()) {
                    recreate();
                }
            });
        }

        /** Forget the stored server and return to the setup screen. */
        @JavascriptInterface
        public void forget() {
            runOnUiThread(() -> {
                if (isOnOfflinePage()) {
                    ServerUrlStore.clear(MainActivity.this);
                    recreate();
                }
            });
        }
    }

    /**
     * Whether the WebView currently shows the bundled offline page.
     *
     * <p>UI thread only: {@link WebView#getUrl()} requires it.
     *
     * @return True only for the errorPath page on the local origin.
     */
    private boolean isOnOfflinePage() {
        WebView view = bridge != null ? bridge.getWebView() : null;
        String url = view != null ? view.getUrl() : null;
        return url != null && url.startsWith("https://localhost/") && url.contains(OFFLINE_ERROR_PATH);
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
        handleDeepLink(intent);
    }

    /**
     * Navigate the WebView to the page a deep link names, if it names one.
     *
     * <p>Shared between the warm path ({@link #onNewIntent}) and the cold one
     * (the launch intent, read at the end of {@link #load()}): the OS delivers
     * the same link through whichever door matches the app's state, and only
     * one of the two ever fires for a given arrival.
     *
     * <p>The intent's data is CONSUMED afterwards. {@code recreate()} — which
     * the offline screen's retry and forget both use — replays the launch
     * intent through {@code onCreate}, and replaying a sign-in link would
     * navigate to a code that was already spent.
     *
     * @param intent The intent that started or resumed us; may be null.
     */
    private void handleDeepLink(Intent intent) {
        Uri data = intent != null ? intent.getData() : null;
        if (data == null || !DEEP_LINK_SCHEME.equals(data.getScheme())) {
            return;
        }
        // Host only, NEVER the query: it carries the single-use sign-in code.
        Log.d("LiaShell", "deep link received, host=" + data.getHost());

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

        intent.setData(null);

        String query = data.getEncodedQuery();
        String target = serverUrl + page + (query != null ? "?" + query : "");
        if (bridge != null && bridge.getWebView() != null) {
            Log.d("LiaShell", "deep link navigating, page=" + page);
            bridge.getWebView().post(() -> bridge.getWebView().loadUrl(target));
        } else {
            Log.d("LiaShell", "deep link dropped: no webview yet");
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
