// Run: NODE_PATH=<directory containing playwright> node tools/ui-check.cjs
const { chromium } = require("playwright");
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
(async () => {
  const browser = await chromium.launch({ headless: true });
  const page = await browser.newPage({
    viewport: { width: 1440, height: 1000 },
  });
  const base = process.env.CORESPACE_URL || "http://127.0.0.1:8080";
  const results = [],
    consoleErrors = [],
    external = [];
  const evidence = path.resolve(__dirname, "../docs/ui-evidence");
  fs.mkdirSync(evidence, { recursive: true });
  page.on("pageerror", (error) => consoleErrors.push(error.message));
  await page.route("**/*", (route) => {
    if (new URL(route.request().url()).origin !== new URL(base).origin) {
      external.push(route.request().url());
      return route.abort();
    }
    return route.continue();
  });
  async function check(name, fn) {
    await fn();
    results.push({ name, result: "PASS" });
    console.log("PASS", name);
  }
  const text = async (selector) => page.locator(selector).innerText();
  try {
    await page.goto(base + "/?mock=1");
    await check(
      "Partial status / no console crash / first 50 rows",
      async () => {
        await page
          .locator(".status h2")
          .filter({ hasText: "ผลบางส่วน" })
          .waitFor();
        await page.waitForFunction(
          () => document.querySelectorAll("tbody tr").length === 50,
        );
        assert.match(await text(".table-tools"), /50.*60/s);
        assert.equal(await page.locator('script[src^="http"]').count(), 0);
      },
    );
    await page.screenshot({
      path: path.join(evidence, "01-root.png"),
      fullPage: true,
    });
    await check("Table pagination 50 + 10 without duplicates", async () => {
      await page
        .getByRole("button", { name: "แสดงเพิ่มเติม 50 รายการ", exact: true })
        .click();
      await page.waitForFunction(
        () => document.querySelectorAll("tbody tr").length === 60,
      );
      const names = await page
        .locator("tbody tr td:first-child")
        .allTextContents();
      assert.equal(new Set(names).size, 60);
      assert.equal(
        await page
          .getByRole("button", { name: "แสดงเพิ่มเติม 50 รายการ", exact: true })
          .count(),
        0,
      );
    });
    await check("Unknown / zero / compressed size / skipped link", async () => {
      assert.match(
        await page
          .locator("tr")
          .filter({ hasText: "อ่านไม่ได้.txt" })
          .innerText(),
        /ไม่ทราบ/,
      );
      assert.match(
        await page
          .locator("tr")
          .filter({ hasText: "ศูนย์ ไบต์.txt" })
          .innerText(),
        /0 B/,
      );
      assert.match(
        await page
          .locator("tr")
          .filter({ hasText: "compressed.bin" })
          .innerText(),
        /1 MiB.*4 KiB/s,
      );
      assert.match(
        await page.locator("tr").filter({ hasText: "loop-link" }).innerText(),
        /ไม่เดินต่อ/,
      );
      await page.getByText("ดูเหตุผลที่ข้อมูลไม่ครบ", { exact: true }).click();
      assert.match(await text(".status"), /ACCESS|ไม่มีสิทธิ์/);
    });
    await check("Reveal error and success are visible", async () => {
      await page
        .getByRole("button", { name: "Reveal อ่านไม่ได้.txt", exact: true })
        .click();
      await page
        .getByRole("alert")
        .filter({ hasText: "เปิดตำแหน่งไม่ได้" })
        .waitFor();
      await page
        .getByRole("button", { name: "Reveal compressed.bin", exact: true })
        .click();
      await page
        .getByRole("status")
        .filter({ hasText: "จำลอง Reveal สำเร็จ" })
        .waitFor();
    });
    await check(
      "Tree pagination includes directories after item 50",
      async () => {
        await page
          .getByRole("button", { name: "กาง many-folders", exact: true })
          .click();
        await page
          .locator(".tree-name")
          .filter({ hasText: /^▱ many-folders$/ })
          .click();
        await page.waitForFunction(() =>
          document.querySelector(".table-tools")?.textContent.includes("50"),
        );
        const treeBranch = page
          .locator("li")
          .filter({
            has: page
              .locator(".tree-name")
              .filter({ hasText: /^▱ many-folders$/ }),
          });
        await page
          .getByRole("button", { name: "แสดงเพิ่มเติมใน tree", exact: true })
          .last()
          .click();
        await page
          .locator(".tree-name")
          .filter({ hasText: /^▱ folder-060$/ })
          .waitFor();
        assert.match(await text(".table-tools"), /60.*60/s);
      },
    );
    await check(
      "Depth 8 / collapse / expand / breadcrumb navigation",
      async () => {
        await page
          .getByRole("button", { name: "กาง deep", exact: true })
          .click();
        for (let depth = 2; depth <= 7; depth++)
          await page
            .getByRole("button", { name: `กาง ชั้น ${depth}`, exact: true })
            .click();
        await page
          .locator(".tree-name")
          .filter({ hasText: /^▱ ชั้น 8$/ })
          .click();
        await page.getByText("· ปลายทาง.txt", { exact: true }).waitFor();
        await page.screenshot({
          path: path.join(evidence, "02-depth-eight.png"),
          fullPage: true,
        });
        await page
          .getByRole("button", { name: "พับ deep", exact: true })
          .click();
        assert.equal(
          await page
            .locator(".tree-name")
            .filter({ hasText: /^▱ ชั้น 8$/ })
            .count(),
          0,
        );
        await page
          .getByRole("button", { name: "กาง deep", exact: true })
          .click();
        await page.locator(".breadcrumbs button").first().click();
        await page.waitForFunction(
          () =>
            document.querySelector(".folder-head h2")?.textContent ===
            "D:\\demo",
        );
      },
    );
    await check("Empty directory / Thai names and spaces", async () => {
      await page
        .locator(".tree-name")
        .filter({ hasText: /^▱ empty$/ })
        .click();
      await page
        .getByText("ไม่มีรายการในโฟลเดอร์นี้", { exact: true })
        .waitFor();
      await page
        .locator(".tree-name")
        .filter({ hasText: /^▱ docs$/ })
        .click();
      await page.getByText("· รายงาน 1.txt", { exact: true }).waitFor();
    });
    await check(
      "Cancel keeps partial results and allows next scan",
      async () => {
        await page.getByLabel("สถานการณ์ตัวอย่าง").selectOption("slow");
        await page.getByRole("button", { name: "Scan", exact: true }).click();
        await page
          .locator(".status h2")
          .filter({ hasText: "กำลังสแกน" })
          .waitFor();
        await page.getByRole("button", { name: "Cancel", exact: true }).click();
        await page
          .locator(".status h2")
          .filter({ hasText: "ยกเลิกแล้ว" })
          .waitFor();
        assert.equal(
          await page
            .getByRole("button", { name: "Scan", exact: true })
            .isEnabled(),
          true,
        );
        await page.screenshot({
          path: path.join(evidence, "03-cancelled.png"),
          fullPage: true,
        });
      },
    );
    await check("Failed scan status is shown", async () => {
      await page.getByLabel("สถานการณ์ตัวอย่าง").selectOption("failed");
      await page.getByRole("button", { name: "Scan", exact: true }).click();
      await page.locator(".status h2").filter({ hasText: "ล้มเหลว" }).waitFor();
      assert.match(await text(".status"), /scanner หยุด/);
    });
    await check("Completed scan and saved-result resume", async () => {
      await page.getByLabel("สถานการณ์ตัวอย่าง").selectOption("completed");
      await page.getByRole("button", { name: "Scan", exact: true }).click();
      await page
        .locator(".status h2")
        .filter({ hasText: "เสร็จแล้ว" })
        .waitFor();
      await page.getByText("เปิดผลสแกนที่เตรียมไว้", { exact: true }).click();
      const id = await page.locator(".status .mono").innerText();
      await page.getByLabel("รหัสงานสแกน").fill(id);
      await page
        .getByRole("button", { name: "เปิดผลด้วยรหัส", exact: true })
        .click();
      await page
        .getByRole("status")
        .filter({ hasText: "เปิดผลที่เก็บไว้แล้ว" })
        .waitFor();
      await page
        .getByRole("button", { name: "ล้างประวัติในเบราว์เซอร์" })
        .click();
      await page
        .getByRole("status")
        .filter({ hasText: "ล้างประวัติในเบราว์เซอร์แล้ว" })
        .waitFor();
    });
    await check("Required path / offline assets / mobile layout", async () => {
      await page.getByLabel("ตำแหน่งโฟลเดอร์").fill("");
      await page.getByRole("button", { name: "Scan", exact: true }).click();
      await page.getByRole("alert").filter({ hasText: "กรุณากรอก" }).waitFor();
      assert.deepEqual(external, []);
      await page.setViewportSize({ width: 390, height: 844 });
      await page.screenshot({
        path: path.join(evidence, "04-mobile.png"),
        fullPage: true,
      });
      assert.equal(
        await page.evaluate(
          () => document.documentElement.scrollWidth <= innerWidth,
        ),
        true,
      );
    });
    await check(
      "Real adapter reports missing new backend truthfully",
      async () => {
        await page.goto(base + "/");
        await page.getByLabel("ตำแหน่งโฟลเดอร์").fill("D:\\demo");
        await page.getByRole("button", { name: "Scan", exact: true }).click();
        await page
          .getByRole("alert")
          .filter({ hasText: /Backend ยังไม่มี|HTTP 404/ })
          .waitFor();
      },
    );
    assert.deepEqual(consoleErrors, []);
  } catch (err) {
    results.push({ name: "Run stopped", result: "FAIL", detail: err.stack });
    await page.screenshot({
      path: path.join(evidence, "failure.png"),
      fullPage: true,
    });
    process.exitCode = 1;
    console.error(err);
  } finally {
    fs.writeFileSync(
      path.join(evidence, "results.json"),
      JSON.stringify(
        {
          date: "2026-10-04",
          scope: "Browser UI simulation; not C/WSL/Windows integration",
          results,
          consoleErrors,
          external,
        },
        null,
        2,
      ),
    );
    await browser.close();
  }
})();
