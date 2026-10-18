import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";
import ts from "typescript";

const source = await readFile(new URL("../src/services/mobileAuth.ts", import.meta.url), "utf8");
const transpiled = ts.transpileModule(source, {
  compilerOptions: { module: ts.ModuleKind.ESNext, target: ts.ScriptTarget.ES2022 },
}).outputText;
const helpers = await import(`data:text/javascript,${encodeURIComponent(`${transpiled}\n//# sourceURL=mobileAuth.test-runtime.mjs`)}`);
const { callbackToken, checkMobileSupport } = helpers;

test("missing mobile endpoint produces an unsupported-server error without credentials", async () => {
  let called = false;
  await assert.rejects(checkMobileSupport("https://old.example/", async (url, init) => {
    called = true;
    assert.equal(url, "https://old.example/api/mobile/whoami");
    assert.equal(init.credentials, "omit");
    assert.equal(Object.keys(init.headers).includes("Authorization"), false);
    return new Response(null, { status: 404, headers: { "content-type": "application/json" } });
  }), (error) => error.name === "MobileServerUnsupportedError");
  assert.equal(called, true);
});

test("JSON 401 continues for a supported server", async () => {
  await checkMobileSupport("https://current.example", async () => new Response(JSON.stringify({ detail: "Not authenticated" }), {
    status: 401, headers: { "content-type": "application/json" },
  }));
});

test("200 requires a profile and proxy or server failures are rejected", async () => {
  await checkMobileSupport("https://current.example", async () => new Response(JSON.stringify({ owner_id: "u1" }), {
    status: 200, headers: { "content-type": "application/json" },
  }));
  await assert.rejects(checkMobileSupport("https://proxy.example", async () => new Response("<html>login</html>", {
    status: 200, headers: { "content-type": "text/html" },
  })), (error) => error.name === "MobileServerPreflightError");
  await assert.rejects(checkMobileSupport("https://error.example", async () => new Response("{}", {
    status: 500, headers: { "content-type": "application/json" },
  })), (error) => error.name === "MobileServerPreflightError");
  await assert.rejects(checkMobileSupport("https://offline.example", async () => { throw new Error("offline"); }), (error) => error.name === "MobileServerPreflightError");
});

test("callback token requires the requested target and a token", () => {
  const redirect = "docuelevate://callback";
  assert.equal(callbackToken("docuelevate://callback?token=abc", redirect), "abc");
  assert.throws(() => callbackToken("docuelevate://other?token=abc", redirect), /unexpected callback URL/);
  assert.throws(() => callbackToken("docuelevate://callback", redirect), /without returning a mobile token/);
  assert.throws(() => callbackToken("not a callback URL", redirect), /invalid callback URL/);
});

test("JSON success responses must contain a valid profile", async () => {
  for (const body of ["{}", "not json", '{"owner_id":123}']) {
    await assert.rejects(checkMobileSupport("https://invalid.example", async () => new Response(body, {
      status: 200, headers: { "content-type": "application/json" },
    })), (error) => error.name === "MobileServerPreflightError");
  }
});

test("preflight timeout covers both connection and response-body waits", async () => {
  const waitForAbort = (signal) => new Promise((_resolve, reject) => {
    signal.addEventListener("abort", () => reject(new Error("aborted")), { once: true });
  });
  await assert.rejects(checkMobileSupport("https://slow.example", async (_url, init) => {
    return waitForAbort(init.signal);
  }, 10), (error) => error.name === "MobileServerPreflightError");
  await assert.rejects(checkMobileSupport("https://slow-body.example", async (_url, init) => ({
    status: 200,
    headers: new Headers({ "content-type": "application/json" }),
    json: () => waitForAbort(init.signal),
  }), 10), (error) => error.name === "MobileServerPreflightError");
});
