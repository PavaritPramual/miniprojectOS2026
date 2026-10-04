// Browser integration against intercepted HTTP fixtures, NOT the real scanner.
const { chromium } = require("playwright");
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
(async () => {
  const browser = await chromium.launch({ headless: true });
  const page = await browser.newPage({
    viewport: { width: 1400, height: 950 },
  });
  const base = process.env.CORESPACE_URL || "http://127.0.0.1:8080";
  const results = [],
    requests = [],
    errors = [];
  let terminal = false,
    scanCount = 0,
    statusFailure = false,
    childFailure = false,
    rejectCancel = true,
    cancelled = false,
    revealFailure = true;
  const entry = (name, kind = "file", relativePath = name) => ({
    name,
    kind,
    relativePath,
    logicalBytes: 1,
    allocatedBytes: 4096,
    partial: false,
    hasChildren: kind === "directory",
  });
  const items = [
    entry("A", "directory"),
    entry("B", "directory"),
    ...Array.from({ length: 58 }, (_, i) =>
      entry(`file-${String(i).padStart(2, "0")}.txt`),
    ),
  ];
  page.on("pageerror", (e) => errors.push(e.message));
  await page.route("**/api/**", async (route) => {
    const req = route.request(),
      url = new URL(req.url());
    const body = req.postDataJSON();
    requests.push({
      path: url.pathname,
      query: url.search,
      method: req.method(),
      body,
    });
    const send = (data, status = 200) =>
      route.fulfill({
        status,
        contentType: "application/json",
        body: JSON.stringify(data),
      });
    if (url.pathname === "/api/drives")
      return send([{ path: "D:\\demo", free_bytes: 4096 }]);
    if (url.pathname === "/api/scans" && req.method() === "POST") {
      scanCount++;
      return send({ id: `http-${scanCount}`, state: "queued" }, 202);
    }
    if (url.pathname.endsWith("/cancel")) {
      if (rejectCancel)
        return send(
          { code: "CANCEL_ERROR", detail: "cancel rejected fixture" },
          500,
        );
      cancelled = true;
      return send({ id: `http-${scanCount}`, state: "cancelling" }, 202);
    }
    if (url.pathname === "/api/reveal")
      return revealFailure
        ? send({ code: "EXPLORER_ERROR", detail: "reveal denied fixture" }, 500)
        : send({ status: "revealed" });
    if (url.pathname.endsWith("/children")) {
      const parent = url.searchParams.get("parent"),
        offset = Number(url.searchParams.get("offset"));
      assert.equal(url.searchParams.get("limit"), "50");
      if (childFailure && parent === "" && offset === 50) {
        childFailure = false;
        return send({ code: "TEMP", detail: "page unavailable fixture" }, 503);
      }
      let all =
        parent === ""
          ? terminal
            ? [...items].reverse()
            : items
          : parent === "A"
            ? [entry("deeper", "directory", "A/deeper")]
            : parent === "A/deeper"
              ? [entry("late.txt", "file", "A/deeper/late.txt")]
              : [entry("B-only.txt", "file", "B/B-only.txt")];
      if (parent === "A/deeper") await new Promise((r) => setTimeout(r, 700));
      const data = all.slice(offset, offset + 50);
      return send({
        scanId: `http-${scanCount}`,
        parent,
        offset,
        limit: 50,
        totalChildren: all.length,
        hasMore: offset + data.length < all.length,
        partial: !terminal,
        items: data,
      });
    }
    if (statusFailure)
      return send({ code: "TEMP", detail: "status unavailable fixture" }, 503);
    return send({
      id: `http-${scanCount}`,
      rootPath: "D:\\demo",
      state: cancelled ? "cancelled" : terminal ? "completed" : "running",
      fileCount: 58,
      directoryCount: 4,
      elapsedSeconds: 2,
      errorCount: 0,
      skippedCount: 0,
      partial: cancelled,
    });
  });
  async function check(name, fn) {
    await fn();
    results.push({ name, result: "PASS" });
    console.log("PASS", name);
  }
  try {
    await page.goto(base + "/");
    await page.getByRole("button", { name: "Scan", exact: true }).click();
    await page.locator(".status h2").filter({ hasText: "กำลังสแกน" }).waitFor();
    await check(
      "POST path, async status and bounded children requests",
      async () => {
        assert.deepEqual(requests.find((x) => x.path === "/api/scans").body, {
          path: "D:\\demo",
        });
        assert.equal(await page.locator("tbody tr").count(), 50);
        assert.ok(
          requests.some(
            (x) => /children/.test(x.path) && x.query.includes("offset=0"),
          ),
        );
      },
    );
    await check(
      "Failed next page preserves existing rows; retry loads once",
      async () => {
        childFailure = true;
        await page
          .getByRole("button", { name: "แสดงเพิ่มเติม 50 รายการ", exact: true })
          .click();
        await page
          .getByRole("alert")
          .filter({ hasText: "page unavailable" })
          .waitFor();
        assert.equal(await page.locator("tbody tr").count(), 50);
        await page.getByRole("button", { name: "ลองโหลดรายการใหม่" }).click();
        await page.waitForFunction(
          () => document.querySelectorAll("tbody tr").length === 60,
        );
      },
    );
    await check("Slow response for A does not replace selected B", async () => {
      await page.locator(".tree-name").filter({ hasText: /^▱ A$/ }).click();
      await page
        .locator("tbody .folder-link")
        .filter({ hasText: "deeper" })
        .click();
      await page.locator(".tree-name").filter({ hasText: /^▱ B$/ }).click();
      await page.getByText("· B-only.txt", { exact: true }).waitFor();
      await page.waitForTimeout(900);
      assert.match(await page.locator("tbody").innerText(), /B-only/);
      assert.doesNotMatch(await page.locator("tbody").innerText(), /late.txt/);
    });
    await check("Status error retains UI; retry recovers", async () => {
      statusFailure = true;
      await page
        .getByRole("alert")
        .filter({ hasText: "status unavailable" })
        .waitFor();
      assert.match(await page.locator("tbody").innerText(), /B-only/);
      statusFailure = false;
      await page.getByRole("button", { name: "ลองอ่านสถานะใหม่" }).click();
      await page.waitForFunction(
        () => !document.querySelector(".message.error"),
      );
    });
    await check("Cancel HTTP error remains visible", async () => {
      await page.getByRole("button", { name: "Cancel", exact: true }).click();
      await page
        .getByRole("alert")
        .filter({ hasText: "cancel rejected fixture" })
        .waitFor();
    });
    await check("Terminal reordering resets previous pagination", async () => {
      await page.locator(".breadcrumbs button").first().click();
      terminal = true;
      await page
        .locator(".status h2")
        .filter({ hasText: "เสร็จแล้ว" })
        .waitFor();
      await page.waitForFunction(
        () => document.querySelectorAll("tbody tr").length === 50,
      );
      assert.match(
        await page.locator("tbody tr").first().innerText(),
        /file-57/,
      );
      await page
        .getByRole("button", { name: "แสดงเพิ่มเติม 50 รายการ", exact: true })
        .click();
      await page.waitForFunction(
        () => document.querySelectorAll("tbody tr").length === 60,
      );
      assert.equal(
        new Set(await page.locator("tbody td:first-child").allTextContents())
          .size,
        60,
      );
    });
    await check(
      "Reveal sends scanId + relativePath and honors HTTP error",
      async () => {
        await page
          .getByRole("button", { name: "Reveal file-57.txt", exact: true })
          .click();
        await page
          .getByRole("alert")
          .filter({ hasText: "reveal denied fixture" })
          .waitFor();
        assert.deepEqual(
          requests.filter((x) => x.path === "/api/reveal").at(-1).body,
          { scanId: "http-1", relativePath: "file-57.txt" },
        );
        revealFailure = false;
        await page
          .getByRole("button", { name: "Reveal file-57.txt", exact: true })
          .click();
        await page
          .getByRole("status")
          .filter({ hasText: "เซิร์ฟเวอร์ยืนยัน" })
          .waitFor();
      },
    );
    await check(
      "Next job does not keep old folder rows; successful cancellation",
      async () => {
        terminal = false;
        rejectCancel = false;
        await page.getByRole("button", { name: "Scan", exact: true }).click();
        await page
          .locator(".status .mono")
          .filter({ hasText: "http-2" })
          .waitFor();
        await page
          .locator(".status h2")
          .filter({ hasText: "กำลังสแกน" })
          .waitFor();
        assert.match(await page.locator("tbody tr").first().innerText(), /A/);
        await page.getByRole("button", { name: "Cancel", exact: true }).click();
        await page
          .locator(".status h2")
          .filter({ hasText: "ยกเลิกแล้ว" })
          .waitFor();
      },
    );
    assert.deepEqual(errors, []);
  } catch (e) {
    results.push({ name: "Run stopped", result: "FAIL", detail: e.stack });
    console.error(e);
    process.exitCode = 1;
  } finally {
    fs.writeFileSync(
      path.resolve(__dirname, "../docs/ui-evidence/http-results.json"),
      JSON.stringify(
        {
          scope: "Intercepted HTTP fixtures; NOT real C/WSL integration",
          results,
          errors,
          requests,
        },
        null,
        2,
      ),
    );
    await browser.close();
  }
})();
