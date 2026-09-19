/**
 * CoreSpace Vue 3 Application
 * TreeSize Model & Tavily Warm Paper Design System
 */

const { createApp, ref, computed, onMounted } = Vue;

// Recursive TreeItem Component for TreeSize Sidebar
const TreeItem = {
  name: 'TreeItem',
  props: {
    node: { type: Object, required: true },
    rootSize: { type: Number, default: 1 },
    selectedPath: { type: String, default: '' },
  },
  emits: ['select-node'],
  setup(props, { emit }) {
    const isOpen = ref(true);

    const dirChildren = computed(() => {
      if (!props.node.children) return [];
      return props.node.children.filter(c => c.is_dir);
    });

    const percent = computed(() => {
      if (!props.rootSize || props.rootSize <= 0) return 0;
      const p = (props.node.size_logical / props.rootSize) * 100;
      return Math.min(100, Math.max(0, p)).toFixed(0);
    });

    const isSelected = computed(() => {
      return props.node.path === props.selectedPath;
    });

    function toggleOpen() {
      isOpen.value = !isOpen.value;
    }

    function select() {
      emit('select-node', props.node);
    }

    return {
      isOpen,
      dirChildren,
      percent,
      isSelected,
      toggleOpen,
      select,
    };
  },
  template: `
    <div class="select-none">
      <div
        class="tree-node-row"
        :class="{ selected: isSelected }"
        @click="select"
      >
        <!-- Toggle chevron -->
        <span
          v-if="dirChildren.length > 0"
          @click.stop="toggleOpen"
          class="w-4 h-4 flex items-center justify-center font-mono text-[11px] text-black/50 hover:text-black cursor-pointer mr-0.5"
        >
          {{ isOpen ? '▾' : '▸' }}
        </span>
        <span v-else class="w-4 h-4 inline-block mr-0.5"></span>

        <!-- Folder icon -->
        <span class="mr-1.5 text-xs text-amber-600">📁</span>

        <!-- Folder Name -->
        <span class="flex-1 truncate text-xs font-mono text-tavilyText" :title="node.name">
          {{ node.name }}
        </span>

        <!-- Size badge -->
        <span class="text-[11px] font-mono text-black/60 mr-2">
          {{ node.formatted_size }}
        </span>

        <!-- Mini % bar -->
        <div class="w-8 bar-track">
          <div class="bar-fill" :style="{ width: percent + '%' }"></div>
        </div>
      </div>

      <!-- Nested Subfolders -->
      <div
        v-if="isOpen && dirChildren.length > 0"
        class="pl-3 border-l border-tavilyBorder ml-2.5 mt-0.5 space-y-0.5"
      >
        <tree-item
          v-for="child in dirChildren"
          :key="child.path"
          :node="child"
          :root-size="rootSize"
          :selected-path="selectedPath"
          @select-node="$emit('select-node', $event)"
        ></tree-item>
      </div>
    </div>
  `,
};

// Main Vue Application
const app = createApp({
  components: {
    TreeItem,
  },
  setup() {
    const drives = ref([]);
    const selectedDrive = ref('');
    const targetPath = ref('');
    const isScanning = ref(false);
    const scanData = ref(null);
    const selectedNode = ref(null);

    // Load Logical Drives
    async function loadDrives() {
      try {
        const res = await fetch('/api/drives');
        const data = await res.json();
        drives.value = data;
        if (data.length > 0) {
          selectedDrive.value = data[0].path;
          targetPath.value = data[0].path;
        }
      } catch (err) {
        console.error('Failed to load drives:', err);
      }
    }

    function onDriveChange() {
      targetPath.value = selectedDrive.value;
    }

    // Start Scan
    async function startScan() {
      const p = targetPath.value.trim();
      if (!p) {
        alert('Please specify a folder path or select a drive');
        return;
      }

      isScanning.value = true;
      try {
        const res = await fetch('/api/scan', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ path: p }),
        });

        if (!res.ok) {
          const err = await res.json();
          alert('Scan failed: ' + (err.detail || 'Unknown error'));
          return;
        }

        const data = await res.json();
        scanData.value = data;
        selectedNode.value = data.tree_view;
      } catch (err) {
        console.error('Scan request error:', err);
        alert('Scan request failed');
      } finally {
        isScanning.value = false;
      }
    }

    // Select Folder Node from Sidebar or Table
    function selectNode(node) {
      selectedNode.value = node;
    }

    // Current Children of Selected Folder (for table)
    const currentChildren = computed(() => {
      if (!selectedNode.value || !selectedNode.value.children) return [];
      return selectedNode.value.children;
    });

    // % of Parent folder
    function getPercentOfParent(item) {
      if (!selectedNode.value || !selectedNode.value.size_logical) return 0;
      const p = (item.size_logical / selectedNode.value.size_logical) * 100;
      return Math.min(100, Math.max(0, p)).toFixed(1);
    }

    // % Slack Space
    function getSlackPercent(node) {
      if (!node || !node.size_physical || node.size_physical <= 0) return 0;
      return ((node.slack_space / node.size_physical) * 100).toFixed(1);
    }

    // Windows Explorer Reveal
    async function revealInExplorer(filePath) {
      if (!filePath) return;
      try {
        await fetch('/api/reveal', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ path: filePath }),
        });
      } catch (err) {
        console.error('Reveal error:', err);
      }
    }

    // Format helpers
    function formatBytes(bytes) {
      if (bytes === undefined || bytes === null || bytes === 0) return '0 B';
      const k = 1024;
      const sizes = ['B', 'KB', 'MB', 'GB', 'TB'];
      const i = Math.floor(Math.log(bytes) / Math.log(k));
      return parseFloat((bytes / Math.pow(k, i)).toFixed(2)) + ' ' + sizes[i];
    }

    function formatNumber(num) {
      if (num === undefined || num === null) return '0';
      return new Intl.NumberFormat().format(num);
    }

    onMounted(() => {
      loadDrives();
    });

    return {
      drives,
      selectedDrive,
      targetPath,
      isScanning,
      scanData,
      selectedNode,
      currentChildren,
      onDriveChange,
      startScan,
      selectNode,
      getPercentOfParent,
      getSlackPercent,
      revealInExplorer,
      formatBytes,
      formatNumber,
    };
  },
});

app.mount('#app');
