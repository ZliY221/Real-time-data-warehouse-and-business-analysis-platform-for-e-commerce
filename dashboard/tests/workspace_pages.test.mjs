import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";

const html = readFileSync(new URL("../static/index.html", import.meta.url), "utf8");
const styles = readFileSync(new URL("../static/styles.css", import.meta.url), "utf8");
const app = readFileSync(new URL("../static/app.js", import.meta.url), "utf8");

test("dashboard exposes four focused commerce operation pages", () => {
  for (const page of ["overview", "analysis", "products", "trust"]) {
    assert.match(html, new RegExp(`data-commerce-page-link="${page}"`));
    assert.match(html, new RegExp(`data-commerce-page-view="${page}"`));
    assert.match(styles, new RegExp(`data-commerce-page="${page}"`));
  }
  assert.match(app, /function activateCommercePage/);
  assert.match(app, /aria-current/);
});
