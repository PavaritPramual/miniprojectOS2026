# CoreSpace — สัญญาข้อมูลที่ใช้ร่วมกัน

**สถานะ:** ข้อตกลงสำหรับลงมือพัฒนา ล็อกให้ทีมเริ่มงานได้ทันที ไม่ต้องประชุมกำหนดชื่อฟิลด์อีก<br>
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
| `POST /api/scans` body `{ "path": "D:\\demo" }` | `202 {"id":"scan-...","state":"queued"}` | `400` path ผิด, `409` มี full-drive scan อีกงาน |
| `GET /api/scans/{id}` | สถานะและ counts ตามตัวอย่าง | `404` ไม่มี id |
| `GET /api/scans/{id}/children?parent=<relativePath>&offset=0&limit=50` | ลูกของ parent 0–50 รายการ | `400` parent/offset/limit ผิด, `404` ไม่มี id |
| `POST /api/scans/{id}/cancel` | `202 {"id":"...","state":"cancelling"}`; status ถัดไปเป็น `cancelled` | `404` ไม่มี id, `409` งานจบแล้ว |
| `GET /api/drives` | รูปแบบรายการเดิมของต้นแบบ | error HTTP จริง ไม่คืนรายการว่างเมื่อ API ล้มเหลว |
| `POST /api/reveal` body `{ "scanId":"...", "relativePath":"..." }` | `200 {"status":"revealed"}` | `400/404` path ไม่อยู่ในผลสแกน, `500` Explorer เปิดไม่ได้ |

HTTP error ทุกตัวใช้ `{ "code": "SOME_CODE", "detail": "ข้อความสั้นที่แสดงให้ผู้ใช้ได้" }`; เว็บต้องเช็ก `response.ok` ก่อนอ่านเป็นผลสำเร็จ

### สถานะงาน

```json
{
  "id": "scan-demo-001",
  "rootPath": "D:\\demo",
  "state": "running",
  "fileCount": 60,
  "directoryCount": 9,
  "errorCount": 0,
  "skippedCount": 0,
  "elapsedSeconds": 2.4,
  "partial": false
}
```

`state` เป็น `queued`, `running`, `cancelling`, `completed`, `partial`, `cancelled` หรือ `failed`; ไม่มีเปอร์เซ็นต์สแกนถ้าไม่รู้จำนวนทั้งหมด `partial=true` เมื่อข้อมูลไม่ครบหรือถูกยกเลิก

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
  "items": [
    {"relativePath":"docs","name":"docs","kind":"directory","logicalBytes":12,"allocatedBytes":4096,"partial":false,"hasChildren":true}
  ]
}
```

ตัวอย่างย่อด้านบนแสดงรูปแบบฟิลด์; ไฟล์ `examples/api.json` มีหน้าเต็ม 50 + 10 รายการให้ใช้ทดสอบ UI จริง `parent` เป็น `""` เมื่อขอลูกของ root; `offset` เริ่ม 0; `limit` สูงสุด 50; `hasMore` คำนวณจากจำนวนที่ส่งจริง `offset + items.length < totalChildren`

- เมื่อสแกนเสร็จ เรียง `allocatedBytes` มากไปน้อย; `null` อยู่ท้าย แล้วเรียง `name` และ `relativePath` เพื่อให้ลำดับคงที่
- ระหว่าง `running` API อาจมีรายการเพิ่มและลำดับเปลี่ยน เว็บต้องล้างหน้าที่โหลดไว้แล้วดึงใหม่เมื่อสถานะเปลี่ยนเป็น `completed` หรือ `partial` เพื่อไม่ให้ผลสุดท้ายขาด/ซ้ำ
- `logicalBytes` และ `allocatedBytes` เป็น integer ไม่ติดลบหรือ `null`; `null` หมายถึงวัดไม่ได้/ยอดโฟลเดอร์ยังไม่สรุป ไม่ใช่ศูนย์
- directory total เป็นผลรวม regular files ที่อ่านได้ใต้โฟลเดอร์; ระหว่างยังไม่จบ subtree ให้แสดง `null` หรือ `partial=true` และป้าย “กำลังคำนวณ”
- `hasChildren` ของ directory บอกว่ามี directory หรือ file อยู่ข้างในเพื่อให้ UI แสดงปุ่มกาง; file/link เป็น `false`
- `GET /api/scans/{id}/children` ส่ง file, directory และ link ใน `items`; tree ซ้ายกรองแสดงเฉพาะ directory, ตารางขวาแสดงทั้งหมด

## 3. สิ่งที่ล็อกเพื่อให้ตัดสินใจเร็ว

1. เว็บยังอยู่บน Windows; C scanner อยู่ใน WSL; Python แปลง path/วัด Allocated/เก็บ SQLite; ไม่แยกบริการเพิ่ม
2. ใช้ localhost เท่านั้น; ไม่มี login, cloud, Docker, search, export, treemap หรือ duplicate detector ในงานส่ง
3. ปุ่ม Scan ใช้ endpoint ใหม่ `/api/scans`; endpoint `/api/scan` เดิมเป็นของต้นแบบและไม่ใช่เส้นทางส่งงาน
4. การ์ด Slack Space จากสูตรเดิมไม่อยู่ในผลส่งงาน; แสดง Logical/Allocated และคำว่า unknown/partial ตรงตามข้อมูล
5. ไม่ต้องมี Git issue, PR หรือประชุมหลายรอบสำหรับงานวันเดียว; ใช้เอกสารนี้เป็นข้อตกลง และแจ้งเฉพาะเมื่อจะเปลี่ยนฟิลด์ที่อีกส่วนใช้
