# 📖 คู่มือการศึกษาโค้ดและการเตรียมตัวนำเสนอ (Study & Defense Guide)

> **วิชา Operating Systems (OS Mini-Project)**  
> **กลุ่ม:** ผู้ก้าวข้ามโชคชะตาด้วยมือของตัวเอง  
> **สมาชิก:** นายศรัณย์ พาพรชัย, นายปวริศช์ ประมวล, นายธีรเมธ สายคำ  

---

## 1. แผนที่โครงสร้างโค้ด (ใครดูแลไฟล์ไหน?)

```text
├── backend/
│   ├── win32_api.py       # [ศรัณย์] เชื่อมต่อ Win32 C-API (FindFirstFileExW, LARGE_FETCH, GetDiskFreeSpaceW)
│   ├── os_storage.py      # [ปวริศช์] คำนวณ Cluster Size, Slack Space (Internal Frag), Resident Files
│   ├── arena.py           # [ธีรเมธ] โครงสร้าง Compact Node (__slots__) ลด RAM ให้ต่ำกว่า 50MB
│   ├── scanner.py         # [ศรัณย์] ระบบสแกนแบบ Producer-Consumer Queue (ดัน NVMe Queue Depth QD > 1)
│   └── aggregator.py      # [ธีรเมธ] แปลงข้อมูลเข้า TreeSize Sidebar และ Squarified Treemap (LoD Pruning)
├── static/
│   ├── index.html         # [ปวริศช์/ธีรเมธ] หน้าจอ TreeSize ผสม Tavily Design Tokens (Vue 3 CDN)
│   ├── app.js             # [ปวริศช์/ธีรเมธ] Vue 3 Component แบบ Recursive Tree + ECharts
│   └── style.css          # [ปวริศช์/ธีรเมธ] สีครีมกระดาษอุ่น (#fefcf5) ตัวหนังสือ #3c3a39 และขอบบาง 1px
└── main.py                # [ทุกคน] รันเซิร์ฟเวอร์ด้วย Python ตัวเดียว (Zero-Dependency)
```

---

## 2. วิธีที่พวกคุณจะศึกษาการทำงาน (เจาะลึก 4 ประเด็นหลัก)

### 📌 จุดที่ 1: ทำไมการอ่านไฟล์ถึงเร็ว และ Concurrency ทำงานอย่างไร? (ไฟล์ `scanner.py` & `win32_api.py`)
* **ปัญหาเดิมของ OS:** คำสั่ง `os.walk` ทั่วไปทำงานแบบเธรดเดี่ยว ทำให้คิวคำสั่งบน SSD มีความลึกเท่ากับ 1 เสมอ ($QD = 1$) และต้องสลับบริบทข้ามโหมด (Context Switch ระหว่าง Ring 3 ผู้ใช้ กับ Ring 0 เคอร์เนล) บ่อยครั้ง
* **วิธีแก้ของเรา:** 
  1. ใช้ **Producer-Consumer Pattern** มี Work Queue เก็บรายชื่อโฟลเดอร์ แล้วใช้ Worker Threads หลายตัวช่วยกันอ่านพร้อมกัน ทำให้ส่ง I/O คำสั่งลง NVMe SSD ได้หลายช่องทาง ($QD > 1$)
  2. เรียกใช้ Win32 API `FindFirstFileExW` พร้อมแฟล็ก `FIND_FIRST_EX_LARGE_FETCH` ขยายบัฟเฟอร์ในเคอร์เนลเป็น 64KB ช่วยลดจำนวน System Call ลงมหาศาล

### 📌 จุดที่ 2: Slack Space และ Resident File คืออะไร? (ไฟล์ `os_storage.py`)
* **Cluster Allocation:** ฮาร์ดดิสก์จัดสรรพื้นที่เป็นบล็อกคงที่ (NTFS ปกติคือ 4,096 Bytes) ถ้าไฟล์มีขนาด 100 Bytes ระบบก็ต้องยกให้ 1 คลัสเตอร์ (4,096 Bytes) ส่วนต่างที่เหลือ 3,996 Bytes เรียกว่า **"Slack Space"** (Internal Fragmentation)
* **NTFS Resident Files (ลูกเล่นเด็ด):** ถ้าไฟล์มีขนาดเล็กมาก ($\le 600$ Bytes) NTFS จะฝังข้อมูลลงในระเบียน Master File Table ($MFT) โดยตรง ทำให้ขนาด Physical บนคลัสเตอร์ภายนอกคิดเป็น **0 Bytes**! โค้ดใน `calculate_physical_and_slack` ได้จำลองทฤษฎีนี้อย่างแม่นยำ

### 📌 จุดที่ 3: Reparse Point Safety Gate (ไฟล์ `scanner.py`)
* **โจทย์:** ถ้ามีโฟลเดอร์ประเภท Directory Junctions หรือ Symlinks ชี้วนกลับไปที่โฟลเดอร์แม่ จะเกิด **Infinite Recursion Loop** ทันที
* **วิธีแก้:** ตรวจจับบิตแฟล็ก `FILE_ATTRIBUTE_REPARSE_POINT` (0x400) ใน Win32 API ถ้าเจอ ให้มองเป็น Leaf Node ห้ามเจาะลึกเข้าไปซ้ำ

### 📌 จุดที่ 4: TreeSize Directory Tree & LoD Pruning (ไฟล์ `app.js` & `aggregator.py`)
* **Tree Component:** ใช้ Vue 3 ทำ Recursive Tree กางและพับกิ่งโฟลเดอร์ได้ลึกไม่จำกัด
* **LoD Pruning:** รวมไฟล์ย่อยที่มีขนาดเล็กกว่า 0.5% เข้าเป็นก้อน `[Others]` ทำให้การเรนเดอร์ Treemap ลื่นไหล 60 FPS ไม่กระตุก

---

## 3. สิ่งที่คุณและเพื่อนๆ สามารถทำเพิ่มกับโค้ดได้ (Customization Ideas)

เพื่อให้เป็นผลงานที่มีลายเซ็นของกลุ่มคุณเอง ทั้ง 3 คนสามารถแบ่งกันเพิ่มลูกเล่นเหล่านี้ได้ง่ายๆ:

1. **เพิ่มแถบ About แสดงรูปและประวัติสมาชิกกลุ่ม (ใน `static/index.html`):**
   * เพิ่มปุ่ม Modal "About Us" เมื่อกดแล้วมีรูปสมาชิก 3 คน, ชื่อ-นามสกุล, และรหัสนิสิตสไตล์การ์ด Tavily
2. **เพิ่มฟังก์ชัน Filter กรองนามสกุลไฟล์ (ใน `static/app.js`):**
   * ทำปุ่มกดกรองดูเฉพาะไฟล์ประเภทที่สนใจในตาราง เช่น กดดูเฉพาะ วิดีโอ (`.mp4`), เอกสาร (`.pdf`), หรือ โค้ด (`.py`)
3. **เพิ่มปุ่ม "Export to CSV" (ใน `static/app.js`):**
   * ให้ผู้ใช้สามารถกดส่งออกรายการไฟล์ของโฟลเดอร์ที่เลือก ออกมาเป็นไฟล์ Excel/CSV ได้
4. **ทดสอบสแกนโฟลเดอร์จริงเพื่อนำรูปมาใส่สไลด์:**
   * ลองสแกนโฟลเดอร์ `C:\Windows` หรือโฟลเดอร์โปรเจกต์ที่มี `.git` หรือ `node_modules` เพื่อแคปเจอร์หน้าจอโชว์ Slack Space สูงๆ ลงในสไลด์และคลิปเดโม
