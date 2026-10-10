import RoomPlan
import SwiftUI

@main
struct RoomScanApp: App {
    var body: some Scene {
        WindowGroup { ContentView() }
    }
}

/// Owns the RoomPlan capture view and receives the processed room when the user taps Done.
@MainActor
final class Scanner: NSObject, ObservableObject, @preconcurrency RoomCaptureViewDelegate {
    @Published var scanning = false
    @Published var room: CapturedRoom?
    @Published var files: [URL] = []
    @Published var error: String?

    let captureView = RoomCaptureView(frame: .zero)

    override init() {
        super.init()
        captureView.delegate = self
    }

    required init?(coder: NSCoder) { nil }
    func encode(with coder: NSCoder) {}

    func start() {
        room = nil
        files = []
        error = nil
        scanning = true
        captureView.captureSession.run(configuration: RoomCaptureSession.Configuration())
    }

    func finish() {
        captureView.captureSession.stop()
    }

    nonisolated func captureView(shouldPresent roomDataForProcessing: CapturedRoomData, error: Error?) -> Bool {
        true
    }

    nonisolated func captureView(didPresent processedResult: CapturedRoom, error: Error?) {
        Task { @MainActor in
            self.room = processedResult
            if let error { self.error = error.localizedDescription }
        }
    }

    /// Writes roomplan.json (every wall, door, window, opening and object with exact size and pose)
    /// and roomplan.usdz into Documents/<name>/, which is visible in the Files app.
    func export(name: String) {
        guard let room else { return }
        do {
            let base = FileManager.default.urls(for: .documentDirectory, in: .userDomainMask)[0]
            let dir = base.appendingPathComponent(name.isEmpty ? "scan" : name)
            try FileManager.default.createDirectory(at: dir, withIntermediateDirectories: true)
            let json = dir.appendingPathComponent("roomplan.json")
            let encoder = JSONEncoder()
            encoder.outputFormatting = [.prettyPrinted, .sortedKeys]
            try encoder.encode(room).write(to: json)
            let usdz = dir.appendingPathComponent("roomplan.usdz")
            try? FileManager.default.removeItem(at: usdz)
            try room.export(to: usdz, exportOptions: .parametric)
            files = [json, usdz]
        } catch {
            self.error = error.localizedDescription
        }
    }
}

struct CaptureView: UIViewRepresentable {
    let scanner: Scanner
    func makeUIView(context: Context) -> RoomCaptureView { scanner.captureView }
    func updateUIView(_ uiView: RoomCaptureView, context: Context) {}
}

struct ContentView: View {
    @StateObject private var scanner = Scanner()
    @State private var name = "venue"
    @State private var recordingRGBD = false

    var body: some View {
        if !RoomCaptureSession.isSupported {
            Text("This iPhone has no LiDAR scanner, so RoomPlan can't run.")
                .padding()
        } else if scanner.scanning && scanner.room == nil {
            ZStack(alignment: .bottom) {
                CaptureView(scanner: scanner).ignoresSafeArea()
                Button("Done") { scanner.finish() }
                    .font(.title2.bold())
                    .padding(.horizontal, 40).padding(.vertical, 14)
                    .background(.white, in: Capsule())
                    .foregroundStyle(.black)
                    .padding(.bottom, 40)
            }
        } else if let room = scanner.room {
            ResultView(room: room, scanner: scanner, name: $name)
        } else {
            VStack(spacing: 24) {
                Text("RoomScan").font(.largeTitle.bold())
                Text("Walk the walls first, then sweep the middle. Keep doors open and lights on. End where you started.")
                    .multilineTextAlignment(.center)
                    .foregroundStyle(.secondary)
                Button("Start scan") { scanner.start() }
                    .font(.title2.bold())
                    .buttonStyle(.borderedProminent)
                if RGBDRecorder.supported {
                    Button("Record RGB-D walkthrough") { recordingRGBD = true }
                        .font(.title3.bold())
                        .buttonStyle(.bordered)
                }
            }
            .padding(32)
            .fullScreenCover(isPresented: $recordingRGBD) {
                RecorderView(name: name) { recordingRGBD = false }
            }
        }
    }
}

struct ResultView: View {
    let room: CapturedRoom
    @ObservedObject var scanner: Scanner
    @Binding var name: String

    var body: some View {
        NavigationStack {
            List {
                Section("Counts") {
                    LabeledContent("Walls", value: "\(room.walls.count)")
                    LabeledContent("Doors", value: "\(room.doors.count)")
                    LabeledContent("Windows", value: "\(room.windows.count)")
                    LabeledContent("Openings", value: "\(room.openings.count)")
                    LabeledContent("Objects", value: "\(room.objects.count)")
                }
                Section("Walls (check against your tape measure)") {
                    ForEach(Array(room.walls.enumerated()), id: \.offset) { i, wall in
                        LabeledContent("Wall \(i + 1)", value: length(wall.dimensions.x))
                    }
                }
                Section("Doors (clear width)") {
                    ForEach(Array(room.doors.enumerated()), id: \.offset) { i, door in
                        LabeledContent("Door \(i + 1)", value: length(door.dimensions.x))
                    }
                }
                Section("Export") {
                    TextField("Scan name", text: $name)
                        .textInputAutocapitalization(.never)
                    Button("Save JSON + USDZ") { scanner.export(name: name) }
                    if !scanner.files.isEmpty {
                        ShareLink("AirDrop to Mac", items: scanner.files)
                    }
                    if let error = scanner.error {
                        Text(error).foregroundStyle(.red)
                    }
                }
                Section {
                    Button("Scan again") { scanner.start() }
                }
            }
            .navigationTitle("Scan result")
        }
    }

    private func length(_ meters: Float) -> String {
        let m = Double(meters)
        let totalInches = m / 0.0254
        let feet = Int(totalInches / 12)
        let inches = totalInches - Double(feet * 12)
        return String(format: "%.2f m  (%d ft %.1f in)", m, feet, inches)
    }
}
