// macOS-only encoder for real Chrome viewport frames; no UI is generated here.
import Foundation
import AVFoundation
import ImageIO
import CoreVideo

struct Frame: Decodable { let file: String; let time: Double }
struct Recording: Decodable {
    let width: Int; let height: Int; let duration: Double; let frames: [Frame]
}

func fail(_ message: String) -> Never {
    FileHandle.standardError.write(Data((message + "\n").utf8)); exit(1)
}
let args = CommandLine.arguments
guard args.count == 3 else { fail("Usage: encode_demo frames.json output.mp4") }
let manifest = URL(fileURLWithPath: args[1])
let target = URL(fileURLWithPath: args[2])
guard !FileManager.default.fileExists(atPath: target.path) else { fail("Refusing to overwrite video") }
let recording = try JSONDecoder().decode(Recording.self, from: Data(contentsOf: manifest))
guard !recording.frames.isEmpty else { fail("No browser frames") }
let writer = try AVAssetWriter(outputURL: target, fileType: .mp4)
let input = AVAssetWriterInput(mediaType: .video, outputSettings: [
    AVVideoCodecKey: AVVideoCodecType.h264,
    AVVideoWidthKey: recording.width, AVVideoHeightKey: recording.height,
    AVVideoCompressionPropertiesKey: [AVVideoAverageBitRateKey: 4_000_000,
        AVVideoProfileLevelKey: AVVideoProfileLevelH264HighAutoLevel],
])
input.expectsMediaDataInRealTime = false
let adaptor = AVAssetWriterInputPixelBufferAdaptor(assetWriterInput: input,
    sourcePixelBufferAttributes: [kCVPixelBufferPixelFormatTypeKey as String: kCVPixelFormatType_32ARGB,
        kCVPixelBufferWidthKey as String: recording.width,
        kCVPixelBufferHeightKey as String: recording.height,
        kCVPixelBufferCGImageCompatibilityKey as String: true,
        kCVPixelBufferCGBitmapContextCompatibilityKey as String: true])
writer.add(input)
guard writer.startWriting() else { fail("Encoder could not start") }
writer.startSession(atSourceTime: .zero)
for frame in recording.frames {
    autoreleasepool {
        let url = manifest.deletingLastPathComponent().appendingPathComponent(frame.file)
        guard let source = CGImageSourceCreateWithURL(url as CFURL, nil),
              let image = CGImageSourceCreateImageAtIndex(source, 0, nil),
              let pool = adaptor.pixelBufferPool else { fail("Cannot decode browser frame") }
        var allocated: CVPixelBuffer?
        guard CVPixelBufferPoolCreatePixelBuffer(nil, pool, &allocated) == kCVReturnSuccess,
              let buffer = allocated else { fail("Cannot allocate encoder frame") }
        CVPixelBufferLockBaseAddress(buffer, [])
        guard let context = CGContext(data: CVPixelBufferGetBaseAddress(buffer),
            width: recording.width, height: recording.height, bitsPerComponent: 8,
            bytesPerRow: CVPixelBufferGetBytesPerRow(buffer), space: CGColorSpaceCreateDeviceRGB(),
            bitmapInfo: CGImageAlphaInfo.noneSkipFirst.rawValue) else { fail("Cannot draw browser frame") }
        context.draw(image, in: CGRect(x: 0, y: 0, width: recording.width, height: recording.height))
        CVPixelBufferUnlockBaseAddress(buffer, [])
        while !input.isReadyForMoreMediaData {
            if writer.status == .failed { fail("Encoding failed") }
            Thread.sleep(forTimeInterval: 0.01)
        }
        guard adaptor.append(buffer, withPresentationTime: CMTime(seconds: frame.time, preferredTimescale: 60000))
        else { fail("Cannot append captured frame") }
    }
}
writer.endSession(atSourceTime: CMTime(seconds: recording.duration, preferredTimescale: 60000))
input.markAsFinished()
let completion = DispatchSemaphore(value: 0)
writer.finishWriting { completion.signal() }
completion.wait()
guard writer.status == .completed else { fail("Video did not finalize") }
let result: [String: Any] = ["encoded": true, "captured_frames": recording.frames.count,
    "next_step": "Run inspect_demo to independently decode and validate the MP4"]
print(String(data: try JSONSerialization.data(withJSONObject: result, options: .sortedKeys), encoding: .utf8)!)
