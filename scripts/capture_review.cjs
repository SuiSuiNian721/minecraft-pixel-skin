// 在本地浏览器验证实际 WebGL 预览；依赖 playwright、sharp。
const fs = require('node:fs');
const path = require('node:path');
const { pathToFileURL } = require('node:url');
const { chromium } = require('playwright');
const sharp = require('sharp');

async function main() {
  const directory = process.argv[2] && path.resolve(process.argv[2]);
  if (!directory) throw new Error('用法：node capture_review.cjs <候选目录> [浏览器可执行文件]');
  const executablePath = process.argv[3];
  const reportPath = path.join(directory, 'preview-validation.json');
  if (fs.existsSync(reportPath)) throw new Error('预览检查记录已存在，请使用新的审阅版本目录');
  const browser = await chromium.launch({headless: true, ...(executablePath ? {executablePath} : {}),
    args: ['--enable-unsafe-swiftshader', '--allow-file-access-from-files']});
  const result = {renderer: 'skinview3d 3.4.2', browser: await browser.version(), errors: [],
    checks: {}, screenshots: [], gameRuntimeVerified: false};
  try {
    const page = await browser.newPage({viewport: {width: 1240, height: 920}, deviceScaleFactor: 1});
    page.on('pageerror', e => result.errors.push(e.message));
    await page.goto(pathToFileURL(path.join(directory, '眼型模板审阅.html')).href);
    await page.evaluate(() => window.reviewReady);
    await page.waitForTimeout(150);
    result.models = await page.evaluate(() => viewers.map(v => ({model: v.playerObject.skin.modelType,
      textureSize: [v.skinCanvas.width, v.skinCanvas.height], canvas: [v.width, v.height]})));
    const requestedModel = await page.evaluate(() => reviewData.model);
    result.checks.explicitModel = result.models.every(m => m.model === requestedModel && m.textureSize[0] === 64 && m.textureSize[1] === 64);
    const snap = async name => {
      const file = path.join(directory, name);
      if (fs.existsSync(file)) throw new Error('截图文件已存在：'+file);
      await page.locator('#hero').screenshot({path: file});result.screenshots.push(name);
    };
    await snap('模型正面.png');
    for (const [view, name] of [['angle','模型斜侧.png'],['other','模型另一侧.png'],['back','模型背面.png'],['top','模型顶部.png']]) {
      await page.locator('#view').selectOption(view);await page.waitForTimeout(80);await snap(name);
    }
    await page.locator('#view').selectOption('front');
    await page.locator('#outer').uncheck();
    result.checks.outerToggleOff = await page.evaluate(() => viewers.every(v => !v.playerObject.skin.head.outerLayer.visible));
    await page.waitForTimeout(80);await snap('仅基础层.png');
    await page.locator('#outer').check();
    result.checks.outerToggleOn = await page.evaluate(() => viewers.every(v => v.playerObject.skin.head.outerLayer.visible));
    const paletteIds = await page.evaluate(() => reviewData.palettes.map(p => p.id));
    if (paletteIds.length > 1) {
      await page.locator('#palette').selectOption(paletteIds[1]);await page.evaluate(() => window.lastUpdate);
      await page.waitForTimeout(80);await snap('第二配色检查.png');
      const switches = await page.evaluate(() => reviewData.cards.map(c => ({id: c.id, changed: c.palette_changed_pixels})));
      result.paletteChanges = switches;
      result.checks.paletteSwitch = await page.evaluate(() => [...document.querySelectorAll('.skin-download')].every(a => a.href===reviewData.cards[Number(a.dataset.index)].skins[document.getElementById('palette').value]));
    }
    // 用单一已知 RGB 头部测量真实渲染通道，避免仅靠肉眼判断预览偏色。
    const expected = [70, 140, 210];
    const calibration = await sharp({create: {width:64,height:64,channels:4,background:{r:70,g:140,b:210,alpha:1}}}).png().toBuffer();
    const calibrationUrl = 'data:image/png;base64,'+calibration.toString('base64');
    await page.evaluate(async data => {
      const v=viewers[0];await v.loadSkin(data,{model:reviewData.model});rawColorMaterials(v);applyView('front');applyOuter(false);
    }, calibrationUrl);
    await page.waitForTimeout(80);
    const calibrationShot = await page.locator('#model-0').screenshot();
    const meta = await sharp(calibrationShot).metadata();
    const sample = await sharp(calibrationShot).extract({left:Math.floor(meta.width/2),top:Math.floor(meta.height/2),width:1,height:1}).removeAlpha().raw().toBuffer();
    result.colorCalibration = {expected, measured: [...sample], tolerance: 1};
    result.checks.rawColorChannels = expected.every((x, i) => Math.abs(x - sample[i]) <= 1);
    await page.evaluate(async id => {document.getElementById('palette').value=id;await applyPalette(id);}, paletteIds[0]);
    await page.evaluate(() => applyOuter(true));
    result.checks.noHorizontalOverflow = await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth);
    result.checks.downloadsNativePng = await page.evaluate(() => [...document.querySelectorAll('.skin-download')].every(a => a.href.startsWith('data:image/png;base64,') && a.download.endsWith('_64x64.png')));
    result.checks.noScriptErrors = result.errors.length === 0;
    result.passed = Object.values(result.checks).every(Boolean);
    fs.writeFileSync(reportPath, JSON.stringify(result, null, 2)+'\n', {flag:'wx'});
    console.log(JSON.stringify(result));
    if (!result.passed) process.exitCode = 1;
  } finally { await browser.close(); }
}
main().catch(error => { console.error(error); process.exitCode = 1; });
