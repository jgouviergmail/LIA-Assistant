package com.lia.assistant;

import android.os.Bundle;
import android.webkit.CookieManager;
import com.getcapacitor.BridgeActivity;
import com.getcapacitor.CapConfig;

/**
 * The shell's entry point: which server to show, and not losing the session.
 */
public class MainActivity extends BridgeActivity {

    @Override
    public void onCreate(Bundle savedInstanceState) {
        // Before super: onCreate builds the bridge, and a plugin registered
        // afterwards would never be part of it.
        registerPlugin(ServerUrlPlugin.class);
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
