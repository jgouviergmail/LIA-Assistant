import Foundation

/// Where this installation's LIA server lives.
///
/// One published app serves every self-hosted instance, so the origin cannot be
/// baked in: the user names it at first launch and it is read back here, before
/// the WebView is built.
enum ServerUrlStore {

    private static let key = "lia.shell.server_url"

    /// Read the configured origin, or `nil` when the shell has never been set up.
    static func read() -> String? {
        UserDefaults.standard.string(forKey: key)
    }

    /// Store an origin, refusing anything that cannot carry a session.
    ///
    /// HTTPS is not a preference here: the session cookie is `Secure`, App
    /// Transport Security refuses cleartext, and a bad origin would fail later —
    /// at sign-in, with nothing on screen to explain why.
    ///
    /// - Parameter url: Candidate origin, as typed.
    /// - Returns: The normalised origin that was stored.
    /// - Throws: ``ServerUrlError/invalid`` when the value is unusable.
    @discardableResult
    static func write(_ url: String?) throws -> String {
        let normalised = try normalise(url)
        UserDefaults.standard.set(normalised, forKey: key)
        return normalised
    }

    /// Reduce a typed value to a bare origin, or refuse it.
    ///
    /// - Parameter url: Candidate origin.
    /// - Returns: Scheme + host (+ port), with no trailing slash.
    /// - Throws: ``ServerUrlError/invalid`` when the value is unusable.
    /// Forget the configured origin, sending the next launch to the setup screen.
    ///
    /// The escape hatch from an address stored wrong on first run: without it,
    /// the shell reaches an unreachable server forever and the only remedy is
    /// reinstalling the app.
    static func clear() {
        UserDefaults.standard.removeObject(forKey: key)
    }

    static func normalise(_ url: String?) throws -> String {
        guard let raw = url?.trimmingCharacters(in: .whitespacesAndNewlines), !raw.isEmpty,
              let parsed = URLComponents(string: raw),
              parsed.scheme?.lowercased() == "https",
              let host = parsed.host, !host.isEmpty
        else {
            throw ServerUrlError.invalid
        }
        if let port = parsed.port {
            return "https://\(host):\(port)"
        }
        return "https://\(host)"
    }
}

/// The single refusal this store can express.
enum ServerUrlError: Error {
    case invalid
}
