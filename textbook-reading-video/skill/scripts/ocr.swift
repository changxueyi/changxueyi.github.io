import Foundation
import Vision
import AppKit

// usage: ocr [--chars] img1 img2 ...
var args = Array(CommandLine.arguments.dropFirst())
var wantChars = false
if args.first == "--chars" { wantChars = true; args.removeFirst() }
for path in args {
  guard let img = NSImage(contentsOfFile: path),
        let cg = img.cgImage(forProposedRect: nil, context: nil, hints: nil) else {
    print("{\"file\":\"\(path)\",\"error\":\"load\"}"); continue
  }
  let req = VNRecognizeTextRequest()
  req.recognitionLevel = .accurate
  req.recognitionLanguages = ["zh-Hans", "en-US"]
  req.usesLanguageCorrection = true
  let handler = VNImageRequestHandler(cgImage: cg, options: [:])
  do { try handler.perform([req]) } catch { print("{\"file\":\"\(path)\",\"error\":\"perform\"}"); continue }
  var out: [[String: Any]] = []
  for obs in req.results ?? [] {
    guard let cand = obs.topCandidates(1).first else { continue }
    let b = obs.boundingBox
    var item: [String: Any] = ["t": cand.string, "x": b.origin.x, "y": b.origin.y, "w": b.size.width, "h": b.size.height, "c": cand.confidence]
    if wantChars {
      var chars: [[Double]] = []
      let s = cand.string
      var idx = s.startIndex
      while idx < s.endIndex {
        let next = s.index(after: idx)
        if let bb = try? cand.boundingBox(for: idx..<next) {
          let r = bb.boundingBox
          chars.append([Double(r.origin.x), Double(r.origin.y), Double(r.size.width), Double(r.size.height)])
        } else { chars.append([]) }
        idx = next
      }
      item["chars"] = chars
    }
    out.append(item)
  }
  let data = try! JSONSerialization.data(withJSONObject: ["file": path, "W": cg.width, "H": cg.height, "items": out])
  print(String(data: data, encoding: .utf8)!)
}
