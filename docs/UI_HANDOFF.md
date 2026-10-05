# งานของธีรเมธ — หน้าเว็บและความเข้าใจระบบ

ปรับวันที่ 5 ตุลาคม 2569 บน branch `feature/theeramet-ui`

## สถานะที่ต้องพูดตรงกัน

หน้าเว็บใหม่ใช้สัญญา `docs/CONTRACT.md` และมี simulator สำหรับทดสอบปุ่มบน Linux/Windows ด้วยหน้าจอชุดเดียวกัน โหมด `?mock=1` ไม่อ่านไฟล์จริง ไม่เรียก C ไม่วัด Windows Allocated และไม่ใช่ benchmark

`main.py` ใน checkout มี `/api/scans`, children พร้อม `folder`, และ `/issues` แล้ว หน้าเว็บอ่าน API เหล่านี้โดยตรง ทดสอบการเชื่อม Browser → Python HTTP → SQLite ด้วยฐานข้อมูลชั่วคราวแยกจากผู้ใช้ ส่วน C/WSL, Windows allocation, Explorer และ full-drive ยังต้องยืนยันบนเครื่อง Windows ของทีม

## เริ่มใช้และลองงานของธีรเมธ

1. เปิด Python server ของโปรเจกต์ตามเดิม
2. เปิด `http://localhost:8080/?mock=1` เพื่อทดสอบ UI ด้วยข้อมูลสมมติ ระบบเริ่มงานตัวอย่างให้อัตโนมัติ
3. รอเปลี่ยนจาก running เป็น partial แล้วลองแสดงเพิ่ม 50 → 60, เลือก `many-folders`, กาง `deep` ถึงชั้น 8, เปิด `docs` และ `empty`
4. เลือกสถานการณ์งานนานแล้ว Scan → Cancel; เลือกล้มเหลวเพื่อดู failed; เลือกสำเร็จเพื่อดู completed
5. Reveal ของ `อ่านไม่ได้.txt` จำลอง HTTP error ส่วนไฟล์อื่นจำลองสำเร็จ มีข้อความชัดเจนว่าไม่ได้เปิด Explorer จริง
6. เปิด `/` เพื่อใช้ HTTP API จริง การสแกนจริงต้องเปิด server บน Windows และตั้งตำแหน่ง C ใน WSL ให้พร้อม
7. ปิดอินเทอร์เน็ตได้ แต่ Python localhost ต้องยังทำงานอยู่ ส่วน Vue และ CSS อยู่ในเครื่องทั้งหมด
8. ผลที่เคยเปิดจะมีรหัสอยู่ใน “เปิดผลสแกนที่เตรียมไว้” หรือกรอกรหัสจาก backend ได้โดยตรง ข้อมูลไฟล์ไม่ได้เก็บใน localStorage

## ไฟล์แต่ละตัวทำอะไร

| ไฟล์ | หน้าที่ |
|---|---|
| `static/index.html` | โครงหน้าเว็บ, ปุ่ม, ตาราง, สถานะ และ accessibility labels |
| `static/style.css` | รูปแบบ cream-paper, responsive, keyboard focus และไม่ใช้ CDN |
| `static/app.js` | Vue state, tree, pagination, polling, เปลี่ยนโฟลเดอร์, Cancel, Reveal, เปิดผลเดิม |
| `static/api.js` | แปลงการกระทำของ UI เป็น HTTP ตาม CONTRACT; ตรวจ HTTP error; timeout 30 วินาที |
| `static/mock-api.js` | simulator สำหรับ UI ส่งข้อมูลรูปแบบเดียวกับ API; ไม่เข้าถึง OS |
| `static/mock-api.json` | ตัวอย่าง 50 + 10 รายการที่คัดลอกจากเอกสารทีม |
| `static/vendor/` | Vue 3.5.13 และ MIT license |
| `tools/ui-check.cjs` | ทดสอบการกดหน้าเว็บด้วย Playwright และบันทึกภาพ |
| `tools/ui-review-check.cjs` + `tools/ui-review-server.py` | ทดสอบ PR #1 กับ Python/SQLite จริงด้วยข้อมูลทดสอบและฐานข้อมูลชั่วคราว |
| `tools/ui-contract-check.cjs` | ทดสอบ HTTP adapter / error / race ด้วยเซิร์ฟเวอร์จำลองใน browser test |
| `docs/ui-evidence/` | ผลและภาพจาก UI tests; ไม่ใช่ผลสแกนไฟล์จริง |
| `static/presentation.html` | สไลด์ 7 หน้าแบบเปิดใน browser ได้ offline |

## ใครคุยกับใคร

```text
Browser (Vue / JavaScript)
    │ HTTP บน loopback: request/response เป็น JSON
    ▼
Python HTTP server บน Windows
    │ subprocess → wsl.exe → โปรแกรม C เป็น process แยก
    │ pipe: stdout ของ C เป็น NDJSON; stderr เป็น diagnostic
    ▼
C scanner ใน WSL
    │ POSIX library/API → Linux kernel → filesystem/DrvFs
    ▼
รายชื่อไฟล์และ metadata บนไดรฟ์ Windows

C ส่ง entry/error/skipped/done กลับทาง stdout
Python ตรวจข้อมูล + เรียก Windows GetCompressedFileSizeW
Python รวมยอดและเก็บ SQLite → Browser ขออ่านทีละ 50 รายการ
```

แผนภาพนี้เป็นสถาปัตยกรรมเป้าหมายของทีม ต้องแยกจากโหมด mock ซึ่งทุกเมธอดตอบข้อมูลสมมติใน JavaScript

### หนึ่งรอบตั้งแต่กด Scan

1. `startScan()` อ่าน path จาก input แล้วเรียก `api.start(path)`
2. `static/api.js` ใช้ `fetch` ส่ง `POST /api/scans` พร้อม `{"path":"D:\\demo"}`
3. Python ต้องตอบ `202 {"id":"scan-...","state":"queued"}` โดยไม่รอทั้งไดรฟ์เสร็จ
4. ตามแผน Python แปลง path เป็น `/mnt/d/demo` แล้วเปิด C ผ่าน WSL; ไม่ใช่ browser เปิดไฟล์เอง
5. C เดิน directory และพิมพ์ JSON ทีละบรรทัด เช่น `{"type":"entry","relativePath":"docs/a.txt","kind":"file","logicalBytes":12,...}`
6. Python อ่าน pipe แบบต่อเนื่อง ตรวจ relative path/schema, ขอ allocated จาก Windows แล้วบันทึก SQLite เป็น batch
7. `refreshStatus()` ส่ง `GET /api/scans/{id}` รอบละประมาณ 2 วินาทีหลังคำขอก่อนหน้าจบ แสดง counts กับ elapsedSeconds; ไม่สร้างเปอร์เซ็นต์ที่ไม่ทราบตัวหาร
8. `loadChildren()` ขอ `GET /api/scans/{id}/children?parent=&offset=0&limit=50`
9. กดแสดงเพิ่มเติมจะขอ offset 50; tree กรองให้เห็นเฉพาะ directory แต่ offset ต้องนับ file/link ด้วยเพื่อไม่ข้ามหรือโหลดซ้ำ
10. ตอน status เปลี่ยนจาก active เป็น completed/partial/cancelled/failed เว็บล้าง cache หน้าที่เคยโหลดแล้วขอใหม่ เพราะข้อมูลและลำดับอาจเปลี่ยนระหว่างสแกน

### เหตุผลด้าน OS

- **Process:** Python และ C มีพื้นที่หน่วยความจำแยกกัน จึงต้องส่งข้อมูลผ่าน IPC ไม่ได้ใช้ตัวแปร Vue ร่วมกัน
- **IPC:** HTTP ผ่าน socket ใช้คุย Browser↔Python; pipe ใช้รับ stdout จาก process scanner ตามสถาปัตยกรรมของทีม; JSON/NDJSON เป็นรูปแบบข้อมูล ไม่ใช่ system call
- **User/kernel boundary:** Vue, Python และ C เป็นโปรแกรม user space; คำขอข้อมูลไฟล์สุดท้ายต้องผ่านบริการของ OS เพื่อให้ kernel ตรวจ path และสิทธิ์
- **POSIX ไม่เท่ากับ syscall ทุกชื่อ:** `opendir`, `readdir`, `closedir` เป็นฟังก์ชัน libc; libc อาจเรียก kernel ผ่าน `openat`, `getdents64`, `close` เป็นต้น จึงไม่ควรพูดว่า `readdir()` เป็น syscall โดยตรงทุกระบบ ใช้ `strace` กับ C จริงจึงยืนยัน syscall ที่เกิดบนเครื่องนั้นได้
- **Metadata:** `lstat` อ่านชนิด/ขนาด/ข้อมูลไฟล์ และคืนข้อมูลตัว symlink แทนการตามปลายทาง ไม่จำเป็นต้องอ่านเนื้อหาไฟล์ทั้งหมดเพื่อรู้ `st_size`
- **File descriptors/resources:** ส่วน scanner ต้องปิด directory stream และตรวจ return/errno มิฉะนั้นอาจรั่วทรัพยากรหรือรายงานผลไม่ครบ
- **Directory traversal:** การเดินโฟลเดอร์ของ scanner กับการกาง tree บนเว็บเป็นคนละอย่าง Scanner เก็บรายการทั้งงาน ส่วนเว็บขอเฉพาะลูกที่กำลังดู
- **Asynchronous UI:** `fetch` คืน Promise, browser จึงรับคลิก/วาดหน้าได้ระหว่างรอ I/O; ส่วน backend ต้องทำงานเบื้องหลังจริงด้วย ไม่ใช่เปลี่ยนเป็น async ในหน้าเว็บแล้วถือว่าทั้งระบบไม่ค้าง
- **Cancel:** เว็บส่ง HTTP คำขอยกเลิก ไม่สามารถหยุด C ด้วยการซ่อน loading หรือยกเลิก fetch; Python ต้องหยุด/รอ process และอัปเดตสถานะ cancelled ตามผลจริง
- **Streaming:** ส่ง NDJSON ทีละบรรทัดช่วยให้ Python ใช้ผลระหว่าง C ทำงานได้ ต้องจัดการ buffering และ drain stderr ไม่ให้ pipe เต็มจน process รอกัน

### ตัวเลขที่ต้องอธิบายได้

Logical คือขนาดเนื้อหาไฟล์ตาม metadata (`st_size` สำหรับ regular file) ส่วน Allocated มาจาก Windows API `GetCompressedFileSizeW` ตามแผนทีม ไฟล์บีบอัดหรือ sparse อาจมี Allocated น้อยกว่า Logical จึงห้ามเรียกผลต่างว่า Slack/Waste เสมอ

UI ไม่คำนวณ allocated ด้วยสูตร cluster และไม่แปลง null เป็น 0 ค่า 0 แปลว่าวัดได้ศูนย์ แต่ null แปลว่าไม่ทราบ/ยังสรุปไม่ได้ ขนาดโฟลเดอร์มาจาก backend ไม่ใช่รวมเฉพาะ 50 แถวที่โหลดมา เพราะจะได้ยอดผิด

ยอดทั้ง root และโฟลเดอร์ที่เลือกอ่านจาก `children.folder` โดยเก็บ metadata แยกตาม relativePath เมื่องานจบจะขอใหม่ให้ยอดและ partial เป็นค่าล่าสุด ไม่รวมแค่ 50 แถวบนหน้าจอ และไม่แปลง 0 เป็น unknown

Hard link มีหลาย path ชี้ข้อมูลเดียวกัน การรวมตาม path อาจนับซ้ำ; ผลรวมไฟล์ยังอาจขาดส่วนที่ไม่มีสิทธิ์เข้าถึงและ metadata ระบบ จึงไม่เท่ากับพื้นที่ใช้ทั้ง volume

## HTTP ที่เพื่อนต้องเตรียม

| การกระทำ | Request | ผลที่เว็บรอ |
|---|---|---|
| โหลดไดรฟ์ | GET /api/drives | array ของไดรฟ์รูปแบบเดิม มี path |
| Scan | POST /api/scans, body {path} | id และ state |
| สถานะ | GET /api/scans/{id} | state, counts, elapsedSeconds, partial, error |
| กาง/เลือก/เพิ่มเติม | GET /api/scans/{id}/children?parent=...&offset=...&limit=50 | folder, items, totalChildren, hasMore, partial |
| รายละเอียดปัญหา | GET /api/scans/{id}/issues?offset=...&limit=50 | items, totalIssues, hasMore |
| Cancel | POST /api/scans/{id}/cancel | cancelling แล้ว status เป็น cancelled |
| Reveal | POST /api/reveal, body {scanId,relativePath} | {status:"revealed"} หรือ HTTP error |

HTTP error ใช้ `{code,detail}`; ข้อมูลชื่อไฟล์แสดงเป็น text ผ่าน Vue interpolation ไม่ใช้ `v-html`

รายละเอียดปัญหาโหลดจาก `/issues` เมื่อกางช่องรายละเอียด: แสดง relativePath, issueType, code และ message ครั้งละไม่เกิน 50 รายการ หากโหลดต่อผิดพลาดจะเก็บรายการเดิมไว้และให้ลองใหม่ เมื่อเปลี่ยนงาน/จำนวนปัญหา/งานจบจะล้าง cache ปัญหา และทิ้ง response จากงานเก่า

แยก `status.error` ซึ่งเป็นเหตุผลสแกนล้มเหลว (แม้ HTTP 200) ออกจาก HTTP error `{code,detail}` หน้าเว็บแสดงทั้งตอน polling และเปิดผลเดิม

การล้าง cache ฝั่ง SQLite เป็นงาน backend และยังไม่มี endpoint ใน CONTRACT ปุ่มล้างประวัติหน้าเว็บจึงลบเฉพาะรหัสงานใน localStorage ไม่อ้างว่าล้าง SQLite หรือไฟล์ผู้ใช้

## จุดป้องกันบั๊กใน UI

- ตรวจ `response.ok` ก่อนถือว่า Reveal/Scan สำเร็จ; HTTP 404 ของ API ใหม่แสดงข้อความให้ผู้ใช้ทราบว่า backend ยังไม่พร้อม
- บันทึก epoch ของคำขอ child list; ถ้าเปลี่ยนงานหรือรีเฟรชแล้ว response เก่ามาถึง จะทิ้งผลเก่านั้น
- แยก cache ตาม relativePath; response ของโฟลเดอร์ A จึงไม่ไปแทนตาราง B ที่เพิ่งเลือก
- ไม่ยิงคำขอหน้าเดียวซ้อนกัน, offset เพิ่มตามจำนวนที่ API ส่ง, รวมรายการด้วย key relativePath
- เมื่อสแกนจบล้างหน้าที่โหลดแล้วเพื่อไม่คงลำดับเก่าจากระหว่าง running
- แสดง error ของการโหลดต่อและให้ retry โดยไม่ทิ้งแถวที่โหลดสำเร็จแล้ว
- ไม่มีการสแกนทั้งไดรฟ์ใน browser หรือโหลด tree ทั้งก้อนล่วงหน้า; user กางเพิ่มจึงขอเพิ่ม

## สิ่งที่ยังต้องทดสอบร่วมก่อนส่งวิชา

- Windows Python เรียก C/WSL จริงและ NDJSON ตรง CONTRACT
- Allocation บน Windows เทียบ API/Properties, รวมกรณี compressed/sparse และ permission
- Cancel หยุด process จริง ไม่ใช่เปลี่ยนเฉพาะ status
- Reveal เปิด Explorer บนเครื่องนำเสนอจริง
- full-drive สแกนจบหรือยกเลิกได้ แสดงจำนวนและปัญหาตามจริง ตาม SPEC ปัจจุบันไม่มีงาน benchmark หรือวัดหน่วยความจำ
- ตกลงวิธีล้าง SQLite cache หากทีมต้องการเพิ่ม endpoint
- เพื่อนกด Scan/Cancel/Reveal และซ้อมนำเสนอร่วมกัน 2 รอบ

## แหล่งอ่านสำหรับตอบคำถาม OS

- readdir / libc / errno: https://man7.org/linux/man-pages/man3/readdir.3.html
- stat / lstat / metadata: https://man7.org/linux/man-pages/man2/stat.2.html
- subprocess / pipes: https://docs.python.org/3/library/subprocess.html
- Allocated บน Windows: https://learn.microsoft.com/en-us/windows/win32/api/fileapi/nf-fileapi-getcompressedfilesizew
- ข้อตกลงของทีม: docs/CONTRACT.md และ docs/SPEC.md
