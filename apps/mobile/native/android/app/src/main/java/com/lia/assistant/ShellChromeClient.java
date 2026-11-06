package com.lia.assistant;

import android.graphics.Bitmap;
import android.net.Uri;
import android.os.Message;
import android.webkit.WebResourceRequest;
import android.webkit.WebView;
import android.webkit.WebViewClient;
import com.getcapacitor.Bridge;
import com.getcapacitor.BridgeWebChromeClient;

/**
 * Where a new window goes: a link the person pressed, a sandboxed frame's included.
 *
 * <p>Measured on Android 16 with Capacitor 8.5.3: a {@code target="_blank"} link in the frame of a
 * mail's original layout opened nothing, because a WebView only reports a new window once it is
 * told it supports them. A window has no address yet when it is asked for, so a page nobody
 * shows is handed over to read it, then let go. Only a gesture of the person opens anything.
 */
final class ShellChromeClient extends BridgeWebChromeClient {

    ShellChromeClient(Bridge bridge) {
        super(bridge);
    }

    @Override
    public boolean onCreateWindow(
        WebView page,
        boolean isDialog,
        boolean isUserGesture,
        Message resultMsg
    ) {
        if (!isUserGesture) {
            return false;
        }
        WebView window = new WebView(page.getContext());
        window.setWebViewClient(new FirstAddress(page));
        ((WebView.WebViewTransport) resultMsg.obj).setWebView(window);
        resultMsg.sendToTarget();
        return true;
    }

    /** Takes the one address a new window was opened for, then lets the window go. */
    private static final class FirstAddress extends WebViewClient {

        private final WebView page;
        private boolean taken;

        FirstAddress(WebView page) {
            this.page = page;
        }

        @Override
        public boolean shouldOverrideUrlLoading(WebView window, WebResourceRequest request) {
            take(window, request.getUrl());
            return true;
        }

        @Override
        public void onPageStarted(WebView window, String url, Bitmap favicon) {
            take(window, Uri.parse(url));
        }

        private void take(WebView window, Uri address) {
            // about:blank comes first, and says nothing of where the window was going.
            if (taken || !ShellLinkRules.mayLeave(address.getScheme())) {
                return;
            }
            taken = true;
            window.stopLoading();
            route(address);
            window.post(window::destroy);
        }

        private void route(Uri address) {
            String server = ShellFiles.serverHost(page.getContext());
            String host = address.getHost();
            boolean own = host != null && host.equalsIgnoreCase(server);
            if (own || ShellLinkRules.isServerApi(server, host, address.getPath())) {
                // The session lives here: the file or the page is the WebView's to reach.
                page.loadUrl(address.toString());
                return;
            }
            ShellFiles.open(page.getContext(), address);
        }
    }
}
