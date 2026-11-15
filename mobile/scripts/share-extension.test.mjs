import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";

const plugin = await import("../plugins/withShareExtension.js");
const { default: withShareExtension, keychainGroups, extensionSettings } = plugin;
const swift = await readFile(new URL("../modules/docuelevate-share/ios/ShareViewController.swift", import.meta.url), "utf8");
const infoPlist = await readFile(new URL("../modules/docuelevate-share/ios/DocuElevateShareExtension-Info.plist", import.meta.url), "utf8");
const pluginSource = await readFile(new URL("../plugins/withShareExtension.js", import.meta.url), "utf8");

test("keychain plugin preserves the app default group before the shared group and is idempotent", () => {
  const once = keychainGroups(["$(AppIdentifierPrefix)org.docuelevate.shared", "com.example.legacy"]);
  const twice = keychainGroups(once);
  assert.deepEqual(twice, once);
  assert.equal(once[0], "$(AppIdentifierPrefix)$(CFBundleIdentifier)");
  assert.equal(once.at(-1), "$(AppIdentifierPrefix)org.docuelevate.shared");
  assert.equal(once.filter((group) => group.includes("shared")).length, 1);
});

test("extension target settings are complete and stable on repeated prebuilds", () => {
  const settings = {};
  extensionSettings(settings, "975U2ZESBM");
  extensionSettings(settings, "975U2ZESBM");
  assert.deepEqual(settings, {
    APPLICATION_EXTENSION_API_ONLY: "YES",
    CODE_SIGN_ENTITLEMENTS: "DocuElevateShareExtension/DocuElevateShareExtension.entitlements",
    CURRENT_PROJECT_VERSION: "7",
    INFOPLIST_FILE: "DocuElevateShareExtension/DocuElevateShareExtension-Info.plist",
    IPHONEOS_DEPLOYMENT_TARGET: "15.0",
    MARKETING_VERSION: "1.0.0",
    PRODUCT_BUNDLE_IDENTIFIER: "org.docuelevate.mobile.share",
    SKIP_INSTALL: "YES",
    SWIFT_VERSION: "5.0",
    TARGETED_DEVICE_FAMILY: '"1,2"',
    DEVELOPMENT_TEAM: "975U2ZESBM",
  });
});

test("extension debug and release settings inherit the configured Apple team", () => {
  const debug = {}, release = {};
  extensionSettings(debug, "975U2ZESBM");
  extensionSettings(release, "975U2ZESBM");
  assert.equal(debug.DEVELOPMENT_TEAM, "975U2ZESBM");
  assert.equal(release.DEVELOPMENT_TEAM, "975U2ZESBM");
  assert.doesNotMatch(pluginSource, /975U2ZESBM/);
});

test("plugin execution applies the Expo Apple team to both generated build configurations", async () => {
  const config = withShareExtension({ ios: { appleTeamId: "975U2ZESBM" }, mods: {} });
  const debug = { buildSettings: { PRODUCT_BUNDLE_IDENTIFIER: "org.docuelevate.mobile.share" } };
  const release = { buildSettings: { PRODUCT_BUNDLE_IDENTIFIER: '"org.docuelevate.mobile.share"' } };
  const project = {
    pbxNativeTargetSection: () => ({ extension: { name: "DocuElevateShareExtension", uuid: "extension" } }),
    pbxXCBuildConfigurationSection: () => ({ debug, release }),
  };
  await config.mods.ios.xcodeproj({ modResults: project, modRequest: { platformProjectRoot: "/tmp" } });
  assert.equal(debug.buildSettings.DEVELOPMENT_TEAM, "975U2ZESBM");
  assert.equal(release.buildSettings.DEVELOPMENT_TEAM, "975U2ZESBM");
});

test("extension Info.plist contains stable bundle identity keys", () => {
  assert.match(infoPlist, /<key>CFBundleName<\/key><string>DocuElevateShareExtension<\/string>/);
  assert.match(infoPlist, /<key>CFBundleExecutable<\/key><string>\$\(EXECUTABLE_NAME\)<\/string>/);
  assert.match(infoPlist, /<key>CFBundleIdentifier<\/key><string>\$\(PRODUCT_BUNDLE_IDENTIFIER\)<\/string>/);
});

test("plugin creates the extension Sources phase before attaching its Swift file", () => {
  const phase = pluginSource.indexOf('addBuildPhase([], "PBXSourcesBuildPhase", "Sources", target.uuid)');
  const source = pluginSource.indexOf('addSourceFile("ShareViewController.swift", { target: target.uuid }, group.uuid)');
  assert.ok(phase >= 0 && source > phase);
  assert.equal((pluginSource.match(/addBuildPhase\(\[\], "PBXSourcesBuildPhase", "Sources", target\.uuid\)/g) || []).length, 1);
  assert.doesNotMatch(pluginSource, /Embed App Extensions/);
});

test("native share contract streams multipart data and accepts only valid queued or duplicate receipts", () => {
  assert.match(swift, /while let chunk = try input\.read\(upToCount: 1024 \* 1024\)/);
  assert.match(swift, /--\\\(boundary\)\\r\\nContent-Disposition: form-data/);
  assert.match(swift, /status == "queued".*json\["task_id"\]/s);
  assert.match(swift, /status == "duplicate" && json\["duplicate_of"\] is \[String: Any\]/);
  assert.match(swift, /httpShouldHandleCookies = false/);
  assert.match(swift, /willPerformHTTPRedirection/);
});

test("native text rendering uses CoreText visible ranges so wrapped long text advances across pages", () => {
  assert.match(swift, /CTFramesetterCreateWithAttributedString/);
  assert.match(swift, /style\.lineBreakMode = \.byWordWrapping/);
  assert.match(swift, /CTFrameGetVisibleStringRange\(frame\)\.length/);
  assert.match(swift, /guard length > 0 else/);
  assert.match(swift, /while location < string\.length/);
  assert.match(swift, /shared-text-\\\(Int\(Date\(\)\.timeIntervalSince1970\)\)-\\\(index \+ 1\)\.pdf/);
});
