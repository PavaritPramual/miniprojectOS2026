# ผลตรวจงานหน้าเว็บของธีรเมธ

วันที่ 4 ตุลาคม 2569 · branch `feature/theeramet-ui`

## ขอบเขตและผล

ผ่าน 20 กลุ่มทดสอบอัตโนมัติ: 12 กลุ่มกด UI ในโหมด mock และ 8 กลุ่มใช้ HTTP fixtures จำลอง นอกจากนี้ตรวจปุ่ม/คีย์บอร์ดสไลด์ HTML 7 หน้า และตรวจโครงสร้าง/การจัดวาง PPTX 7 หน้าแล้ว

ทดสอบด้วย Chromium headless บน Linux โดยใช้ Python server ต้นแบบในเครื่อง ไม่ใช่ผลทดสอบ C, WSL, Windows Allocated, Explorer จริง หรือ full-drive benchmark

## รายการที่ตรวจ

| กลุ่มทดสอบ | ผล |
|---|---|
| Partial status / no console crash / first 50 rows | PASS |
| Table pagination 50 + 10 without duplicates | PASS |
| Unknown / zero / compressed size / skipped link | PASS |
| Reveal error and success are visible | PASS |
| Tree pagination includes directories after item 50 | PASS |
| Depth 8 / collapse / expand / breadcrumb navigation | PASS |
| Empty directory / Thai names and spaces | PASS |
| Cancel keeps partial results and allows next scan | PASS |
| Failed scan status is shown | PASS |
| Completed scan and saved-result resume | PASS |
| Required path / offline assets / mobile layout | PASS |
| Real adapter reports missing new backend truthfully | PASS |
| POST path, async status and bounded children requests | PASS |
| Failed next page preserves existing rows; retry loads once | PASS |
| Slow response for A does not replace selected B | PASS |
| Status error retains UI; retry recovers | PASS |
| Cancel HTTP error remains visible | PASS |
| Terminal reordering resets previous pagination | PASS |
| Reveal sends scanId + relativePath and honors HTTP error | PASS |
| Next job does not keep old folder rows; successful cancellation | PASS |

## หลักฐาน

- `ui-evidence/results.json` — ผล UI พร้อมการตรวจ console error และการร้องขอแหล่งภายนอก
- `ui-evidence/http-results.json` — ผล HTTP fixtures พร้อม method/path/query/body ที่หน้าเว็บส่ง
- `ui-evidence/01-root.png` — หน้าแรก 50 รายการจาก mock
- `ui-evidence/02-depth-eight.png` — tree ถึงชั้น 8
- `ui-evidence/03-cancelled.png` — ยกเลิกงานตัวอย่าง
- `ui-evidence/04-mobile.png` — หน้าจอกว้าง 390 px ไม่มีการล้นทั้งหน้า

ภาพทั้งหมดเป็น UI ที่รันจริงกับข้อมูลสมมติ มีการระบุโหมด mock บนหน้า ไม่ใช่หลักฐานสแกนไฟล์จริง

## สิ่งที่เปลี่ยน

ปรับหน้าเว็บให้ใช้สัญญาใหม่และใช้ adapter เดียวกันสำหรับ API จริงกับ simulator เพิ่มสถานะงาน, pagination ทั้ง tree/table, Cancel, Reveal ที่ตรวจ HTTP status, เปิดผลเดิมด้วย scan id, ข้อผิดพลาดที่ retry ได้, unknown/partial และป้องกัน response เก่าทับโฟลเดอร์ใหม่ เก็บ Vue เวอร์ชัน 3.5.13 กับ CSS ไว้ในเครื่อง เอาสูตร/การ์ด Slack ออกจาก UI

คงธีมกระดาษสีครีมของโครงการ รองรับมือถือและ keyboard focus พร้อมเอกสารอธิบาย OS, บทพูด, สไลด์ HTML และ PPTX

## สถานะ Git และขอบเขตการแก้

ไฟล์แก้ไขอยู่ในเครื่องบน branch `feature/theeramet-ui` ยังไม่ได้ commit หรือ push ตรวจว่า `main.py` และ `backend/` ไม่มี diff การแก้อยู่ใน `static/`, เอกสาร/สไลด์/ภาพหลักฐาน และเครื่องมือทดสอบ UI

## สิ่งที่ยังไม่ผ่านการยืนยัน

1. Backend ใหม่ใน checkout ยังไม่มี `/api/scans`; โหมดจริงแจ้ง error ตามจริง
2. ต้องเชื่อม C/WSL และทดสอบบน Windows ก่อนนำเสนอว่าระบบจริงเสร็จ
3. รายละเอียด error รายไฟล์กับวิธีล้าง SQLite cache ยังไม่มีสัญญา endpoint ครบ ปุ่มล้างประวัติ UI ลบเฉพาะ localStorage
4. ยอด root ไม่อยู่ในสัญญาปัจจุบัน UI แสดงไม่ทราบ แทนการรวมเพียงแถวที่โหลดมา
5. การอ้างว่าเร็วขึ้น, full-drive จบ, allocation แม่นยำ หรือ Cancel หยุด C จริง ต้องมีผลวัดจากเพื่อน/เครื่องนำเสนอ
6. PPTX ตรวจด้วยตัวอ่านและ renderer ของเครื่องมือ ยังไม่ได้เปิดใน Microsoft PowerPoint; ควรลองบนเครื่องนำเสนอและตรวจฟอนต์ Noto Sans Thai

## รันทดสอบซ้ำ

เปิด Python server ของโปรเจกต์ก่อน แล้วใช้ Node.js ที่มีแพ็กเกจ Playwright และ Chromium พร้อมใช้งาน:

```bash
node tools/ui-check.cjs
node tools/ui-contract-check.cjs
```

ตั้ง `NODE_PATH` ถ้า Playwright ไม่ได้อยู่ใน node_modules ของโปรเจกต์ และตั้ง `PLAYWRIGHT_BROWSERS_PATH` ถ้า browser อยู่ตำแหน่งอื่น ใช้ `CORESPACE_URL` เปลี่ยนค่า URL จากค่าเริ่มต้น `http://127.0.0.1:8080` การทดสอบไม่จำเป็นต่อการเปิดใช้งานหน้าเว็บตามปกติ
