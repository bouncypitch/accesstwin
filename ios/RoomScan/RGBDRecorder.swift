import ARKit
import CoreImage
import SwiftUI

/// Records an RGB-D walkthrough: color JPEGs, LiDAR depth (uint16 millimeters), depth confidence (uint8),
/// and per-frame intrinsics and camera pose, into Documents/<name>/rgbd/. Zips it for AirDrop when stopped.
///
/// Layout: frames.jsonl (one JSON object per frame) plus color/000123.jpg, depth/000123.u16, conf/000123.u8.
@MainActor
final class RGBDRecorder: NSObject, ObservableObject, ARSessionDelegate {
    @Published var recording = false
    @Published var frames = 0
    @Published var tracking = "starting"
    @Published var zip: URL?
    @Published var error: String?

    let session = ARSession()
    private var dir: URL?
    private var meta: FileHandle?
    private var lastTime: TimeInterval = 0
    private var busy = false
    private let interval: TimeInterval = 0.1  // 10 Hz
    private let colorScale: CGFloat = 0.5  // 1920x1440 -> 960x720
    private let queue = DispatchQueue(label: "rgbd.writer")
    private let ciContext = CIContext()

    static var supported: Bool { ARWorldTrackingConfiguration.supportsFrameSemantics(.sceneDepth) }

    override init() {
        super.init()
        session.delegate = self
        session.run(Self.configuration())  // live preview before recording starts
    }

    private static func configuration() -> ARWorldTrackingConfiguration {
        let config = ARWorldTrackingConfiguration()
        config.frameSemantics = [.sceneDepth, .smoothedSceneDepth]
        return config
    }

    func start(name: String) {
        do {
            let base = FileManager.default.urls(for: .documentDirectory, in: .userDomainMask)[0]
            let d = base.appendingPathComponent(name.isEmpty ? "scan" : name).appendingPathComponent("rgbd")
            try? FileManager.default.removeItem(at: d)
            for sub in ["color", "depth", "conf"] {
                try FileManager.default.createDirectory(at: d.appendingPathComponent(sub), withIntermediateDirectories: true)
            }
            FileManager.default.createFile(atPath: d.appendingPathComponent("frames.jsonl").path, contents: nil)
            meta = try FileHandle(forWritingTo: d.appendingPathComponent("frames.jsonl"))
            dir = d
        } catch {
            self.error = error.localizedDescription
            return
        }
        frames = 0
        zip = nil
        error = nil
        // Reset so the walkthrough's world origin is where recording starts.
        session.run(Self.configuration(), options: [.resetTracking, .removeExistingAnchors])
        recording = true
    }

    func stop() {
        recording = false
        session.pause()
        queue.async { [weak self] in
            guard let self else { return }
            Task { @MainActor in self.finish() }
        }
    }

    private func finish() {
        try? meta?.close()
        meta = nil
        guard let dir else { return }
        // NSFileCoordinator's .forUploading option produces a zip of a directory.
        var zipped: URL?
        var coordError: NSError?
        NSFileCoordinator().coordinate(readingItemAt: dir, options: .forUploading, error: &coordError) { tmp in
            let dest = dir.deletingLastPathComponent().appendingPathComponent("rgbd.zip")
            try? FileManager.default.removeItem(at: dest)
            do {
                try FileManager.default.copyItem(at: tmp, to: dest)
                zipped = dest
            } catch {
                self.error = error.localizedDescription
            }
        }
        if let coordError { error = coordError.localizedDescription }
        zip = zipped
    }

    nonisolated func session(_ session: ARSession, didUpdate frame: ARFrame) {
        let time = frame.timestamp
        let trackingText: String
        switch frame.camera.trackingState {
        case .normal: trackingText = "normal"
        case .notAvailable: trackingText = "not available"
        case .limited(let reason): trackingText = "limited (\(reason))"
        }
        guard let depth = frame.smoothedSceneDepth ?? frame.sceneDepth else { return }

        // Copy what we need out of the frame now so ARKit can recycle its buffers.
        let depthData = Self.depthMillimeters(depth.depthMap)
        let confData = depth.confidenceMap.map(Self.bytes)
        let image = CIImage(cvPixelBuffer: frame.capturedImage)
        let res = frame.camera.imageResolution
        let k = frame.camera.intrinsics
        let t = frame.camera.transform
        let dw = CVPixelBufferGetWidth(depth.depthMap), dh = CVPixelBufferGetHeight(depth.depthMap)
        let intrinsics = [k.columns.0.x, k.columns.1.y, k.columns.2.x, k.columns.2.y].map(Double.init)
        let pose = [t.columns.0, t.columns.1, t.columns.2, t.columns.3].flatMap { [$0.x, $0.y, $0.z, $0.w] }.map(Double.init)

        Task { @MainActor in
            self.tracking = trackingText
            guard self.recording, !self.busy, time - self.lastTime >= self.interval, let dir = self.dir else { return }
            self.lastTime = time
            self.busy = true
            let index = self.frames
            let scale = self.colorScale
            let ctx = self.ciContext
            let entry: [String: Any] = [
                "index": index, "timestamp": time, "tracking": trackingText,
                "image_size": [Double(res.width) * Double(scale), Double(res.height) * Double(scale)],
                // fx, fy, cx, cy for the saved (downscaled) color image
                "intrinsics": intrinsics.map { $0 * Double(scale) },
                "depth_size": [dw, dh],
                "camera_to_world": pose,  // column-major 4x4, ARKit camera convention (x right, y up, -z forward)
            ]
            self.queue.async {
                let name = String(format: "%06d", index)
                let scaled = image.transformed(by: CGAffineTransform(scaleX: scale, y: scale))
                if let space = CGColorSpace(name: CGColorSpace.sRGB),
                   let jpg = ctx.jpegRepresentation(of: scaled, colorSpace: space,
                                                    options: [kCGImageDestinationLossyCompressionQuality as CIImageRepresentationOption: 0.85]) {
                    try? jpg.write(to: dir.appendingPathComponent("color/\(name).jpg"))
                }
                try? depthData.write(to: dir.appendingPathComponent("depth/\(name).u16"))
                try? confData?.write(to: dir.appendingPathComponent("conf/\(name).u8"))
                let line = (try? JSONSerialization.data(withJSONObject: entry)) ?? Data()
                Task { @MainActor in
                    self.meta?.write(line + Data([0x0A]))
                    self.frames += 1
                    self.busy = false
                }
            }
        }
    }

    nonisolated private static func depthMillimeters(_ buffer: CVPixelBuffer) -> Data {
        CVPixelBufferLockBaseAddress(buffer, .readOnly)
        defer { CVPixelBufferUnlockBaseAddress(buffer, .readOnly) }
        let w = CVPixelBufferGetWidth(buffer), h = CVPixelBufferGetHeight(buffer)
        let stride = CVPixelBufferGetBytesPerRow(buffer) / MemoryLayout<Float32>.size
        let src = CVPixelBufferGetBaseAddress(buffer)!.assumingMemoryBound(to: Float32.self)
        var out = [UInt16](repeating: 0, count: w * h)
        for y in 0..<h {
            for x in 0..<w {
                let m = src[y * stride + x]
                out[y * w + x] = m.isFinite ? UInt16(max(0, min(65535, m * 1000))) : 0
            }
        }
        return out.withUnsafeBufferPointer { Data(buffer: $0) }
    }

    nonisolated private static func bytes(_ buffer: CVPixelBuffer) -> Data {
        CVPixelBufferLockBaseAddress(buffer, .readOnly)
        defer { CVPixelBufferUnlockBaseAddress(buffer, .readOnly) }
        let w = CVPixelBufferGetWidth(buffer), h = CVPixelBufferGetHeight(buffer)
        let row = CVPixelBufferGetBytesPerRow(buffer)
        let src = CVPixelBufferGetBaseAddress(buffer)!.assumingMemoryBound(to: UInt8.self)
        var out = Data(capacity: w * h)
        for y in 0..<h { out.append(src + y * row, count: w) }
        return out
    }
}

struct ARPreview: UIViewRepresentable {
    let session: ARSession
    func makeUIView(context: Context) -> ARSCNView {
        let v = ARSCNView(frame: .zero)
        v.session = session
        v.automaticallyUpdatesLighting = false
        return v
    }
    func updateUIView(_ uiView: ARSCNView, context: Context) {}
}

struct RecorderView: View {
    @StateObject private var recorder = RGBDRecorder()
    let name: String
    let close: () -> Void

    var body: some View {
        ZStack(alignment: .bottom) {
            ARPreview(session: recorder.session).ignoresSafeArea()
            VStack(spacing: 14) {
                Text(recorder.recording ? "Recording \(recorder.frames) frames" : "\(recorder.frames) frames recorded")
                    .font(.headline)
                Text("Tracking: \(recorder.tracking)").font(.subheadline).foregroundStyle(.secondary)
                if let error = recorder.error { Text(error).foregroundStyle(.red) }
                if recorder.recording {
                    Button("Stop") { recorder.stop() }
                        .font(.title2.bold()).buttonStyle(.borderedProminent).tint(.red)
                } else if let zip = recorder.zip {
                    ShareLink("AirDrop rgbd.zip to Mac", item: zip).font(.title3.bold())
                    Button("Done", action: close)
                } else if recorder.frames == 0 {
                    Text("Walk slowly, about 1 step per second. Keep surfaces 0.5 to 4 m away; LiDAR depth fades beyond ~5 m.")
                        .font(.footnote).multilineTextAlignment(.center)
                    Button("Start recording") { recorder.start(name: name) }
                        .font(.title2.bold()).buttonStyle(.borderedProminent)
                    Button("Cancel", action: close)
                } else {
                    ProgressView("Packaging…")
                }
            }
            .padding(20)
            .frame(maxWidth: .infinity)
            .background(.ultraThinMaterial)
        }
    }
}
