# รูปแบบข้อมูลสำหรับเชื่อมโปรแกรม CoreSpace

หน้านี้เปิดใช้ตอนเขียนส่วนที่ต้องส่งข้อมูลให้เพื่อน เช่น ศรัณย์ต้องส่งชื่อไฟล์ให้ปวริศช์ และปวริศช์ต้องส่งขนาดให้ธีรเมธ ชื่อภาษาอังกฤษในตัวอย่างต้องเขียนให้ตรงกัน เพื่อให้โปรแกรมอ่านข้อมูลของกันและกันได้

หากต้องการรู้แค่หน้าที่ของตัวเอง ให้เริ่มจาก [แผนรายคน](PROJECT_PLAN.md) ก่อน

| คำที่ใช้ต่อจากนี้ | หมายถึงอะไร |
| --- | --- |
| C scanner | โปรแกรม C ที่อ่านรายการไฟล์และโฟลเดอร์ |
| NDJSON / record | ข้อความข้อมูลที่ส่งทีละบรรทัด หนึ่งบรรทัดเป็นหนึ่งรายการหรือเหตุการณ์ |
| field / ฟิลด์ | ช่องข้อมูล เช่น ชื่อไฟล์หรือขนาดไฟล์ |
| path | ตำแหน่งไฟล์หรือโฟลเดอร์ เช่น D:\\demo |
| root | โฟลเดอร์ที่ผู้ใช้เลือกเป็นจุดเริ่มอ่าน |
| API / endpoint | คำขอที่หน้าเว็บส่งไปยัง Python แต่ละคำขอมีหน้าที่เฉพาะ |
| request / response | คำขอที่ส่งไป / ข้อมูลที่ตอบกลับ |
| schema | รูปแบบที่กำหนดว่าต้องมีช่องข้อมูลอะไรบ้าง |
| stdout / stderr | ช่องส่งผลข้อมูล / ช่องส่งข้อความแจ้งปัญหาของโปรแกรม |
| partial / null | ผลที่ยังไม่ครบ / ช่องที่ยังไม่มีค่าหรืออ่านค่าไม่ได้ |
| offset / limit | เริ่มหยิบรายการที่ตำแหน่งใด / หยิบได้มากที่สุดกี่รายการ |

ตัวอย่างเช่น เว็บขอรายการเริ่มที่ 0 จำนวน 50 รายการ จากนั้นขอเริ่มที่ 50 เพื่อดูชุดถัดไป วิธีนี้คือการแสดงทีละหน้า

**สถานะ:** รูปแบบที่เตรียมให้ทีมใช้เขียนโปรแกรม ข้อมูลตัวอย่างเป็นข้อมูลสมมติสำหรับลองเชื่อมงาน ไม่ใช่ผลการสแกนจริง<br>
**ข้อกำหนดภาพรวม:** [SPEC.md](SPEC.md) · **แผนวันเดียว:** [ONE_DAY_PLAN.md](ONE_DAY_PLAN.md)<br>
**ข้อมูลตัวอย่าง:** [`examples/scan.ndjson`](examples/scan.ndjson), [`examples/api.json`](examples/api.json) · **ชุดโฟลเดอร์ทดสอบ:** [`prepare_demo_fixture.ps1`](../tools/prepare_demo_fixture.ps1)

หากพบว่าสัญญานี้ใช้ไม่ได้จริง ให้เจ้าของส่วนที่พบปัญหาแก้เอกสารนี้พร้อมแจ้งอีกสองคนในข้อความเดียว: **ฟิลด์ที่เปลี่ยน + ตัวอย่างใหม่ + เหตุผล** ไม่ต้องนัดประชุม

## 1. C scanner → Python: NDJSON

- โปรแกรมรับ `diskviz-scan --root <absolute-WSL-path> --ndjson` และพิมพ์ UTF-8 JSON หนึ่ง record ต่อหนึ่งบรรทัดบน stdout; diagnostic อยู่ stderr
- `relativePath` เป็น path เทียบจาก root ใช้ `/`; root เป็น `""`; ห้าม absolute path หรือ `..` ที่ออกนอก root
- `parentRelativePath` ของ root เป็น `null`; ลูกของ root เป็น `""`; path ลึกใช้ชื่อพ่อ เช่น `"docs"`
- `entry` ของ root ต้องมาก่อน; directory ใช้ `logicalBytes: 0` เพราะ Python เป็นฝ่ายรวมยอดของไฟล์ใต้โฟลเดอร์; file ใช้ `st_size`
- สำหรับ symbolic link/junction ที่ไม่เดินต่อ ให้ส่งทั้ง `entry` ชนิด `link` และ `skipped` ของ path เดียวกัน เพื่อให้ UI เห็นว่ามีรายการและรู้เหตุผลที่ข้าม
- `done` เป็น record สุดท้าย; `fileCount` นับ regular files, `directoryCount` **รวม root**, `skippedCount` นับรายการที่ข้าม, `errorCount` นับรายการอ่านไม่ได้; `complete=false` หากมี error หรือ skipped
- `exit code`: `0` เดินครบโดยไม่มี error/skip, `1` ผลบางส่วน, `2` input ผิด, `130` ถูกยกเลิก

ตัวอย่าง entry:

```json
{"type":"entry","relativePath":"docs/รายงาน 1.txt","parentRelativePath":"docs","name":"รายงาน 1.txt","kind":"file","logicalBytes":12}
```

Python ต้องตรวจ schema/path/count ก่อนบันทึก ไม่เชื่อ path จาก stdout โดยตรง และแปลงเป็น Windows path ภายใต้ root ที่ผู้ใช้เลือกเท่านั้น

## 2. Python → เว็บ: API

| คำขอ | ผลสำเร็จ | กรณีผิดพลาดที่ต้องส่ง |
| --- | --- | --- |
| `POST /api/scans` body `{ "path": "D:\\demo" }` | `202 {"id":"scan-...","state":"queued","source":"wsl"}` | `400` path ผิด, `409` มี full-drive scan อีกงาน, `503` ยังไม่ตั้งค่า C/WSL |
| `GET /api/scans/{id}` | สถานะและ counts ตามตัวอย่าง | `404` ไม่มี id |
| `GET /api/scans/latest?path=<Windows-path>` | สถานะของผลจริงล่าสุดที่เป็น `completed` หรือ `partial` ใช้รูปแบบเดียวกับ status | `400` path ไม่ใช่ตำแหน่งเต็มในไดรฟ์เครื่องนี้, `404` ไม่มีผลจริง |
| `GET /api/scans/{id}/children?parent=<relativePath>&offset=0&limit=50` | ลูกของ parent 0–50 รายการ | `400` parent/offset/limit ผิด, `404` ไม่มี id |
| `GET /api/scans/{id}/issues?offset=0&limit=50` | รายการอ่านไม่ได้หรือข้าม พร้อมเหตุผล ไม่เกิน 50 รายการ | `400` offset/limit ผิด, `404` ไม่มี id |
| `POST /api/scans/{id}/cancel` | `202 {"id":"...","state":"cancelling"}`; status ถัดไปเป็น `cancelled` | `404` ไม่มี id, `409` งานจบแล้ว |
| `GET /api/drives` | รูปแบบรายการเดิมของต้นแบบ | error HTTP จริง ไม่คืนรายการว่างเมื่อ API ล้มเหลว |
| `POST /api/reveal` body `{ "scanId":"...", "relativePath":"..." }` | `200 {"status":"revealed"}` | `400/404` path ไม่อยู่ในผลสแกน, `500` Explorer เปิดไม่ได้ |

HTTP error ทุกตัวใช้ `{ "code": "SOME_CODE", "detail": "ข้อความสั้นที่แสดงให้ผู้ใช้ได้" }`; เว็บต้องเช็ก `response.ok` ก่อนอ่านเป็นผลสำเร็จ

### เลือกแหล่งข้อมูลและตั้งค่า

- ค่าเริ่มต้น `source` คือ `wsl`; Python จะเรียกโปรแกรม C ที่กำหนดด้วย `CORESPACE_SCANNER_WSL_PATH` ใน WSL distro จาก `CORESPACE_WSL_DISTRO` (ค่าเริ่มต้น `Ubuntu`)
- ทดสอบการเชื่อมหน้าเว็บโดยเลือก `source: "sample"` อย่างชัดเจน; ผลนี้เป็นข้อมูลสมมติและ status จะมี `isSample: true` ห้ามใช้เป็นผลทดสอบหรือ benchmark จริง
- หากเรียก WSL หรือโปรแกรม C ไม่ได้ งานต้องแสดง error; ห้ามสลับไปข้อมูลตัวอย่างให้อัตโนมัติ
- SQLite เก็บผลไว้ใน `%LOCALAPPDATA%\\CoreSpace\\scans.sqlite3`; ตั้ง `CORESPACE_DB_PATH` เพื่อใช้ตำแหน่งอื่น
- เก็บผลไว้เปิดดูภายหลัง เมื่อสแกนใหม่สำเร็จหรือได้ผลบางส่วน จะลบผลเก่าที่จบแล้วของตำแหน่งและแหล่งข้อมูลเดียวกัน; งานที่กำลังทำจะไม่ถูกลบ ผลตัวอย่างไม่ลบผลจริง
- `/latest` ค้นเฉพาะผลจาก `source: "wsl"` โดยไม่ต้องให้โฟลเดอร์นั้นยังมีอยู่ ไม่ค้นผล `sample`, `cancelled` หรือ `failed`; path ใช้ตัวพิมพ์ใหญ่/เล็กต่างกันได้ และใช้ `/` หรือ `\\` คั่นได้
- Python บันทึก root ทันที แล้วบันทึกรายการเพิ่มทุก 128 รายการหรือทุก 1 วินาที แม้โปรแกรมส่งข้อมูลหยุดส่งชั่วคราว จึงดูข้อมูลที่รับแล้วได้ระหว่างสแกน
- การยกเลิกตรวจ PID ของโปรแกรมใน Ubuntu หลังสั่งหยุด/บังคับหยุด หากยืนยันไม่ได้ภายใน 15 วินาที งานเป็น `failed` พร้อม issue `CANCEL_NOT_CONFIRMED`; ห้ามแสดงว่าหยุดสำเร็จเพียงเพราะ `wsl.exe` จบ
- เซิร์ฟเวอร์รับคำขอเฉพาะ `127.0.0.1`; สแกนทั้งไดรฟ์ได้ครั้งละหนึ่งงาน
- Python ไม่เชื่อ `allocatedBytes` ที่ C ส่งมา แต่เรียก Windows API กับไฟล์จริง; ค่าที่มาจาก `source: "sample"` ในตัวอย่างนี้เป็นค่าจำลอง

### สถานะงาน

```json
{
  "id": "scan-demo-001",
  "rootPath": "D:\\demo",
  "source": "wsl",
  "isSample": false,
  "state": "running",
  "fileCount": 60,
  "directoryCount": 9,
  "errorCount": 0,
  "skippedCount": 0,
  "elapsedSeconds": 2.4,
  "partial": false,
  "error": null
}
```

`state` เป็น `queued`, `running`, `cancelling`, `completed`, `partial`, `cancelled` หรือ `failed`; ไม่มีเปอร์เซ็นต์สแกนถ้าไม่รู้จำนวนทั้งหมด `partial=true` เมื่อข้อมูลไม่ครบหรือถูกยกเลิก

`errorCount` ใน status นับปัญหาทั้งจาก C และจากการวัดพื้นที่/รับข้อมูลของ Python; ตัวเลขใน record `done` ใช้ตรวจเฉพาะปัญหาที่ C รายงาน

### รายการลูก

```json
{
  "scanId": "scan-demo-001",
  "parent": "",
  "offset": 0,
  "limit": 50,
  "totalChildren": 60,
  "hasMore": true,
  "partial": false,
  "folder": {"relativePath":"","name":"demo","kind":"directory","logicalBytes":71,"allocatedBytes":245760,"partial":false,"hasChildren":true},
  "items": [
    {"relativePath":"docs","name":"docs","kind":"directory","logicalBytes":12,"allocatedBytes":4096,"partial":false,"hasChildren":true}
  ]
}
```

ตัวอย่างย่อด้านบนแสดงรูปแบบฟิลด์; `examples/scan.ndjson` มีข้อมูลจำลอง 64 ไฟล์/13 โฟลเดอร์ตามชุดทดสอบ ส่วน `examples/api.json` มี `rootChildren` และ `childrenPage1/childrenPage2` ของโฟลเดอร์ `many` จำนวน 50 + 10 รายการ ข้อมูลสองไฟล์สร้างร่วมกันด้วย `tools/generate_examples.py` และมีการตรวจว่า Python ให้คำตอบตรงตัวอย่าง `parent` เป็น `""` เมื่อขอลูกของ root; `offset` เริ่ม 0; `limit` สูงสุด 50; `hasMore` คำนวณจากจำนวนที่ส่งจริง `offset + items.length < totalChildren`

ทุกคำตอบ children มี `folder` ซึ่งบอกขนาดและสถานะของโฟลเดอร์ที่กำลังเปิด โดยใช้ฟิลด์แบบเดียวกับรายการใน `items`; ใช้ได้กับ root ด้วย เมื่อสแกนยังทำงานอยู่ ยอดโฟลเดอร์ที่ยังสรุปไม่เสร็จส่งเป็น `null`; หน้าเว็บแสดงว่ากำลังคำนวณได้จากสถานะงาน `running`. API issues ส่ง `{scanId, offset, limit, totalIssues, hasMore, items}`; แต่ละรายการมี `relativePath`, `code`, `message`, `issueType`.

- เมื่อสแกนเสร็จ เรียง `allocatedBytes` มากไปน้อย; `null` อยู่ท้าย แล้วเรียง `name` และ `relativePath` เพื่อให้ลำดับคงที่
- ระหว่าง `queued/running/cancelling` API เรียงตามลำดับที่บันทึก รายการใหม่ต่อท้าย เว็บต้องล้างหน้าที่โหลดไว้แล้วดึงใหม่เมื่อสถานะเปลี่ยนเป็น `completed`, `partial`, `cancelled` หรือ `failed` เพราะงานที่จบจะเรียงตามพื้นที่แทน
- `logicalBytes` และ `allocatedBytes` เป็น integer ไม่ติดลบหรือ `null`; `null` หมายถึงวัดไม่ได้/ยอดโฟลเดอร์ยังไม่สรุป ไม่ใช่ศูนย์
- directory total เป็นผลรวม regular files ที่อ่านได้ใต้โฟลเดอร์; ระหว่างยังไม่จบ subtree ส่ง `null` และเมื่อสแกนมีปัญหาส่ง `partial=true`
- `hasChildren` ของ directory บอกว่ามี directory หรือ file อยู่ข้างในเพื่อให้ UI แสดงปุ่มกาง; file/link เป็น `false`
- `GET /api/scans/{id}/children` ส่ง file, directory และ link ใน `items`; tree ซ้ายกรองแสดงเฉพาะ directory, ตารางขวาแสดงทั้งหมด

### ตัวอย่างทดสอบข้อมูลจำลอง

คำขอเริ่มข้อมูลตัวอย่าง:

```json
{"path":"D:\\demo","source":"sample"}
```

ตัวอย่างเต็มของการเริ่มงาน สถานะ รายการลูกหน้า 1/2 รายการ issues และการยกเลิกอยู่ใน [`examples/api.json`](examples/api.json). ค่า Allocated ของไฟล์ในตัวอย่างเป็นค่าจำลอง ไม่ใช่ค่าที่ Windows วัดได้

## 3. สิ่งที่ล็อกเพื่อให้ตัดสินใจเร็ว

1. เว็บยังอยู่บน Windows; C scanner อยู่ใน WSL; Python แปลง path/วัด Allocated/เก็บ SQLite; ไม่แยกบริการเพิ่ม
2. ใช้ localhost เท่านั้น; ไม่มี login, cloud, Docker, search, export, treemap หรือ duplicate detector ในงานส่ง
3. ปุ่ม Scan ใช้ endpoint ใหม่ `/api/scans`; endpoint `/api/scan` เดิมเป็นของต้นแบบและไม่ใช่เส้นทางส่งงาน
4. การ์ด Slack Space จากสูตรเดิมไม่อยู่ในผลส่งงาน; แสดง Logical/Allocated และคำว่า unknown/partial ตรงตามข้อมูล
5. ไม่ต้องมี Git issue, PR หรือประชุมหลายรอบสำหรับงานวันเดียว; ใช้เอกสารนี้เป็นข้อตกลง และแจ้งเฉพาะเมื่อจะเปลี่ยนฟิลด์ที่อีกส่วนใช้
