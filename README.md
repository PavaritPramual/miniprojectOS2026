# CoreSpace | High-Performance OS Storage Analyzer

ระบบวิเคราะห์และตรวจสอบโครงสร้างพื้นที่จัดเก็บข้อมูล (Disk Space Analyzer) ประสิทธิภาพสูง ทำงานบนระบบปฏิบัติการ Windows โดยเชื่อมต่อโดยตรงกับ Win32 C-API และจำลองหลักการจัดสรรพื้นที่ระดับคลัสเตอร์ของระบบไฟล์ NTFS อย่างถูกต้องแม่นยำ

---

## 📌 คุณสมบัติเด่นของระบบ (Key Features)

* **TreeSize Directory Tree:** แสดงโครงสร้างโฟลเดอร์แบบแตกกิ่ง พับและกางดูโฟลเดอร์ย่อยได้ลึกไม่จำกัด (`▾` / `▸`) พร้อมแถบสัดส่วน % การใช้พื้นที่
* **OS Storage Specification:** แสดงข้อมูลขนาดเชิงตรรกะ (Logical Size), ขนาดการจัดสรรจริงบนดิสก์ (Physical / Size on Disk), และพื้นที่หย่อนที่สูญเปล่าจาก Internal Fragmentation (Slack Space)
* **NTFS Resident File Handling:** คำนวณขนาดอย่างถูกต้องสำหรับไฟล์ขนาดเล็ก ($\le 600$B) ที่ถูกฝังในระเบียน Master File Table ($MFT) โดยไม่คิดขนาดคลัสเตอร์ภายนอก
* **Reparse Point Safety Gate:** ตรวจจับ Directory Junctions และ Symbolic Links ป้องกันการเกิดวงวนไม่สิ้นสุด (Circular Infinite Loops)
* **High-Speed Concurrency:** สแกนโฟลเดอร์คู่ขนานด้วย Producer-Consumer Work Queue ผลักดันค่า Queue Depth ($QD > 1$) บนอุปกรณ์ความเร็วสูง NVMe SSD
* **Reveal in Windows Explorer:** สั่งให้ระบบปฏิบัติการเปิด Windows File Explorer พร้อมไฮไลต์ไฟล์หรือโฟลเดอร์เป้าหมายได้โดยตรงจากหน้าเว็บ
* **Zero-Dependency Setup:** พัฒนาด้วย Python 3 Standard Library ทั้งหมด ไม่ต้องติดตั้งแพ็กเกจภายนอก ไม่ต้องติดตั้ง Node.js หรือ npm

---

## 🏗️ สถาปัตยกรรมระบบ (System Architecture)

ระบบถูกออกแบบด้วยสถาปัตยกรรม **Lightweight Single-Process Architecture** แบ่งการทำงานออกเป็น 2 ชั้นหลัก:

```text
┌────────────────────────────────────────────────────────┐
│  Frontend: Browser Client                              │
│  - Framework: Vue 3 (Reactive State via CDN)           │
│  - Design System: Tavily Warm Paper Palette            │
│  - Components: TreeItem Recursive Sidebar, Specs Grid  │
└──────────────────────────┬─────────────────────────────┘
                           │ JSON over HTTP
┌──────────────────────────▼─────────────────────────────┐
│  Backend: Python 3 Standard Library                    │
│  - Server: http.server.ThreadingHTTPServer             │
│  - Endpoints: /api/drives, /api/scan, /api/reveal      │
├────────────────────────────────────────────────────────┤
│  Core OS Engine:                                       │
│  - Win32 C-API: FindFirstFileExW (LARGE_FETCH 64KB)    │
│  - Geometry: GetDiskFreeSpaceW (Cluster Size)          │
│  - Concurrency: Thread-safe Producer-Consumer Queue    │
│  - Memory: Compact Node Representation (__slots__)     │
└────────────────────────────────────────────────────────┘
```

---

## 📂 โครงสร้างโฟลเดอร์ (Project Structure)

```text
├── backend/
│   ├── __init__.py        # แพ็กเกจโมดูลระบบหลังบ้าน
│   ├── win32_api.py       # Ctypes Wrapper สำหรับเรียก Win32 C-API (FindFirstFileExW, GetDiskFreeSpaceW)
│   ├── os_storage.py      # ฟังก์ชันคำนวณ Cluster Size, Slack Space และ NTFS Resident Files
│   ├── scanner.py         # เอนจินสแกนไดเรกทอรีแบบมัลติเธรด (Producer-Consumer Queue)
│   ├── arena.py           # โครงสร้าง Compact Node ในหน่วยความจำ (__slots__ 32-64 bytes)
│   └── aggregator.py      # จัดเตรียมโครงสร้างข้อมูลสำหรับ TreeSize Sidebar และ Table
├── static/
│   ├── index.html         # โครงสร้างหน้าเว็บหลักและ UI Layout (Vue 3 + Tailwind CDN)
│   ├── app.js             # Logic ควบคุม Vue 3 App, Tree Component, และ API calls
│   └── style.css          # Design Tokens ตามมาตรฐาน Tavily Warm Paper
├── tools/
│   └── benchmark.py       # สคริปต์ CLI สำหรับทดสอบวัดความเร็วการสแกนผ่าน Terminal
├── main.py                # จุดเริ่มต้นระบบ (Entry Point) รันเซิร์ฟเวอร์และเปิดเบราว์เซอร์
├── CHANGELOG.md           # ประวัติการพัฒนาและแผนงานฟีเจอร์ในอนาคต (Roadmap)
├── DESIGN.md              # ข้อกำหนดระบบดีไซน์ (Tavily Design System Specification)
└── .gitignore             # ตัวกรองไฟล์ที่ไม่เกี่ยวข้องกับ Git
```

---

## 🚀 วิธีการเริ่มต้นใช้งาน (Getting Started)

### ความต้องการของระบบ
* ระบบปฏิบัติการ: Windows 10 หรือ Windows 11
* สภาพแวดล้อม: Python 3.10 ขึ้นไป (ไม่ต้องติดตั้งโมดูลภายนอกเพิ่มเติม)

### 1. การรันระบบ Web Application
เปิด PowerShell หรือ Command Prompt ในโฟลเดอร์โปรเจกต์ แล้วสั่งรัน:

```bash
python main.py
```

เมื่อเซิร์ฟเวอร์เริ่มทำงาน ระบบจะเปิดหน้าต่างเว็บเบราว์เซอร์ขึ้นมาให้อัตโนมัติที่:
```text
http://localhost:8080
```

---

## 🖥️ คู่มือการใช้งานหน้าเว็บ (User Guide)

```text
┌─────────────────────────────────────────────────────────────────────────────────┐
│  /corespace       [Drive: C:\ ▼]  [Path: C:\Users\Downloads ]   ( Scan Folder ) │
├──────────────────────────┬──────────────────────────────────────────────────────┤
│  /directory-tree         │  /selected-folder: C:\Users\Downloads                │
│  ▾ C:\ (246.2 GB)   100% │  ┌──────────┬──────────┬──────────┬──────────┐       │
│    ▾ Users (182.4 GB)74% │  │ Logical  │ On Disk  │ Slack    │ Files    │       │
│      ▸ Saran (85.2 GB)   │  │ 45.2 GB  │ 47.1 GB  │ 1.9 GB   │ 12,450   │       │
│      ▾ Pawarit (62.0 GB) │  └──────────┴──────────┴──────────┴──────────┘       │
│        ▸ Documents       │                                                      │
│        ▾ Downloads <sel> │  /contents-specification                             │
│          ▸ Videos        │  Name        | % of Folder | Size     | Action       │
│          ▸ Compressed    │  📁 Videos   | [=====] 66% | 30.1 GB  | [Reveal]     │
│      ▸ Theerameth        │  📁 Compress | [==   ] 22% | 10.0 GB  | [Reveal]     │
│                          │  📄 file.iso | [=    ] 12% |  5.1 GB  | [Reveal]     │
└──────────────────────────┴──────────────────────────────────────────────────────┘
```

1. **เลือกไดรฟ์หรือโฟลเดอร์ที่ต้องการตรวจสอบ:**
   * เลือกไดรฟ์ที่ต้องการจากเมนู **Drive** (เช่น `C:\`, `D:\`)
   * หรือพิมพ์เส้นทางโฟลเดอร์ที่ต้องการลงในช่อง **Path** (เช่น `C:\Users\User\Downloads`)
2. **เริ่มการสแกน:**
   * กดปุ่ม **Scan Folder** (ระบบจะประมวลผลด้วยมัลติเธรดแบบคู่ขนานอัตโนมัติ)
3. **การสำรวจโครงสร้างผ่าน Directory Tree (ฝั่งซ้าย):**
   * คลิกที่สัญลักษณ์ `▾` หรือ `▸` หน้าชื่อโฟลเดอร์เพื่อพับหรือกางดูโฟลเดอร์ย่อย
   * คลิกที่ชื่อโฟลเดอร์ใดๆ เพื่อเลือกโฟลเดอร์นั้นเป็นโฟลเดอร์หลักในการดูรายละเอียด
4. **การดูสถิติและสเปกของโฟลเดอร์ (ฝั่งขวาบน):**
   * **Logical Size (EOF):** ขนาดเนื้อหาจริงของไฟล์ทั้งหมดรวมกัน
   * **Size on Disk (Physical):** พื้นที่บล็อกคลัสเตอร์จริงที่ระบบไฟล์จับจองบนดิสก์
   * **Slack Space (Waste):** พื้นที่สูญเปล่าจากความกระจัดกระจายภายใน (Internal Fragmentation)
   * **Total Items:** จำนวนไฟล์และโฟลเดอร์ย่อยทั้งหมดที่บรรจุอยู่ข้างใน
   * **Cluster Size:** ขนาดหน่วยจัดสรรข้อมูลพื้นฐานของไดรฟ์ (NTFS ปกติคือ 4,096 ไบต์)
5. **การดูรายการไฟล์ย่อยและการเปิดใน Windows Explorer:**
   * ตาราง **Subfolders & Files Details** จะแจกแจงรายการข้างใน พร้อมแถบแสดงเปอร์เซ็นต์สัดส่วน
   * คลิกปุ่ม **Reveal** เพื่อสั่งให้ Windows Explorer เด้งเปิดหน้าต่างชี้ไปยังไฟล์หรือโฟลเดอร์นั้นทันที

---

## 🛠️ เครื่องมือทดสอบความเร็วผ่าน Command Line (CLI Tool)

สามารถรันสคริปต์ทดสอบในโฟลเดอร์ `tools/` เพื่อวัดความเร็วการสแกนของไดรฟ์ได้โดยตรง:

```bash
python tools/benchmark.py <path_to_folder>
```
*ตัวอย่าง:*
```bash
python tools/benchmark.py C:\Users
```

---

## 🐧 การเชื่อมโยงทฤษฎีระบบปฏิบัติการและ POSIX Mapping (OS Concepts Alignment)

โปรเจกต์นี้ตอบโจทย์ข้อกำหนดของรายวิชา Operating Systems โดยครอบคลุมทั้งแนวคิดเชิงทฤษฎีและการประยุกต์ใช้งานจริงในระดับ System Calls:

| สาระการเรียนรู้ในวิชา OS | มาตรฐาน POSIX System Calls (Unix/Linux) | คำสั่ง Win32 API ที่ใช้ใน CoreSpace | กลไกในระบบปฏิบัติการ |
| :--- | :--- | :--- | :--- |
| **Directory Traversal** | `opendir()`, `readdir()`, `closedir()` | `FindFirstFileExW()`, `FindNextFileW()` | การสลับโหมดข้าม User/Kernel เพื่ออ่านไดเรกทอรี |
| **File Logical Size** | `lstat() -> st_size` | `(nFileSizeHigh << 32) \| nFileSizeLow` | ดึงขนาดของเนื้อไฟล์จริง (End of File) |
| **Physical Allocation** | `lstat() -> st_blocks * 512` | `Cluster Size * ceil(Size / Cluster Size)` | คำนวณขนาดคลัสเตอร์จริงบนฮาร์ดแวร์จัดเก็บข้อมูล |
| **Filesystem Geometry** | `statvfs() -> f_blocks, f_bavail` | `GetDiskFreeSpaceExW()`, `GetDiskFreeSpaceW()` | ดึงข้อมูลความจุ คลัสเตอร์ และพื้นที่ว่างของระบบไฟล์ |
| **Cycle & Loop Safety** | `S_ISLNK(st_mode)` | `FILE_ATTRIBUTE_REPARSE_POINT (0x400)` | ป้องกัน Infinite Recursion จาก Junctions/Symlinks |
| **Concurrency / Worker**| `pthread_create()`, `pthread_join()` | Producer-Consumer Worker Queue (Multi-threading) | ผลักดัน Queue Depth ($QD > 1$) ดึงประสิทธิภาพ NVMe |

> เอกสารประกอบการเรียนรู้และคู่มือเตรียมสอบสัมภาษณ์ฉบับเต็ม สามารถศึกษาเพิ่มเติมได้ที่:
> - [`OS_CONCEPTS_EXPLAINED.md`](./OS_CONCEPTS_EXPLAINED.md) — คำอธิบายทฤษฎี OS เชิงลึกพร้อมอภิธานศัพท์
> - [`STUDY_GUIDE.md`](./STUDY_GUIDE.md) — คู่มือเตรียมตัวนำเสนอและแบ่งหน้าที่สมาชิกกลุ่ม
> - [`HANDOFF.md`](./HANDOFF.md) — เอกสารส่งมอบโครงการและแผนงาน

