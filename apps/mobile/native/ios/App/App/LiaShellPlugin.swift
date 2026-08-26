import Capacitor
import Foundation
import UIKit

/// The web layer's only door into the shell.
///
/// Deliberately small: the setup screen is a bundled HTML page and the sign-in
/// flow is the web app's own, so layout, wording, six languages and
/// accessibility stay where the rest of the product's do. What is left is what
/// a page genuinely cannot do — reach the network without CORS, remember an
/// origin across launches, rebuild the bridge, and hand a URL to the system
/// browser.
@objc(LiaShellPlugin)
public class LiaShellPlugin: CAPPlugin, CAPBridgedPlugin {

    public let identifier = "LiaShellPlugin"
    public let jsName = "LiaShell"
    public let pluginMethods: [CAPPluginMethod] = [
        CAPPluginMethod(name: "get", returnType: CAPPluginReturnPromise),
        CAPPluginMethod(name: "probe", returnType: CAPPluginReturnPromise),
        CAPPluginMethod(name: "set", returnType: CAPPluginReturnPromise),
        CAPPluginMethod(name: "openExternal", returnType: CAPPluginReturnPromise),
        CAPPluginMethod(name: "forget", returnType: CAPPluginReturnPromise),
        CAPPluginMethod(name: "registerPush", returnType: CAPPluginReturnPromise),
        CAPPluginMethod(name: "restart", returnType: CAPPluginReturnPromise)
    ]

    /// Long enough for a home server behind a tunnel, short enough to fail visibly.
    private static let probeTimeout: TimeInterval = 8

    /// Report the configured origin, if any.
    @objc func get(_ call: CAPPluginCall) {
        call.resolve(["url": ServerUrlStore.read() as Any])
    }

    /// Ask an origin whether a LIA lives there — from the NATIVE side.
    ///
    /// This check cannot run in the page. The setup screen is served from the
    /// shell's own local origin, so calling the server from JavaScript is a
    /// cross-origin request, and the API's `CORS_ORIGINS` names the web app —
    /// never a shell. Every correctly configured server would have been
    /// reported unreachable. A native client has no such notion.
    @objc func probe(_ call: CAPPluginCall) {
        guard let origin = try? ServerUrlStore.normalise(call.getString("url")),
              let url = URL(string: origin + "/api/v1/health")
        else {
            call.reject("server url must be https", "INVALID_SERVER_URL")
            return
        }

        var request = URLRequest(url: url)
        request.httpMethod = "GET"
        request.timeoutInterval = Self.probeTimeout
        request.cachePolicy = .reloadIgnoringLocalCacheData

        URLSession.shared.dataTask(with: request) { _, response, _ in
            // Unreachable, wrong host, bad certificate: all one answer. The user
            // can only do one thing about any of them.
            let status = (response as? HTTPURLResponse)?.statusCode ?? 0
            call.resolve(["ok": (200..<300).contains(status), "status": status])
        }.resume()
    }

    /// Store an origin and report the normalised value.
    ///
    /// Rejection is a normal outcome, not an error to swallow: the setup screen
    /// shows the reason, which is the only moment a typo is still cheap to fix.
    @objc func set(_ call: CAPPluginCall) {
        do {
            let stored = try ServerUrlStore.write(call.getString("url"))
            call.resolve(["url": stored])
        } catch {
            call.reject("server url must be https", "INVALID_SERVER_URL")
        }
    }

    /// Hand a URL to the system browser.
    ///
    /// Provider sign-in cannot run in a WebView — both engines are refused with
    /// `disallowed_useragent` — so the flow has to leave the app. What brings
    /// the user back is the `lia://auth-callback` scheme declared in Info.plist.
    @objc func openExternal(_ call: CAPPluginCall) {
        guard let raw = call.getString("url"),
              let url = URL(string: raw),
              url.scheme == "https" || url.scheme == "http"
        else {
            // Only ever an http(s) URL: handing an arbitrary scheme to the
            // system would let the page open any other application.
            call.reject("url must be http(s)", "INVALID_URL")
            return
        }

        DispatchQueue.main.async {
            UIApplication.shared.open(url, options: [:]) { opened in
                if opened {
                    call.resolve()
                } else {
                    call.reject("no browser available", "NO_BROWSER")
                }
            }
        }
    }

    /// Forget the configured origin.
    ///
    /// Separate from `set` on purpose: `set` validates and stores an address,
    /// and letting it also mean "erase" when handed nothing would weaken the
    /// one check standing between a typo and an app that never loads.
    ///
    /// - Parameter call: Resolves once the origin is forgotten.
    @objc func forget(_ call: CAPPluginCall) {
        ServerUrlStore.clear()
        call.resolve()
    }

    /// Obtain a push token for this device.
    ///
    /// The web layer hands over the whole `/notifications/push-config` payload
    /// and each platform reads its own half, so the page never has to know
    /// which one it is running on. Here that half is a relay URL — see
    /// `PushRegistrar` for why iOS cannot be notified by its own server.
    ///
    /// - Parameter call: Expects the push configuration; resolves with
    ///   `{token: string|null, deviceType: "ios", reason?: string}`.
    @objc func registerPush(_ call: CAPPluginCall) {
        guard
            let ios = call.getObject("ios"),
            let relayUrl = ios["relay_url"] as? String,
            !relayUrl.isEmpty
        else {
            // The server offers no relay. Not an error: a deployment may
            // simply have chosen not to use one, and the page says so.
            call.resolve(["token": NSNull(), "deviceType": "ios", "reason": "not_configured"])
            return
        }

        PushRegistrar.register(
            relayUrl: relayUrl,
            language: call.getString("language") ?? "fr"
        ) { outcome in
            call.resolve([
                "token": outcome.token ?? NSNull(),
                "deviceType": "ios",
                "reason": outcome.reason ?? NSNull(),
            ])
        }
    }

    /// Rebuild the shell so a newly stored origin takes effect.
    ///
    /// The server URL is read when the bridge is BUILT, and a bridge is built
    /// once. Replacing the root view controller is what applies it — reloading
    /// the WebView would only reload the setup screen.
    @objc func restart(_ call: CAPPluginCall) {
        call.resolve()
        DispatchQueue.main.async {
            guard
                let scene = UIApplication.shared.connectedScenes.first as? UIWindowScene,
                let window = scene.windows.first(where: { $0.isKeyWindow }) ?? scene.windows.first,
                let controller = UIStoryboard(name: "Main", bundle: nil)
                    .instantiateInitialViewController()
            else { return }
            window.rootViewController = controller
        }
    }
}
