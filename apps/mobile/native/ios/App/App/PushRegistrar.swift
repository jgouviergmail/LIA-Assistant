import Capacitor
import Foundation
import UIKit
import UserNotifications

/// Getting an iPhone notifiable, when this app cannot be notified by its server.
///
/// One app is published, pointed at whichever LIA server its user runs. On
/// Android that server can notify the device itself, through its own Firebase
/// project. Here it cannot: only the Apple Developer team that owns this bundle
/// identifier may push to it, and a self-hosted deployment is not that team.
///
/// So the device registers with a *wake relay* instead — the deployment that
/// does publish the app — and gets back an opaque handle. The handle is the
/// only thing that then travels: it names no user, carries no content, and
/// permits exactly one action, waking this device with a fixed sentence.
///
/// **The registration call is made from here, natively, and that is not an
/// implementation detail.** The page runs on the user's own server origin, so
/// calling a relay from JavaScript is cross-origin, and a relay serving every
/// self-hosted server cannot enumerate their origins in a CORS policy. The same
/// reasoning already moved the server health probe into the shell.
enum PushRegistrar {

    /// Long enough for a slow network, short enough that a stuck registration
    /// surfaces as "unavailable" rather than a spinner nobody can interrupt.
    private static let apnsTimeout: TimeInterval = 15
    private static let relayTimeout: TimeInterval = 15

    /// What a registration attempt produced.
    struct Outcome {
        let token: String?
        let reason: String?
    }

    /// Ask for permission, register with Apple, and exchange the token for a handle.
    ///
    /// - Parameters:
    ///   - relayUrl: Base URL of the relay this server has chosen to use.
    ///   - language: Language the relay should write its generic wake text in.
    ///   - completion: Receives the handle, or the reason there is none.
    static func register(
        relayUrl: String,
        language: String,
        completion: @escaping (Outcome) -> Void
    ) {
        UNUserNotificationCenter.current().requestAuthorization(
            options: [.alert, .sound, .badge]
        ) { granted, _ in
            guard granted else {
                // A refusal is an answer, not a failure: the page says
                // notifications are off, and the user can change their mind in
                // Settings whenever they like.
                DispatchQueue.main.async { completion(Outcome(token: nil, reason: "permission_denied")) }
                return
            }
            DispatchQueue.main.async {
                ApnsTokenBroker.requestToken(timeout: apnsTimeout) { deviceToken in
                    guard let deviceToken else {
                        completion(Outcome(token: nil, reason: "apns_unavailable"))
                        return
                    }
                    exchange(
                        deviceToken: deviceToken,
                        relayUrl: relayUrl,
                        language: language,
                        completion: completion
                    )
                }
            }
        }
    }

    /// Trade an APNs device token for a relay handle.
    ///
    /// - Parameters:
    ///   - deviceToken: The token Apple issued, hexadecimal.
    ///   - relayUrl: Base URL of the relay.
    ///   - language: Language sealed into the handle.
    ///   - completion: Receives the prefixed handle, or a reason.
    private static func exchange(
        deviceToken: String,
        relayUrl: String,
        language: String,
        completion: @escaping (Outcome) -> Void
    ) {
        guard let url = URL(string: relayUrl.hasSuffix("/") ? String(relayUrl.dropLast()) : relayUrl)?
            .appendingPathComponent("api/v1/push-relay/devices")
        else {
            completion(Outcome(token: nil, reason: "relay_url_invalid"))
            return
        }

        var request = URLRequest(url: url, timeoutInterval: relayTimeout)
        request.httpMethod = "POST"
        request.setValue("application/json", forHTTPHeaderField: "Content-Type")
        request.httpBody = try? JSONSerialization.data(withJSONObject: [
            "device_token": deviceToken,
            // Which of Apple's two gateways minted this token. A debug build
            // registers against the development gateway, and a handle sent to
            // the wrong one is permanently invalid there.
            "sandbox": isDebugBuild,
            "language": language,
        ])

        URLSession.shared.dataTask(with: request) { data, response, _ in
            let status = (response as? HTTPURLResponse)?.statusCode ?? 0
            guard
                status == 201,
                let data,
                let body = try? JSONSerialization.jsonObject(with: data) as? [String: Any],
                let handle = body["handle"] as? String
            else {
                DispatchQueue.main.async { completion(Outcome(token: nil, reason: "relay_unreachable")) }
                return
            }
            // The prefix is the shell's own declaration of route: this server
            // must reach the device through a relay, not through Firebase. It
            // is the shell that KNOWS this, so it is the shell that says it.
            DispatchQueue.main.async { completion(Outcome(token: "relay:" + handle, reason: nil)) }
        }
        .resume()
    }

    /// Whether this build registers against Apple's development gateway.
    private static var isDebugBuild: Bool {
        #if DEBUG
            return true
        #else
            return false
        #endif
    }
}

/// Bridges Apple's delegate callback back to whoever asked for a token.
///
/// `registerForRemoteNotifications()` answers through the application delegate,
/// with no way to correlate a call to its reply. This holds the waiting
/// callbacks and hands them the result. Everything here is touched on the main
/// queue only — UIKit delivers on the main thread, and a lock buys nothing
/// beside the risk of forgetting it once.
enum ApnsTokenBroker {

    private static var waiting: [(String?) -> Void] = []

    /// Register with Apple and call back with the device token, or nil.
    ///
    /// - Parameters:
    ///   - timeout: How long to wait before giving up on Apple answering.
    ///   - completion: Receives the hexadecimal token, or nil.
    static func requestToken(timeout: TimeInterval, completion: @escaping (String?) -> Void) {
        waiting.append(completion)
        UIApplication.shared.registerForRemoteNotifications()

        DispatchQueue.main.asyncAfter(deadline: .now() + timeout) {
            // Silence is a real outcome here: on a device with no APNs
            // connectivity the delegate is simply never called, and a caller
            // left waiting forever is a spinner that never resolves.
            deliver(nil)
        }
    }

    /// Hand a result to every waiting caller, once.
    ///
    /// - Parameter token: The hexadecimal device token, or nil.
    static func deliver(_ token: String?) {
        let callbacks = waiting
        waiting = []
        callbacks.forEach { $0(token) }
    }
}

extension AppDelegate {

    /// Apple issued a device token.
    ///
    /// Capacitor's generated delegate does not forward these callbacks — the
    /// push plugin that used to is not installed here. An extension is enough:
    /// UIKit looks its delegate methods up through the Objective-C runtime, so
    /// implementing one alongside rather than inside `AppDelegate` avoids
    /// shadowing a generated file that would then freeze at whatever Capacitor
    /// shipped the day it was copied.
    public func application(
        _ application: UIApplication,
        didRegisterForRemoteNotificationsWithDeviceToken deviceToken: Data
    ) {
        ApnsTokenBroker.deliver(deviceToken.map { String(format: "%02x", $0) }.joined())
    }

    /// Apple refused to issue one.
    public func application(
        _ application: UIApplication,
        didFailToRegisterForRemoteNotificationsWithError error: Error
    ) {
        ApnsTokenBroker.deliver(nil)
    }
}
