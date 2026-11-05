import ExpoModulesCore
import Foundation
import Security

private let service = "org.docuelevate.share-auth"
private func accessGroup() -> String { Bundle.main.object(forInfoDictionaryKey: "DocuElevateKeychainAccessGroup") as? String ?? "org.docuelevate.shared" }

public class DocuElevateAuthModule: Module {
  public func definition() -> ModuleDefinition {
    Name("DocuElevateAuth")
    AsyncFunction("syncCredentials") { (baseURL: String, token: String, ownerID: String) throws in
      guard let url = URL(string: baseURL), let scheme = url.scheme?.lowercased(), ["https", "http"].contains(scheme),
            !token.isEmpty, !ownerID.isEmpty else { throw AuthBridgeError.invalidCredentials }
      let data = try JSONSerialization.data(withJSONObject: ["baseURL": baseURL, "token": token, "ownerID": ownerID])
      try Keychain.write(data, accessGroup: accessGroup())
    }
    AsyncFunction("clearCredentials") { () throws in try Keychain.delete(accessGroup: accessGroup()) }
  }
}

private enum AuthBridgeError: Error { case invalidCredentials }

private enum Keychain {
  static func write(_ data: Data, accessGroup: String) throws {
    let query: [String: Any] = [kSecClass as String: kSecClassGenericPassword, kSecAttrService as String: service, kSecAttrAccount as String: service, kSecAttrAccessGroup as String: accessGroup]
    SecItemDelete(query as CFDictionary)
    var item = query
    item[kSecValueData as String] = data; item[kSecAttrAccessible as String] = kSecAttrAccessibleAfterFirstUnlockThisDeviceOnly
    guard SecItemAdd(item as CFDictionary, nil) == errSecSuccess else { throw AuthBridgeError.invalidCredentials }
  }
  static func delete(accessGroup: String) throws {
    let query: [String: Any] = [kSecClass as String: kSecClassGenericPassword, kSecAttrService as String: service, kSecAttrAccount as String: service, kSecAttrAccessGroup as String: accessGroup]
    let status = SecItemDelete(query as CFDictionary)
    guard status == errSecSuccess || status == errSecItemNotFound else { throw AuthBridgeError.invalidCredentials }
  }
}
