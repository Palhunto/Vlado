// Renderiza as pranchetas estáticas do canvas em PNG, com as fontes locais da Mesa.
const {chromium} = require('playwright');
const fs = require('node:fs');
const path = require('node:path');
const [src, out, fontsDir] = process.argv.slice(2);
const FD = fontsDir.split(String.fromCharCode(92)).join('/');
const fontCss = `@font-face{font-family:"Source Serif 4";src:url('file:///${FD}/SourceSerif4-Roman.ttf') format('truetype');font-weight:200 900}
@font-face{font-family:"Source Sans 3";src:url('file:///${FD}/SourceSans3-Upright.otf') format('opentype');font-weight:200 900}`;
const boards = JSON.parse(fs.readFileSync(path.join(src,'canvas.json'),'utf8')).boards;
(async () => {
  const browser = await chromium.launch({headless:true, executablePath:chromium.executablePath()});
  fs.mkdirSync(out,{recursive:true});
  const outline = {};
  for (const [file, b] of Object.entries(boards)) {
    const raw = fs.readFileSync(path.join(src,file),'utf8');
    const prev = JSON.parse(raw.match(/data-props='([^']*)'/)[1]).$preview;
    let inner = raw.match(/<x-dc>([\s\S]*)<\/x-dc>/)[1];
    const helmet = (inner.match(/<helmet>([\s\S]*?)<\/helmet>/)||['',''])[1].replace(/<link[^>]*fonts\.googleapis[^>]*>/g,'');
    inner = inner.replace(/<helmet>[\s\S]*?<\/helmet>/,'');
    const lang = (raw.match(/<html lang="([^"]+)"/)||[,'pt-BR'])[1];
    const html = `<!doctype html><html lang="${lang}"><head><meta charset="utf-8"><style>${fontCss}</style>${helmet}</head><body>${inner}</body></html>`;
    const page = await browser.newPage({viewport:{width:prev.width,height:prev.height}, deviceScaleFactor:1});
    await page.route('**/*', r => r.request().url().startsWith('file:') || r.request().url().startsWith('data:') || r.request().url()==='about:blank' ? r.continue() : r.abort());
    const tmp = path.join(out, '_tmp.html'); fs.writeFileSync(tmp, html);
    await page.goto(require('node:url').pathToFileURL(tmp).href);
    await page.evaluate(() => document.fonts.ready);
    const root = page.locator('body > div').first();
    const base = file.replace('.dc.html','');
    await root.screenshot({path:path.join(out, base+'.png')});
    outline[base] = await page.evaluate(() => {
      const keep = ['font-size','font-weight','font-family','color','background','border','border-top','border-left','border-bottom','stroke','fill','border-radius','height','width','padding','gap','outline','box-shadow','line-height'];
      const lines=[];
      const walk=(el,d)=>{
        const own=[...el.childNodes].filter(n=>n.nodeType===3).map(n=>n.textContent.trim()).join(' ').trim();
        const st=el.getAttribute('style')||'';
        const attrs=['aria-label','aria-current','aria-invalid','disabled','role','type','value','placeholder','href'].filter(a=>el.hasAttribute(a)).map(a=>`${a}=${el.getAttribute(a)}`).join(' ');
        const props=st.split(';').map(s=>s.trim()).filter(s=>keep.some(k=>s.startsWith(k+':'))).join('; ');
        if(own||attrs||['BUTTON','INPUT','TEXTAREA','SELECT','A','H1','H2','H3','SECTION','NAV','ASIDE','HEADER','MAIN','LABEL','svg'].includes(el.tagName)||/border|background/.test(st))
          lines.push(`${'  '.repeat(d)}<${el.tagName.toLowerCase()}${attrs?' '+attrs:''}> ${own?'«'+own.slice(0,160)+'» ':''}${el.tagName==='svg'?'':'{'+props+'}'}`);
        if(el.tagName!=='svg') for(const c of el.children) walk(c,d+1);
      };
      walk(document.body.firstElementChild,0); return lines.join('\n');
    });
    fs.writeFileSync(path.join(out, base+'.outline.txt'), outline[base]);
    await page.close();
  }
  fs.unlinkSync(path.join(out,'_tmp.html'));
  await browser.close();
})().catch(e=>{console.error(e);process.exit(1)});
