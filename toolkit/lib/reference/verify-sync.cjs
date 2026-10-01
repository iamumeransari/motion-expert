// Browser half of `reference-board.py --verify`: proves that the frame a board page
// shows is the frame its overlay says it shows. Reads a job file
//   {board, jobs: [{file, times: [beat seconds]}], play: [{file, from, seconds}], out}
// opens each page in Chrome (H.264 needs the real browser, not Playwright's Chromium)
// with ?clean so the video fills the frame, seeks through window.__storyboard, waits
// for `seeked` and the presented frame (requestVideoFrameCallback), screenshots the
// <video> and records the overlay's time, the video's currentTime and the presented
// frame's mediaTime. Playback runs record, on every animation frame, the time the
// overlay draws against the mediaTime of the frame on screen. Writes out/sync.json.
const fs = require('fs');
const path = require('path');
const pw = process.env.PLAYWRIGHT_PATH || path.join(process.env.HOME, 'demofold/engine/node_modules/playwright');
const { chromium } = require(pw);

const job = JSON.parse(fs.readFileSync(process.argv[2], 'utf8'));
fs.mkdirSync(job.out, { recursive: true });

async function open(page, file) {
  await page.goto('file://' + path.join(job.board, file) + '?clean');
  await page.waitForFunction(() => window.__storyboard && document.getElementById('src').readyState >= 2, null, { timeout: 20000 });
}

(async () => {
  const browser = await chromium.launch({ channel: 'chrome', headless: true, args: ['--autoplay-policy=no-user-gesture-required'] });
  const page = await browser.newPage({ viewport: { width: 1920, height: 1080 } });
  const errors = [];
  page.on('pageerror', (e) => errors.push(String(e)));
  const seeks = [], plays = [];
  for (const j of job.jobs) {
    await open(page, j.file);
    for (let i = 0; i < j.times.length; i++) {
      const t = j.times[i];
      const r = await page.evaluate((t) => new Promise((res) => {
        const v = document.getElementById('src');
        let done = false;
        const fin = (now, meta) => {
          if (done) return; done = true;
          // one more frame callback tick so the compositor has the frame up
          requestAnimationFrame(() => res({ media: meta ? meta.mediaTime : null, cur: v.currentTime, overlay: window.__storyboard.time() }));
        };
        if (v.requestVideoFrameCallback) v.requestVideoFrameCallback(fin);
        window.__storyboard.seek(t);
        setTimeout(() => fin(0, null), 1500);
      }), t);
      const png = path.join(job.out, `${j.file.replace(/\.html$/, '')}_${String(i).padStart(3, '0')}.png`);
      await page.locator('#src').screenshot({ path: png });
      seeks.push({ file: j.file, t, png, ...r });
    }
  }
  for (const p of job.play || []) {
    await open(page, p.file);
    const r = await page.evaluate((p) => new Promise((res) => {
      const v = document.getElementById('src');
      const S = window.__storyboard;
      const samples = [];
      let media = null, alive = true;
      const onFrame = (now, meta) => { media = meta.mediaTime; if (alive) v.requestVideoFrameCallback(onFrame); };
      v.requestVideoFrameCallback(onFrame);
      S.seek(p.from);
      setTimeout(() => {
        S.play();
        const t0 = performance.now();
        const tick = () => {
          if (media != null) samples.push({ overlay: S.time(), cur: v.currentTime, media });
          if (performance.now() - t0 < p.seconds * 1000) requestAnimationFrame(tick);
          else { alive = false; S.pause(); res(samples); }
        };
        requestAnimationFrame(tick);
      }, 400);
    }), p);
    plays.push({ file: p.file, samples: r });
  }
  await browser.close();
  fs.writeFileSync(path.join(job.out, 'sync.json'), JSON.stringify({ seeks, plays, errors }));
  console.log(path.join(job.out, 'sync.json'));
})().catch((e) => { console.error(e); process.exit(1); });
