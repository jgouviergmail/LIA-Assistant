import Capacitor
import UIKit
import WebKit

/// The shell's entry point: which server to show, and its own plugin.
class MainViewController: CAPBridgeViewController {

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

    /// Register the shell's own plugin.
    ///
    /// iOS discovers plugins from `packageClassList` in the bundled Capacitor
    /// config, which only ever lists installed npm packages. A plugin that lives
    /// in the app target has to say so here — this hook exists for exactly that.
    override func capacitorDidLoad() {
        bridge?.registerPluginInstance(ServerUrlPlugin())
    }
}
