package com.lia.assistant;

import android.app.DownloadManager;
import android.content.Context;
import android.content.Intent;
import android.net.Uri;
import android.os.Build;
import android.os.Environment;
import android.util.Log;
import android.webkit.CookieManager;
import android.webkit.DownloadListener;
import android.webkit.URLUtil;

/**
 * A file the server sends, taken by the system's download manager with the person's session.
 *
 * <p>Measured on Android 16 with Capacitor 8.5.3: neither sets a {@link DownloadListener}, so a
 * {@code Content-Disposition: attachment} was answered and dropped, with no file and no error.
 * The session cookie goes to the host that set it and to no other, exactly as the WebView itself
 * would send it. A file of any other site leaves for the system browser, without it.
 */
final class ShellFiles implements DownloadListener {

    private final Context context;

    ShellFiles(Context context) {
        this.context = context;
    }

    @Override
    public void onDownloadStart(
        String url,
        String userAgent,
        String contentDisposition,
        String mimeType,
        long contentLength
    ) {
        Uri address = Uri.parse(url);
        if (!ShellLinkRules.isSameSite(serverHost(context), address.getHost())) {
            open(context, address);
            return;
        }
        try {
            enqueue(address, url, userAgent, contentDisposition, mimeType);
        } catch (IllegalArgumentException | IllegalStateException | SecurityException refused) {
            // The class, never the address: it may carry an id of the person's.
            Log.w("LiaShell", "download refused: " + refused.getClass().getSimpleName());
        }
    }

    private void enqueue(
        Uri address,
        String url,
        String userAgent,
        String contentDisposition,
        String mimeType
    ) {
        String name = ShellLinkRules.encodedFileName(contentDisposition);
        if (name == null) {
            name = URLUtil.guessFileName(url, contentDisposition, mimeType);
        }
        DownloadManager.Request request = new DownloadManager.Request(address);
        String cookies = CookieManager.getInstance().getCookie(url);
        if (cookies != null) {
            request.addRequestHeader("Cookie", cookies);
        }
        request.addRequestHeader("User-Agent", userAgent);
        request.setMimeType(mimeType);
        request.setTitle(name);
        request.setNotificationVisibility(DownloadManager.Request.VISIBILITY_VISIBLE_NOTIFY_COMPLETED);
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.Q) {
            request.setDestinationInExternalPublicDir(Environment.DIRECTORY_DOWNLOADS, name);
        } else {
            // Before Android 10 the public folder needs a storage permission the shell does not
            // ask: the file lands in the app's own folder, reached from its notification.
            request.setDestinationInExternalFilesDir(context, Environment.DIRECTORY_DOWNLOADS, name);
        }
        DownloadManager manager = (DownloadManager) context.getSystemService(Context.DOWNLOAD_SERVICE);
        manager.enqueue(request);
    }

    /**
     * The host of the server this installation points at.
     *
     * @param context Any context.
     * @return Its host, or null before the shell is set up.
     */
    static String serverHost(Context context) {
        String server = ServerUrlStore.read(context);
        return server == null ? null : Uri.parse(server).getHost();
    }

    /**
     * Hand an address to the application that takes it.
     *
     * @param context Any context.
     * @param address A web or mail address; any other scheme stays here.
     */
    static void open(Context context, Uri address) {
        if (!ShellLinkRules.mayLeave(address.getScheme())) {
            return;
        }
        try {
            Intent intent = new Intent(Intent.ACTION_VIEW, address);
            intent.addFlags(Intent.FLAG_ACTIVITY_NEW_TASK);
            context.startActivity(intent);
        } catch (android.content.ActivityNotFoundException nothing) {
            Log.w("LiaShell", "no application for scheme " + address.getScheme());
        }
    }
}
