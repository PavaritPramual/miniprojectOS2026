# ผลตรวจงานหน้าเว็บของธีรเมธ

วันที่ 5 ตุลาคม 2569 · branch `feature/theeramet-ui` · แก้รีวิว PR #1

## ผลทดสอบหน้าเว็บ

ผ่าน 27 กลุ่ม: UI simulator 12 กลุ่ม, HTTP fixtures 8 กลุ่ม และ Python HTTP/SQLite จริงกับข้อมูลทดสอบ 7 กลุ่ม ไม่มี JavaScript page error ในทั้งสามชุด

| ชุด | หลักฐาน | ขอบเขต |
|---|---|---|
| UI simulator | `ui-evidence/results.json` | แสดงเพิ่ม 50+10, tree ถึงชั้น 8, unknown/0, Cancel, Reveal, เปิดผลเดิม, offline assets และมือถือ |
| HTTP fixtures | `ui-evidence/http-results.json` | ส่ง request ตามสัญญา, คำตอบช้า, retry, HTTP error และโหลดลำดับใหม่เมื่องานจบ; metadata อ้างรูปแบบ `docs/examples/api.json` ล่าสุด |
| Python/SQLite | `ui-evidence/review-results.json` | ใช้ handler, ScanManager และ ScanStore ของโปรเจกต์จริงบน localhost กับฐานข้อมูลชั่วคราว |

การตรวจ PR ทั้ง 7 กรณี:

1. root ที่เสร็จแล้วแสดง Logical/Allocated 1 MiB และครบถ้วนจาก `children.folder`
2. root ว่างแสดง 0 B ทั้งสองค่า
3. โหลด `/issues` หน้าแรก 50 รายการ แล้วจำลอง HTTP 503 ของหน้าถัดไป; retry ได้ครบ 60 โดยไม่ซ้ำและไม่ทิ้งรายการเดิม แสดง path/type/code/message
4. เปิดงาน failed เดิมเห็น `status.error` และล้างปัญหาของงานก่อนหน้า
5. polling จาก running → failed เห็นเหตุผลจาก `status.error`
6. โฟลเดอร์ย่อยที่เลือกอยู่และ root เปลี่ยนยอดจาก unknown เป็น 1 MiB หลังงานเสร็จ
7. response ของ issues หน้าถัดไปที่มาช้าไม่ปนกับงานใหม่

ฐานข้อมูลทดสอบสร้างจากข้อมูลที่กำหนดไว้และลบอัตโนมัติ ไม่อ่านหรือแก้ฐานข้อมูลผู้ใช้ ไม่ได้รัน C/WSL หรือวัด allocation ของ Windows ภาพ `review-failed.png` แสดง UI ที่รับ failed status ผ่าน Python จริง ส่วนภาพ 01–04 เป็น simulator

## สิ่งที่แก้ตามรีวิว

- เก็บ `children.folder` ตาม path และใช้กับ root/โฟลเดอร์ที่เลือก; ขอใหม่เมื่องานจบ
- แยกโหลด `/issues` ครั้งละ 50 พร้อม loading, error, retry และป้องกันคำตอบเก่า
- แสดงเหตุผลสแกนล้มเหลวจาก `status.error`; HTTP error ยังคงอ่าน `{code,detail}`
- ปรับ mock, HTTP fixtures, คู่มือ, บทพูดและสไลด์ให้ตรง API ล่าสุด

แก้เฉพาะหน้าเว็บ เอกสาร และเครื่องมือทดสอบ ไม่มีการแก้ `main.py` หรือ `backend/`

## ผลชุดทดสอบ backend เดิมบน Linux

รัน `python3 -m unittest discover -v`: 21 กรณี, ผ่าน 14, ข้าม 5, ไม่ผ่าน 2 กรณีที่มีสมมติฐานของ Windows:

- `test_latest_real_and_reveal`: fixture ใช้ path ชั่วคราวของ Linux แต่ `/latest` รับ absolute path ของไดรฟ์ Windows จึงตอบ 400 และ test อ่าน `id` ไม่ได้
- `test_whole_drive_guard_and_no_automatic_sample`: backend ตรวจ Windows ก่อน guard ทั้งไดรฟ์ บน Linux จึงตอบ 503 แทน 409 ที่ test คาดไว้

ทั้งสองกรณีอยู่ในโค้ด backend/tests ที่ไม่ได้แก้ในงานนี้ ไม่ถือว่าชุด backend ผ่านทั้งหมด ต้องให้ทีมตรวจซ้ำบน Windows ส่วน 5 กรณีที่ข้ามต้องใช้ Windows allocation หรือเปิด WSL tests

## สิ่งที่ยังต้องยืนยันบนเครื่องนำเสนอ

C/WSL จริง, Windows Allocated, Cancel หยุด process, Explorer และการสแกนทั้งไดรฟ์ยังไม่ถูกยืนยันจากการทดสอบรอบนี้ การเปิดผลด้วยรหัสมีแล้ว ส่วน UI เลือก Python sample และค้นหาผลล่าสุดผ่าน `/latest` ยังเป็นงานเชื่อมต่อเพิ่มเติม ข้อตกลงกลุ่มวันที่ 5 ต.ค. ตัด benchmark และการวัดหน่วยความจำออกตาม SPEC

สไลด์ PPTX ตรวจด้วยเครื่องมือสร้างและ renderer ไม่ได้ตรวจใน Microsoft PowerPoint ควรเปิดและตรวจฟอนต์บนเครื่องนำเสนอ

## รันทดสอบซ้ำ

ติดตั้ง Node.js + Playwright/Chromium สำหรับผู้พัฒนา เปิด Python server ก่อนสำหรับสองชุดแรก:

```bash
node tools/ui-check.cjs
node tools/ui-contract-check.cjs
node tools/ui-review-check.cjs
```

สองชุดแรกใช้ `CORESPACE_URL` (ค่าเริ่มต้น `http://127.0.0.1:8080`) ชุด review เปิด Python server และฐานข้อมูลชั่วคราวเอง ใช้ `PYTHON` กำหนด interpreter ได้ ตั้ง `NODE_PATH` และ `PLAYWRIGHT_BROWSERS_PATH` หากแพ็กเกจ/browser อยู่ที่อื่น ไม่ต้องมีเครื่องมือเหล่านี้เพื่อเปิดหน้าเว็บตามปกติ
