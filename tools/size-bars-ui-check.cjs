// Browser checks through the real Python HTTP/SQLite API with isolated fixture records.
const { chromium } = require("playwright");
const { spawn } = require("node:child_process");
const { createInterface } = require("node:readline");
const { once } = require("node:events");
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
(async () => {
  const server = spawn(process.env.PYTHON || "python3", [path.join(__dirname,"ui-review-server.py")], {stdio:["pipe","pipe","pipe"]});
  const lines = createInterface({input:server.stdout});
  let diagnostics="";server.stderr.on("data",c=>diagnostics+=c);
  const ready = await Promise.race([once(lines,"line").then(([l])=>JSON.parse(l)),once(server,"exit").then(()=>{throw Error(diagnostics);})]);
  let browser;
  try { browser=await chromium.launch({headless:true, ...(process.env.CORESPACE_BROWSER_CHANNEL ? {channel:process.env.CORESPACE_BROWSER_CHANNEL} : {})}); }
  catch (error) { server.stdin.end(); await once(server,"exit"); throw error; }
  const page=await browser.newPage({viewport:{width:1440,height:1100}});
  const errors=[],checks=[];page.on("pageerror",e=>errors.push(e.message));
  const check=async(name,fn)=>{await fn();checks.push({name,result:"PASS"});console.log("PASS",name);};
  const open=async(id)=>{
    await page.getByPlaceholder("scan-…").fill(id);
    await page.getByRole("button",{name:"เปิดผลด้วยรหัส",exact:true}).click();
    await page.locator(".status .mono").filter({hasText:new RegExp(`^${id}$`)}).waitFor();
    if (!id.startsWith("live-")) await page.waitForFunction(()=>![...document.querySelectorAll("button")].find(b=>b.textContent.trim()==="เปิดผลด้วยรหัส")?.disabled);
  };
  const out=path.join(__dirname,"../docs/results");fs.mkdirSync(out,{recursive:true});
  try{
    await page.goto(ready.url);
    await page.locator("details").filter({has:page.getByPlaceholder("scan-…")}).locator("summary").click();
    await check("Top ten uses real HTTP values; chart and original table coexist",async()=>{
      await open("bars");
      assert.equal(await page.locator(".bar-row").count(),10);
      assert.equal(await page.locator("tbody tr").count(),50);
      assert.ok((await page.locator(".bar-row").first().innerText()).includes("80 KiB"));
      assert.ok((await page.locator(".size-chart").innerText()).includes("ผลบางส่วน"));
      assert.equal(await page.locator(".bar-fill").first().evaluate(el=>el.style.width),"100%");
    });
    await check("Loading next page preserves top ten and exposes unknown instead of zero",async()=>{
      await page.getByRole("button",{name:"แสดงเพิ่มเติม 50 รายการ",exact:true}).click();
      await page.waitForFunction(()=>document.querySelectorAll("tbody tr").length===63);
      assert.equal(await page.locator(".bar-row").count(),10);
      assert.ok((await page.locator(".size-chart").innerText()).includes("ไม่ทราบขนาด 1 รายการ"));
      assert.ok((await page.locator(".size-chart").innerText()).includes("จาก 63 รายการที่โหลดแล้ว"));
    });
    await check("Folder bar navigates to the same folder as tree/table",async()=>{
      await page.locator(".size-chart").getByRole("button",{name:"▱ ชื่อ ไทย",exact:true}).click();
      await page.getByRole("heading",{name:"ชื่อ ไทย",exact:true}).waitFor();
      assert.equal(await page.locator(".bar-row").count(),1);
      assert.ok((await page.locator(".bar-row").innerText()).includes("child.txt"));
      assert.ok((await page.locator(".bar-row").innerText()).includes("100%"));
    });
    await check("Mobile viewport has no page-wide overflow and chart remains readable",async()=>{
      await page.setViewportSize({width:390,height:900});
      assert.ok(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth+1));
      await page.locator(".size-chart").screenshot({path:path.join(out,"size-bars-mobile.png")});
      await page.setViewportSize({width:1440,height:1100});
    });
    await check("Running scan shows pending sizes; terminal polling refreshes the chart",async()=>{
      // A running scan intentionally disables the resume button.
      await open("live-complete");
      assert.ok((await page.locator(".size-chart").innerText()).includes("ขณะสแกน"));
      assert.equal(await page.locator(".bar-row").count(),0);
      const finished=once(lines,"line");
      server.stdin.write(JSON.stringify({id:"live-complete",state:"completed"})+"\n");
      await finished;
      await page.locator(".status h2").filter({hasText:"เสร็จแล้ว"}).waitFor();
      await page.waitForFunction(()=>document.querySelectorAll(".bar-row").length===1);
      assert.ok((await page.locator(".bar-row").innerText()).includes("1 MiB"));
      assert.ok(!(await page.locator(".size-chart").innerText()).includes("ขณะสแกน"));
    });
    await check("Empty folder and all-unknown folder have separate messages",async()=>{
      await open("empty");assert.equal(await page.locator(".bar-row").count(),0);
      assert.ok((await page.locator(".size-chart").innerText()).includes("ไม่มีรายการ"));
      await open("bars-unknown");assert.equal(await page.locator(".bar-row").count(),0);
      assert.ok((await page.locator(".size-chart").innerText()).includes("ยังไม่มีรายการที่วัดพื้นที่ได้"));
      assert.ok((await page.locator(".size-chart").innerText()).includes("ไม่แทนด้วย 0 B"));
    });
    await check("Zero-byte file has text and a genuine zero-width bar",async()=>{
      await open("bars");
      await page.getByRole("button",{name:"แสดงเพิ่มเติม 50 รายการ",exact:true}).click();
      // Root's top ten intentionally omit the small zero file; dedicated zero-only fixture below is served via the same store.
      await open("bars-zero");
      assert.ok((await page.locator(".bar-row").innerText()).includes("0 B"));
      assert.equal(await page.locator(".bar-fill").evaluate(el=>el.style.width),"0%");
    });
    await open("bars");
    await page.locator(".size-chart").screenshot({path:path.join(out,"size-bars-http-fixture.png")});
    assert.deepEqual(errors,[]);
  }catch(e){checks.push({name:"Run stopped",result:"FAIL",detail:e.stack});console.error(e);process.exitCode=1;}
  finally{
    fs.writeFileSync(path.join(out,"size-bars-ui-check.json"),JSON.stringify({scope:"Real localhost Python HTTP/SQLite with fixture records; not a new C scan",checks,errors},null,2));
    await browser.close();const exited=once(server,"exit");server.stdin.end();await exited;
  }
})();
