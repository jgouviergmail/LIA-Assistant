package com.lia.assistant;

import java.io.UnsupportedEncodingException;
import java.net.URLDecoder;
import java.nio.charset.StandardCharsets;
import java.util.Locale;
import java.util.Set;
import java.util.regex.Matcher;
import java.util.regex.Pattern;

/**
 * Which way an address goes, and what a file is called.
 *
 * <p>Pure, so the JVM tests hold it: {@link ShellFiles} and {@link ShellChromeClient} only apply
 * what it decides. One published app serves every self-hosted server, so nothing here names a
 * host: "the server" is whatever the person typed at first launch.
 */
final class ShellLinkRules {

    /** Every route of a LIA API starts here, on whichever host it is served. */
    private static final String API_PREFIX = "/api/v1/";

    /** What may leave for another application: never {@code intent:}, {@code file:} and the like. */
    private static final Set<String> OUTSIDE_SCHEMES = Set.of("http", "https", "mailto");

    /** The name a response gives in UTF-8 (RFC 6266), beside its plain ASCII one. */
    private static final Pattern ENCODED_NAME =
        Pattern.compile("filename\\*=UTF-8''([^;\\s]+)", Pattern.CASE_INSENSITIVE);

    private ShellLinkRules() {}

    /**
     * Whether an address may be handed to another application.
     *
     * @param scheme The address's scheme; may be null.
     * @return True for a web or mail address alone.
     */
    static boolean mayLeave(String scheme) {
        return scheme != null && OUTSIDE_SCHEMES.contains(scheme.toLowerCase(Locale.ROOT));
    }

    /**
     * Whether a host is the server's, or a sibling under its domain.
     *
     * <p>Production serves the web and the API on two hosts of one registrable domain
     * ({@code lia.} and {@code lia-back.}), which the iOS shell requires anyway. No list of public
     * suffixes ships here: a wrong "yes" only keeps an address in the WebView, and a cookie still
     * reaches no host but its own.
     *
     * @param serverHost The configured server's host; may be null.
     * @param host The address's host; may be null.
     * @return True when both belong to the same site.
     */
    static boolean isSameSite(String serverHost, String host) {
        if (serverHost == null || host == null) {
            return false;
        }
        String server = serverHost.toLowerCase(Locale.ROOT);
        String other = host.toLowerCase(Locale.ROOT);
        if (server.equals(other) || server.endsWith("." + other) || other.endsWith("." + server)) {
            return true;
        }
        String parent = parentOf(server);
        return parent.contains(".") && parent.equals(parentOf(other));
    }

    /**
     * Whether an address is the server's API, which only the WebView can reach with the session.
     *
     * @param serverHost The configured server's host; may be null.
     * @param host The address's host; may be null.
     * @param path The address's path; may be null.
     * @return True when the address must stay in the WebView.
     */
    static boolean isServerApi(String serverHost, String host, String path) {
        return path != null && path.startsWith(API_PREFIX) && isSameSite(serverHost, host);
    }

    /**
     * The file name a response gives in UTF-8, without any path it may carry.
     *
     * @param contentDisposition The response's header; may be null.
     * @return The name, or null when it gives none or none that can be read.
     */
    static String encodedFileName(String contentDisposition) {
        if (contentDisposition == null) {
            return null;
        }
        Matcher found = ENCODED_NAME.matcher(contentDisposition);
        if (!found.find()) {
            return null;
        }
        try {
            String name = URLDecoder.decode(
                found.group(1).replace("+", "%2B"),
                StandardCharsets.UTF_8.name()
            );
            String base = name.substring(Math.max(name.lastIndexOf('/'), name.lastIndexOf('\\')) + 1);
            return base.isEmpty() ? null : base;
        } catch (IllegalArgumentException | UnsupportedEncodingException unreadable) {
            return null;
        }
    }

    private static String parentOf(String host) {
        return host.substring(host.indexOf('.') + 1);
    }
}
