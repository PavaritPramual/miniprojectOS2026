/* HTTP boundary: only this adapter knows URLs. UI and mock share this interface. */
(() => {
  class ApiError extends Error {
    constructor(message, code = "REQUEST_FAILED", status = 0) {
      super(message);
      this.code = code;
      this.status = status;
    }
  }
  async function request(url, { method = "GET", body } = {}) {
    const controller = new AbortController();
    const timeout = setTimeout(() => controller.abort(), 30000);
    try {
      const response = await fetch(url, {
        method,
        signal: controller.signal,
        cache: "no-store",
        headers: body ? { "Content-Type": "application/json" } : {},
        body: body ? JSON.stringify(body) : undefined,
      });
      const data = await response.json().catch(() => null);
      if (!response.ok) {
        const hint =
          response.status === 404 && url.includes("/api/scans")
            ? "Backend ยังไม่มี API งานสแกนใหม่ หรือไม่พบงานนี้ — ตรวจ CONTRACT.md กับผู้ทำ backend"
            : `คำขอไม่สำเร็จ (HTTP ${response.status})`;
        throw new ApiError(data?.detail || hint, data?.code, response.status);
      }
      if (!data || typeof data !== "object")
        throw new ApiError("Backend ส่งข้อมูลที่ไม่ใช่ JSON ตามสัญญา");
      return data;
    } catch (error) {
      if (error instanceof ApiError) throw error;
      throw new ApiError(
        error.name === "AbortError"
          ? "รอคำตอบเกิน 30 วินาที กรุณาลองใหม่"
          : "ติดต่อเซิร์ฟเวอร์ไม่ได้ กรุณาตรวจว่า Python ยังทำงานอยู่",
      );
    } finally {
      clearTimeout(timeout);
    }
  }
  window.CoreSpaceAPI = {
    ApiError,
    create: () => ({
      drives: () => request("/api/drives"),
      start: (path) =>
        request("/api/scans", { method: "POST", body: { path } }),
      status: (id) => request(`/api/scans/${encodeURIComponent(id)}`),
      children: (id, parent, offset) =>
        request(
          `/api/scans/${encodeURIComponent(id)}/children?${new URLSearchParams({ parent, offset, limit: 50 })}`,
        ),
      cancel: (id) =>
        request(`/api/scans/${encodeURIComponent(id)}/cancel`, {
          method: "POST",
        }),
      reveal: (scanId, relativePath) =>
        request("/api/reveal", {
          method: "POST",
          body: { scanId, relativePath },
        }),
    }),
  };
})();
