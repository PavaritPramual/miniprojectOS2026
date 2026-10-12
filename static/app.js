/* CoreSpace UI — ธีรเมธ. See docs/UI_HANDOFF.md for the OS/data flow. */
const { createApp, ref, reactive, computed, onMounted, onUnmounted, watch } = Vue;
const ACTIVE_STATES = new Set(["queued", "running", "cancelling"]);
const STATES = {
  queued: "รอคิว",
  running: "กำลังสแกน",
  cancelling: "กำลังยกเลิก",
  completed: "เสร็จแล้ว",
  partial: "ผลบางส่วน",
  cancelled: "ยกเลิกแล้ว",
  failed: "ล้มเหลว",
};
function formatBytes(bytes) {
  if (
    bytes === null ||
    bytes === undefined ||
    !Number.isFinite(bytes) ||
    bytes < 0
  )
    return "ไม่ทราบ";
  if (bytes === 0) return "0 B";
  const units = ["B", "KiB", "MiB", "GiB", "TiB", "PiB"];
  const i = Math.min(
    Math.floor(Math.log(bytes) / Math.log(1024)),
    units.length - 1,
  );
  return `${new Intl.NumberFormat("th-TH", { maximumFractionDigits: 2 }).format(bytes / 1024 ** i)} ${units[i]}`;
}
createApp({
  components: { FileCity },
  setup() {
    const apiReady = ref(false),
      drives = ref([]),
      driveError = ref(""),
      drivesLoading = ref(false);
    const targetPath = ref(""),
      selectedDrive = ref(""),
      job = ref(null),
      selected = ref(null);
    watch([targetPath,drives],()=>{
      const path=targetPath.value.replaceAll('/','\\').toUpperCase();
      selectedDrive.value=drives.value.find(drive=>path.startsWith(drive.path.toUpperCase()))?.path||'';
    });
    const notice = ref(""),
      error = ref(""),
      starting = ref(false),
      cancelBusy = ref(false),
      revealBusy = ref(null);
    const inspectedPath = ref(null);
    const latestBusy = ref(false);
    async function inspectItem(item) {
      if(cityView.value)cityView.value.query='';
      if(!item.relativePath){
        inspectedPath.value=null;
        await Vue.nextTick();
        document.querySelector('.table-scroll')?.scrollIntoView({behavior:'smooth',block:'start'});
        return;
      }
      mode.value='list';
      const parent = item.relativePath.includes('/') ? item.relativePath.slice(0,item.relativePath.lastIndexOf('/')) : '';
      await navigate(parent);
      if(pages[parent]?.loading){notice.value='รายการกำลังโหลด กรุณาลองเลือกอีกครั้ง';return;}
      while (pages[parent]?.hasMore && !pages[parent].items.some(x=>x.relativePath===item.relativePath)) {
        const offset=pages[parent].offset;
        await loadChildren(parent);
        if(pages[parent]?.error||pages[parent].offset===offset)break;
      }
      inspectedPath.value = item.relativePath;
      await Vue.nextTick();
      const row=[...document.querySelectorAll('tr[data-path]')].find(x=>x.dataset.path===item.relativePath);
      row?.scrollIntoView({behavior:'smooth',block:'center'});
    }
    const pages = reactive(Object.create(null)),
      expanded = reactive(Object.create(null));
    let api,
      timer = null,
      epoch = 0,
      statusBusy = false;
    const active = computed(() => ACTIVE_STATES.has(job.value?.state));
    const root = computed(
      () =>
        pages[""]?.folder || {
          relativePath: "",
          name: job.value?.rootPath || "โฟลเดอร์",
          kind: "directory",
          logicalBytes: null,
          allocatedBytes: null,
          partial: true,
          hasChildren: true,
        },
    );
    const currentPage = computed(
      () => pages[selected.value?.relativePath ?? ""],
    );
    const currentItems = computed(() => currentPage.value?.items || []);
    const selectedPath = computed(() => selected.value?.relativePath || "");
    const breadcrumbs = computed(() => {
      const parts = selectedPath.value.split("/").filter(Boolean);
      return parts.map((name, index) => ({
        name,
        path: parts.slice(0, index + 1).join("/"),
      }));
    });
    const selectedFolder = computed(
      () => currentPage.value?.folder || selected.value,
    );
    const issues = reactive({
      items: [],
      offset: 0,
      totalIssues: 0,
      hasMore: false,
      loaded: false,
      loading: false,
      error: "",
    });
    const issuesOpen = ref(false);
    function issueReason(issue) {
      const reasons={symlink:'ไม่เดินตามลิงก์ เพื่อป้องกันการอ่านวนกลับ',directory_loop:'โฟลเดอร์นี้เคยอ่านแล้ว จึงข้ามเพื่อไม่อ่านวน',special_file:'รายการนี้ไม่ใช่ไฟล์หรือโฟลเดอร์ปกติ',ALLOCATED_SIZE_UNKNOWN:'Windows อ่านพื้นที่บนดิสก์ของไฟล์นี้ไม่ได้'};
      return issue.code==='ALLOCATED_SIZE_UNKNOWN' ? issue.message : reasons[issue.code]||issue.message;
    }
    let issueEpoch = 0;
    function resetIssues() {
      issueEpoch++;
      Object.assign(issues, {
        items: [],
        offset: 0,
        totalIssues: 0,
        hasMore: false,
        loaded: false,
        loading: false,
        error: "",
      });
    }
    async function loadIssues() {
      if (!job.value || issues.loading || (issues.loaded && !issues.hasMore))
        return;
      const generation = issueEpoch,
        id = job.value.id,
        offset = issues.offset;
      issues.loading = true;
      issues.error = "";
      try {
        const result = await api.issues(id, offset);
        if (generation !== issueEpoch || id !== job.value?.id) return;
        if (
          result.scanId !== id ||
          result.offset !== offset ||
          result.limit !== 50 ||
          !Array.isArray(result.items) ||
          result.items.length > 50 ||
          !Number.isSafeInteger(result.totalIssues) ||
          result.totalIssues < offset + result.items.length ||
          typeof result.hasMore !== "boolean" ||
          (result.hasMore && !result.items.length) ||
          result.items.some((item) =>
            [item.relativePath, item.code, item.message, item.issueType].some(
              (value) => typeof value !== "string",
            ),
          )
        )
          throw new Error("อ่านรายละเอียดปัญหาจากเซิร์ฟเวอร์ไม่ได้");
        issues.items.push(...result.items);
        issues.offset += result.items.length;
        issues.totalIssues = result.totalIssues;
        issues.hasMore = result.hasMore;
        issues.loaded = true;
      } catch (err) {
        if (generation === issueEpoch) issues.error = err.message;
      } finally {
        if (generation === issueEpoch) issues.loading = false;
      }
    }
    function toggleIssues(event) {
      issuesOpen.value = event.target.open;
      if (issuesOpen.value && !issues.loaded) loadIssues();
    }
    function newPage() {
      return {
        folder: null,
        items: [],
        offset: 0,
        totalChildren: 0,
        hasMore: true,
        loaded: false,
        loading: false,
        error: "",
        partial: true,
      };
    }
    function resetPages() {
      epoch++;
      for (const key of Object.keys(pages)) delete pages[key];
    }
    function stopPoll() {
      clearTimeout(timer);
      timer = null;
    }
    const events=ref([]),logOpen=ref(false),mode=ref('city'),cityView=ref(null);
    let eventId=0;
    function recordEvent(message){
      events.value.push({id:++eventId,time:new Date().toLocaleTimeString('th-TH',{hour12:false}),message});
      if(events.value.length>80)events.value.shift();
      Vue.nextTick(()=>{const log=document.querySelector('[role="log"]');if(log)log.scrollTop=log.scrollHeight;});
    }
    async function searchEntries(query,offset=0){return api.search(job.value.id,query,offset);}
    async function focusEntry(item){const view=mode.value;await inspectItem(item);mode.value=view;await Vue.nextTick();cityView.value?.choose(item,true);}
    function chooseEntry(item){cityView.value?.choose(item,true);}
    async function loadDrives() {
      driveError.value = "";
      drivesLoading.value = true;
      try {
        const result = await api.drives();
        if (
          !Array.isArray(result) ||
          result.some((x) => typeof x.path !== "string")
        )
          throw new Error("รูปแบบรายชื่อไดรฟ์ไม่ตรงสัญญา");
        drives.value = result;
        if (!targetPath.value && result.length) {
          selectedDrive.value = result[0].path;
          targetPath.value = result[0].path;
        }
      } catch (err) {
        driveError.value = err.message;
      } finally {
        drivesLoading.value = false;
      }
    }
    function validateStatus(result, id) {
      if(result.isSample)throw new Error('ผลนี้เป็นข้อมูลทดสอบ กรุณาสแกนโฟลเดอร์จริง');
      const counts = [
        result.fileCount,
        result.directoryCount,
        result.errorCount,
        result.skippedCount,
      ];
      if (
        result.id !== id ||
        !STATES[result.state] ||
        typeof result.rootPath !== "string" ||
        counts.some((value) => !Number.isSafeInteger(value) || value < 0) ||
        !Number.isFinite(result.elapsedSeconds) ||
        result.elapsedSeconds < 0 ||
        typeof result.partial !== "boolean"
      ) {
        throw new Error("สถานะหรือจำนวนรายการจากเซิร์ฟเวอร์ไม่ถูกต้อง");
      }
    }
    function validatePage(result, parent, offset) {
      if (
        result.parent !== parent ||
        result.scanId !== job.value?.id ||
        result.offset !== offset ||
        !Array.isArray(result.items) ||
        result.items.length > 50 ||
        typeof result.hasMore !== "boolean" ||
        !Number.isInteger(result.totalChildren) ||
        result.totalChildren < offset + result.items.length ||
        typeof result.partial !== "boolean" ||
        (result.hasMore && !result.items.length)
      )
        throw new Error(
          "รายการจากเซิร์ฟเวอร์ไม่ครบหรือแบ่งหน้าไม่ถูกต้อง",
        );
      const folder = result.folder;
      if (
        !folder ||
        folder.relativePath !== parent ||
        folder.kind !== "directory" ||
        typeof folder.partial !== "boolean" ||
        typeof folder.hasChildren !== "boolean"
      )
        throw new Error("ข้อมูลโฟลเดอร์จากเซิร์ฟเวอร์ไม่ถูกต้อง");
      for (const item of [folder, ...result.items]) {
        if (
          typeof item.relativePath !== "string" ||
          typeof item.name !== "string" ||
          !["file", "directory", "link"].includes(item.kind) ||
          [item.logicalBytes, item.allocatedBytes].some(
            (x) => x !== null && (!Number.isSafeInteger(x) || x < 0),
          )
        )
          throw new Error("รายการไฟล์มีฟิลด์หรือขนาดไม่ถูกต้อง");
      }
    }
    async function loadChildren(parent, replace = false) {
      if (!job.value) return;
      let page = pages[parent];
      if (page?.loading || (!replace && page?.loaded && !page.hasMore)) return;
      if (!page || replace) {
        pages[parent] = newPage();
        page = pages[parent];
      }
      page.loading = true;
      page.error = "";
      const generation = epoch,
        id = job.value.id,
        offset = page.offset;
      try {
        const result = await api.children(id, parent, offset);
        if (generation !== epoch || id !== job.value?.id) return;
        validatePage(result, parent, offset);
        recordEvent(`โหลด ${parent||"โฟลเดอร์เริ่มต้น"} · ${result.items.length} รายการ`);
        const merged = new Map(
          page.items.map((item) => [item.relativePath, item]),
        );
        result.items.forEach((item) => merged.set(item.relativePath, item));
        page.items = [...merged.values()];
        // Offset counts ALL returned kinds, not only folders visible in the tree.
        page.offset += result.items.length;
        page.totalChildren = result.totalChildren;
        page.hasMore = result.hasMore;
        page.partial = !!result.partial;
        page.folder = result.folder;
        page.loaded = true;
      } catch (err) {
        if (generation === epoch) page.error = err.message;
      } finally {
        if (generation === epoch) page.loading = false;
      }
    }
    async function select(node) {
      selected.value = node;
      if (!pages[node.relativePath]?.loaded)
        await loadChildren(node.relativePath);
    }
    async function toggle(node) {
      const path = node.relativePath;
      expanded[path] = !expanded[path];
      if (expanded[path] && !pages[path]?.loaded) await loadChildren(path);
    }
    const treeView = reactive({
      pages,
      expanded,
      selectedPath,
      select,
      toggle,
      load: loadChildren,
    });
    function findNode(path) {
      if (!path) return root.value;
      if (pages[path]?.folder) return pages[path].folder;
      for (const page of Object.values(pages)) {
        const node = page.items.find((x) => x.relativePath === path);
        if (node) return node;
      }
      return {
        relativePath: path,
        name: path.split("/").pop(),
        kind: "directory",
        logicalBytes: null,
        allocatedBytes: null,
        partial: true,
      };
    }
    async function navigate(path) {
      await select(findNode(path));
    }
    async function initialTree() {
      expanded[""] = true;
      await loadChildren("");
      // Root + its direct folders start expanded. Deeper folders load on demand.
      const folders =
        pages[""]?.items.filter((x) => x.kind === "directory") || [];
      for (const node of folders) expanded[node.relativePath] = true;
      await Promise.all(folders.map((node) => loadChildren(node.relativePath)));
    }
    async function refreshVisible() {
      const paths = [
        ...new Set([
          "",
          selectedPath.value,
          ...Object.keys(expanded).filter((path) => expanded[path]),
        ]),
      ];
      resetPages();
      await Promise.all(paths.map((path) => loadChildren(path)));
      // A fast scan can start before the root's folders have arrived.
      // Discover them again after final results, for both the tree and the city.
      const folders=pages['']?.items.filter(item=>item.kind==='directory')||[];
      await Promise.all(folders.map(async node=>{
        if(!(node.relativePath in expanded))expanded[node.relativePath]=true;
        if(!pages[node.relativePath]?.loaded)await loadChildren(node.relativePath);
      }));
      selected.value = findNode(selectedPath.value);
    }
    async function refreshStatus() {
      if (!job.value || statusBusy) return;
      statusBusy = true;
      const id = job.value.id,
        previous = job.value.state;
      try {
        const result = await api.status(id);
        if (id !== job.value?.id) return;
        validateStatus(result, id);
        if(result.state!==job.value.state||result.fileCount!==job.value.fileCount||result.directoryCount!==job.value.directoryCount)recordEvent(`${STATES[result.state]} · อ่านได้ ${result.fileCount} ไฟล์ / ${result.directoryCount} โฟลเดอร์`);
        const issuesChanged =
          job.value.errorCount !== result.errorCount ||
          job.value.skippedCount !== result.skippedCount;
        job.value = result;
        error.value = "";
        if(ACTIVE_STATES.has(result.state)&&pages['']?.loaded&&!pages[''].items.length&&result.directoryCount>1){
          await loadChildren('',true);
        }
        if (
          issuesChanged ||
          (ACTIVE_STATES.has(previous) && !ACTIVE_STATES.has(result.state))
        ) {
          resetIssues();
          if (issuesOpen.value) await loadIssues();
        }
        if (ACTIVE_STATES.has(previous) && !ACTIVE_STATES.has(result.state)) {
          // Final sorting can change page boundaries: invalidate all loaded pages.
          await refreshVisible();

          notice.value =
            result.state === "completed"
              ? "สแกนเสร็จแล้ว"
              : `งาน${STATES[result.state]} — ตรวจข้อมูลและรายละเอียดด้านล่าง`;
        }
      } catch (err) {
        error.value = `อ่านสถานะไม่ได้: ${err.message}`;
      } finally {
        statusBusy = false;
        stopPoll();
        if (active.value) timer = setTimeout(refreshStatus, 2000);
      }
    }
    async function startScan() {
      if (!apiReady.value || starting.value || active.value) return;
      if (!targetPath.value.trim()) {
        error.value = "กรุณากรอกตำแหน่งโฟลเดอร์หรือเลือกไดรฟ์";
        return;
      }
      starting.value = true;
      error.value = "";
      events.value=[];logOpen.value=true;
      recordEvent(`ขอเริ่มสแกน ${targetPath.value.trim()}`);
      notice.value = "กำลังขอเริ่มสแกน…";
      try {
        const result = await api.start(targetPath.value.trim());
        if (typeof result.id !== "string" || !STATES[result.state])
          throw new Error("เซิร์ฟเวอร์ไม่ยืนยันการเริ่มสแกน");
        stopPoll();
        resetPages();
        resetIssues();
        for (const key of Object.keys(expanded)) delete expanded[key];
        job.value = {
          ...result,
          rootPath: targetPath.value.trim(),
          fileCount: 0,
          directoryCount: 0,
          errorCount: 0,
          skippedCount: 0,
          elapsedSeconds: 0,
        };
        selected.value = root.value;
        notice.value = "กำลังสแกน";

        await initialTree();
        await refreshStatus();
      } catch (err) {
        notice.value = "";
        error.value = err.message;
        recordEvent(`เริ่มสแกนไม่ได้: ${err.message}`);
      } finally {
        starting.value = false;
      }
    }
    async function cancelScan() {
      if (!active.value || job.value.state === "cancelling" || cancelBusy.value)
        return;
      recordEvent("ขอยกเลิกการสแกน");
      cancelBusy.value = true;
      error.value = "";
      try {
        const result = await api.cancel(job.value.id);
        if (result.state !== "cancelling" && result.state !== "cancelled")
          throw new Error("เซิร์ฟเวอร์ไม่ยืนยันการยกเลิก");
        job.value.state = "cancelling";
        notice.value = "กำลังรอให้การสแกนหยุด";
        await refreshStatus();
      } catch (err) {
        await refreshStatus();
        error.value = `ยกเลิกไม่ได้: ${err.message}`;
      } finally {
        cancelBusy.value = false;
      }
    }
    async function reveal(node) {
      if (!job.value || revealBusy.value !== null) return;
      revealBusy.value = node.relativePath;
      error.value = "";
      notice.value = "กำลังขอเปิดตำแหน่ง…";
      try {
        const result = await api.reveal(job.value.id, node.relativePath);
        if (result.status !== "revealed")
          throw new Error("ไม่ได้รับคำยืนยันจาก Explorer");
        notice.value = "ส่งคำสั่งเปิดตำแหน่งใน Explorer แล้ว";
      } catch (err) {
        notice.value = "";
        error.value = `เปิดตำแหน่งไม่ได้: ${err.message}`;
      } finally {
        revealBusy.value = null;
      }
    }
    async function resume(id) {
      if (!id || active.value || starting.value) return;
      starting.value = true;
      error.value = "";
      try {
        const result = await api.status(id);
        validateStatus(result, id);
        stopPoll();
        resetPages();
        resetIssues();
        for (const key of Object.keys(expanded)) delete expanded[key];
        job.value = result;
        selected.value = root.value;
        targetPath.value = result.rootPath;
        await initialTree();
        if (issuesOpen.value) await loadIssues();

        notice.value = "เปิดผลที่บันทึกไว้แล้ว";
        recordEvent(`เปิดผลจริง ${result.rootPath}`);
        if (active.value) timer = setTimeout(refreshStatus, 2000);
      } catch (err) {
        error.value = `เปิดผลเดิมไม่ได้: ${err.message}`;
      } finally {
        starting.value = false;
      }
    }
    async function resumeLatest() {
      if(active.value||starting.value||latestBusy.value||!targetPath.value.trim())return;
      error.value='';
      latestBusy.value=true;
      const path=targetPath.value.trim();
      try {
        const result=await api.latest(path);
        validateStatus(result,result.id);
        if(targetPath.value.trim()===path&&!active.value&&!starting.value)await resume(result.id);
      } catch(err) { error.value=`เปิดผลล่าสุดไม่ได้: ${err.message}`; }
      finally {latestBusy.value=false;}
    }
    function changeDrive() {
      targetPath.value = selectedDrive.value;
    }
    onMounted(async () => {
      try {
        api = CoreSpaceAPI.create();
        apiReady.value = true;
        await loadDrives();
        const scanId=new URLSearchParams(location.search).get('scan');
        if(scanId)await resume(scanId);
      } catch (err) {
        error.value = err.message;
      }
    });
    onUnmounted(() => {
      stopPoll();
      epoch++;
      issueEpoch++;
    });
    return {
      events, logOpen, recordEvent, mode, cityView, searchEntries, focusEntry, chooseEntry,
      pages,
      inspectedPath,
      inspectItem,
      resumeLatest,
      latestBusy,
      apiReady,
      drives,
      driveError,
      drivesLoading,
      targetPath,
      selectedDrive,
      job,
      selected,
      notice,
      error,
      starting,
      cancelBusy,
      revealBusy,
      active,
      root,
      currentPage,
      currentItems,
      breadcrumbs,
      selectedFolder,
      issues,
      issuesOpen,
      issueReason,
      loadIssues,
      toggleIssues,
      treeView,
      STATES,
      formatBytes,
      loadDrives,
      startScan,
      cancelScan,
      reveal,
      resume,
      changeDrive,
      navigate,
      select,
      loadChildren,
      refreshStatus,
      refreshVisible,
    };
  },
}).mount("#app");
