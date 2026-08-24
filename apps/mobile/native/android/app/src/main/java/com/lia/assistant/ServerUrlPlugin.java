package com.lia.assistant;

import com.getcapacitor.JSObject;
import com.getcapacitor.Plugin;
import com.getcapacitor.PluginCall;
import com.getcapacitor.PluginMethod;
import com.getcapacitor.annotation.CapacitorPlugin;
import java.net.HttpURLConnection;
import java.net.URL;

/**
 * The setup screen's only door into the native layer.
 *
 * Deliberately small: the screen itself is a bundled HTML page, so its layout,
 * its six languages and its accessibility stay in the codebase that already
 * owns them instead of being written twice, in Android XML and in SwiftUI.
 */
@CapacitorPlugin(name = "ServerUrl")
public class ServerUrlPlugin extends Plugin {

    /** Long enough for a home server behind a tunnel, short enough to fail visibly. */
    private static final int PROBE_TIMEOUT_MS = 8000;

    /**
     * Report the configured origin, if any.
     *
     * @param call Resolves with {@code {url: string|null}}.
     */
    @PluginMethod
    public void get(PluginCall call) {
        JSObject result = new JSObject();
        result.put("url", ServerUrlStore.read(getContext()));
        call.resolve(result);
    }

    /**
     * Ask an origin whether a LIA lives there — from the NATIVE side.
     *
     * <p>This check cannot run in the page. The setup screen is served from the
     * shell's own local origin, so calling the server from JavaScript is a
     * cross-origin request, and the API's {@code CORS_ORIGINS} names the web app
     * — never a shell. Every correctly configured server would have been
     * reported unreachable. A native client has no such notion.
     *
     * @param call Expects {@code {url: string}}; resolves with
     *     {@code {ok: boolean, status: number}}.
     */
    @PluginMethod
    public void probe(PluginCall call) {
        final String url = call.getString("url");
        // Off the main thread: Android throws NetworkOnMainThreadException, and
        // a plugin method runs on the main thread by default.
        getBridge()
            .execute(() -> {
                HttpURLConnection connection = null;
                try {
                    String origin = ServerUrlStore.normalise(url);
                    connection = (HttpURLConnection) new URL(origin + "/api/v1/health").openConnection();
                    connection.setRequestMethod("GET");
                    connection.setConnectTimeout(PROBE_TIMEOUT_MS);
                    connection.setReadTimeout(PROBE_TIMEOUT_MS);
                    connection.setInstanceFollowRedirects(true);
                    int status = connection.getResponseCode();

                    JSObject result = new JSObject();
                    result.put("ok", status >= 200 && status < 300);
                    result.put("status", status);
                    call.resolve(result);
                } catch (IllegalArgumentException e) {
                    call.reject(e.getMessage(), "INVALID_SERVER_URL");
                } catch (Exception e) {
                    // Unreachable, wrong host, bad certificate: all one answer.
                    // The user can only do one thing about any of them.
                    JSObject result = new JSObject();
                    result.put("ok", false);
                    result.put("status", 0);
                    call.resolve(result);
                } finally {
                    if (connection != null) {
                        connection.disconnect();
                    }
                }
            });
    }

    /**
     * Store an origin and report the normalised value.
     *
     * <p>Rejection is a normal outcome, not an error to swallow: the setup
     * screen shows the reason, which is the only moment a typo is still cheap
     * to fix.
     *
     * @param call Expects {@code {url: string}}; resolves with the stored origin.
     */
    @PluginMethod
    public void set(PluginCall call) {
        String url = call.getString("url");
        try {
            String stored = ServerUrlStore.write(getContext(), url);
            JSObject result = new JSObject();
            result.put("url", stored);
            call.resolve(result);
        } catch (IllegalArgumentException e) {
            call.reject(e.getMessage(), "INVALID_SERVER_URL");
        }
    }

    /**
     * Rebuild the shell so a newly stored origin takes effect.
     *
     * <p>The server URL is read when the bridge is BUILT, and a bridge is built
     * once per activity. Recreating the activity is what applies it — reloading
     * the WebView would only reload the setup screen.
     *
     * @param call Resolves once the restart is scheduled.
     */
    @PluginMethod
    public void restart(PluginCall call) {
        call.resolve();
        getActivity().runOnUiThread(() -> getActivity().recreate());
    }
}
