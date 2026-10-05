// Real Python HTTP + SQLite regression for PR #1. Fixture data, no C/WSL scan.
const { chromium } = require("playwright");
const { spawn } = require("node:child_process");
const { createInterface } = require("node:readline");
const { once } = require("node:events");
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
(async () => {
  const server = spawn(
    process.env.PYTHON || "python3",
    [path.join(__dirname, "ui-review-server.py")],
    { stdio: ["pipe", "pipe", "pipe"] },
  );
  let diagnostics = "";
  server.stderr.on("data", (chunk) => (diagnostics += chunk));
  const lines = createInterface({ input: server.stdout });
  const ready = await Promise.race([
    once(lines, "line").then(([line]) => JSON.parse(line)),
    once(server, "exit").then(() => {
      throw Error(diagnostics);
    }),
  ]);
  const browser = await chromium.launch({ headless: true });
  const page = await browser.newPage({
    viewport: { width: 1440, height: 1000 },
  });
  const errors = [],
    results = [],
    requests = [];
  page.on("pageerror", (e) => errors.push(e.message));
  page.on("request", (r) => {
    if (r.url().includes("/api/scans/")) requests.push(r.url());
  });
  const check = async (name, fn) => {
    await fn();
    results.push({ name, result: "PASS" });
    console.log("PASS", name);
  };
  const open = async (id) => {
    await page.getByPlaceholder("scan-…").fill(id);
    await page
      .getByRole("button", { name: "เปิดผลด้วยรหัส", exact: true })
      .click();
    await page
      .locator(".status .mono")
      .filter({ hasText: new RegExp(`^${id}$`) })
      .waitFor();
    await page
      .getByRole("button", { name: "เปิดผลด้วยรหัส", exact: true })
      .waitFor({ state: "visible" });
    if (!id.startsWith("live-"))
      await page.waitForFunction(
        () =>
          ![...document.querySelectorAll("button")].find(
            (el) => el.textContent.trim() === "เปิดผลด้วยรหัส",
          )?.disabled,
      );
  };
  const finish = async (id, state, error) => {
    const response = once(lines, "line");
    server.stdin.write(JSON.stringify({ id, state, error }) + "\n");
    await response;
  };
  try {
    await page.goto(ready.url);
    // Drive enumeration is host-dependent; opening saved jobs does not require a drive.
    await page
      .locator("details")
      .filter({ has: page.getByPlaceholder("scan-…") })
      .locator("summary")
      .click();
    await check(
      "Real completed root displays 1 MiB and complete metadata",
      async () => {
        await open("root");
        await page.waitForFunction(() =>
          document.querySelector(".metrics")?.innerText.includes("1 MiB"),
        );
        assert.equal(
          await page.locator(".metrics strong").nth(0).innerText(),
          "1 MiB",
        );
        assert.equal(
          await page.locator(".metrics strong").nth(1).innerText(),
          "1 MiB",
        );
        assert.match(
          await page.locator(".metrics").innerText(),
          /ตามข้อมูลที่อ่านได้/,
        );
      },
    );
    await check("Real empty root displays zero, not unknown", async () => {
      await open("empty");
      await page.waitForFunction(
        () => document.querySelector(".metrics strong")?.textContent === "0 B",
      );
      assert.equal(
        await page.locator(".metrics strong").nth(1).innerText(),
        "0 B",
      );
    });
    await check(
      "Issue endpoint: first 50, retry failed next page, then all 60",
      async () => {
        await open("issues");
        await page.locator(".issues summary").click();
        await page.waitForFunction(
          () => document.querySelectorAll(".issues li").length === 50,
        );
        assert.match(
          await page.locator(".issues").innerText(),
          /secret-00.txt.*error \/ ACCESS_DENIED: REVIEW_REASON_00/s,
        );
        assert.match(
          await page.locator(".issues").innerText(),
          /skipped \/ SYMLINK_SKIPPED/,
        );
        await page.route(
          "**/issues?offset=50&limit=50",
          (route) =>
            route.fulfill({
              status: 503,
              contentType: "application/json",
              body: JSON.stringify({ code: "TEMP", detail: "REVIEW_RETRY" }),
            }),
          { times: 1 },
        );
        await page
          .getByRole("button", { name: "แสดงปัญหาเพิ่มเติม 50 รายการ" })
          .click();
        await page
          .locator(".issues [role=alert]")
          .filter({ hasText: "REVIEW_RETRY" })
          .waitFor();
        assert.equal(await page.locator(".issues li").count(), 50);
        await page.getByRole("button", { name: "ลองโหลดปัญหาใหม่" }).click();
        await page.waitForFunction(
          () => document.querySelectorAll(".issues li").length === 60,
        );
        assert.match(
          await page.locator(".issues").innerText(),
          /REVIEW_REASON_59/,
        );
        assert.equal(
          new Set(await page.locator(".issues li").allTextContents()).size,
          60,
        );
      },
    );
    await check(
      "Saved failed status displays error and clears previous issues",
      async () => {
        await open("failed");
        await page
          .locator(".status p.error")
          .filter({ hasText: "REVIEW_FAILED_SAVED" })
          .waitFor();
        await page
          .getByText("ไม่พบรายละเอียดปัญหาที่บันทึกไว้สำหรับงานนี้")
          .waitFor();
        assert.equal(await page.locator(".issues li").count(), 0);
      },
    );
    await check(
      "Polling transition to failed displays status.error",
      async () => {
        await open("live-failed");
        await finish("live-failed", "failed", "REVIEW_FAILED_POLL");
        await page
          .locator(".status p.error")
          .filter({ hasText: "REVIEW_FAILED_POLL" })
          .waitFor();
      },
    );
    await check(
      "Selected nested folder and root totals refresh after completion",
      async () => {
        await open("live-complete");
        await page
          .locator("tbody .folder-link")
          .filter({ hasText: "nested" })
          .click();
        await page.waitForFunction(
          () =>
            document.querySelector(".folder-head h2")?.textContent === "nested",
        );
        assert.match(await page.locator(".metrics").innerText(), /ไม่ทราบ/);
        await finish("live-complete", "completed");
        await page.waitForFunction(
          () =>
            document.querySelector(".metrics strong")?.textContent === "1 MiB",
        );
        assert.equal(
          await page.locator(".folder-head h2").innerText(),
          "nested",
        );
        await page.locator(".breadcrumbs button").first().click();
        assert.equal(
          await page.locator(".metrics strong").first().innerText(),
          "1 MiB",
        );
        assert.match(
          await page.locator(".metrics").innerText(),
          /ตามข้อมูลที่อ่านได้/,
        );
      },
    );
    await check(
      "Late issues response cannot leak into a different scan",
      async () => {
        await open("issues");
        if (!(await page.locator(".issues").evaluate((el) => el.open)))
          await page.locator(".issues summary").click();
        await page.waitForFunction(
          () => document.querySelectorAll(".issues li").length === 50,
        );
        let release;
        const gate = new Promise((resolve) => (release = resolve));
        let arrived;
        const received = new Promise((resolve) => (arrived = resolve));
        await page.route(
          "**/scans/issues/issues?offset=50&limit=50",
          async (route) => {
            const response = await route.fetch();
            arrived();
            await gate;
            await route.fulfill({ response });
          },
          { times: 1 },
        );
        await page
          .getByRole("button", { name: "แสดงปัญหาเพิ่มเติม 50 รายการ" })
          .click();
        await received;
        await open("failed");
        release();
        await page
          .getByText("ไม่พบรายละเอียดปัญหาที่บันทึกไว้สำหรับงานนี้")
          .waitFor();
        await page.waitForTimeout(200);
        assert.equal(await page.locator(".issues li").count(), 0);
      },
    );
    assert.deepEqual(errors, []);
    assert.ok(
      requests
        .filter((url) => url.includes("/issues?"))
        .every((url) => new URL(url).searchParams.get("limit") === "50"),
    );
    await page.screenshot({
      path: path.join(__dirname, "../docs/ui-evidence/review-failed.png"),
      fullPage: true,
    });
  } catch (e) {
    results.push({ name: "Run stopped", result: "FAIL", detail: e.stack });
    console.error(e);
    process.exitCode = 1;
  } finally {
    fs.writeFileSync(
      path.join(__dirname, "../docs/ui-evidence/review-results.json"),
      JSON.stringify(
        {
          scope:
            "Real Python HTTP/SQLite with isolated generated records; no C/WSL/Windows allocation test",
          results,
          errors,
        },
        null,
        2,
      ),
    );
    await browser.close();
    server.stdin.end();
    await once(server, "exit");
  }
})();
