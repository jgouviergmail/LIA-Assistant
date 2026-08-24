import Capacitor
import Foundation
import UIKit

/// The setup screen's only door into the native layer.
///
/// Deliberately small: the screen itself is a bundled HTML page, so its layout,
/// its six languages and its accessibility stay in the codebase that already
/// owns them instead of being written twice, in Android XML and in SwiftUI.
@objc(ServerUrlPlugin)
public class ServerUrlPlugin: CAPPlugin, CAPBridgedPlugin {

    public let identifier = "ServerUrlPlugin"
    public let jsName = "ServerUrl"
    public let pluginMethods: [CAPPluginMethod] = [
        CAPPluginMethod(name: "get", returnType: CAPPluginReturnPromise),
        CAPPluginMethod(name: "probe", returnType: CAPPluginReturnPromise),
        CAPPluginMethod(name: "set", returnType: CAPPluginReturnPromise),
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
