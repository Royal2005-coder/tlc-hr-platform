/**
 * Verify a delivered single-file pack really works OFFLINE in the browser the customer uses.
 *
 * The container Chromium in this repo has no H.264 decoder, so Playwright says every recording is unsupported;
 * real Chrome is the only honest check. Network is not disabled but anything that is not file:/data:/blob: is
 * reported, because the pack must open with no internet at all.
 *
 * Usage: node verify_pack.mjs "file:///Z:/New%20folder%20(7)/TLC_HRM_Proposal_UAT_20261021-2056.html" [deck]
 */
import { spawn } from "node:child_process";

const TARGET = process.argv[2];
const MODE = process.argv[3] || "deck";
const PORT = Number(process.env.VERIFY_PORT || 9345);
const CHROME = process.env.CHROME_PATH || "C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe";
const PROFILE = `${process.env.TEMP || "."}\\pack-verify-chrome`;
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

const chrome = spawn(CHROME, [
  `--remote-debugging-port=${PORT}`, `--user-data-dir=${PROFILE}`, "--no-first-run", "--no-default-browser-check",
  "--allow-file-access-from-files", "--window-size=1600,950", "about:blank",
], { stdio: "ignore" });

let target;
for (let i = 0; i < 100; i += 1) {
  try {
    const list = await (await fetch(`http://127.0.0.1:${PORT}/json/list`)).json();
    target = list.find((t) => t.type === "page");
    if (target) break;
  } catch { /* chrome still starting */ }
  await sleep(150);
}
if (!target) { chrome.kill("SIGKILL"); throw new Error("no chrome page target"); }

const ws = new WebSocket(target.webSocketDebuggerUrl);
const pending = new Map();
let seq = 0;
const external = [];
const errors = [];
ws.addEventListener("message", (ev) => {
  const msg = JSON.parse(ev.data);
  if (msg.id != null && pending.has(msg.id)) {
    const { resolve, reject } = pending.get(msg.id);
    pending.delete(msg.id);
    msg.error ? reject(new Error(JSON.stringify(msg.error))) : resolve(msg.result);
    return;
  }
  if (msg.method === "Network.requestWillBeSent") {
    const url = msg.params.request.url;
    if (!/^(file|data|blob):/.test(url)) external.push(url.slice(0, 100));
  }
  if (msg.method === "Runtime.exceptionThrown") {
    errors.push((msg.params.exceptionDetails.exception?.description || "").split("\n")[0].slice(0, 160));
  }
});
const send = (method, params = {}) => new Promise((resolve, reject) => {
  const id = ++seq;
  pending.set(id, { resolve, reject });
  ws.send(JSON.stringify({ id, method, params }));
});
const evaluate = async (expression) => {
  const r = await send("Runtime.evaluate", { expression, awaitPromise: true, returnByValue: true });
  if (r.exceptionDetails) throw new Error(r.exceptionDetails.exception?.description || "eval failed");
  return r.result.value;
};

await new Promise((resolve, reject) => {
  ws.addEventListener("open", resolve, { once: true });
  ws.addEventListener("error", () => reject(new Error("CDP socket failed")), { once: true });
});
await send("Network.enable");
await send("Page.enable");
await send("Runtime.enable");
await send("Page.navigate", { url: TARGET });
await sleep(MODE === "deck" ? 6000 : 9000); // a 90 MB file still has to be read off disk

const report = { target: TARGET.slice(-46), mode: MODE };
if (MODE === "deck") {
  report.slides = await evaluate("document.querySelectorAll('.slide').length");
  report.firstTitle = await evaluate("document.querySelector('.slide').dataset.title");
  report.appendixRows = await evaluate("document.querySelectorAll('.p-cases tbody tr').length");
  report.fonts = await evaluate("[document.fonts.status, document.fonts.check('700 40px Fraunces'), document.fonts.check('400 20px \"Be Vietnam Pro\"'), document.fonts.check('400 16px \"JetBrains Mono\"')]");
  report.permissionSlide = await evaluate("[...document.querySelectorAll('.slide')].some(s=>/Phân quyền/.test(s.dataset.title)) ? 'có' : 'KHÔNG'");
  // a role slide: its journey video must actually decode
  const hr = await evaluate("[...document.querySelectorAll('.slide')].findIndex(s=>/Vai trò · HR/.test(s.dataset.title))");
  await evaluate(`show(${hr >= 0 ? hr : 8})`);
  await sleep(1500);
  report.roleVideo = await evaluate(`(() => { const v = document.querySelector('.p-journey video') || document.querySelector('.p-pane.on video');
    if (!v) return 'KHÔNG CÓ video trên slide vai trò'; if (!v.src) v.src = blobUrl(v.dataset.blob);
    return new Promise(res => { v.addEventListener('loadedmetadata', () => res(['decode được', v.readyState, v.duration.toFixed(1), v.videoWidth]), {once:true});
      setTimeout(() => res(['chưa decode', v.readyState, v.videoWidth]), 8000); }); })()`);
  // the appendix: a case row that seeks into the recording
  const apx = await evaluate("[...document.querySelectorAll('.slide')].findIndex(s=>/Phụ lục/.test(s.dataset.title))");
  await evaluate(`show(${apx >= 0 ? apx : 1})`);
  await sleep(1200);
  report.appendixPlay = await evaluate(`(() => { const b = document.querySelector('.p-play'); if (!b) return 'không có nút ▶'; b.click();
    return new Promise(res => { const v = document.querySelector('#mbody video'); if (!v) return res('không mở được video');
      v.addEventListener('loadedmetadata', () => res([v.readyState, v.duration.toFixed(1), v.currentTime.toFixed(1)]), {once:true});
      setTimeout(() => res(['chưa decode', v.readyState]), 6000); }); })()`);
} else {
  report.rows = await evaluate("document.querySelectorAll('table tbody tr, .case, tr').length");
  report.videos = await evaluate("document.querySelectorAll('video').length");
  report.firstVideo = await evaluate(`(() => { const v = document.querySelector('video'); if (!v) return 'không có video';
    const blob = v.dataset.blob || v.dataset.src;
    if (blob && typeof blobUrl === 'function') v.src = blobUrl(blob);
    return new Promise(res => { v.addEventListener('loadedmetadata', () => res([v.readyState, v.duration, v.videoWidth]), {once:true});
      setTimeout(() => res(['chưa decode', v.readyState, v.videoWidth, (v.currentSrc||'').slice(0,24)]), 8000); }); })()`);
  report.title = await evaluate("document.title");
}
report.externalRequests = external.slice(0, 6);
report.pageErrors = errors.slice(0, 4);
console.log(JSON.stringify(report, null, 1));

ws.close();
chrome.kill("SIGKILL");
