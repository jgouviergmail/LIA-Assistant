import Capacitor
import UIKit
import WebKit

/// The shell's entry point: which server to show, and its own plugin.
class MainViewController: CAPBridgeViewController {

    /// Scheme Info.plist registers for the sign-in return trip.
    private static let deepLinkScheme = "lia"

    /// Web route that spends a handoff code; localisation is the app's own job.
    private static let nativeAuthPath = "/native-auth"

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
                  let serverUrl = ServerUrlStore.read(), !serverUrl.isEmpty
            else { return }

            // The query is carried across verbatim — the code, or the error the
            // provider reported. Building the target here keeps the WebView
            // from ever seeing the custom-scheme URL itself.
            let query = URLComponents(url: url, resolvingAgainstBaseURL: false)?.query
            let suffix = query.map { "?\($0)" } ?? ""
            guard let target = URL(string: serverUrl + Self.nativeAuthPath + suffix) else { return }
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
