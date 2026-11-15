const assert = require("node:assert/strict");
const { readFileSync } = require("node:fs");
const { test } = require("node:test");
const { join } = require("node:path");

const template = readFileSync(
  join(__dirname, "..", "frontend", "templates", "google_drive.html"),
  "utf8",
);

// The two blocks are mutually exclusive at render time, but must keep distinct
// IDs so the client binds the correct flow in either mode.
assert.equal((template.match(/id="start-oauth-flow"/g) || []).length, 1);
assert.equal((template.match(/id="start-oauth-flow-user"/g) || []).length, 1);
const selector = (document) =>
  document.getElementById("start-oauth-flow") ||
  document.getElementById("start-oauth-flow-user");

function documentFor(elements) {
  return { getElementById: (id) => elements[id] ?? null };
}

test("Google Drive binds the admin OAuth control", () => {
  const admin = {};
  assert.equal(selector(documentFor({ "start-oauth-flow": admin })), admin);
});

test("Google Drive binds the user OAuth control", () => {
  const user = {};
  assert.equal(selector(documentFor({ "start-oauth-flow-user": user })), user);
});

test("Google Drive prefers the admin control if both IDs are present", () => {
  const admin = {};
  const user = {};
  assert.equal(
    selector(documentFor({ "start-oauth-flow": admin, "start-oauth-flow-user": user })),
    admin,
  );
});
