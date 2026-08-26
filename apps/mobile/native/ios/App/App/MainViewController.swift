import Capacitor
import UIKit
import WebKit

/// The shell's entry point: which server to show, and its own plugin.
class MainViewController: CAPBridgeViewController {

    /// Scheme Info.plist registers for the sign-in return trip.
    private static let deepLinkScheme = "lia"

    /// Where each deep-link host puts the user.
    ///
    /// A map rather than one constant because two flows now come home this way
    /// — provider sign-in and connector authorization — and a third would
    /// otherwise be a third branch. The PATHS are fixed here on purpose: a link
    /// carrying its own destination would let whoever claims the scheme choose
    /// where the WebView goes next, and a custom scheme must be assumed
    /// interceptable (App Links pin domains at build time, and one published
    /// app serves every self-hosted server).
    private static let deepLinkPages = [
        "auth-callback": "/native-auth",
        "connector-callback": "/dashboard/settings",
        "mcp-callback": "/dashboard/settings",
    ]

    /// Point the WebView at this installation's server, when it has one.
    ///
    /// Without a stored origin the descriptor is left alone, so the bridge falls
    /// back to the bundled assets — the setup screen.
    override func instanceDescriptor() -> InstanceDescriptor {
        let descriptor = super.instanceDescriptor()
        if let serverUrl = ServerUrlStore.read(), !serverUrl.isEmpty {
            descriptor.serverURL = serverUrl
        }
        return descriptor
    }

    /// Bring a provider sign-in back into the WebView.
    ///
    /// The system browser finished the flow and iOS handed the app
    /// `lia://auth-callback?code=…`. That code is not a session: it is spent by
    /// the web layer, from this WebView, against the verifier it kept — so all
    /// this does is put the WebView on the page that knows how.
    ///
    /// Capacitor's application-delegate proxy publishes every opened URL as a
    /// notification, which is a smaller surface to take than a custom
    /// AppDelegate — one more generated file to shadow, for nothing.
    private func observeDeepLinks() {
        NotificationCenter.default.addObserver(
            forName: .capacitorOpenURL,
            object: nil,
            queue: .main
        ) { [weak self] notification in
            guard let payload = notification.object as? [String: Any],
                  let url = payload["url"] as? URL,
                  url.scheme == Self.deepLinkScheme,
                  // A host we do not serve: navigating anywhere would be guessing.
                  let page = url.host.flatMap({ Self.deepLinkPages[$0] }),
                  let serverUrl = ServerUrlStore.read(), !serverUrl.isEmpty
            else { return }

            // The query is carried across verbatim — the code, or the error the
            // provider reported. Building the target here keeps the WebView
            // from ever seeing the custom-scheme URL itself.
            let query = URLComponents(url: url, resolvingAgainstBaseURL: false)?.query
            let suffix = query.map { "?\($0)" } ?? ""
            guard let target = URL(string: serverUrl + page + suffix) else { return }
            self?.webView?.load(URLRequest(url: target))
        }
    }

    /// Register the shell's own plugin.
    ///
    /// iOS discovers plugins from `packageClassList` in the bundled Capacitor
    /// config, which only ever lists installed npm packages. A plugin that lives
    /// in the app target has to say so here — this hook exists for exactly that.
    override func capacitorDidLoad() {
        bridge?.registerPluginInstance(LiaShellPlugin())
        observeDeepLinks()
    }
}
