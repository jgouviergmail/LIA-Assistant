import Capacitor
import Foundation
import UIKit
import WebKit
import ImageIO
import UniformTypeIdentifiers

/// Only an already-previewed bounded JPEG may reach the system activity sheet.
final class WorldImageShare {
    private let maxBytes = 2 * 1024 * 1024
    private let lifetime: TimeInterval = 15 * 60
    private var busy = false

    func share(_ call: CAPPluginCall, presenter: UIViewController?, page: WKWebView?) {
        DispatchQueue.main.async { [weak self, weak presenter, weak page] in
            guard let self else { call.reject("world_photo_page_closed"); return }
            guard !self.busy else { call.reject("world_photo_busy"); return }
            guard let presenter, let page, let location = page.url, page.window != nil,
                  presenter.viewIfLoaded?.window != nil, presenter.presentedViewController == nil
            else { call.reject("world_photo_presenter_unavailable"); return }
            self.busy = true
            DispatchQueue.global(qos: .userInitiated).async { [weak presenter, weak page] in
                do {
                    let data = try self.validate(call)
                    let file = try self.store(data)
                    DispatchQueue.main.async { [weak presenter, weak page] in
                        guard let presenter, let page, page.url == location, page.window != nil,
                              presenter.viewIfLoaded?.window != nil, presenter.presentedViewController == nil,
                              UIApplication.shared.applicationState == .active
                        else { self.busy = false; self.remove(file); call.reject("world_photo_page_closed"); return }
                        let sheet = UIActivityViewController(activityItems: [file], applicationActivities: nil)
                        if let popover = sheet.popoverPresentationController {
                            popover.sourceView = presenter.view
                            popover.sourceRect = CGRect(x: presenter.view.bounds.midX, y: presenter.view.bounds.midY, width: 1, height: 1)
                            popover.permittedArrowDirections = []
                        }
                        sheet.completionWithItemsHandler = { _, completed, _, error in
                            self.busy = false
                            if error != nil { call.reject("world_photo_share_failed") }
                            else { call.resolve(["status": completed ? "offered" : "cancelled"]) }
                        }
                        presenter.present(sheet, animated: true)
                    }
                } catch {
                    DispatchQueue.main.async { self.busy = false; call.reject("world_photo_share_failed") }
                }
            }
        }
    }
    private func validate(_ call: CAPPluginCall) throws -> Data {
        guard call.getString("mimeType") == "image/jpeg", call.getString("filename") == "lia-world-photo.jpg",
              let encoded = call.getString("base64"), !encoded.isEmpty,
              encoded.utf8.count <= 2796204, encoded.utf8.count % 4 == 0,
              let data = Data(base64Encoded: encoded), data.count >= 12, data.count <= maxBytes,
              data.starts(with: [255, 216, 255]), data.suffix(2).elementsEqual([255, 217])
        else { throw Failure.input }
        let options = [kCGImageSourceShouldCache: false] as CFDictionary
        guard let source = CGImageSourceCreateWithData(data as CFData, options),
              let type = CGImageSourceGetType(source), type as String == UTType.jpeg.identifier,
              let properties = CGImageSourceCopyPropertiesAtIndex(source, 0, options) as? [CFString: Any],
              let width = properties[kCGImagePropertyPixelWidth] as? NSNumber,
              let height = properties[kCGImagePropertyPixelHeight] as? NSNumber,
              (1...1600).contains(width.intValue), (1...1600).contains(height.intValue),
              width.intValue * height.intValue <= 2560000,
              CGImageSourceGetStatus(source) == .statusComplete
        else { throw Failure.input }
        return data
    }
    private func store(_ data: Data) throws -> URL {
        let manager = FileManager.default
        let root = try manager.url(for: .cachesDirectory, in: .userDomainMask, appropriateFor: nil, create: true)
            .appendingPathComponent("world-share", isDirectory: true)
        try manager.createDirectory(at: root, withIntermediateDirectories: true)
        let entries = try manager.contentsOfDirectory(at: root, includingPropertiesForKeys: [.creationDateKey])
        for entry in entries {
            let values = try entry.resourceValues(forKeys: [.creationDateKey])
            if let created = values.creationDate, Date().timeIntervalSince(created) >= lifetime {
                remove(entry.appendingPathComponent("lia-world-photo.jpg"))
            }
        }
        guard try manager.contentsOfDirectory(atPath: root.path).count < 8 else { throw Failure.capacity }
        let directory = root.appendingPathComponent(UUID().uuidString, isDirectory: true)
        try manager.createDirectory(at: directory, withIntermediateDirectories: false)
        let file = directory.appendingPathComponent("lia-world-photo.jpg")
        do { try data.write(to: file, options: .atomic) }
        catch { remove(file); throw error }
        DispatchQueue.global(qos: .utility).asyncAfter(deadline: .now() + lifetime) { self.remove(file) }
        return file
    }
    private func remove(_ file: URL) {
        try? FileManager.default.removeItem(at: file)
        try? FileManager.default.removeItem(at: file.deletingLastPathComponent())
    }
    private enum Failure: Error { case input, capacity }
}
