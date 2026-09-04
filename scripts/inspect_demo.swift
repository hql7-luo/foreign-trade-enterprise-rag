// Decode every video frame and extract scene checkpoints using native macOS APIs.
import Foundation
import AVFoundation
import ImageIO
import UniformTypeIdentifiers

@main struct InspectDemo {
    static func main() async throws {
        let args = CommandLine.arguments
        guard args.count == 4 else {
            throw NSError(domain: "Usage: inspect_demo video.mp4 workflow.json NEW_OUTPUT_DIR", code: 1)
        }
        let asset = AVURLAsset(url: URL(fileURLWithPath: args[1]))
        let duration = try await asset.load(.duration)
        let tracks = try await asset.loadTracks(withMediaType: .video)
        guard let track = tracks.first else { throw NSError(domain: "No video track", code: 2) }
        let size = try await track.load(.naturalSize)
        let audio = try await asset.loadTracks(withMediaType: .audio)
        let metadata = try await asset.load(.metadata)
        let reader = try AVAssetReader(asset: asset)
        let output = AVAssetReaderTrackOutput(track: track, outputSettings: [
            kCVPixelBufferPixelFormatTypeKey as String: kCVPixelFormatType_32BGRA])
        reader.add(output)
        guard reader.startReading() else { throw NSError(domain: "Video decode failed", code: 3) }
        var decoded = 0
        while autoreleasepool(invoking: { output.copyNextSampleBuffer() != nil }) { decoded += 1 }
        guard reader.status == .completed else { throw NSError(domain: "Incomplete decode", code: 4) }
        let destination = URL(fileURLWithPath: args[3], isDirectory: true)
        guard !FileManager.default.fileExists(atPath: destination.path) else {
            throw NSError(domain: "Refusing to overwrite inspection frames", code: 5)
        }
        try FileManager.default.createDirectory(at: destination, withIntermediateDirectories: true)
        let workflow = try JSONSerialization.jsonObject(with: Data(contentsOf: URL(fileURLWithPath: args[2]))) as! [String: Any]
        let generator = AVAssetImageGenerator(asset: asset)
        generator.appliesPreferredTrackTransform = true
        generator.requestedTimeToleranceBefore = .zero
        generator.requestedTimeToleranceAfter = .zero
        for scene in workflow["scenes"] as! [[String: Any]] {
            let name = scene["name"] as! String
            let time = CMTime(seconds: min(duration.seconds - 0.5, (scene["time"] as! Double) + 1), preferredTimescale: 60000)
            let image = try await generator.image(at: time).image
            let url = destination.appendingPathComponent(name).appendingPathExtension("png")
            let encoded = CGImageDestinationCreateWithURL(url as CFURL, UTType.png.identifier as CFString, 1, nil)!
            CGImageDestinationAddImage(encoded, image, nil)
            guard CGImageDestinationFinalize(encoded) else { throw NSError(domain: "Frame export failed", code: 6) }
        }
        let metrics: [String: Any] = ["duration_seconds": duration.seconds, "width": size.width,
            "height": size.height, "decoded_frames": decoded, "audio_tracks": audio.count,
            "all_frames_decoded": true, "metadata_items": metadata.count]
        print(String(data: try JSONSerialization.data(withJSONObject: metrics, options: .sortedKeys), encoding: .utf8)!)
    }
}
