package com.lia.assistant;

import android.content.Context;
import com.google.firebase.FirebaseApp;
import com.google.firebase.FirebaseOptions;
import com.google.firebase.messaging.FirebaseMessaging;

/**
 * Obtain an FCM token for whichever Firebase project the user's server owns.
 *
 * <p>One app is published, and it points at whichever LIA server its user runs.
 * Baking a {@code google-services.json} into the binary would tie every install
 * to ONE Firebase project — the publisher's — and route every self-hoster's
 * notifications through it. So the options arrive at runtime from the server
 * itself (they are not secrets: every Android build ships them inside its APK)
 * and Firebase is initialised with them here.
 *
 * <p>The default app is what gets initialised, deliberately:
 * {@code FirebaseMessaging.getInstance()} reads no other.
 */
final class PushRegistrar {

    private PushRegistrar() {}

    /** Callback shape, so the plugin owns the bridge and this owns Firebase. */
    interface TokenCallback {
        void onToken(String token);

        void onFailure(String reason);
    }

    /**
     * Point Firebase at a project, replacing any project it was pointed at before.
     *
     * <p>Switching servers must switch projects: a token minted against the old
     * project is worthless to the new server, and Firebase refuses a second
     * {@code initializeApp} on the default name. Deleting first is the supported
     * way to change one's mind.
     *
     * @param context Application context.
     * @param options Options published by the server.
     */
    private static void pointAt(Context context, FirebaseOptions options) {
        for (FirebaseApp existing : FirebaseApp.getApps(context)) {
            if (FirebaseApp.DEFAULT_APP_NAME.equals(existing.getName())) {
                if (options.equals(existing.getOptions())) {
                    return;
                }
                existing.delete();
                break;
            }
        }
        FirebaseApp.initializeApp(context, options);
    }

    /**
     * Initialise Firebase and fetch this device's registration token.
     *
     * @param context Application context.
     * @param appId The project's mobilesdk_app_id.
     * @param apiKey The project's API key.
     * @param projectId The project id.
     * @param senderId The Cloud Messaging sender id.
     * @param callback Receives the token, or the reason there is none.
     */
    static void fetchToken(
        Context context,
        String appId,
        String apiKey,
        String projectId,
        String senderId,
        TokenCallback callback
    ) {
        try {
            FirebaseOptions options = new FirebaseOptions.Builder()
                .setApplicationId(appId)
                .setApiKey(apiKey)
                .setProjectId(projectId)
                .setGcmSenderId(senderId)
                .build();
            pointAt(context, options);
        } catch (IllegalArgumentException | IllegalStateException e) {
            // A partial or malformed set of options. The server said it had
            // push configured and it does not — saying so beats a crash.
            callback.onFailure("firebase_init_failed");
            return;
        }

        FirebaseMessaging.getInstance()
            .getToken()
            .addOnCompleteListener(task -> {
                if (task.isSuccessful() && task.getResult() != null) {
                    callback.onToken(task.getResult());
                } else {
                    // Play Services missing, no network, project misconfigured:
                    // one answer, because the user can do one thing about any.
                    callback.onFailure("token_unavailable");
                }
            });
    }
}
