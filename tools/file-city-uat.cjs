/* UAT against the configured Windows Python + real WSL C server, no request mocks. */
const {chromium}=require('playwright');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const path=require('node:path');
const base=process.env.CORESPACE_UAT_URL||'http://127.0.0.1:8080';
const target=process.env.CORESPACE_UAT_PATH;
const cancelTarget=process.env.CORESPACE_UAT_CANCEL_PATH;
const issuesTarget=process.env.CORESPACE_UAT_ISSUES_PATH;
const projectTarget=process.env.CORESPACE_UAT_PROJECT_PATH;
if(!target)throw Error('Set CORESPACE_UAT_PATH to the real 64-file demo fixture with -VariedSizes');
if(!cancelTarget||!issuesTarget)throw Error('Set CORESPACE_UAT_CANCEL_PATH and CORESPACE_UAT_ISSUES_PATH to generated fixtures');
(async()=>{
  const out=path.resolve('output/playwright/file-city-uat');fs.mkdirSync(out,{recursive:true});
  const browser=await chromium.launch({channel:process.env.CORESPACE_BROWSER_CHANNEL||'chrome',headless:true});
  const page=await browser.newPage({viewport:{width:1550,height:1100}});
  const checks=[],errors=[];page.on('pageerror',error=>errors.push(error.message));
  page.on('console',message=>{if(/Unhandled error|TypeError|ReferenceError|Error in render/.test(message.text()))errors.push(message.text());});
  const check=async(name,action)=>{await action();checks.push({name,result:'PASS'});console.log('PASS',name);};
  const city=()=>page.locator('.file-city');
  const ready=()=>page.waitForFunction(()=>{const button=[...document.querySelectorAll('button')].find(x=>x.textContent.trim()==='Scan');return !!button&&!button.disabled;});
  let id;
  try{
    await page.goto(base);
    await check('Scan button runs actual C and returns 64 files / 13 directories',async()=>{
      await page.getByLabel('ตำแหน่งโฟลเดอร์',{exact:true}).fill(target);
      await page.getByRole('button',{name:'Scan',exact:true}).click();
      await page.waitForFunction(()=>document.querySelector('.status h2')?.textContent.includes('เสร็จแล้ว'),null,{timeout:60000});
      await ready();
      id=(await page.locator('.status .mono').innerText()).trim();
      const status=await (await fetch(`${base}/api/scans/${id}`)).json();
      assert.equal(status.source,'wsl');assert.equal(status.isSample,false);assert.equal(status.state,'completed');assert.equal(status.fileCount,64);assert.equal(status.directoryCount,13);
      assert.ok(await city().locator('.city-building').count()>0);assert.equal(await page.locator('tbody tr[data-path]').count(),6);
      await city().screenshot({path:path.join(out,'real-root-city.png')});
    });
    await check('Choose district, show real details and enter folder',async()=>{
      await city().getByRole('button',{name:'เลือกย่าน many',exact:true}).click();
      assert.match(await city().locator('.city-details').innerText(),/many.*1\.79 MiB/s);
      await city().getByRole('button',{name:'เข้าโฟลเดอร์',exact:true}).click();
      await page.waitForFunction(()=>document.querySelector('.folder-head h2')?.textContent==='many');
      assert.equal(await page.locator('tbody tr[data-path]').count(),50);
    });
    await check('Load city next page: 50 + 10 items, no duplicate buildings',async()=>{
      await city().getByRole('button',{name:'โหลดเมืองเพิ่มเติม 50 รายการ',exact:true}).click();
      await page.waitForFunction(()=>document.querySelectorAll('tbody tr[data-path]').length===60);
      assert.equal(await city().locator('.city-building').count(),60);
      await city().screenshot({path:path.join(out,'real-many-city.png')});
    });
    await check('Building selection and show-in-table locate the actual file',async()=>{
      await city().getByRole('button',{name:'เลือก child-060.txt',exact:true}).focus();await page.keyboard.press('Enter');
      assert.match(await city().locator('.city-details').innerText(),/60 KiB/);
      await city().getByRole('button',{name:'ดูในตาราง',exact:true}).click();
      assert.equal(await page.locator('.inspected-row').getAttribute('data-path'),'many/child-060.txt');
    });
    await check('Map / city, rotate, zoom and reset change the view',async()=>{
      await city().getByRole('button',{name:'มุมมองแผนที่',exact:true}).click();assert.equal(await city().locator('.building-left').count(),0);
      const before=await city().locator('.building-roof').first().getAttribute('points');
      await city().getByRole('button',{name:'หมุนเมือง',exact:true}).click();assert.notEqual(await city().locator('.building-roof').first().getAttribute('points'),before);
      await city().getByRole('button',{name:'ขยายเมือง',exact:true}).click();assert.match(await city().locator('.city-toolbar').innerText(),/125%/);
      await city().getByRole('button',{name:'ย่อเมือง',exact:true}).click();assert.match(await city().locator('.city-toolbar').innerText(),/100%/);
      await city().getByRole('button',{name:'คืนมุมมอง',exact:true}).click();
      await city().getByRole('button',{name:'มุมมองเมือง',exact:true}).click();assert.ok(await city().locator('.building-left').count()>0);
    });
    await check('Pointer drag and wheel really pan and zoom the scene',async()=>{
      const svg=city().locator('svg');await svg.scrollIntoViewIfNeeded();const box=await svg.boundingBox();const before=await svg.locator('g').first().getAttribute('transform');
      await page.mouse.move(box.x+15,box.y+15);await page.mouse.down();await page.mouse.move(box.x+70,box.y+45,{steps:4});await page.mouse.up();
      assert.notEqual(await svg.locator('g').first().getAttribute('transform'),before);
      await page.mouse.wheel(0,-150);await page.waitForTimeout(100);assert.match(await city().locator('.city-toolbar').innerText(),/112%/);
      await city().getByRole('button',{name:'คืนมุมมอง',exact:true}).click();
    });
    await check('Name/type filters find files without changing byte sizes',async()=>{
      await city().getByLabel('หาชื่อในเมือง').fill('child-060');
      assert.match(await city().locator('.city-results').innerText(),/พบ 1 รายการ/);
      await city().getByLabel('ประเภทไฟล์ในเมือง',{exact:true}).selectOption('video');assert.match(await city().locator('.city-results').innerText(),/พบ 0 รายการ/);
      await city().getByLabel('ประเภทไฟล์ในเมือง',{exact:true}).selectOption('all');await city().getByLabel('หาชื่อในเมือง').fill('');
    });
    await check('Size selector uses actual logical values and restores allocation view',async()=>{
      await city().getByLabel('ขนาดที่ใช้สร้างเมือง',{exact:true}).selectOption('logicalBytes');assert.match(await city().innerText(),/พื้นที่แปลงเทียบขนาด เนื้อหา/);
      await city().getByLabel('ขนาดที่ใช้สร้างเมือง',{exact:true}).selectOption('allocatedBytes');assert.match(await city().innerText(),/พื้นที่แปลงเทียบขนาด บนดิสก์/);
    });
    await check('Latest-result button opens real stored scan after page reload',async()=>{
      await page.reload();await page.getByLabel('ตำแหน่งโฟลเดอร์',{exact:true}).fill(target);
      await page.getByRole('button',{name:'เปิดผลล่าสุดของตำแหน่งนี้',exact:true}).click();
      await page.waitForFunction(()=>!!document.querySelector('.status .mono'));
      assert.equal((await page.locator('.status .mono').innerText()).trim(),id);
    });
    await check('Saved scan link opens real data and synchronizes the drive selector',async()=>{
      await page.goto(`${base}/?scan=${encodeURIComponent(id)}`);await ready();await page.locator('.status .mono').waitFor();assert.equal((await page.locator('.status .mono').innerText()).trim(),id);assert.equal(await page.locator('.controls select').first().inputValue(),target.slice(0,3));
    });
    await check('Zero-byte item remains selectable and is not assigned disk area',async()=>{
      await city().locator('.city-unplaced summary').click();await city().getByRole('button',{name:'zero.bin · 0 B',exact:true}).click();
      assert.match(await city().locator('.city-details').innerText(),/zero.bin.*0 B/s);
      assert.equal(await city().getByRole('button',{name:'เลือก zero.bin',exact:true}).count(),0);
    });
    await check('Reveal button sends a real successful Windows Explorer command',async()=>{
      const response=page.waitForResponse(r=>r.url().endsWith('/api/reveal')&&r.request().method()==='POST');
      await city().getByRole('button',{name:'เปิดตำแหน่ง',exact:true}).click();const result=await response;assert.equal(result.status(),200);assert.equal((await result.json()).status,'revealed');
      await page.waitForFunction(()=>document.querySelector('.message:not(.error)')?.textContent.includes('Explorer'));
    });
    await check('Real C cancellation stops within 15 seconds and permits next scan',async()=>{
      await page.getByLabel('ตำแหน่งโฟลเดอร์',{exact:true}).fill(cancelTarget);await page.getByRole('button',{name:'Scan',exact:true}).click();
      await page.waitForFunction(()=>![...document.querySelectorAll('button')].find(x=>x.textContent.trim()==='Cancel')?.disabled);
      await page.getByRole('button',{name:'Cancel',exact:true}).click();
      await page.waitForFunction(()=>document.querySelector('.status h2')?.textContent.includes('ยกเลิกแล้ว'),null,{timeout:15000});
      const cancelledId=(await page.locator('.status .mono').innerText()).trim();const status=await(await fetch(`${base}/api/scans/${cancelledId}`)).json();assert.equal(status.state,'cancelled');assert.equal(status.source,'wsl');
      await page.getByLabel('ตำแหน่งโฟลเดอร์',{exact:true}).fill(issuesTarget);await page.getByRole('button',{name:'Scan',exact:true}).click();
      await page.waitForFunction(()=>document.querySelector('.status h2')?.textContent.includes('ผลบางส่วน'),null,{timeout:60000});
    });
    await check('Actual skipped junction reason appears and tree/refresh still work',async()=>{
      await page.locator('.issues summary').click();await page.waitForFunction(()=>document.querySelector('.issues')?.textContent.includes('back-to-root'));
      assert.match(await page.locator('.issues').innerText(),/symlink/);
      assert.match(await page.locator('.issues').innerText(),/ไม่เดินตามลิงก์/);
      await page.getByRole('button',{name:'พับ many',exact:true}).click();await page.getByRole('button',{name:'กาง many',exact:true}).click();
      await page.getByRole('button',{name:'รีเฟรชรายการ',exact:true}).click();await page.waitForFunction(()=>!!document.querySelector('tbody tr[data-path="many"]'));
    });
    await check('Missing saved result reports the actual error',async()=>{
      await page.getByLabel('ตำแหน่งโฟลเดอร์',{exact:true}).fill('Z:\\corespace-uat-missing');await page.getByRole('button',{name:'เปิดผลล่าสุดของตำแหน่งนี้',exact:true}).click();await page.locator('.message.error').waitFor();assert.match(await page.locator('.message.error').innerText(),/ไม่มีผลสแกนจริง/);
    });
    await check('Invalid path gives a real server error, no sample fallback',async()=>{
      await page.getByLabel('ตำแหน่งโฟลเดอร์',{exact:true}).fill('Z:\\corespace-uat-missing');
      await page.getByRole('button',{name:'Scan',exact:true}).click();await page.locator('.message.error').waitFor();
      assert.ok((await page.locator('.message.error').innerText()).length>0);
      assert.equal(await page.locator('.mock-banner').count(),0);
    });
    await check('City and original controls fit mobile width',async()=>{
      await page.setViewportSize({width:390,height:844});assert.ok(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth));
      await city().screenshot({path:path.join(out,'real-city-mobile.png')});
    });
    await check('Saved history can reopen a scan and clear only browser history',async()=>{
      const saved=page.locator('.saved');await saved.locator('summary').click();await saved.locator('ul button').first().click();await ready();
      await saved.getByRole('button',{name:'ล้างประวัติในเบราว์เซอร์',exact:true}).click();assert.equal(await saved.locator('ul button').count(),0);assert.equal((await(await fetch(`${base}/api/scans/${id}`)).json()).state,'completed');
    });
    if(projectTarget)await check('Project documents create a city from everyday files, not demo data',async()=>{
      await page.setViewportSize({width:1550,height:1100});await page.getByLabel('ตำแหน่งโฟลเดอร์',{exact:true}).fill(projectTarget);await page.getByRole('button',{name:'Scan',exact:true}).click();
      await page.waitForFunction(()=>['เสร็จแล้ว','ผลบางส่วน'].some(x=>document.querySelector('.status h2')?.textContent.includes(x)),null,{timeout:60000});
      await ready();
      const actualId=(await page.locator('.status .mono').innerText()).trim();const status=await(await fetch(`${base}/api/scans/${actualId}`)).json();assert.equal(status.source,'wsl');assert.equal(status.isSample,false);assert.ok(status.fileCount>0);
      assert.ok(await city().locator('.city-building').count()>0);await city().screenshot({path:path.join(out,'project-documents-city.png')});fs.writeFileSync(path.join(out,'project-status.json'),JSON.stringify(status,null,2));
    });
    assert.deepEqual(errors,[]);
  }catch(error){checks.push({name:'Run stopped',result:'FAIL',detail:error.stack});console.error(error);await page.screenshot({path:path.join(out,'failure.png'),fullPage:true});process.exitCode=1;}
  finally{fs.writeFileSync(path.join(out,'results.json'),JSON.stringify({source:'Actual Windows Python API and WSL C; no request interception',scanId:id,checks,errors},null,2));await browser.close();}
})().catch(error=>{console.error(error);process.exit(1)});
