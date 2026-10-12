/* Rendering boundaries through real HTTP/SQLite with generated records, not real C. */
const {chromium}=require('playwright');const {spawn}=require('node:child_process');const {createInterface}=require('node:readline');const {once}=require('node:events');const assert=require('node:assert/strict');const fs=require('node:fs');const path=require('node:path');
(async()=>{
  const server=spawn(process.env.PYTHON||'python3',[path.join(__dirname,'ui-review-server.py')],{stdio:['pipe','pipe','pipe']});let diagnostics='';server.stderr.on('data',c=>diagnostics+=c);const lines=createInterface({input:server.stdout});
  const ready=await Promise.race([once(lines,'line').then(([l])=>JSON.parse(l)),once(server,'exit').then(()=>{throw Error(diagnostics);})]);
  const browser=await chromium.launch({channel:process.env.CORESPACE_BROWSER_CHANNEL||'chrome',headless:true});const page=await browser.newPage({viewport:{width:1500,height:1000}});const checks=[],errors=[];page.on('pageerror',e=>errors.push(e.message));
  const check=async(name,fn)=>{await fn();checks.push({name,result:'PASS'});console.log('PASS',name);};
  const open=async id=>{await page.getByPlaceholder('scan-…').fill(id);await page.getByRole('button',{name:'เปิดผลด้วยรหัส',exact:true}).click();await page.waitForFunction(()=>{const b=[...document.querySelectorAll('button')].find(x=>x.textContent.trim()==='Scan');return b&&!b.disabled;});};
  try{
    await page.goto(ready.url);await page.locator('.saved summary').click();await open('city-large');
    const city=page.locator('.file-city');
    await check('400 loaded files keep 250 individual buildings and one aggregate',async()=>{
      while(await city.getByRole('button',{name:'โหลดเมืองเพิ่มเติม 50 รายการ',exact:true}).count()){await city.getByRole('button',{name:'โหลดเมืองเพิ่มเติม 50 รายการ',exact:true}).click();await page.waitForFunction(()=>!document.querySelector('.table-tools button').disabled);}
      assert.equal(await page.locator('tbody tr[data-path]').count(),400);assert.equal(await city.locator('.city-building').count(),251);
    });
    await check('Aggregate has a true byte total and show-table works for root',async()=>{
      await city.getByRole('button',{name:'เลือก รายการรวม 150 รายการ',exact:true}).focus();await page.keyboard.press('Enter');assert.match(await city.locator('.city-details').innerText(),/รายการรวม 150 รายการ/);await city.getByRole('button',{name:'ดูในตาราง',exact:true}).click();assert.ok(await page.locator('.table-scroll').isVisible());
    });
    await check('Search finds an actual loaded file beyond the drawing limit',async()=>{
      await city.getByLabel('หาชื่อในเมือง').fill('large-000.bin');assert.match(await city.locator('.city-results').innerText(),/พบ 1 รายการ/);await city.locator('.city-results button').click();assert.match(await city.locator('.city-details').innerText(),/large-000.bin.*1 KiB/s);await city.getByRole('button',{name:'ดูในตาราง',exact:true}).click();assert.equal(await page.locator('.inspected-row').getAttribute('data-path'),'large-000.bin');
    });
    await check('Unknown allocation stays selectable and logical size can still be mapped',async()=>{
      await open('bars-unknown');await city.locator('.city-unplaced summary').click();await city.getByRole('button',{name:'unknown.bin · ไม่ทราบ',exact:true}).click();assert.match(await city.locator('.city-details').innerText(),/บนดิสก์ ไม่ทราบ/);assert.equal(await city.locator('.city-building').count(),0);await city.getByLabel('ขนาดที่ใช้สร้างเมือง',{exact:true}).selectOption('logicalBytes');assert.equal(await city.locator('.city-building').count(),1);assert.match(await city.locator('.city-status').innerText(),/ข้อมูลบางส่วน/);
    });assert.deepEqual(errors,[]);
  }catch(error){checks.push({name:'Run stopped',result:'FAIL',detail:error.stack});console.error(error);process.exitCode=1;}
  finally{const out=path.resolve('output/playwright/file-city-fixture');fs.mkdirSync(out,{recursive:true});fs.writeFileSync(path.join(out,'results.json'),JSON.stringify({scope:'Real HTTP/SQLite with generated records; not C/Windows size evidence',checks,errors},null,2));await browser.close();const exited=once(server,'exit');server.stdin.end();await exited;}
})().catch(e=>{console.error(e);process.exit(1);});
