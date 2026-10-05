/* Explicit simulator. No filesystem access, scanner, Windows API, or benchmark. */
(() => {
  const copy = (value) => JSON.parse(JSON.stringify(value));
  const pause = () => new Promise((resolve) => setTimeout(resolve, 90));
  window.createMockAPI = async () => {
    const response = await fetch("/static/mock-api.json");
    if (!response.ok) throw new Error("โหลด fixture ไม่สำเร็จ");
    const fixture = await response.json();
    const pages = new Map();
    const root = [...fixture.rootPage1.items, ...fixture.rootPage2.items];
    const directory = (path, name) => ({
      relativePath: path,
      name,
      kind: "directory",
      logicalBytes: null,
      allocatedBytes: null,
      partial: true,
      hasChildren: true,
    });
    root.splice(
      1,
      3,
      directory("deep", "deep"),
      directory("many-folders", "many-folders"),
      {
        ...directory("empty", "empty"),
        logicalBytes: 0,
        allocatedBytes: 0,
        partial: false,
        hasChildren: false,
      },
    );
    root[4] = {
      ...root[4],
      name: "ศูนย์ ไบต์.txt",
      relativePath: "ศูนย์ ไบต์.txt",
      logicalBytes: 0,
      allocatedBytes: 0,
    };
    root[5] = {
      ...root[5],
      name: "อ่านไม่ได้.txt",
      relativePath: "อ่านไม่ได้.txt",
      logicalBytes: 123,
      allocatedBytes: null,
      partial: true,
    };
    root[6] = {
      ...root[6],
      name: "compressed.bin",
      relativePath: "compressed.bin",
      logicalBytes: 1048576,
      allocatedBytes: 4096,
    };
    root[7] = {
      ...root[7],
      name: "loop-link",
      relativePath: "loop-link",
      kind: "link",
      logicalBytes: null,
      allocatedBytes: null,
      partial: true,
    };
    pages.set("", root);
    pages.set("docs", fixture.docsChildren.items);
    pages.set("empty", []);
    let path = "deep";
    for (let depth = 2; depth <= 8; depth++) {
      const next = `${path}/ชั้น ${depth}`;
      pages.set(path, [directory(next, `ชั้น ${depth}`)]);
      path = next;
    }
    pages.set(path, [
      {
        relativePath: `${path}/ปลายทาง.txt`,
        name: "ปลายทาง.txt",
        kind: "file",
        logicalBytes: 12,
        allocatedBytes: 4096,
        partial: false,
        hasChildren: false,
      },
    ]);
    pages.set(
      "many-folders",
      Array.from({ length: 60 }, (_, i) => {
        const name = `folder-${String(i + 1).padStart(3, "0")}`,
          p = `many-folders/${name}`;
        pages.set(p, []);
        return {
          ...directory(p, name),
          logicalBytes: 0,
          allocatedBytes: 0,
          partial: false,
          hasChildren: false,
        };
      }),
    );
    for (const items of pages.values())
      items.sort(
        (a, b) =>
          (a.allocatedBytes === null) - (b.allocatedBytes === null) ||
          (b.allocatedBytes ?? 0) - (a.allocatedBytes ?? 0) ||
          a.name.localeCompare(b.name, "th") ||
          a.relativePath.localeCompare(b.relativePath),
      );
    let job = null,
      polls = 0,
      serial = 0,
      scenario = "partial";
    const check = (id) => {
      if (!job || id !== job.id)
        throw new CoreSpaceAPI.ApiError(
          "ไม่พบงานตัวอย่าง",
          "SCAN_NOT_FOUND",
          404,
        );
    };
    return {
      setScenario: (value) => {
        scenario = value;
      },
      async drives() {
        await pause();
        return [
          { path: "D:\\demo", total_bytes: 100000000, free_bytes: 50000000 },
        ];
      },
      async start(path) {
        await pause();
        if (!path.trim())
          throw new CoreSpaceAPI.ApiError("กรุณากรอก path", "BAD_PATH", 400);
        polls = 0;
        job = {
          id: `mock-${++serial}`,
          rootPath: path,
          state: "queued",
          fileCount: 0,
          directoryCount: 0,
          elapsedSeconds: 0,
          errorCount: 0,
          skippedCount: 0,
          partial: false,
        };
        return { id: job.id, state: "queued" };
      },
      async status(id) {
        await pause();
        check(id);
        polls++;
        if (job.state === "cancelling") job.state = "cancelled";
        else if (["queued", "running"].includes(job.state)) {
          job.state =
            polls < (scenario === "slow" ? 100 : 3)
              ? "running"
              : scenario === "failed"
                ? "failed"
                : scenario === "completed"
                  ? "completed"
                  : "partial";
        }
        const all = [...pages.values()].flat();
        job.fileCount = ["running", "queued"].includes(job.state)
          ? Math.min(polls * 17, 58)
          : all.filter((x) => x.kind === "file").length;
        job.directoryCount =
          all.filter((x) => x.kind === "directory").length + 1;
        job.elapsedSeconds = Math.max(0, (polls - 1) * 2);
        job.partial = ["partial", "cancelled", "failed"].includes(job.state);
        job.errorCount = job.state === "partial" ? 1 : 0;
        job.skippedCount = job.state === "partial" ? 1 : 0;
        job.error = job.state === "failed" ? "จำลอง: scanner หยุดทำงาน" : null;
        return copy(job);
      },
      async issues(id, offset) {
        await pause();
        check(id);
        const all =
          job.state === "partial"
            ? [
                {
                  relativePath: "อ่านไม่ได้.txt",
                  code: "ACCESS_DENIED",
                  message: "จำลอง: ไม่มีสิทธิ์อ่านพื้นที่จัดสรร",
                  issueType: "error",
                },
                {
                  relativePath: "loop-link",
                  code: "SYMLINK_SKIPPED",
                  message: "จำลอง: ไม่ตาม symbolic link",
                  issueType: "skipped",
                },
              ]
            : [];
        return {
          scanId: id,
          offset,
          limit: 50,
          totalIssues: all.length,
          hasMore: offset + 50 < all.length,
          items: all.slice(offset, offset + 50),
        };
      },
      async children(id, parent, offset) {
        await pause();
        check(id);
        if (!pages.has(parent))
          throw new CoreSpaceAPI.ApiError(
            "ไม่พบโฟลเดอร์ตัวอย่าง",
            "BAD_PARENT",
            400,
          );
        let source = copy(pages.get(parent));
        if (scenario === "completed")
          source = source.filter(
            (x) => x.kind !== "link" && x.relativePath !== "อ่านไม่ได้.txt",
          );
        const items = source.slice(offset, offset + 50);
        return {
          scanId: id,
          parent,
          offset,
          limit: 50,
          totalChildren: source.length,
          hasMore: offset + items.length < source.length,
          partial: job.state !== "completed",
          folder: {
            ...directory(parent, parent.split("/").pop() || job.rootPath),
            logicalBytes: source.some((x) => x.logicalBytes === null)
              ? null
              : source.reduce((sum, x) => sum + x.logicalBytes, 0),
            allocatedBytes: source.some((x) => x.allocatedBytes === null)
              ? null
              : source.reduce((sum, x) => sum + x.allocatedBytes, 0),
            partial: source.some((x) => x.partial),
            hasChildren: source.length > 0,
          },
          items,
        };
      },
      async cancel(id) {
        await pause();
        check(id);
        job.state = "cancelling";
        return { id, state: "cancelling" };
      },
      async reveal(id, path) {
        await pause();
        check(id);
        if (path === "อ่านไม่ได้.txt")
          throw new CoreSpaceAPI.ApiError(
            "จำลอง: Explorer เปิดรายการนี้ไม่ได้",
            "REVEAL_FAILED",
            500,
          );
        return { status: "revealed", mock: true };
      },
    };
  };
})();
