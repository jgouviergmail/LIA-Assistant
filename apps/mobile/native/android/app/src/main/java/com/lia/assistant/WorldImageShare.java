package com.lia.assistant;

import android.content.ClipData;
import android.content.Intent;
import android.graphics.Bitmap;
import android.graphics.BitmapFactory;
import android.net.Uri;
import android.os.Handler;
import android.os.Looper;
import android.webkit.WebView;
import android.util.Base64;
import androidx.core.content.FileProvider;
import androidx.lifecycle.Lifecycle;
import com.getcapacitor.PluginCall;
import java.io.File;
import java.util.concurrent.atomic.AtomicBoolean;

/** One chooser, read-only URI, and a small private expiring cache. */
final class WorldImageShare {
    private final AtomicBoolean busy = new AtomicBoolean(false);
    private boolean destroyed;

    void share(LiaShellPlugin plugin, PluginCall call) {
        if (!busy.compareAndSet(false, true)) { call.reject("world_photo_busy"); return; }
        plugin.getActivity().runOnUiThread(() -> {
            if (destroyed || plugin.getActivity().isFinishing()) {
                busy.set(false); call.reject("world_photo_page_closed"); return;
            }
            WebView page = plugin.getBridge().getWebView();
            prepare(plugin, call, page, page.getUrl());
        });
    }
    private void prepare(LiaShellPlugin plugin, PluginCall call, WebView page, String location) {
        plugin.getBridge().execute(() -> {
            File image = null;
            try {
                String encoded = call.getString("base64");
                WorldPhotoInput.validateEnvelope(encoded, call.getString("mimeType"), call.getString("filename"));
                byte[] bytes = Base64.decode(encoded, Base64.NO_WRAP);
                // Decoded, the base64 copy is dead weight: the call outlives it while
                // the chooser is open, and Capacitor keeps the last activity's call.
                call.getData().remove("base64");
                WorldPhotoInput.validateBytes(bytes);
                verifyImage(bytes);
                image = WorldPhotoCache.store(plugin.getContext().getCacheDir(), bytes, System.currentTimeMillis());
                final File expires = image;
                new Handler(Looper.getMainLooper()).postDelayed(() -> WorldPhotoCache.remove(expires), WorldPhotoCache.TTL_MS);
                final File ready = image;
                plugin.getActivity().runOnUiThread(() -> present(plugin, call, page, location, ready));
            } catch (Exception | OutOfMemoryError error) {
                if (image != null) remove(image);
                busy.set(false);
                call.reject("world_photo_share_failed");
            }
        });
    }
    private static void verifyImage(byte[] bytes) {
        BitmapFactory.Options options = new BitmapFactory.Options();
        options.inJustDecodeBounds = true;
        BitmapFactory.decodeByteArray(bytes, 0, bytes.length, options);
        if (!"image/jpeg".equals(options.outMimeType) || options.outWidth < 1 || options.outHeight < 1
            || options.outWidth > 1600 || options.outHeight > 1600) throw new IllegalArgumentException();
        try {
            Bitmap bitmap = BitmapFactory.decodeByteArray(bytes, 0, bytes.length);
            if (bitmap == null) throw new IllegalArgumentException();
            bitmap.recycle();
        } catch (OutOfMemoryError error) { throw new IllegalArgumentException("world_photo_memory"); }
    }
    private void present(LiaShellPlugin plugin, PluginCall call, WebView page, String location, File image) {
        if (destroyed || !page.isAttachedToWindow() || location == null || !location.equals(page.getUrl())
            || plugin.getActivity().isFinishing() || plugin.getActivity().isDestroyed()
            || !plugin.getActivity().getLifecycle().getCurrentState().isAtLeast(Lifecycle.State.RESUMED)) {
            remove(image); busy.set(false); call.reject("world_photo_page_closed"); return;
        }
        try {
            Uri uri = FileProvider.getUriForFile(plugin.getContext(), plugin.getContext().getPackageName() + ".worldshare", image);
            Intent send = new Intent(Intent.ACTION_SEND);
            send.setType("image/jpeg"); send.putExtra(Intent.EXTRA_STREAM, uri);
            send.setClipData(ClipData.newRawUri("LIA World", uri));
            send.addFlags(Intent.FLAG_GRANT_READ_URI_PERMISSION);
            Intent chooser = Intent.createChooser(send, "LIA World");
            chooser.addFlags(Intent.FLAG_GRANT_READ_URI_PERMISSION);
            plugin.startActivityForResult(call, chooser, "imageShared");
        } catch (Exception error) {
            // The launch may throw after startActivityForResult saved the call on
            // the bridge: release it with the rejection (a no-op when unsaved).
            remove(image); busy.set(false); call.reject("world_photo_chooser_unavailable");
            plugin.getBridge().releaseCall(call);
        }
    }
    void finished() { busy.set(false); }
    void destroy() { destroyed = true; }
    private static void remove(File image) { WorldPhotoCache.remove(image); }
}
