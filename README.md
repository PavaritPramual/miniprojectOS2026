# CoreSpace — Disk Space Visualization

- **วิชา:** Operating Systems and System Calls Programming (Mini Project)
- **กลุ่ม:** ผู้ก้าวข้ามโชคชะตาด้วยมือของตัวเอง
- **สมาชิก:** นายศรัณย์ พาพรชัย (673380515-5), นายปวริศช์ ประมวล (673380278-9), นายธีรเมธ สายคำ (673380273-9)
- **นำเสนอ:** 9 ต.ค. 2569 เวลา 13:00 น. (กลุ่มยืนยันแล้ว)

CoreSpace มี **ต้นแบบเว็บบน Windows** ที่แสดงโฟลเดอร์เป็น tree และตารางไฟล์ ทีมจะพัฒนาต่อให้ใช้ C/POSIX ใน WSL เป็นแกนสแกนตาม syllabus พร้อมวัด Logical/Allocated จริง โหลดผลสแกนทั้งไดรฟ์แบบเบื้องหลัง และแสดงข้อมูลทีละหน้า รายละเอียดที่ถือเป็นข้อกำหนดอยู่ใน [SPEC](docs/SPEC.md); [แผนรายคน](docs/PROJECT_PLAN.md) และ [แผนนำเสนอ](docs/PRESENTATION_PLAN.md) ระบุงานที่ยังต้องทำ

## สถานะปัจจุบัน

| มีใน repository | ยังไม่เสร็จ/ยังไม่ได้ยืนยัน |
| --- | --- |
| Python server และเว็บ tree/table ที่ใช้ Win32 scanner | C/POSIX scanner ใน WSL, API งานเบื้องหลัง, pagination, cancel และผลสแกนทั้งไดรฟ์ตาม SPEC |
| โค้ดคำนวณ Logical และสูตรประมาณ Allocated/Slack | การวัด Allocated จริงจาก Windows API และการแก้ UI ไม่ให้แสดงค่าประมาณเป็นค่าจริง |
| เอกสารต้นแบบและโครงสไลด์ | ผลทดสอบปุ่ม, benchmark, รายงาน และเดโมของเวอร์ชันส่งงาน |

การที่โค้ด import ได้หรือสแกนโฟลเดอร์เล็กได้ **ยังไม่ยืนยัน** ว่าปุ่มเว็บทั้งหมดทำงานหรือสแกนทั้งไดรฟ์ได้ เอกสารเก่าใน [archive](docs/archive/HANDOFF.md) เป็นประวัติต้นแบบ ไม่ใช้เป็นหลักฐานว่าเวอร์ชันส่งงานเสร็จแล้ว

## ลองเปิดต้นแบบปัจจุบัน

บน Windows ที่ติดตั้ง Python 3.10+ ให้เปิด terminal ในโฟลเดอร์นี้แล้วรัน:

```powershell
python main.py
```

เปิด `http://localhost:8080` หาก browser ไม่เปิดอัตโนมัติ เว็บปัจจุบันโหลด Vue/Tailwind จาก CDN จึงต้องมีอินเทอร์เน็ตจนกว่างาน offline assets ในแผนจะเสร็จ **คำสั่งนี้เปิดต้นแบบ Python/Win32 ไม่ใช่เวอร์ชัน C/POSIX ตามเป้าหมาย**

## โครงสร้างงาน

```text
README.md                หน้าเริ่มต้นและสถานะ
docs/                    สเปก แผนงาน แผนนำเสนอ และเอกสารประกอบ
docs/archive/            HANDOFF ของต้นแบบเดิม
docs/reference/          สำเนาตำรา PDF ในเครื่อง (Git ignore)
backend/                 โค้ด Python/Win32 ต้นแบบ
static/                  หน้าเว็บต้นแบบ
tools/                   เครื่องมือ benchmark ต้นแบบ
main.py                  HTTP server ต้นแบบ
```

## เอกสาร

- [SPEC.md](docs/SPEC.md) — ขอบเขต สัญญาข้อมูล API ตัวเลข และเกณฑ์รับงาน
- [PROJECT_PLAN.md](docs/PROJECT_PLAN.md) — งานของสมาชิก 3 คน กำหนดส่งและหลักฐาน
- [PRESENTATION_PLAN.md](docs/PRESENTATION_PLAN.md) — สไลด์ 7 หน้า เดโม และหัวข้อรายงาน
- [DESIGN.md](docs/DESIGN.md) — อ้างอิงภาพลักษณ์เว็บ (ไม่ใช่หลักฐานฟีเจอร์)
- [CHANGELOG.md](docs/CHANGELOG.md) — ประวัติต้นแบบและสถานะงาน
- [OS_CONCEPTS_EXPLAINED.md](docs/OS_CONCEPTS_EXPLAINED.md) และ [STUDY_GUIDE.md](docs/STUDY_GUIDE.md) — เอกสารศึกษา; ให้ตรวจข้อกล่าวอ้างกับผลจริงก่อนนำเสนอ

**ขอบเขตรอบจัดเอกสาร:** ย้ายและปรับ Markdown/PDF เท่านั้น ไม่แก้ `main.py`, `backend/`, `static/` หรือ `tools/`
