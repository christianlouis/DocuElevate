const { withDangerousMod, withEntitlementsPlist, withInfoPlist, withXcodeProject } = require("@expo/config-plugins");
const fs = require("fs");
const path = require("path");

const EXTENSION = "DocuElevateShareExtension";
const BUNDLE_ID = "org.docuelevate.mobile.share";
const SHARED_GROUP = "$(AppIdentifierPrefix)org.docuelevate.shared";
const DEFAULT_GROUP = "$(AppIdentifierPrefix)$(CFBundleIdentifier)";
const SOURCE_FILES = ["ShareViewController.swift", "DocuElevateShareExtension.entitlements", "DocuElevateShareExtension-Info.plist"];

function keychainGroups(existing = []) {
  return [DEFAULT_GROUP, ...existing.filter((group) => group !== DEFAULT_GROUP && group !== SHARED_GROUP), SHARED_GROUP];
}

function extensionSettings(settings, appleTeamId) {
  Object.assign(settings, {
    APPLICATION_EXTENSION_API_ONLY: "YES",
    CODE_SIGN_ENTITLEMENTS: `${EXTENSION}/DocuElevateShareExtension.entitlements`,
    CURRENT_PROJECT_VERSION: "7",
    INFOPLIST_FILE: `${EXTENSION}/DocuElevateShareExtension-Info.plist`,
    IPHONEOS_DEPLOYMENT_TARGET: "15.0",
    MARKETING_VERSION: "1.0.0",
    PRODUCT_BUNDLE_IDENTIFIER: BUNDLE_ID,
    SKIP_INSTALL: "YES",
    SWIFT_VERSION: "5.0",
    TARGETED_DEVICE_FAMILY: '"1,2"',
  });
  if (appleTeamId) settings.DEVELOPMENT_TEAM = appleTeamId;
}

function targetNamed(project, name) {
  return Object.values(project.pbxNativeTargetSection()).find((target) => target?.name && String(target.name).replace(/[\"]/g, "") === name);
}

function withShareExtension(config) {
  config = withEntitlementsPlist(config, (mod) => {
    mod.modResults["keychain-access-groups"] = keychainGroups(mod.modResults["keychain-access-groups"] || []);
    return mod;
  });
  config = withInfoPlist(config, (mod) => {
    mod.modResults.DocuElevateKeychainAccessGroup = SHARED_GROUP;
    return mod;
  });
  config = withDangerousMod(config, ["ios", async (mod) => {
    const targetRoot = path.join(mod.modRequest.platformProjectRoot, EXTENSION);
    const sourceRoot = path.join(__dirname, "../modules/docuelevate-share/ios");
    fs.mkdirSync(targetRoot, { recursive: true });
    SOURCE_FILES.forEach((file) => fs.copyFileSync(path.join(sourceRoot, file), path.join(targetRoot, file)));
    return mod;
  }]);
  return withXcodeProject(config, (mod) => {
    const project = mod.modResults;
    let target = targetNamed(project, EXTENSION);
    if (!target) {
      target = project.addTarget(EXTENSION, "app_extension", EXTENSION, BUNDLE_ID);
      const group = project.addPbxGroup([], EXTENSION, EXTENSION);
      const mainGroup = project.findPBXGroupKey({ name: "DocuElevate" }) || project.findPBXGroupKey({ name: "" });
      project.addToPbxGroup({ fileRef: group.uuid, basename: EXTENSION }, mainGroup);
      // node-xcode's addTarget does not create a Sources phase for an app
      // extension. Create it before addSourceFile so it cannot fall back to
      // the host app's Sources phase.
      project.addBuildPhase([], "PBXSourcesBuildPhase", "Sources", target.uuid);
      // The group itself is rooted at `DocuElevateShareExtension`; keep the
      // file reference relative to that group so Xcode does not double it.
      project.addSourceFile("ShareViewController.swift", { target: target.uuid }, group.uuid);
    }
    for (const buildConfig of Object.values(project.pbxXCBuildConfigurationSection())) {
      const settings = buildConfig?.buildSettings;
      if (settings && (settings.PRODUCT_BUNDLE_IDENTIFIER === `\"${BUNDLE_ID}\"` || settings.PRODUCT_BUNDLE_IDENTIFIER === BUNDLE_ID)) extensionSettings(settings, config.ios?.appleTeamId);
    }
    return mod;
  });
}

module.exports = withShareExtension;
module.exports.keychainGroups = keychainGroups;
module.exports.extensionSettings = extensionSettings;
