# diskviz-scan — โปรแกรม C อ่านโฟลเดอร์ (ส่วน C)

โปรแกรมนี้เดินอ่านโฟลเดอร์ที่ระบุ แล้วพิมพ์ชื่อ ชนิด และขนาดของทุกรายการออกทาง stdout ทีละบรรทัดเป็น NDJSON ตาม [CONTRACT ข้อ 1](../docs/CONTRACT.md#1-c-scanner--python-ndjson) เพื่อให้ Python รับไปรวมยอดและวัดพื้นที่บนดิสก์ต่อ โปรแกรมไม่ส่ง `allocatedBytes` เพราะ Python วัดจาก Windows API เอง

## Build

ทำใน Ubuntu ของ WSL (ใช้ได้ทั้งโฟลเดอร์ใน `/mnt/d/...` หรือสำเนาใน home ของ Ubuntu):

```bash
sudo apt install build-essential      # ทำครั้งเดียว ถ้ายังไม่มี gcc/make
cd scanner
make                                  # ได้ไฟล์ ./diskviz-scan
./diskviz-scan --help
```

ต้องการวางไว้ที่ตำแหน่งถาวร: `make install` (ค่าเริ่มต้นคือ `~/.local/bin/diskviz-scan`, เปลี่ยนด้วย `PREFIX=...`)

> ไฟล์ใน `scanner/` ต้องเป็นบรรทัดแบบ LF เสมอ (ตั้งไว้ใน `.gitattributes` แล้ว) ถ้า Makefile หรือสคริปต์ถูกแปลงเป็น CRLF บน Windows จะรันใน WSL ไม่ได้

## Run

```bash
./diskviz-scan --root /mnt/d/demo --ndjson
```

- `--root` ต้องเป็น path เต็มใน WSL (ไม่มี `.` หรือ `..`, ห้ามเป็น `/`) ท้ายมี `/` ได้
- ต้องใส่ `--ndjson` (เป็นรูปแบบผลลัพธ์เดียว)
- ผลอยู่ใน stdout, ข้อความแจ้งปัญหาอยู่ใน stderr

เรียกจาก Windows (เหมือนที่ Python ทำ):

```powershell
wsl -d Ubuntu --exec /home/<user>/.local/bin/diskviz-scan --root /mnt/d/demo --ndjson
```

ต่อกับเว็บ: ตั้ง `CORESPACE_SCANNER_WSL_PATH` เป็น path เต็มของไฟล์นี้ใน Ubuntu (หรือส่ง `-ScannerWslPath` ให้ `tools/start.ps1`) ตาม [คู่มือปวริศช์](../docs/PAVARIT_HANDOFF.md) ถ้า exec ไฟล์ใน `/mnt/d` ไม่ได้ ให้ `make install` ไปไว้ใน home ของ Ubuntu แล้วชี้ไปที่นั่น

## ผลลัพธ์

| record | เมื่อไหร่ | ฟิลด์ |
| --- | --- | --- |
| `entry` | ทุกไฟล์/โฟลเดอร์/ลิงก์ root มาก่อน และโฟลเดอร์มาก่อนของข้างใน | `relativePath`, `parentRelativePath`, `name`, `kind` (`file`/`directory`/`link`), `logicalBytes` |
| `error` | อ่านรายการไม่ได้ ไม่ใส่ขนาดแทน | `relativePath`, `code`, `message` |
| `skipped` | ตั้งใจไม่เดินต่อ | `relativePath`, `reason` |
| `done` | บรรทัดสุดท้ายเสมอ | `fileCount`, `directoryCount` (รวม root), `errorCount`, `skippedCount`, `complete` |

กติกาที่โปรแกรมทำตาม:

- `logicalBytes` ของไฟล์คือ `st_size` ของ regular file; โฟลเดอร์และลิงก์เป็น `0` (Python รวมยอดโฟลเดอร์เอง)
- Symbolic link ส่งสอง record ของ path เดียวกัน: `entry` ชนิด `link` แล้ว `skipped` เหตุผล `symlink` และไม่เดินตาม
- ถ้าโฟลเดอร์ชี้ย้อนเป็นบรรพบุรุษของตัวเอง (เทียบ device+inode) จะส่ง `entry` ชนิด `link` กับ `skipped` เหตุผล `directory_loop`
- ไฟล์พิเศษ (FIFO, socket, device) ส่งเฉพาะ `skipped` เหตุผล `special_file` เพราะ contract ไม่มี kind สำหรับมัน
- ชื่อที่ไม่ใช่ UTF-8 ที่ถูกต้อง หรือมี `\` ส่งเป็น `error` รหัส `UNSUPPORTED_NAME` (Python ปฏิเสธ path แบบนี้อยู่แล้ว ถ้าส่งเป็น entry ตัวเลขจะไม่ตรงกัน)
- `error` ที่เกิดจากระบบใช้รหัส errno เช่น `EACCES`, `ENOENT` พร้อมข้อความภาษาอังกฤษจาก `strerror`
- **ส่งผลทันทีที่ `readdir` เจอแต่ละรายการ** ไม่เก็บชื่อทั้งโฟลเดอร์ไว้ในหน่วยความจำ จึงใช้ RAM คงที่แม้โฟลเดอร์เดียวมีไฟล์เป็นล้าน และรายการแรกออกมาทันที
- ลำดับชื่อในโฟลเดอร์เป็นไปตามที่ระบบไฟล์ให้ (ไม่เรียง) แต่โฟลเดอร์มาก่อนของข้างในเสมอ ซึ่งเป็นสิ่งเดียวที่ CONTRACT กำหนด
- ถือ DIR ที่เปิดค้างพร้อมกันไม่เกิน 33 ตัว: 32 ชั้นบนเดินลงทันที ส่วนโฟลเดอร์ย่อยที่ซ้อนลึกกว่านั้นจะเข้าคิว (ชื่อ + device/inode) แล้วค่อยเดินหลังปิดโฟลเดอร์แม่ จึงเดินโฟลเดอร์ซ้อนลึกได้โดยไม่ชน limit ของ file descriptor
- หน่วยความจำเพิ่มตามจำนวนโฟลเดอร์ย่อยเฉพาะที่ระดับลึกเกิน 32 ชั้นเท่านั้น (ชื่อโฟลเดอร์ย่อยเหล่านั้น)
- เขียน stdout ทุก 128 record หรือทุก 250 ms และก่อนเปิดโฟลเดอร์ใหม่ถ้าค้างเกิน 100 ms

Exit code: `0` ครบ · `1` ผลบางส่วน (มี error/skipped) · `2` input ผิด (stdout ว่าง) · `3` ข้อผิดพลาดภายใน (หน่วยความจำไม่พอ) · `130` ถูกยกเลิก

**ยกเลิก:** เมื่อได้ SIGTERM/SIGINT/SIGHUP โปรแกรมจบทันทีด้วย `130` และ **ไม่พิมพ์ `done`** (ถ้าไม่มี `done` แปลว่าผลไม่ครบ) ตั้งใจให้หยุดทันทีเพราะตอน Python ยกเลิกจะหยุดอ่าน pipe ถ้าโปรแกรมรอเขียนอยู่แล้วเพียงแค่ตั้งธงจะไม่ยอมจบ มีเทสต์ครอบกรณีนี้แล้ว

## ตัวอย่างผลจากโฟลเดอร์จริง

สร้างโฟลเดอร์ทดสอบแล้วรัน (ชุดเดียวกับ `prepare_demo_fixture.ps1`: 64 ไฟล์ 13 โฟลเดอร์):

```bash
sh tools/make_demo_fixture.sh /tmp/demo                   # ไม่เขียนทับถ้ามีอยู่แล้ว
scanner/diskviz-scan --root /tmp/demo --ndjson
```

ไฟล์เต็ม: [`examples/demo.ndjson`](examples/demo.ndjson) (exit 0) ย่อดังนี้

```json
{"type":"entry","relativePath":"","parentRelativePath":null,"name":"demo","kind":"directory","logicalBytes":0}
{"type":"entry","relativePath":"depth","parentRelativePath":"","name":"depth","kind":"directory","logicalBytes":0}
...
{"type":"entry","relativePath":"large.bin","parentRelativePath":"","name":"large.bin","kind":"file","logicalBytes":1048576}
{"type":"entry","relativePath":"zero.bin","parentRelativePath":"","name":"zero.bin","kind":"file","logicalBytes":0}
{"type":"entry","relativePath":"ชื่อ ไทย/รายงาน 1.txt","parentRelativePath":"ชื่อ ไทย","name":"รายงาน 1.txt","kind":"file","logicalBytes":5}
{"type":"done","fileCount":64,"directoryCount":13,"errorCount":0,"skippedCount":0,"complete":true}
```

กรณีมีปัญหา สร้างด้วย `--with-issues` และรันด้วยผู้ใช้ปกติ: [`examples/demo-with-issues.ndjson`](examples/demo-with-issues.ndjson) (exit 1) ย่อดังนี้

```json
{"type":"entry","relativePath":"back-to-root","parentRelativePath":"","name":"back-to-root","kind":"link","logicalBytes":0}
{"type":"skipped","relativePath":"back-to-root","reason":"symlink"}
{"type":"error","relativePath":"back\\slash.txt","code":"UNSUPPORTED_NAME","message":"name is not valid UTF-8 or contains a backslash; it cannot be reported safely"}
{"type":"error","relativePath":"no-access","code":"EACCES","message":"opendir: Permission denied"}
{"type":"skipped","relativePath":"pipe.fifo","reason":"special_file"}
{"type":"done","fileCount":64,"directoryCount":14,"errorCount":3,"skippedCount":3,"complete":false}
```

ลำดับบรรทัดในตัวอย่างขึ้นกับระบบไฟล์ ถ้ารันบนเครื่องคุณอาจสลับลำดับกัน แต่ชุด record เหมือนกัน

**ที่มาของตัวอย่าง:** รันบน Ubuntu 24.04 (gcc 13.3, ext4) ไม่ใช่ WSL บนไดรฟ์ D: ของทีม ตัวเลขไฟล์/โฟลเดอร์/ขนาดตรงกับ `docs/examples/scan.ndjson` (เทสต์ตรวจให้) แต่ตัวอย่างนั้นมี `allocatedBytes` จำลอง ส่วนผลจริงนี้ไม่มี

## ทดสอบ

```bash
cd scanner && make check        # หรือจากราก repo: python3 -m unittest tests.test_c_scanner -v
```

เทสต์ build ด้วย Makefile, สร้างโฟลเดอร์ทดสอบ, และส่งทุก record เข้า `ScanManager._validate_entry/_validate_done` ตัวจริงของ Python ตรวจลำดับ parent→child, จำนวนใน `done`, ชื่อไทย/อักขระพิเศษ, ลิงก์วน, สิทธิ์ไม่พอ, input ผิด, โฟลเดอร์ซ้อนเกิน 32 ชั้น (เดินได้แม้จำกัด fd เหลือ 40) และการยกเลิกขณะ pipe เต็ม เทสต์จะข้ามเองบน Windows

ตรวจเพิ่มด้วยมือ: build ด้วย `-fsanitize=address,undefined` ไม่พบปัญหา และสแกน `/usr` (122,137 record) เทียบกับ `find` ได้จำนวนโฟลเดอร์/ลิงก์ตรงกัน ไฟล์ขาดไป 2 ไฟล์ที่ชื่อมี `\` ซึ่งถูกรายงานเป็น `UNSUPPORTED_NAME` ตามออกแบบ และผลรวมไบต์ต่างกันเท่ากับขนาดสองไฟล์นั้นพอดี

## ยังไม่ได้ทดสอบ

- **WSL บน `/mnt/d` (NTFS):** ยังไม่เคยรันบนไดรฟ์ Windows จริง ควรรัน `./diskviz-scan --root /mnt/d/<โฟลเดอร์ทดสอบ> --ndjson` แล้วเทียบจำนวนกับ `prepare_demo_fixture.ps1`
- **NTFS junction:** ไม่รู้ว่า WSL แสดง junction เป็น symlink หรือโฟลเดอร์ ถ้าเป็นโฟลเดอร์ โปรแกรมพึ่งการเทียบ inode เพื่อตัดวง ซึ่งยังไม่ยืนยัน ให้ลอง `prepare_demo_fixture.ps1 -IncludeJunction` แล้วสแกนว่าจบและไม่มีรายการลึกซ้ำ ๆ ใต้ `back-to-root`
- **ทั้งไดรฟ์:** ยังไม่ได้สแกนไดรฟ์ Windows ทั้งลูก
- โปรแกรมไม่ข้ามไปยัง filesystem อื่นที่ mount อยู่ใต้ root (ไม่มี `-xdev`)

## คำสั่งระบบที่เกี่ยวข้องกับวิชา (สำหรับสไลด์ 2–3)

| ส่วนของโปรแกรม | คำสั่ง/แนวคิด |
| --- | --- |
| อ่านรายชื่อในโฟลเดอร์ | `opendir`/`readdir` (ล่างลงไปคือ system call `getdents64`) |
| อ่านชนิดและขนาด | `lstat` อ่านค่าจาก inode ไม่เปิดไฟล์; `st_size` คือขนาด logical ไม่ใช่พื้นที่บนดิสก์ |
| ไม่ตามลิงก์ | `lstat` ไม่ตาม symlink ต่างจาก `stat`; ตัดวงด้วยคู่ device+inode |
| ส่งผลให้ Python | process สองตัวคุยกันผ่าน pipe ของ stdout (บัฟเฟอร์ แล้ว `write`) |
| ยกเลิก | signal (`SIGTERM`) กับ `sigaction`; `_exit` ที่ใช้ใน handler ได้อย่างปลอดภัย |
| รายงานผล | exit status ของ process (0/1/2/130) |
