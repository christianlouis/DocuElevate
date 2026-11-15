const assert = require("node:assert/strict");
const { readFileSync } = require("node:fs");
const { test } = require("node:test");
const { join } = require("node:path");

const template = readFileSync(join(__dirname, "..", "frontend", "templates", "file_detail.html"), "utf8");
const start = template.indexOf("const errorContainer = document.createElement('div');");
const endMarker = "loadingElement.replaceChildren(errorContainer);";
const end = template.indexOf(endMarker, start);
assert.ok(start >= 0 && end >= 0, "text-error rendering block must remain present");
const renderError = template.slice(start, end + endMarker.length);

function makeElement() {
  const element = {
    children: [],
    style: {},
    append(...children) {
      this.children.push(...children);
    },
    replaceChildren(...children) {
      this.children = children;
    },
  };
  Object.defineProperty(element, "innerHTML", {
    get() {
      return "";
    },
    set() {
      throw new Error("unsafe innerHTML assignment");
    },
  });
  return element;
}

test("PDF text errors stay literal DOM text", () => {
  const loading = makeElement();
  const elements = { "original-text-loading": loading };
  const document = {
    createElement: makeElement,
    getElementById(id) {
      return elements[id] ?? (elements[id] = makeElement());
    },
  };
  const error = { message: '<img src=x onerror="globalThis.pwned=1">' };

  new Function("document", "loadingId", "error", renderError)(document, "original-text-loading", error);

  const [container] = loading.children;
  assert.equal(container.children[1].textContent, "Failed to extract text from PDF");
  assert.equal(container.children[2].textContent, error.message);
  assert.equal(container.children[2].children.length, 0);
  assert.equal(globalThis.pwned, undefined);
});
