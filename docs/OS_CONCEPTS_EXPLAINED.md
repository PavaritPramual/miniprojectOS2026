# ความรู้ OS ที่ใช้ใน CoreSpace

**สถานะ:** คู่มือศึกษาเพื่อทำงานและเตรียมตอบคำถาม ไม่ใช่ผลทดสอบ<br>
**สเปกงาน:** [SPEC.md](SPEC.md)<br>
**บันทึกทฤษฎีของต้นแบบเดิม:** [OS_CONCEPTS_PROTOTYPE.md](archive/OS_CONCEPTS_PROTOTYPE.md)

Syllabus ของวิชาเน้น C/POSIX ใน Linux และงาน Mini Project แบบ system-level tool หัวข้อที่ตรงกับ CoreSpace มากที่สุดคือ system calls (สัปดาห์ 2), file system/metadata (สัปดาห์ 12), directory/permissions (สัปดาห์ 13) และ I/O (สัปดาห์ 14) เรื่อง threads (สัปดาห์ 5–6) เป็นทางเลือกเมื่อวัดแล้วว่าจำเป็นต่อความเร็ว

## 1. System-level tool และเส้นทางข้อมูล

CoreSpace ขอข้อมูลโครงสร้างไฟล์จาก OS แล้วสรุปเป็น tree จึงเป็น system-level tool ส่วน C scanner ต้องเรียก POSIX API จริง เช่น `opendir()`, `readdir()`, `lstat()` และ `closedir()` โดยตรวจค่าที่คืนและ `errno` ไม่ถือว่าการเรียก Python/Win32 ของต้นแบบเทียบเท่าการลงมือเขียน C/POSIX ตาม syllabus

```text
Browser Windows -> Python bridge -> C/POSIX ใน WSL -> directory metadata
                               └── Windows API -> allocated bytes ของไฟล์ Windows
```

Python จัดการ HTTP, สถานะงานและผลสแกน; C เป็นผู้เดิน directory; Windows API วัดค่าที่เป็นคุณสมบัติของไฟล์ Windows การแยกหน้าที่นี้ต้องอธิบายในรายงานอย่างตรงไปตรงมา

## 2. Directory tree และ metadata

| แนวคิด | ใช้อย่างไร |
| --- | --- |
| `opendir()` / `readdir()` | เปิดและอ่านรายการลูกของโฟลเดอร์; `readdir()` คืน `NULL` ได้ทั้งจบรายการและ error จึงต้องตรวจ `errno` |
| `lstat()` | อ่านชนิดและขนาดของรายการโดยไม่ตาม symbolic link; regular file ใช้ `st_size` เป็น Logical Size |
| Directory traversal | เดินรายการย่อยและรวมขนาดกลับขึ้น parent; tree บนเว็บเปิดดูได้ทีละชั้น |
| Permissions / I/O errors | รายการที่เข้าไม่ได้ต้องนับและแสดง “ผลบางส่วน”; ห้ามถือว่าเท่ากับ 0 ไบต์ |
| Link / junction | ไม่ตาม symbolic link และต้องทดสอบ junction จริงบน `/mnt/c`/`/mnt/d` เพื่อป้องกันวงวน |

ตัวเลข `st_blocks` ของ Linux รายงานบล็อกที่ filesystem จัดสรร แต่หน่วยและความหมายต้องดู filesystem ที่อ่านจริง สำหรับไฟล์ Windows ผ่าน WSL งานนี้จึงใช้ Windows API วัด Allocated Size แยกจาก `st_size` ของ POSIX [Linux man-pages: inode fields](https://man7.org/linux/man-pages/man7/inode.7.html)

## 3. Logical, Allocated และข้อควรระวัง

- **Logical Size:** จำนวนไบต์เนื้อหาไฟล์ตาม metadata (`st_size`) ไฟล์ว่างมีค่า 0
- **Allocated Size:** จำนวนไบต์ที่ Windows รายงานว่าไฟล์ใช้บนดิสก์ผ่าน `GetCompressedFileSizeW`; compressed/sparse file อาจใช้พื้นที่น้อยกว่า Logical [Microsoft Learn](https://learn.microsoft.com/en-us/windows/win32/api/fileapi/nf-fileapi-getcompressedfilesizew)
- **ยอดโฟลเดอร์:** ผลรวมไฟล์ที่เดินได้ใต้ path นั้น ไม่รวมทุกโครงสร้าง metadata ของ volume และอาจนับ hard link ซ้ำตาม path จึงไม่ควรเทียบเป็นยอดใช้พื้นที่ทั้งหมดของไดรฟ์
- **ค่าที่อ่านไม่ได้:** ต้องเป็น `unknown`/`partial`; การปัดขนาดไฟล์ขึ้นตาม cluster คงที่หรือสมมติว่าไฟล์ต่ำกว่า 600 ไบต์เป็น resident เสมอ เป็นแบบจำลองของต้นแบบ ไม่ใช่ผลวัดจริง
- **Slack:** `Allocated - Logical` ไม่ใช่ slack ในทุกกรณี โดยเฉพาะ compression และ sparse data เวอร์ชันส่งงานจึงไม่แสดงการ์ด Slack Space จากสูตรนี้

## 4. I/O และความเร็ว

การเดินไฟล์ทั้งไดรฟ์อาจช้าเพราะต้องอ่าน metadata จำนวนมากผ่าน WSL และ Windows filesystem การมีหลายเธรดไม่ได้รับประกันว่าเร็วขึ้น จึงต้องวัดบน fixture เดียวกันและไดรฟ์เดโมจริงก่อนกล่าวอ้าง ผลที่ทีมต้องเก็บคือเวลาสแกน จำนวนรายการ/วินาที และ peak memory แยกจากเวลาโต้ตอบของหน้าเว็บ

เว็บควรเริ่มงานเบื้องหลัง คืนสถานะทุก 2 วินาที และอ่านข้อมูลทีละ 50 รายการ เพื่อให้ผู้ใช้ยังใช้เว็บได้ระหว่างสแกน หากความเร็วแกนสแกนไม่ดีพอ ให้ profiling แล้วค่อยตัดสินใจเรื่อง worker threads แบบมีจำนวนจำกัด ไม่มีเป้าหมาย “60 FPS”, “RAM < 50 MB” หรือ “QD > 1” ที่ถือว่าผ่านโดยไม่มีผลวัด

## 5. คำตอบที่ควรซ้อม

**ทำไมต้องใช้ C/POSIX ทั้งที่เว็บอยู่บน Windows?** เพราะเงื่อนไขวิชาต้องการโปรแกรม C ที่ใช้ POSIX APIs ใน Linux; WSL ให้สภาพแวดล้อม Linux ส่วน browser/Python เป็นส่วนแสดงผลและเชื่อมข้อมูล

**ทำไมยอดของ tree ไม่เท่าพื้นที่ใช้ของไดรฟ์?** tree รวมไฟล์ที่สแกนได้ตาม path เท่านั้น อาจมีไฟล์เข้าไม่ถึง, hard links, metadata ของ filesystem และข้อมูลนอก root ที่เลือก ข้อมูลความจุไดรฟ์เป็นคนละตัววัด

**รู้ได้อย่างไรว่าเร็ว?** แสดงผล benchmark ที่วัดบนเครื่องเดโมพร้อมจำนวนรายการและเงื่อนไขการวัด ไม่อ้างจากชื่อ API หรือจำนวนเธรด

**ถ้าสแกนไม่ครบ?** หน้าเว็บแสดง `partial` พร้อมจำนวน error/skipped และรายงานอธิบายผลกระทบต่อยอดรวม ไม่มีการแสดง 0 แทนค่าที่ไม่ทราบ
