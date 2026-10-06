# 📋 เอกสารส่งมอบงานโครงการ (Project Handoff Document)

> **เอกสารเก็บประวัติต้นแบบ:** ไฟล์นี้บรรยายระบบ Python/Win32 เดิมและมีข้อกล่าวอ้างด้านความเร็ว/ความแม่นยำที่ยังไม่ได้ยืนยัน ไม่ใช่สเปกหรือสถานะเวอร์ชันส่งงาน ให้ใช้ [SPEC ปัจจุบัน](../SPEC.md), [แผนพัฒนา](../PROJECT_PLAN.md) และผลทดสอบจริงแทน
# โครงการ: CoreSpace — High-Performance OS Storage Analyzer

> **วิชา:** Operating Systems (Mini-Project)  
> **วันนำเสนอ:** 9 ตุลาคม 2569 (13:00 น.) | เวลาบรรยาย 5–10 นาที  
> **กลุ่ม:** ผู้ก้าวข้ามโชคชะตาด้วยมือของตัวเอง  
> **สมาชิกกลุ่ม:**  
> 1. นายศรัณย์ พาพรชัย (673380515-1) — Backend Engine & Win32 Concurrency  
> 2. นายปวริศช์ ประมวล (673380278-9) — OS Storage Mechanics & Slack Space Calculation  
> 3. นายธีรเมธ สายคำ (673380273-9) — Frontend UI, TreeSize Model & Presentation Delivery  

---

## 1. บทสรุปโครงการ (Executive Summary)

**CoreSpace** เป็นระบบวิเคราะห์และจำลองการจัดสรรพื้นที่จัดเก็บข้อมูล (Disk Space Analyzer) ประสิทธิภาพสูงบนระบบปฏิบัติการ Windows พัฒนาขึ้นโดยมีเป้าหมายเพื่อตอบโจทย์วิชา Operating Systems โดยเฉพาะ:
- **ไม่ใช่เพียงแค่การคำนวณขนาดไฟล์ทั่วไป** แต่สะท้อนกลไกการทำงานระดับล่างของระบบไฟล์ (NTFS), สถาปัตยกรรมเคอร์เนล (Ring 3 $\leftrightarrow$ Ring 0), การจัดสรรหน่วยข้อมูล (Cluster Allocation), และการทำงานแบบขนาน (Concurrency) บนอุปกรณ์จัดเก็บข้อมูลความเร็วสูง NVMe SSD
- **สถาปัตยกรรมแบบ Zero-Dependency:** พัฒนาด้วย Python 3 Standard Library ผสานกับ Vue 3 (via CDN) ไม่ต้องติดตั้ง Node.js, npm หรือ pip packages เพิ่มเติม รันคำสั่งเดียว `python main.py` สามารถเปิดใช้งานได้ทันทีบนทุกเครื่องของสมาชิกในกลุ่ม

---

## 2. สถาปัตยกรรมระบบและเทคโนโลยี (Architecture & Tech Stack)

### 2.1 Backend Layer (Python 3.11+ Standard Library)
* **Server:** `http.server.ThreadingHTTPServer` รองรับการทำงานแบบ Multi-threaded ให้บริการทั้ง Static UI และ JSON REST API (`/api/drives`, `/api/scan`, `/api/reveal`)
* **Kernel & Low-Level API Interop (`backend/win32_api.py`):**
  * เรียกใช้ Win32 C-API ผ่าน `ctypes` โดยตรง ซึ่งจะ **ปลดล็อก Python GIL (Global Interpreter Lock)** ขณะรอ I/O
  * `FindFirstFileExW` ร่วมกับแฟล็ก `FIND_FIRST_EX_LARGE_FETCH` (ขยายบัฟเฟอร์ในเคอร์เนลเป็น 64KB) และ `FindExInfoBasic` (ข้ามการอ่านชื่อสั้น 8.3 DOS Names) ช่วยลด User-to-Kernel Mode Context Switches
  * `GetDiskFreeSpaceW` ดึงค่า Cluster Geometry จริงของแต่ละไดรฟ์
  * `GetDiskFreeSpaceExW` และ `GetLogicalDriveStringsW` ตรวจสอบความจุและสถานะของไดรฟ์ทั้งหมด
* **Concurrency Engine (`backend/scanner.py`):**
  * ใช้โมเดล **Producer-Consumer Work Queue** (`queue.Queue` + Worker Threads)
  * ไร้ปัญหา Deadlock 100% เพราะไม่มีการรอ Future ซ้อน Future
  * ส่งคำสั่งอ่านไฟล์แบบคู่ขนาน ช่วยผลักดันค่า **Queue Depth ($QD > 1$)** บนคอนโทรลเลอร์ของ NVMe SSD
  * **Reparse Point Safety Gate:** ดักจับบิตแฟล็ก `FILE_ATTRIBUTE_REPARSE_POINT` (0x400) เพื่อตัด Directory Junctions และ Symbolic Links ป้องกันวงวนไม่สิ้นสุด (Infinite Recursion Loop)
* **OS Storage Mechanics (`backend/os_storage.py`):**
  * คำนวณความต่างระหว่าง **Logical Size (EOF)** และ **Physical Size on Disk (Cluster Allocation)**
  * คำนวณ **Internal Fragmentation (Slack Space)**: $S_{slack} = S_{physical} - S_{logical}$
  * ตรวจจับ **NTFS Resident Files:** ไฟล์ขนาด $\le 600$ ไบต์ ถูกฝังในระเบียน Master File Table ($MFT) โดยตรง ทำให้ขนาด Physical บนคลัสเตอร์ภายนอกคิดเป็น 0 ไบต์อย่างถูกต้อง
* **Memory Optimization (`backend/arena.py`):**
  * โครงสร้าง `CompactFileNode` ใช้ `__slots__` เพื่อลดหน่วยความจำอ็อบเจกต์ในไพทอน สแกนไฟล์หลักแสนรายการโดยใช้ RAM ต่ำกว่า 50MB

### 2.2 Frontend Layer (Single Page Application via CDN)
* **Framework:** **Vue 3 (via CDN)** ไม่ต้องมี Node.js หรือ build step
* **UI Pattern:** **TreeSize Model**
  * ฝั่งซ้าย: **Directory Tree Sidebar** แบบแตกกิ่ง พับ/กางได้ (`▾` / `▸`) มี mini % bar และไอคอน
  * ฝั่งขวา: **Folder Specs Cards** แสดงสเปกเชิงลึก (Logical, Physical, Slack, Items, Cluster Size)
  * ตาราง **Contents Specification Table:** แจกแจงไฟล์และโฟลเดอร์ย่อย พร้อมปุ่ม **Reveal in Explorer** (สั่งเปิด Windows File Explorer ชี้หาไฟล์จริงผ่าน `POST /api/reveal`)
* **Design System (`static/style.css`, `DESIGN.md`):**
  * ถอดแบบมาจาก **Tavily Warm Editorial Paper Palette**
  * พื้นหลังกระดาษครีมอุ่น `#fefcf5`, การ์ดสีขาวอุ่น `#fffcf6`, เส้นขอบ 1px `rgba(11, 9, 7, 0.1)`, ตัวหนังสือ `#3c3a39`, ปุ่ม Dark Pill ทรงรี, และ `/slash-prefix` Mono Eyebrows

---

## 3. โครงสร้างโฟลเดอร์และไฟล์ (File & Folder Inventory)

```text
D:\673380278-9\2569\OS\project\
├── backend/                           # โค้ดระบบหลังบ้านและ Win32 OS Interop
│   ├── __init__.py                    # กำหนดความเป็น Python Package
│   ├── win32_api.py                   # Ctypes Wrapper: FindFirstFileExW, GetDiskFreeSpaceW
│   ├── os_storage.py                  # คำนวณ Cluster, Slack Space, Resident Files, หมวดหมู่ไฟล์
│   ├── scanner.py                     # Producer-Consumer Multi-threaded Scanner
│   ├── arena.py                       # โครงสร้างหน่วยความจำ Compact Node (__slots__)
│   └── aggregator.py                  # จัดโครงสร้างข้อมูลสำหรับ Sidebar และ Table
├── static/                            # ทรัพยากรหน้าเว็บ (Frontend)
│   ├── index.html                     # HTML Layout หลัก + Vue 3 App Template
│   ├── app.js                         # Vue 3 Reactive State, Recursive TreeItem Component
│   └── style.css                      # Design Tokens สไตล์ Tavily Warm Paper
├── tools/                             # สคริปต์เครื่องมือเสริม
│   └── benchmark.py                   # CLI Benchmark เปรียบเทียบความเร็วผ่าน Terminal
├── main.py                            # Entry Point หลัก: รัน HTTP Server และเปิดเบราว์เซอร์
├── README.md                          # หน้าเริ่มต้นของ repository
├── docs/                              # สเปก แผน และเอกสารประกอบ
│   ├── SPEC.md                        # ข้อกำหนดเวอร์ชันส่งงาน
│   ├── PROJECT_PLAN.md                # แผนงานทีม
│   ├── PRESENTATION_PLAN.md           # แผนนำเสนอ
│   ├── CHANGELOG.md                   # ประวัติ/สถานะ
│   ├── OS_CONCEPTS_EXPLAINED.md       # เอกสารศึกษา
│   ├── STUDY_GUIDE.md                 # คู่มือศึกษา
│   ├── DESIGN.md                      # อ้างอิงภาพลักษณ์
│   ├── archive/HANDOFF.md             # เอกสารเก็บประวัติฉบับนี้
│   └── reference/Emailing Abraham-Silberschatz...pdf # สำเนาตำราในเครื่อง (Git ignore)
└── .gitignore                         # ตัวกรองไฟล์แคชและไฟล์ที่ไม่เกี่ยวข้อง
```

---

## 4. วิธีการติดตั้งและรันระบบ (How to Run & Verify)

### ข้อกำหนดขั้นต่ำ
- **ระบบปฏิบัติการ:** Windows 10 หรือ Windows 11
- **โปรแกรมที่ต้องมี:** Python 3.10 ขึ้นไป (ติดตั้งแบบเพิ่มเข้า PATH)

### ขั้นตอนการรัน
1. เปิด Terminal หรือ PowerShell ในโฟลเดอร์โครงการ:
   ```powershell
   cd D:\673380278-9\2569\OS\project
   ```
2. รันแอปพลิเคชัน:
   ```powershell
   python main.py
   ```
3. ระบบจะสตาร์ต HTTP Server ที่พอร์ต `8080` และเปิดเว็บเบราว์เซอร์อัตโนมัติไปที่:
   ```text
   http://localhost:8080
   ```
4. เลือก Drive หรือระบุ Path ที่ต้องการ แล้วกดปุ่ม **Scan Folder**
5. ทดลองคลิกที่ Directory Tree ฝั่งซ้าย หรือกดปุ่ม **Reveal** เพื่อดูผลลัพธ์

### การทดสอบความเร็วผ่าน CLI (ทางเลือกเสริม)
```powershell
python tools/benchmark.py C:\Users
```

---

## 5. การเชื่อมโยงกับทฤษฎีในตำรา OS (Syllabus Mapping)

| บทเรียนในตำรา Silberschatz 10th Ed. | ทฤษฎี OS ที่ใช้ | การประยุกต์ใช้ใน CoreSpace |
| :--- | :--- | :--- |
| **Chapter 2: Operating-System Structures** | System Calls & Dual-Mode (Ring 3 $\leftrightarrow$ Ring 0) | ใช้ `FIND_FIRST_EX_LARGE_FETCH` บัฟเฟอร์ 64KB เพื่อลด Context Switches |
| **Chapter 4: Threads & Concurrency** | Thread Pools & Synchronization | ออกแบบระบบ Producer-Consumer Work Queue ดัน I/O Concurrency |
| **Chapter 12: I/O Systems** | Storage Device Queuing & I/O Bound | ผลักดัน Queue Depth ($QD > 1$) เพื่อดึงศักยภาพชิป Multi-channel บน NVMe SSD |
| **Chapter 13: File-System Interface** | Tree-structured Directories & Acyclic Graphs | ตรวจจับ Reparse Points ป้องกัน Infinite Recursion Loop จาก Junctions |
| **Chapter 14: File-System Implementation** | Allocation Methods & Internal Fragmentation | คำนวณ Cluster Allocation (4,096 B) และ Slack Space บนระบบไฟล์ NTFS |
| **Chapter 14: Inodes / Indexed Allocation** | Resident Metadata Storage | คำนวณขนาด NTFS Resident Files ($\le 600$B) ให้มี Physical On-Disk Size = 0 Bytes |

---

## 6. ประวัติการตัดสินใจและการปรับแก้ (Decision History)

1. **การยกเลิกระบบ Benchmark Battle บนหน้าจอ:** ปรับออกตามความต้องการของผู้ใช้ เพื่อไม่ให้หน้าจอดูรกและไม่จำเป็นต่อการใช้งานจริง
2. **การลบช่องเลือก Threads ออกจาก Header:** เปลี่ยนมาใช้การคำนวณเธรดอัตโนมัติในเบื้องหลัง เพื่อให้ UI คลีนและตรงตามหลัก UX
3. **การนำ Treemap ออกชั่วคราว:** เอาแผนผัง Treemap เดิมออกเพื่อให้พื้นที่หน้าจอเทให้แก่การ์ดสเปกและตาราง TreeSize อย่างเต็มที่
4. **การเลือกใช้ Vue 3 ผ่าน CDN:** ตัดสินใจไม่ใช้ Node.js/Vite เพื่อรักษาหลักการ Zero-Dependency ให้เพื่อนทุกคนรันโค้ดได้โดยไม่ติดปัญหา Environment
5. **Git Versioning:** บันทึก Commit ประวัติการพัฒนาไว้ใน Git Repository อย่างเป็นระเบียบตามหลัก Semantic Commits

---

## 7. สิ่งที่ต้องดำเนินการต่อ (Pending Actions & Next Steps)

### สำหรับเตรียมนำเสนอในชั้นเรียน (เดดไลน์ 9 ต.ค. 2569)
1. **จัดทำสไลด์นำเสนอ (Presentation Files):**
   - ใช้ [PRESENTATION_PLAN.md](../PRESENTATION_PLAN.md) เป็นแผนสไลด์ปัจจุบัน; เนื้อหาในไฟล์นี้เป็นภาพต้นแบบที่ต้องตรวจเทียบกับโค้ดก่อนใช้
2. **อัดคลิปวิดีโอสาธิต (Demo Video 2–3 นาที):**
   - สาธิตการเปิดแอป $\rightarrow$ เลือก Drive $\rightarrow$ สแกน $\rightarrow$ ชี้ให้เห็น Slack Space $\rightarrow$ กาง Directory Tree $\rightarrow$ กดปุ่ม Reveal เพื่อเปิด Explorer
3. **ซักซ้อมการตอบคำถาม (Code Defense):**
   - สมาชิกทั้ง 3 คนควรอ่าน [OS_CONCEPTS_EXPLAINED.md](../OS_CONCEPTS_EXPLAINED.md) เพื่อทบทวนคำศัพท์ แล้วใช้ผลทดสอบจริงตอบคำถามเกี่ยวกับโค้ด

### สำหรับการพัฒนาฟีเจอร์ในอนาคต (Future Enhancements)
- **v1.1.0:** เพิ่มระบบ Search และ Filter กรองนามสกุลไฟล์ (.mp4, .pdf, .zip) ในตาราง
- **v1.2.0:** เพิ่มปุ่ม Export รายงานเป็นไฟล์ CSV หรือ JSON
- **v1.3.0:** พัฒนาแผนผัง Visual Treemap หรือ Sunburst ใหม่ที่ออกแบบให้เข้ากับธีมกระดาษครีม Tavily อย่างประณีต
