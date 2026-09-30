# CoreSpace — ข้อกำหนดเวอร์ชันส่งงาน

**สถานะ:** สเปกสำหรับพัฒนาต่อ ยังไม่ใช่คำรับรองว่าโค้ดทำได้ครบ<br>
**เจ้าของการตัดสินใจ:** สมาชิกทั้ง 3 คน<br>
**วันนำเสนอที่ยืนยันแล้ว:** 9 ต.ค. 2569 เวลา 13:00 น. (5–10 นาที)<br>
**เอกสารประกอบ:** [แผนงาน](PROJECT_PLAN.md) · [แผนนำเสนอ](PRESENTATION_PLAN.md) · [คู่มือหน้าแรก](../README.md)

## 1. เป้าหมายและขอบเขต

ผู้ใช้เปิดเว็บบน Windows เลือกโฟลเดอร์หรือไดรฟ์ในเครื่อง แล้วดูโครงสร้างโฟลเดอร์ ขนาดไฟล์เชิงตรรกะ และพื้นที่ที่ไฟล์จัดสรรจริงบน Windows ได้ โปรแกรม C ใน WSL เป็นส่วนที่เดิน directory และอ่าน metadata ด้วย POSIX API ตาม syllabus; Python บน Windows ทำหน้าที่เป็นตัวเชื่อมเว็บ เก็บผล และอ่านค่าจัดสรรจริงจาก Windows API

เวอร์ชันส่งงานต้องสแกนทั้งไดรฟ์ได้แบบเบื้องหลัง แต่การสาธิตสดใช้โฟลเดอร์ย่อยที่เตรียมไว้ ผลทั้งไดรฟ์ต้องเป็นผลสแกนจริงที่เสร็จก่อนเริ่มนำเสนอ ฟีเจอร์ search, export, treemap, duplicate detector และการลบไฟล์อยู่นอกขอบเขต

### สถานะ ณ วันที่ทำสเปก

| ส่วน | มีในต้นแบบ | งานที่ยังต้องทำ |
| --- | --- | --- |
| เว็บ tree + ตาราง | มี Vue UI และ API แบบสแกนแล้วส่ง tree ก้อนเดียว | โหลดข้อมูลทีละหน้า, แสดงสถานะงาน, ปุ่มยกเลิก, ตรวจปุ่มทั้งหมด |
| Scanner | Python/Win32 แบบหลายเธรด | C/POSIX ใน WSL และสัญญาข้อมูลแบบ streaming |
| ขนาดไฟล์ | Logical จากรายการ Windows; Allocated จากสูตรประมาณ cluster | ใช้ Windows API วัด Allocated จริง, แสดง unknown/partial เมื่อวัดไม่ได้ |
| ขนาดงาน | API ตอบหลังสแกนเสร็จ | งานเบื้องหลัง ผลเก็บใน SQLite และอ่านลูกทีละหน้า |
| เอกสาร/ผลทดสอบ | มีคำอธิบายต้นแบบ | ทดสอบบนเครื่องเดโมแล้วบันทึกหลักฐานจริง |

## 2. สถาปัตยกรรมและสัญญาข้อมูล

```text
Browser (Windows)
  -> Python HTTP server (Windows, 127.0.0.1)
      -> wsl.exe -> C scanner (Linux/POSIX) -> NDJSON entries/errors
      -> Windows GetCompressedFileSizeW -> allocated bytes ของแต่ละไฟล์
      -> SQLite scan cache -> API หน้า 50 รายการ -> Browser
```

Python server ยังคงอยู่บน Windows เพื่อให้ตัวเลือกไดรฟ์และ Reveal ใน Explorer ทำงานกับ path Windows ส่วนแกนสแกนย้ายไป C/POSIX จริง ใช้ `subprocess` แบบ argument list ไม่ต่อคำสั่ง shell จาก path ของผู้ใช้ แปลง path ด้วย `wslpath` เพียงครั้งเดียวต่อการสแกน และให้ C ส่ง **relative path** เพื่อให้ Python ประกอบเป็น path Windows โดยไม่เรียก `wslpath` ต่อไฟล์

### สัญญา C scanner

คำสั่ง: `diskviz-scan --root <WSL-absolute-path> --ndjson`<br>
stdout เป็น UTF-8 NDJSON หนึ่ง record ต่อบรรทัด; stderr ใช้สำหรับ diagnostic ไม่ใช้แทน record ข้อมูล; exit code `0` = เดินครบ, `1` = ผลบางส่วน, `2` = path/argument ไม่ถูกต้อง, `130` = ยกเลิก

| Record | ฟิลด์จำเป็น | ความหมาย |
| --- | --- | --- |
| `entry` | `type`, `relativePath`, `parentRelativePath`, `name`, `kind` (`file`/`directory`/`link`), `logicalBytes` | path ภายใน root; file ใช้ `st_size`; directory และ link ใส่ 0 ก่อนรวมยอด |
| `error` | `type`, `relativePath`, `code`, `message` | สิทธิ์ไม่พอ, ไฟล์หายระหว่างสแกน หรือ I/O error; ห้ามกลืนเงียบ |
| `skipped` | `type`, `relativePath`, `reason` | symbolic link, junction/reparse point หรือ path ที่เสี่ยงวนซ้ำ |
| `done` | `type`, `fileCount`, `directoryCount`, `errorCount`, `skippedCount`, `complete` | record สุดท้ายก่อนปิด stdout; `complete=false` หากมีข้อผิดพลาด/ข้ามรายการ |

Record `entry` ของ root มี `relativePath=""`; path ย่อยใช้ `/` เป็นตัวคั่นและห้ามขึ้นต้นด้วย `/` หรือมี `..` ที่ออกนอก root ต้องตรวจเมื่อ Python รับข้อมูล ใช้ `opendir()`, `readdir()`, `lstat()`, `closedir()` ใน C และปิดทุก directory handle ตรวจ error ของ `readdir()` แยกจากจบรายการ ไม่ตามลิงก์ ติดตาม directory identity เพื่อกันวงวน และไม่เดินออกนอก volume ที่เลือก กรณี DrvFs แสดง junction ต่างจาก symlink ต้องทดสอบจริงก่อนเปิดสแกนทั้งไดรฟ์

### ความหมายของตัวเลข

| ค่า | แหล่งข้อมูล | สิ่งที่แสดง |
| --- | --- | --- |
| Logical Size | `st_size` ของ regular file จาก C/POSIX | จำนวนไบต์เนื้อหาไฟล์ตาม metadata |
| Allocated Size | `GetCompressedFileSizeW` บน Windows | ไบต์ที่ Windows รายงานว่าไฟล์ใช้บนดิสก์; ผลอาจต่ำกว่า Logical สำหรับ compressed/sparse file |
| Folder totals | รวมค่าของ regular files ที่อ่านได้ใต้โฟลเดอร์ | ยอดตาม **path ที่สแกน** ไม่ใช่ยอดใช้พื้นที่ทั้ง volume |
| Drive total/free | Windows volume API | สรุประดับไดรฟ์ แยกจากผลรวมรายการ |

ใช้ `null` สำหรับ Allocated ที่อ่านไม่ได้ และตั้ง `partial=true` ให้ไฟล์/บรรพบุรุษที่ได้รับผลกระทบ ห้ามแทนด้วย 0 หรือสูตร cluster แบบเดิม สำหรับ hard link เวอร์ชันนี้แสดงแต่ละ path และอาจนับไบต์ซ้ำในผลรวม ต้องมีข้อความอธิบายบนหน้าเว็บและรายงาน ดังนั้นห้ามเรียกผลรวมนี้ว่า “พื้นที่ใช้จริงทั้งไดรฟ์” ไม่แสดง Slack Space จาก `Allocated - Logical`: ค่านี้อาจติดลบและไม่ใช่ slack ในกรณีบีบอัดหรือ sparse file [Microsoft ระบุความหมายของ `GetCompressedFileSizeW`](https://learn.microsoft.com/en-us/windows/win32/api/fileapi/nf-fileapi-getcompressedfilesizew); [Linux อธิบาย `st_size` และ `st_blocks` แยกกัน](https://man7.org/linux/man-pages/man7/inode.7.html)

## 3. API และหน้าเว็บ

| Endpoint | สัญญาที่ต้องได้ |
| --- | --- |
| `GET /api/drives` | รายชื่อ local fixed drives, total/free, และ path Windows; ระบุ error หากอ่านไม่ได้ |
| `POST /api/scans` | รับ `{ "path": "C:\\..." }` หรือ root ไดรฟ์; ตรวจว่าเป็น local path จริง; คืน `202 { "id": "...", "state": "queued" }`; หากมีสแกนทั้งไดรฟ์กำลังทำอยู่คืน `409` |
| `GET /api/scans/{id}` | `state` = queued/running/completed/partial/cancelled/failed, counts, elapsed time, error/skipped count; ขณะสแกนยังไม่แสดงเปอร์เซ็นต์ที่ไม่ทราบตัวหาร |
| `GET /api/scans/{id}/children?parent=<relativePath>&offset=0&limit=50` | ลูกของโฟลเดอร์ที่สแกนแล้ว, `totalChildren`, `hasMore`, `partial`; จำกัด `limit` ไม่เกิน 50 และไม่ส่ง tree ทั้งก้อน |
| `POST /api/scans/{id}/cancel` | ขอหยุด process, เก็บสถานะ cancelled และผลบางส่วนให้ตรวจได้ |
| `POST /api/reveal` | เปิด Explorer เฉพาะ path ที่อยู่ในผลสแกน; คืนสถานะสำเร็จหรือข้อผิดพลาดจริง |

SQLite เป็น cache ภายในเครื่องสำหรับงานสแกน ไม่ commit ลง Git ใช้การเขียนเป็น batch และ index ตาม `(scan_id, parent_relative_path)` เพื่อโหลดลูกทีละหน้า เก็บหนึ่งผลสแกนล่าสุดต่อไดรฟ์/โฟลเดอร์ และมีคำสั่ง/ปุ่มล้างผลสแกนเก่าที่ไม่ใช่การลบไฟล์ของผู้ใช้ เซิร์ฟเวอร์ bind `127.0.0.1` เท่านั้น

Tree ฝั่งซ้ายแสดง **โฟลเดอร์**; ตารางฝั่งขวาแสดงลูกทั้งไฟล์และโฟลเดอร์ เปิด tree เริ่มต้น 2 ชั้น แต่ขยายลึกได้ตามข้อมูลจริง โหลดครั้งละ 50 และมี “แสดงเพิ่มเติม” ทั้งสองพื้นที่ เรียง Allocated จากมากไปน้อย, `null` อยู่ท้ายและใช้ชื่อเป็นตัวตัดสินลำดับเมื่อขนาดเท่ากัน ระหว่างสแกนแสดงจำนวนที่อ่านแล้วกับปุ่ม Cancel; ยอดและเปอร์เซ็นต์ของโฟลเดอร์ที่ยังไม่สรุปต้องมีป้าย “กำลังคำนวณ” ไม่แสดงเป็นยอดสุดท้าย เมื่อสแกนมี error ให้แสดงป้าย “ผลบางส่วน” พร้อมจำนวนและรายละเอียดที่เปิดดูได้

ปุ่มที่ต้องใช้งานได้: เลือกไดรฟ์, Scan, เลือก/กาง/พับโฟลเดอร์, แสดงเพิ่มเติม, Cancel และ Reveal ทุกปุ่มต้องมีสถานะกำลังทำ/สำเร็จ/ล้มเหลว หน้าเว็บต้องเปิดได้ในห้องนำเสนอโดยไม่พึ่ง CDN runtime: เก็บ Vue และ CSS ที่ใช้จริงใน `static/` พร้อมเวอร์ชันที่ระบุ

## 4. ความเร็ว ความปลอดภัย และข้อจำกัด

- เริ่มงานสแกนแล้วเว็บยังตอบสนอง; status polling ทุก 2 วินาที; หน้า tree ส่งไม่เกิน 50 รายการต่อ request งานทั้งไดรฟ์ต้องจบหรือถูกยกเลิกได้โดยไม่ทำให้ browser เก็บรายการทั้งหมดในหน่วยความจำ
- วัดเวลาสแกน จำนวนไฟล์/วินาที และ peak memory บน fixture เดียวกันกับต้นแบบ Python/Win32 และบนหนึ่งไดรฟ์ของเครื่องเดโม แยก cold/warm run ถ้ามีความต่างชัดเจน อย่าอ้าง “เร็วกว่า” จนกว่าจะมีผลวัดรองรับ
- ไม่เปิดไฟล์เพื่ออ่านเนื้อหา ไม่ลบ/ย้ายไฟล์ของผู้ใช้ ไม่สแกน network/UNC path ในเวอร์ชันส่งงาน งานที่เข้าไม่ถึงต้องนับและแสดง ไม่วนลูปจาก link/junction
- ก่อนเปิดใช้สแกนทั้งไดรฟ์ ต้องพิสูจน์บนเครื่องเดโมว่า WSL path mapping, directory identity และ cancellation ทำงานจริง หาก WSL ยังไม่พร้อม ให้ทีมจัดสภาพแวดล้อมก่อนอ้างว่าฟีเจอร์นี้เสร็จ

## 5. เกณฑ์รับงาน

1. โปรแกรม C build/run บน WSL และแสดงการใช้ POSIX API จริง พร้อมผล fixture ที่ตรวจเทียบได้
2. หน้าเว็บบน Windows เริ่มสแกนโฟลเดอร์สดได้ สแกนทั้งไดรฟ์เป็นงานเบื้องหลังได้ และยกเลิกได้โดยไม่ค้าง
3. Tree ลึกเกิน 6 ชั้นและรายการเกิน 50 ยังเข้าถึงได้ ไม่มีการตัดข้อมูลเงียบ ๆ
4. Logical/Allocated ใช้แหล่งข้อมูลตามตาราง; ค่าอ่านไม่ได้แสดง partial/unknown ไม่ใช้สูตรจำลองเป็นข้อมูลจริง
5. มีผลทดสอบปุ่ม กรณีผิดพลาด และ benchmark จากเครื่องเดโม; รายงานและสไลด์อธิบายข้อจำกัดตรงตามผลที่วัด
