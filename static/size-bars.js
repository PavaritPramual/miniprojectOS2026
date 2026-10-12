/* Shared by the Vue chart and its data-boundary checks. No network or chart dependency. */
((root) => {
  function buildSizeBars(items, folderBytes, limit = 10) {
    const known = items.filter((item) => Number.isSafeInteger(item.allocatedBytes) && item.allocatedBytes >= 0);
    const sorted = known.slice().sort((a, b) => b.allocatedBytes - a.allocatedBytes || a.relativePath.localeCompare(b.relativePath));
    const visible = sorted.slice(0, limit);
    const largest = visible[0]?.allocatedBytes || 0;
    const hasTotal = Number.isSafeInteger(folderBytes) && folderBytes > 0;
    return {
      rows: visible.map((item) => ({
        item,
        width: largest > 0 ? (item.allocatedBytes / largest) * 100 : 0,
        share: hasTotal ? (item.allocatedBytes / folderBytes) * 100 : null,
      })),
      largest,
      knownCount: known.length,
      unknownCount: items.length - known.length,
    };
  }
  root.CoreSpaceSizeBars = { buildSizeBars };
  if (typeof module !== "undefined" && module.exports) module.exports = { buildSizeBars };
})(typeof window !== "undefined" ? window : globalThis);
