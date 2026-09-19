# 📋 CoreSpace Project Documentation & Changelog

เอกสารบันทึกประวัติการพัฒนา สถาปัตยกรรมระบบ และแผนการอัปเดตฟีเจอร์ในอนาคต (Roadmap)

---

## 📦 Version 1.0.0 (Current Release)

### 1. ระบบหลังบ้านและวิศวกรรมระบบปฏิบัติการ (Backend & OS Core)
- [x] **Win32 Low-Level C-API (`backend/win32_api.py`):**
  - เชื่อมต่อ `FindFirstFileExW` ผ่าน `ctypes` พร้อมเปิดแฟล็ก `FIND_FIRST_EX_LARGE_FETCH` (บัฟเฟอร์ในเคอร์เนล 64KB) เพื่อลด Context Switches (Ring 3 $\leftrightarrow$ Ring 0)
  - เปิดใช้งาน `FindExInfoBasic` ข้ามการสืบค้นชื่อไฟล์สั้นแบบ 8.3 ช่วยลดภาระการทำงานของไดรเวอร์ระบบไฟล์
  - เรียกใช้ `GetDiskFreeSpaceW` ดึงค่าเรขาคณิตคลัสเตอร์จริง (BytesPerSector $\times$ SectorsPerCluster) สำหรับคำนวณการจัดสรรพื้นที่
  - ดึงรายชื่อและสถานะความจุของทุก Logical Drive บนระบบผ่าน `GetLogicalDriveStringsW` และ `GetDiskFreeSpaceExW`
- [x] **การคำนวณพื้นที่จัดเก็บข้อมูลระดับ OS (`backend/os_storage.py`):**
  - คำนวณความต่างระหว่าง **Logical File Size** (ขนาดข้อมูลจริง) และ **Physical Size on Disk** (ขนาดการจองคลัสเตอร์)
  - คำนวณ **Internal Fragmentation (Slack Space)**: $S_{slack} = S_{physical} - S_{logical}$
  - รองรับกลไก **NTFS Resident Files**: ไฟล์ขนาด $\le 600$ ไบต์ถูกฝังใน Master File Table ($MFT) โดยตรง ทำให้ขนาดจัดสรรภายนอกดิสก์คิดเป็น 0 ไบต์อย่างถูกต้อง
- [x] **ระบบสแกนแบบมัลติเธรดไร้ Deadlock (`backend/scanner.py`):**
  - ใช้ **Producer-Consumer Work Queue** (`queue.Queue` + Worker Threads) กระจายงานสำรวจโฟลเดอร์แบบคู่ขนาน ดันค่า Queue Depth ($QD > 1$) บนอุปกรณ์จัดเก็บข้อมูลความเร็วสูง NVMe SSD
  - มี **Reparse Point Safety Gate**: ดักจับบิตแฟล็ก `FILE_ATTRIBUTE_REPARSE_POINT` (0x400) เพื่อตัด Directory Junctions และ Symbolic Links ออก ป้องกันปัญหา Circular Infinite Loop
- [x] **โครงสร้างหน่วยความจำแบบประหยัด (`backend/arena.py`):**
  - ออกแบบ `CompactFileNode` โดยใช้ `__slots__` ลดหน่วยความจำอ็อบเจกต์ในไพทอน ทำให้การสแกนไฟล์หลักแสนใช้ RAM ไม่เกิน 50MB
  - ทำการคำนวณสะสมขนาดแบบ Bottom-Up (Post-Order Traversal Rollup)
- [x] **Zero-Dependency Server (`main.py`):**
  - ใช้ `http.server.ThreadingHTTPServer` ให้บริการทั้งหน้าเว็บและ JSON REST API (`/api/drives`, `/api/scan`, `/api/reveal`) รันผ่าน Python 3 Standard Library ตัวเดียว ไม่ต้องพึ่งพาแพ็กเกจภายนอก

### 2. ระบบส่วนหน้าและส่วนต่อประสานผู้ใช้ (Frontend & UI/UX)
- [x] **TreeSize Interactive Sidebar (`static/index.html`, `static/app.js`):**
  - พัฒนาด้วย **Vue 3 (ผ่าน CDN)** ไม่ต้องใช้ Node.js หรือ build step
  - ใช้ **Recursive Tree Component** สำหรับ Directory Tree ฝั่งซ้าย พับและกางกิ่งโฟลเดอร์ได้ลึกไม่จำกัด (`▾` / `▸`)
  - ซิงค์ข้อมูลอัตโนมัติ: เมื่อคลิกเลือกโฟลเดอร์ใดใน Sidebar ข้อมูลฝั่งขวาจะสลับไปแสดงรายละเอียดของโฟลเดอร์นั้นทันที
- [x] **Contents Specification Table:**
  - แสดงรายชื่อโฟลเดอร์ย่อยและไฟล์ พร้อมแถบ mini % of parent, ขนาดจริง, ขนาดบนดิสก์, จำนวนไอเทม
  - ฟังก์ชัน **Reveal in Explorer**: กดปุ่มแล้วสั่งให้ Windows Explorer เด้งเปิดโฟลเดอร์จริงพร้อมไฮไลต์ไฟล์นั้น
- [x] **Tavily Warm Paper Design System (`static/style.css`):**
  - สีพื้นหลัง Canvas: ครีมกระดาษอุ่น (`#fefcf5`)
  - การ์ดและคอนเทนเนอร์: สีขาวอุ่น (`#fffcf6`) พร้อมเส้นขอบบาง 1px (`rgba(11, 9, 7, 0.1)`) ไร้เงาหนา
  - ตัวหนังสือ: สีเข้มอุ่น (`#3c3a39`)
  - เอกลักษณ์ **`/slash-prefix` Mono Eyebrows** (เช่น `/directory-tree`, `/selected-folder`, `/contents-specification`)

---

## 🔮 แผนการอัปเดตฟีเจอร์ในอนาคต (Future Roadmap)

| ระยะการพัฒนา | ฟีเจอร์ที่วางแผนไว้ | รายละเอียดเชิงเทคนิค |
| :--- | :--- | :--- |
| **v1.1.0** | **Search & Quick Filter** | ช่องค้นหาชื่อไฟล์แบบเรียลไทม์ และปุ่มกรองตามนามสกุล (.mp4, .zip, .pdf, .py) ในตาราง |
| **v1.2.0** | **Export Report** | ปุ่มส่งออกข้อมูลโครงสร้างและขนาดพื้นที่ของโฟลเดอร์ที่เลือกเป็นไฟล์ CSV หรือ JSON |
| **v1.3.0** | **Polished Visual Treemap** | ออกแบบ Treemap หรือ Sunburst Chart ใหม่ในสไตล์มินิมอลที่เข้ากับ Tavily Warm Paper อย่างประณีต |
| **v1.4.0** | **Duplicate & Temp File Detector** | อัลกอริทึมตรวจจับไฟล์ซ้ำ (Duplicate Finder) และระบบระบุไฟล์ขยะชั่วคราว (Temp/Cache files) |
| **v1.5.0** | **Direct MFT Parser Engine (Optional)** | โหมดทางเลือกแบบต้องการสิทธิ์ Administrator เพื่ออ่าน `$MFT` ดิบระดับดิสก์สำหรับเปรียบเทียบ |
