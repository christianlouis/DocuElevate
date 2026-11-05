import CoreText
import Security
import UIKit
import UniformTypeIdentifiers

private let keychainService = "org.docuelevate.share-auth"
private let maxItems = 10
private let maxItemBytes: Int64 = 50 * 1024 * 1024
private let maxTotalBytes: Int64 = 100 * 1024 * 1024
private func keychainGroup() -> String { Bundle.main.object(forInfoDictionaryKey: "DocuElevateKeychainAccessGroup") as? String ?? "org.docuelevate.shared" }
private struct Credential: Decodable, Equatable { let baseURL: String; let token: String; let ownerID: String }
private struct StagedFile { let index: Int; let url: URL; let name: String; let mime: String }
private struct UploadFailure { let file: StagedFile; let message: String }
private struct StageError: Error { let message: String }

final class ShareViewController: UIViewController, URLSessionTaskDelegate {
  private var staged = [StagedFile](), failures = [UploadFailure]()
  private var acceptedCredential: Credential?
  private var session: URLSession?, currentTask: URLSessionUploadTask?, currentBody: URL?
  private var cancelled = false
  private let status = UILabel(), upload = UIButton(type: .system), retry = UIButton(type: .system), cancel = UIButton(type: .system)
  private let spinner = UIActivityIndicatorView(style: .medium)

  override func viewDidLoad() {
    super.viewDidLoad(); view.backgroundColor = .systemBackground
    status.numberOfLines = 0; status.text = "Preparing shared items…"
    upload.setTitle("Upload", for: .normal); retry.setTitle("Retry failed", for: .normal); cancel.setTitle("Cancel", for: .normal)
    upload.addTarget(self, action: #selector(startUpload), for: .touchUpInside)
    retry.addTarget(self, action: #selector(retryFailed), for: .touchUpInside)
    cancel.addTarget(self, action: #selector(cancelShare), for: .touchUpInside)
    upload.isHidden = true; retry.isHidden = true
    let stack = UIStackView(arrangedSubviews: [status, spinner, upload, retry, cancel]); stack.axis = .vertical; stack.spacing = 16; stack.translatesAutoresizingMaskIntoConstraints = false; view.addSubview(stack)
    NSLayoutConstraint.activate([stack.leadingAnchor.constraint(equalTo: view.layoutMarginsGuide.leadingAnchor), stack.trailingAnchor.constraint(equalTo: view.layoutMarginsGuide.trailingAnchor), stack.centerYAnchor.constraint(equalTo: view.centerYAnchor)])
    guard readCredential() != nil else { fail("Sign in to DocuElevate first, then share again."); return }; stageItems()
  }

  @objc private func cancelShare() { cancelled = true; currentTask?.cancel(); session?.invalidateAndCancel(); removeCurrentBody(); cleanup(); extensionContext?.cancelRequest(withError: NSError(domain: "DocuElevate.Share", code: NSUserCancelledError)) }
  @objc private func startUpload() {
    guard let credential = readCredential(), let base = secureURL(credential.baseURL) else { fail("Your signed-in server is unavailable or is not an HTTPS URL."); return }
    guard stagedBytes() <= maxTotalBytes else { fail("Shared files exceed the 100 MB limit."); return }
    acceptedCredential = credential; failures = []; begin(files: staged, credential: credential, base: base)
  }
  @objc private func retryFailed() {
    let files = failures.map(\.file)
    guard let previous = acceptedCredential, let current = readCredential(), previous.baseURL == current.baseURL, previous.ownerID == current.ownerID, let base = secureURL(current.baseURL) else { fail("Your signed-in server or account changed. Reopen sharing from the current session."); return }
    failures = []; begin(files: files, credential: current, base: base)
  }
  private func begin(files: [StagedFile], credential: Credential, base: URL) {
    guard !files.isEmpty else { fail("No supported shared content was found."); return }
    cancelled = false; upload.isHidden = true; retry.isHidden = true; cancel.isHidden = false; spinner.startAnimating(); status.text = "Uploading 0 of \(files.count)…"; uploadNext(files, 0, credential, base)
  }

  private func stageItems() {
    let providers = (extensionContext?.inputItems ?? []).compactMap { $0 as? NSExtensionItem }.flatMap { $0.attachments ?? [] }
    guard !providers.isEmpty else { fail("No supported shared content was found."); return }
    guard providers.count <= maxItems else { fail("Select no more than \(maxItems) items."); return }
    let group = DispatchGroup(); var results = Array<Result<StagedFile, StageError>?>(repeating: nil, count: providers.count)
    for (index, provider) in providers.enumerated() { group.enter(); stage(provider, index) { result in DispatchQueue.main.async { if self.cancelled, case let .success(file) = result { try? FileManager.default.removeItem(at: file.url) } else { results[index] = result }; group.leave() } } }
    group.notify(queue: .main) {
      guard !self.cancelled else { return }
      let finished = results.compactMap { $0 }, errors = finished.compactMap { result -> String? in if case let .failure(error) = result { return error.message }; return nil }
      self.staged = finished.compactMap { try? $0.get() }.sorted { $0.index < $1.index }
      guard errors.isEmpty else { self.cleanup(); self.fail(errors.joined(separator: "\n")); return }
      guard !self.staged.isEmpty else { self.fail("No supported shared content was found."); return }
      guard self.stagedBytes() <= maxTotalBytes else { self.cleanup(); self.fail("Shared files exceed the 100 MB limit."); return }
      self.status.text = self.reviewSummary(); self.upload.isHidden = false
    }
  }
  private func stage(_ provider: NSItemProvider, _ index: Int, _ completion: @escaping (Result<StagedFile, StageError>) -> Void) {
    let fileTypes = [UTType.pdf.identifier, "public.email-message", UTType.fileURL.identifier]
    if let type = fileTypes.first(where: provider.hasItemConformingToTypeIdentifier) {
      if type == UTType.fileURL.identifier {
        provider.loadObject(ofClass: NSURL.self) { object, error in
          let source = (object as? NSURL).map { $0 as URL }
          guard let source, error == nil else { completion(.failure(StageError(message: self.itemError(index, "could not be read")))); return }
          self.stageFile(source, provider.suggestedName, index, completion)
        }
        return
      }
      provider.loadFileRepresentation(forTypeIdentifier: type) { source, error in
        guard let source, error == nil else { completion(.failure(StageError(message: self.itemError(index, "could not be read")))); return }
        if source.pathExtension.lowercased() == "eml" || self.isRawEML(source, provider.suggestedName) { completion(.failure(self.rawEMLGuard(index))); return }
        do { let values = try source.resourceValues(forKeys: [.fileSizeKey, .nameKey]); guard let size = values.fileSize, Int64(size) <= maxItemBytes else { completion(.failure(StageError(message: self.itemError(index, "exceeds the 50 MB limit")))); return }; let name = self.safeName(values.name ?? source.lastPathComponent); let dest = FileManager.default.temporaryDirectory.appendingPathComponent(UUID().uuidString + "-" + name); try FileManager.default.copyItem(at: source, to: dest); completion(.success(StagedFile(index: index, url: dest, name: name, mime: self.mime(source.pathExtension)))) } catch { completion(.failure(StageError(message: self.itemError(index, "could not be staged")))) }
      }; return
    }
    if let type = [UTType.url.identifier, UTType.plainText.identifier].first(where: provider.hasItemConformingToTypeIdentifier) {
      provider.loadItem(forTypeIdentifier: type, options: nil) { item, error in
        guard error == nil else { completion(.failure(StageError(message: self.itemError(index, "could not be read")))); return }
        do { completion(.success(try self.makePDF((item as? URL)?.absoluteString ?? (item as? String) ?? "", index))) } catch { completion(.failure(StageError(message: self.itemError(index, "could not be converted to a document")))) }
      }
      return
    }
    guard provider.hasItemConformingToTypeIdentifier(UTType.data.identifier) else { completion(.failure(StageError(message: itemError(index, "uses an unsupported format")))); return }
    provider.loadFileRepresentation(forTypeIdentifier: UTType.data.identifier) { source, error in
      guard let source, error == nil else { completion(.failure(StageError(message: self.itemError(index, "could not be read")))); return }
      if source.pathExtension.lowercased() == "eml" || self.isRawEML(source, provider.suggestedName) { completion(.failure(self.rawEMLGuard(index))); return }
      do { let values = try source.resourceValues(forKeys: [.fileSizeKey, .nameKey]); guard let size = values.fileSize, Int64(size) <= maxItemBytes else { completion(.failure(StageError(message: self.itemError(index, "exceeds the 50 MB limit")))); return }; let name = self.safeName(values.name ?? source.lastPathComponent); let dest = FileManager.default.temporaryDirectory.appendingPathComponent(UUID().uuidString + "-" + name); try FileManager.default.copyItem(at: source, to: dest); completion(.success(StagedFile(index: index, url: dest, name: name, mime: self.mime(source.pathExtension)))) } catch { completion(.failure(StageError(message: self.itemError(index, "could not be staged")))) }
    }
  }
  private func stageFile(_ source: URL, _ suggestedName: String?, _ index: Int, _ completion: @escaping (Result<StagedFile, StageError>) -> Void) {
    if isRawEML(source, suggestedName) { completion(.failure(rawEMLGuard(index))); return }
    do { let values = try source.resourceValues(forKeys: [.fileSizeKey, .nameKey]); guard let size = values.fileSize, Int64(size) <= maxItemBytes else { completion(.failure(StageError(message: itemError(index, "exceeds the 50 MB limit")))); return }; let name = safeName(values.name ?? source.lastPathComponent); let dest = FileManager.default.temporaryDirectory.appendingPathComponent(UUID().uuidString + "-" + name); try FileManager.default.copyItem(at: source, to: dest); completion(.success(StagedFile(index: index, url: dest, name: name, mime: mime(source.pathExtension)))) } catch { completion(.failure(StageError(message: itemError(index, "could not be staged")))) }
  }
  private func makePDF(_ text: String, _ index: Int) throws -> StagedFile {
    guard !text.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty else { throw CocoaError(.fileWriteInvalidFileName) }
    let url = FileManager.default.temporaryDirectory.appendingPathComponent(UUID().uuidString + "-shared-text.pdf"), page = CGSize(width: 612, height: 792), margin: CGFloat = 40
    let style = NSMutableParagraphStyle(); style.lineBreakMode = .byWordWrapping
    let string = NSAttributedString(string: text, attributes: [.font: UIFont.systemFont(ofSize: 12), .paragraphStyle: style]), framesetter = CTFramesetterCreateWithAttributedString(string)
    var location = 0, couldNotAdvance = false
    try UIGraphicsPDFRenderer(bounds: CGRect(origin: .zero, size: page)).writePDF(to: url) { context in
      while location < string.length {
        context.beginPage(); let cg = context.cgContext; cg.saveGState(); cg.textMatrix = .identity; cg.translateBy(x: margin, y: page.height - margin); cg.scaleBy(x: 1, y: -1); let path = CGMutablePath(); path.addRect(CGRect(x: 0, y: 0, width: page.width - 2 * margin, height: page.height - 2 * margin)); let frame = CTFramesetterCreateFrame(framesetter, CFRange(location: location, length: 0), path, nil); CTFrameDraw(frame, cg); let length = CTFrameGetVisibleStringRange(frame).length; cg.restoreGState()
        guard length > 0 else { couldNotAdvance = true; break }
        location += length
      }
    }
    guard !couldNotAdvance else { try? FileManager.default.removeItem(at: url); throw CocoaError(.fileWriteUnknown) }
    return StagedFile(index: index, url: url, name: "shared-text-\(Int(Date().timeIntervalSince1970))-\(index + 1).pdf", mime: "application/pdf")
  }

  private func uploadNext(_ files: [StagedFile], _ index: Int, _ credential: Credential, _ base: URL) {
    guard !cancelled else { return }; guard index < files.count else { finish(); return }; let file = files[index], boundary = "DocuElevate-\(UUID().uuidString)", body = FileManager.default.temporaryDirectory.appendingPathComponent(UUID().uuidString + ".multipart")
    do { try multipart(file, boundary, body) } catch { failures.append(UploadFailure(file: file, message: itemError(file.index, "could not be prepared for upload"))); uploadNext(files, index + 1, credential, base); return }
    var request = URLRequest(url: base.appendingPathComponent("api/ui-upload")); request.httpMethod = "POST"; request.httpShouldHandleCookies = false; request.setValue("Bearer \(credential.token)", forHTTPHeaderField: "Authorization"); request.setValue("multipart/form-data; boundary=\(boundary)", forHTTPHeaderField: "Content-Type"); currentBody = body
    if session == nil { session = URLSession(configuration: .ephemeral, delegate: self, delegateQueue: nil) }
    currentTask = session?.uploadTask(with: request, fromFile: body) { [weak self] data, response, error in DispatchQueue.main.async { guard let self else { return }; self.removeCurrentBody(); self.currentTask = nil; guard !self.cancelled else { return }; if self.accepted(data, response, error) { self.status.text = "Uploading \(index + 1) of \(files.count)…" } else { self.failures.append(UploadFailure(file: file, message: self.itemError(file.index, self.failureMessage(response, error)))) }; self.uploadNext(files, index + 1, credential, base) } }
    currentTask?.resume()
  }
  private func finish() { spinner.stopAnimating(); if failures.isEmpty { cleanup(); session?.finishTasksAndInvalidate(); status.text = "Uploaded and queued for processing."; extensionContext?.completeRequest(returningItems: nil) } else { status.text = failures.map(\.message).joined(separator: "\n"); retry.isHidden = false; cancel.isHidden = false } }
  private func accepted(_ data: Data?, _ response: URLResponse?, _ error: Error?) -> Bool { guard error == nil, let http = response as? HTTPURLResponse, (200..<300).contains(http.statusCode), let data, let json = try? JSONSerialization.jsonObject(with: data) as? [String: Any], let status = json["status"] as? String else { return false }; if status == "queued" { return !(json["task_id"] as? String ?? "").isEmpty }; return status == "duplicate" && json["duplicate_of"] is [String: Any] }
  private func failureMessage(_ response: URLResponse?, _ error: Error?) -> String { if error != nil { return "could not reach the server" }; if let http = response as? HTTPURLResponse { switch http.statusCode { case 401, 403: return "was not accepted by the server (HTTP \(http.statusCode)). Open the main DocuElevate app, sign in with upload permission, then retry."; case 400, 415, 422: return "was rejected by the server (HTTP \(http.statusCode)). Share a PDF or another supported document, then retry."; default: return "was not accepted by the server (HTTP \(http.statusCode))" } }; return "did not receive a valid server response" }
  private func multipart(_ file: StagedFile, _ boundary: String, _ destination: URL) throws { FileManager.default.createFile(atPath: destination.path, contents: nil); let out = try FileHandle(forWritingTo: destination); defer { try? out.close() }; out.write(Data("--\(boundary)\r\nContent-Disposition: form-data; name=\"file\"; filename=\"\(file.name)\"\r\nContent-Type: \(file.mime)\r\n\r\n".utf8)); let input = try FileHandle(forReadingFrom: file.url); defer { try? input.close() }; while let chunk = try input.read(upToCount: 1024 * 1024), !chunk.isEmpty { out.write(chunk) }; out.write(Data("\r\n--\(boundary)--\r\n".utf8)) }
  func urlSession(_: URLSession, task _: URLSessionTask, willPerformHTTPRedirection _: HTTPURLResponse, newRequest _: URLRequest, completionHandler: @escaping (URLRequest?) -> Void) { completionHandler(nil) }
  private func secureURL(_ value: String) -> URL? { guard let url = URL(string: value), url.scheme?.lowercased() == "https", url.host != nil else { return nil }; return url }
  private func readCredential() -> Credential? { let query: [String: Any] = [kSecClass as String: kSecClassGenericPassword, kSecAttrService as String: keychainService, kSecAttrAccount as String: keychainService, kSecAttrAccessGroup as String: keychainGroup(), kSecReturnData as String: true]; var result: CFTypeRef?; guard SecItemCopyMatching(query as CFDictionary, &result) == errSecSuccess, let data = result as? Data else { return nil }; return try? JSONDecoder().decode(Credential.self, from: data) }
  private func stagedBytes() -> Int64 { staged.reduce(0) { $0 + Int64((try? $1.url.resourceValues(forKeys: [.fileSizeKey]).fileSize) ?? 0) } }
  private func reviewSummary() -> String {
    let visible = staged.prefix(3).map { String($0.name.prefix(64)) }
    let remaining = staged.count - visible.count
    let names = visible.joined(separator: "\n") + (remaining > 0 ? "\n… and \(remaining) more" : "")
    let host = readCredential().flatMap { secureURL($0.baseURL)?.host } ?? "configured server"
    return "Review \(staged.count) item(s):\n\(names)\nServer: \(host)"
  }
  private func cleanup() { Set(staged.map { $0.url.path }).forEach { try? FileManager.default.removeItem(atPath: $0) }; staged = []; failures = [] }
  private func removeCurrentBody() { if let currentBody { try? FileManager.default.removeItem(at: currentBody) }; currentBody = nil }
  private func fail(_ message: String) { status.text = message; spinner.stopAnimating(); upload.isHidden = true; retry.isHidden = true }
  private func itemError(_ index: Int, _ message: String) -> String { "Item \(index + 1) \(message)." }
  private func isRawEML(_ source: URL, _ suggestedName: String?) -> Bool { source.pathExtension.lowercased() == "eml" || suggestedName?.split(separator: ".").last?.lowercased() == "eml" }
  private func rawEMLGuard(_ index: Int) -> StageError { StageError(message: itemError(index, "raw .eml files are not supported; share the mail text or a PDF attachment, or print the mail as PDF, then retry")) }
  private func safeName(_ value: String) -> String { let clean = value.replacingOccurrences(of: "[^A-Za-z0-9._-]", with: "_", options: .regularExpression); return clean.isEmpty ? "shared-document" : String(clean.prefix(120)) }
  private func mime(_ ext: String) -> String { UTType(filenameExtension: ext)?.preferredMIMEType ?? "application/octet-stream" }
}

#if SHARE_EXTENSION_HARNESS
import PDFKit

private final class HarnessURLProtocol: URLProtocol {
  struct Reply { let status: Int; let data: Data; let hold: Bool }
  private static let lock = NSLock()
  private static var replies = [Reply](), recordedRequests = 0, stoppedRequests = 0
  private var stopped = false

  static func configure(_ values: [Reply]) { lock.lock(); replies = values; recordedRequests = 0; stoppedRequests = 0; lock.unlock() }
  static var requestCount: Int { lock.lock(); defer { lock.unlock() }; return recordedRequests }
  static var stopCount: Int { lock.lock(); defer { lock.unlock() }; return stoppedRequests }
  override class func canInit(with request: URLRequest) -> Bool { request.url?.host == "example.invalid" }
  override class func canonicalRequest(for request: URLRequest) -> URLRequest { request }
  override func startLoading() {
    Self.lock.lock(); Self.recordedRequests += 1; let reply = Self.replies.removeFirst(); Self.lock.unlock()
    guard !reply.hold else { return }
    DispatchQueue.global().async { [weak self] in
      guard let self, !self.stopped, let url = self.request.url else { return }
      let response = HTTPURLResponse(url: url, statusCode: reply.status, httpVersion: nil, headerFields: nil)!
      self.client?.urlProtocol(self, didReceive: response, cacheStoragePolicy: .notAllowed)
      self.client?.urlProtocol(self, didLoad: reply.data)
      self.client?.urlProtocolDidFinishLoading(self)
    }
  }
  override func stopLoading() { Self.lock.lock(); stopped = true; Self.stoppedRequests += 1; Self.lock.unlock() }
}

private extension ShareViewController {
  func waitForHarness(_ condition: @escaping () -> Bool, timeout: TimeInterval = 3) -> Bool {
    let deadline = Date().addingTimeInterval(timeout)
    while !condition(), Date() < deadline { RunLoop.current.run(until: Date().addingTimeInterval(0.01)) }
    return condition()
  }
  func harnessSession() -> URLSession {
    let configuration = URLSessionConfiguration.ephemeral
    configuration.protocolClasses = [HarnessURLProtocol.self]
    return URLSession(configuration: configuration, delegate: self, delegateQueue: nil)
  }
  func runHarness() throws {
    let tail = "TAIL-DO-NOT-CLIP"
    let longText = (0..<80).map { "Paragraph \($0): " + String(repeating: "wrapped words ", count: 20) }.joined(separator: "\n\n") + "\n" + String(repeating: "x", count: 192) + "\n" + tail
    let rendered = try makePDF(longText, 0)
    defer { try? FileManager.default.removeItem(at: rendered.url) }
    guard let document = PDFDocument(url: rendered.url), document.pageCount > 1,
          (0..<document.pageCount).compactMap({ document.page(at: $0)?.string }).joined().contains(tail) else { fatalError("PDF pagination lost wrapped content") }

    let input = FileManager.default.temporaryDirectory.appendingPathComponent(UUID().uuidString + ".pdf")
    try Data([0x25, 0x50, 0x44, 0x46]).write(to: input)
    defer { try? FileManager.default.removeItem(at: input) }
    let body = FileManager.default.temporaryDirectory.appendingPathComponent(UUID().uuidString + ".multipart")
    defer { try? FileManager.default.removeItem(at: body) }
    try multipart(StagedFile(index: 0, url: input, name: "sample.pdf", mime: "application/pdf"), "HarnessBoundary", body)
    let multipart = try Data(contentsOf: body)
    guard String(data: multipart, encoding: .utf8)?.contains("--HarnessBoundary\r\nContent-Disposition: form-data; name=\"file\"; filename=\"sample.pdf\"") == true,
          String(data: multipart, encoding: .utf8)?.hasSuffix("\r\n--HarnessBoundary--\r\n") == true else { fatalError("multipart framing is invalid") }

    let queued = try JSONSerialization.data(withJSONObject: ["status": "queued", "task_id": "harness-task"])
    let duplicate = try JSONSerialization.data(withJSONObject: ["status": "duplicate", "duplicate_of": ["id": 1]])
    let missingTask = try JSONSerialization.data(withJSONObject: ["status": "queued"])
    let response = HTTPURLResponse(url: URL(string: "https://example.invalid/api/ui-upload")!, statusCode: 200, httpVersion: nil, headerFields: nil)!
    guard accepted(queued, response, nil), accepted(duplicate, response, nil), !accepted(missingTask, response, nil) else { fatalError("upload receipt validation is invalid") }
    for status in [401, 403] {
      let response = HTTPURLResponse(url: URL(string: "https://example.invalid/api/ui-upload")!, statusCode: status, httpVersion: nil, headerFields: nil)!
      let message = failureMessage(response, nil)
      guard message.contains("Open the main DocuElevate app"), message.contains("upload permission"), message.contains("retry") else { fatalError("HTTP \(status) guidance is not actionable") }
    }
    for status in [400, 415, 422] {
      let response = HTTPURLResponse(url: URL(string: "https://example.invalid/api/ui-upload")!, statusCode: status, httpVersion: nil, headerFields: nil)!
      let message = failureMessage(response, nil)
      guard message.contains("PDF"), message.contains("supported document") else { fatalError("HTTP \(status) rejection guidance is incomplete") }
    }
    let rawEMLMessage = rawEMLGuard(0).message
    guard rawEMLMessage.contains("raw .eml files"), rawEMLMessage.contains("mail text"), rawEMLMessage.contains("PDF attachment"), rawEMLMessage.contains("print the mail as PDF") else { fatalError("raw .eml guidance is incomplete") }
    guard isRawEML(URL(fileURLWithPath: "/tmp/file_URL"), "message.eml"), isRawEML(URL(fileURLWithPath: "/tmp/message.eml"), nil), !isRawEML(URL(fileURLWithPath: "/tmp/file_URL"), "message.pdf") else { fatalError("raw .eml source-name guard is invalid") }
    let emlFixture = FileManager.default.temporaryDirectory.appendingPathComponent(UUID().uuidString + ".eml")
    try Data("From: harness@example.invalid\r\n\r\nMail body".utf8).write(to: emlFixture)
    defer { try? FileManager.default.removeItem(at: emlFixture) }
    guard let emlProvider = NSItemProvider(contentsOf: emlFixture) else { fatalError("could not create EML item provider") }
    var emlResult: Result<StagedFile, StageError>?
    stage(emlProvider, 0) { emlResult = $0 }
    guard waitForHarness({ emlResult != nil }), case let .failure(error) = emlResult!, error.message.contains("raw .eml files") else { fatalError("NSItemProvider EML was not rejected before upload") }
    let genericBytes = Data("generic file bytes".utf8), genericFixture = FileManager.default.temporaryDirectory.appendingPathComponent(UUID().uuidString + ".bin")
    try genericBytes.write(to: genericFixture)
    defer { try? FileManager.default.removeItem(at: genericFixture) }
    guard let genericProvider = NSItemProvider(contentsOf: genericFixture) else { fatalError("could not create generic item provider") }
    var genericResult: Result<StagedFile, StageError>?
    stage(genericProvider, 0) { genericResult = $0 }
    guard waitForHarness({ genericResult != nil }), case let .success(genericFile) = genericResult!, (try? Data(contentsOf: genericFile.url)) == genericBytes else { fatalError("NSItemProvider generic file bytes changed") }
    try? FileManager.default.removeItem(at: genericFile.url)

    let credential = Credential(baseURL: "https://example.invalid", token: "harness-token", ownerID: "harness-owner")
    func stagedFile(_ name: String, _ index: Int) throws -> StagedFile {
      let url = FileManager.default.temporaryDirectory.appendingPathComponent(UUID().uuidString + "-" + name)
      try Data("harness".utf8).write(to: url)
      return StagedFile(index: index, url: url, name: name, mime: "application/pdf")
    }
    let first = try stagedFile("first.pdf", 0), second = try stagedFile("second.pdf", 1)
    let uploadController = ShareViewController()
    defer { uploadController.session?.invalidateAndCancel(); uploadController.cleanup() }
    uploadController.staged = [first, second]
    uploadController.acceptedCredential = credential
    uploadController.session = uploadController.harnessSession()
    HarnessURLProtocol.configure([
      .init(status: 200, data: queued, hold: false),
      .init(status: 503, data: Data(), hold: false),
      .init(status: 200, data: queued, hold: false),
    ])
    uploadController.begin(files: [first, second], credential: credential, base: URL(string: credential.baseURL)!)
    guard waitForHarness({ uploadController.failures.count == 1 && !uploadController.retry.isHidden }),
          uploadController.failures.first?.file.name == "second.pdf", HarnessURLProtocol.requestCount == 2 else { fatalError("partial upload failure was not retained for retry") }

    let beforeNoAuthRetry = HarnessURLProtocol.requestCount
    guard uploadController.readCredential() == nil else { fatalError("harness unexpectedly found a share credential") }
    uploadController.retryFailed()
    guard HarnessURLProtocol.requestCount == beforeNoAuthRetry else { fatalError("retry uploaded without a stored credential") }

    let retryFiles = uploadController.failures.map(\.file)
    guard retryFiles.map(\.name) == ["second.pdf"] else { fatalError("retry selected an already accepted item") }
    uploadController.failures = []
    uploadController.begin(files: retryFiles, credential: credential, base: URL(string: credential.baseURL)!)
    guard waitForHarness({ HarnessURLProtocol.requestCount == 3 && uploadController.failures.isEmpty }),
          HarnessURLProtocol.requestCount == 3 else { fatalError("retry did not send exactly the failed item") }

    let cancellable = try stagedFile("cancel.pdf", 0)
    let cancelController = ShareViewController()
    defer { cancelController.session?.invalidateAndCancel(); cancelController.cleanup() }
    cancelController.staged = [cancellable]
    cancelController.session = cancelController.harnessSession()
    HarnessURLProtocol.configure([.init(status: 200, data: queued, hold: true)])
    cancelController.begin(files: [cancellable], credential: credential, base: URL(string: credential.baseURL)!)
    guard waitForHarness({ HarnessURLProtocol.requestCount == 1 && cancelController.currentBody != nil }) else { fatalError("cancellation upload did not start") }
    cancelController.cancelShare()
    guard cancelController.cancel.isHidden == false, cancelController.currentBody == nil, cancelController.staged.isEmpty,
          !FileManager.default.fileExists(atPath: cancellable.url.path), waitForHarness({ HarnessURLProtocol.stopCount > 0 }) else { fatalError("cancellation did not retain its control or clean up") }
  }
}

@main
private struct ShareExtensionHarness {
  static func main() throws {
    try ShareViewController().runHarness()
    print("share-extension-harness: passed")
  }
}
#endif
