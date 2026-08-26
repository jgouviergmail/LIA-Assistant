package com.lia.assistant;

import android.content.Context;
import android.content.SharedPreferences;
import java.net.MalformedURLException;
import java.net.URL;

/**
 * Where this installation's LIA server lives.
 *
 * One published app serves every self-hosted instance, so the origin cannot be
 * baked in: the user names it at first launch and it is read back here, before
 * the WebView is built.
 */
public final class ServerUrlStore {

    private static final String PREFS = "lia.shell";
    private static final String KEY = "server_url";

    private ServerUrlStore() {}

    /**
     * Read the configured origin.
     *
     * @param context Any context.
     * @return The stored origin, or null when the shell has never been set up.
     */
    public static String read(Context context) {
        return prefs(context).getString(KEY, null);
    }

    /**
     * Store an origin, refusing anything that cannot carry a session.
     *
     * <p>HTTPS is not a preference here. The session cookie is {@code Secure},
     * Android 17 enforces certificate transparency with no opt-out, and a
     * cleartext origin would fail later — at sign-in, with nothing on screen to
     * explain why. Refusing it at the door is the only place the user can still
     * act on it.
     *
     * @param context Any context.
     * @param url Candidate origin, as typed.
     * @return The normalised origin that was stored.
     * @throws IllegalArgumentException When the value is not a usable HTTPS origin.
     */
    public static String write(Context context, String url) {
        String normalised = normalise(url);
        prefs(context).edit().putString(KEY, normalised).apply();
        return normalised;
    }

    /** Forget the configured origin (used when the user switches instance). */
    public static void clear(Context context) {
        prefs(context).edit().remove(KEY).apply();
    }

    /**
     * Reduce a typed value to a bare origin, or refuse it.
     *
     * @param url Candidate origin.
     * @return Scheme + host (+ port), with no trailing slash.
     * @throws IllegalArgumentException When the value is unusable.
     */
    static String normalise(String url) {
        if (url == null || url.trim().isEmpty()) {
            throw new IllegalArgumentException("server url is empty");
        }
        URL parsed;
        try {
            parsed = new URL(url.trim());
        } catch (MalformedURLException e) {
            throw new IllegalArgumentException("server url is not a URL", e);
        }
        if (!"https".equalsIgnoreCase(parsed.getProtocol())) {
            throw new IllegalArgumentException("server url must be https");
        }
        if (parsed.getHost() == null || parsed.getHost().isEmpty()) {
            throw new IllegalArgumentException("server url has no host");
        }
        String port = parsed.getPort() == -1 ? "" : ":" + parsed.getPort();
        return "https://" + parsed.getHost() + port;
    }

    private static SharedPreferences prefs(Context context) {
        return context.getSharedPreferences(PREFS, Context.MODE_PRIVATE);
    }
}
