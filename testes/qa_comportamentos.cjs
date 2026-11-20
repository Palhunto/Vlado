'use strict';
// Real browser + actual interface files. All API responses are synthetic and intercepted.
const {chromium} = require('playwright');
const assert = require('node:assert/strict');
const fs = require('node:fs/promises');
const path = require('node:path');
const http = require('node:http');
const [output, chrome] = process.argv.slice(2);
const interfaceRoot = path.resolve(__dirname, '../interface');
const snapshot = (estado='concluido',aprovacoes=[],cursor=0,eventos=[]) => ({conversa:{estado},aprovacoes,cursor,eventos});
const until = async predicate => { const end=Date.now()+10000;while(!predicate()){if(Date.now()>end)throw new Error('Espera sintética excedida');await new Promise(r=>setTimeout(r,10));} };
(async()=>{
  await fs.mkdir(output,{recursive:true});
  const server=http.createServer(async(req,res)=>{
    try {
      const file=path.resolve(interfaceRoot,'.'+decodeURIComponent(new URL(req.url,'http://localhost').pathname==='/'?'/index.html':new URL(req.url,'http://localhost').pathname));
      if(!file.startsWith(interfaceRoot+path.sep))throw new Error('Fora da interface');
      const body=await fs.readFile(file),ext=path.extname(file);
      res.writeHead(200,{'Content-Type':{'.html':'text/html; charset=utf-8','.js':'text/javascript; charset=utf-8','.css':'text/css; charset=utf-8','.ttf':'font/ttf','.otf':'font/otf'}[ext]||'application/octet-stream'});res.end(body);
    } catch {res.writeHead(404);res.end();}
  });
  await new Promise(resolve=>server.listen(0,'127.0.0.1',resolve));
  let browser;
  const calls=[],pending=[],errors=[],checks=[];
  try {
    browser=await chromium.launch({headless:true,...(chrome?{executablePath:chrome}:{})});
    const page=await browser.newPage({viewport:{width:1365,height:1000}});
    page.on('pageerror',e=>errors.push(e.message));
    await page.route('**/api/**',async route=>{
      const op=new URL(route.request().url()).pathname.split('/').pop(),data=route.request().postDataJSON();calls.push({op,data});
      if(op==='codex-eventos'){pending.push(route);return;}
      let result={};
      if(op==='catalogo')result={casos:[{id:'alpha',titulo:'Pauta Alpha sintética',rodadas:[]},{id:'beta',titulo:'Pauta Beta sintética',rodadas:[]}]};
      if(op==='ambiente')result={extracao_pdf:{disponivel:true}};
      if(op==='codex-status')result={autenticado:true};
      if(op==='inventario')result={caso_id:data.caso,documentos:[],total_documentos:0};
      if(op==='codex-listar')result={conversas:[{id:'chat1',titulo:'Conversa 1',estado:'concluido'},{id:'chat2',titulo:'Conversa 2',estado:'concluido'}]};
      if(op==='codex-perguntar')result={conversa:data.conversa||'chat-novo',estado:'executando'};
      await route.fulfill({json:result});
    });
    async function respond(value){await until(()=>pending.length);const route=pending.shift();await route.fulfill(value instanceof Error?{status:503,json:{erro:value.message}}:{json:value});}
    async function scope(){if(!await page.locator('#codex-acervo').evaluate(node=>node.open))await page.locator('#codex-acervo>summary').click();}
    async function selectCase(id){await scope();await page.selectOption('#contexto-caso',id);}
    async function openChat(id){await scope();await page.selectOption('#codex-conversa',id);await respond(snapshot());await page.locator('#codex-enviar:not([disabled])').waitFor({state:'attached'});}
    await page.goto(`http://127.0.0.1:${server.address().port}`);
    await page.click('#ver-codex');await selectCase('alpha');
    await page.locator('#codex-conversa option[value="chat1"]').waitFor({state:'attached'});
    await page.fill('#codex-pergunta','Rascunho da nova conversa Alpha');
    await openChat('chat1');assert.equal(await page.inputValue('#codex-pergunta'),'');
    await page.fill('#codex-pergunta','Rascunho Alpha conversa 1');
    await openChat('chat2');await page.fill('#codex-pergunta','Rascunho Alpha conversa 2');
    await selectCase('beta');assert.equal(await page.inputValue('#codex-pergunta'),'');
    await page.fill('#codex-pergunta','Rascunho Beta');await selectCase('alpha');
    assert.equal(await page.inputValue('#codex-pergunta'),'Rascunho da nova conversa Alpha');
    await page.locator('#codex-conversa option[value="chat1"]').waitFor({state:'attached'});await openChat('chat1');
    assert.equal(await page.inputValue('#codex-pergunta'),'Rascunho Alpha conversa 1');
    assert.match(await page.textContent('#codex-destino'),/Pauta Alpha sintética.*Conversa 1/);
    checks.push('Rascunhos separados entre duas pautas, duas conversas e nova conversa; destino identificado.');
    await page.click('#codex-enviar');
    await respond(snapshot('executando',[],5,[{tipo:'aviso',dados:{mensagem:'Evento sintético preservado'}}]));
    await respond(new Error('Queda sintética do acompanhamento'));
    await page.locator('#codex-reconectar').waitFor();
    assert.equal(await page.isDisabled('#codex-cancelar'),false);assert.equal(await page.isDisabled('#codex-enviar'),true);
    const sends=calls.filter(c=>c.op==='codex-perguntar').length;
    await page.click('#codex-reconectar');await respond(snapshot('executando',[],6,[{tipo:'uso',dados:{etapa:'busca',uso:{entrada:10,saida:2},total:{entrada:10,saida:2}}}]));
    await page.locator('#codex-atividades li').nth(1).waitFor();
    assert.equal(calls.filter(c=>c.op==='codex-perguntar').length,sends);
    assert.equal(calls.filter(c=>c.op==='codex-eventos').at(-2).data.cursor,5);
    assert.equal(await page.locator('#codex-atividades li').count(),2);
    checks.push('Queda HTTP e reconexão no cursor existente sem reenvio da pergunta; histórico preservado e cancelamento disponível.');
    await page.click('#codex-cancelar');await until(()=>calls.some(c=>c.op==='codex-cancelar'));await respond(snapshot('interrompido',[],10));
    await page.locator('#codex-enviar:not([disabled])').waitFor({state:'attached'});
    checks.push('Uso de tokens exibido nas atividades; cancelamento da execução existente.');
    const isolation=await page.evaluate(()=>{
      window.mostrarRegistrosCaderno($('caderno-resultados'),{caso_id:'alpha',registros:[{sha256:'sintetico',registro:{id:'H001',tipo:'trecho',titulo:'Registro sintético',autor:'Teste',criado_em_utc:'2026-11-09T00:00:00Z',fontes:[],vinculos:[]}}]},true);
      const foreign=$('caderno-resultados').querySelector('input');foreign.click();
      $('caderno-manual').checked=true;$('caderno-manual').disabled=true;
      $('diligencias-incorporar').checked=true;$('diligencias-incorporar').disabled=true;
      findingResult={registros_sha256:'sintetico'};
      const label=window.observacoesAchado({id:'A001',versao:1,redacao:'Afirmação sintética',revisao_humana:{evento_id:'e1'}},{caso:'alpha',rodada:'R001',revisao:'r1',geracao_achados:'g1'});
      $('achados-resultados').append(label);const own=label.querySelector('input');own.click();window.limparObservacoes();
      return {own:own.checked,foreign:foreign.checked,count:$('caderno-contagem').textContent,manual:$('caderno-manual').checked,manualDisabled:$('caderno-manual').disabled,diligence:$('diligencias-incorporar').checked,diligenceDisabled:$('diligencias-incorporar').disabled};
    });
    assert.deepEqual(isolation,{own:false,foreign:true,count:'1 registro selecionado.',manual:true,manualDisabled:true,diligence:true,diligenceDisabled:true});
    checks.push('No navegador, limpar observações preserva caixa e contagem interna do caderno, transcrição manual e opção de diligências.');
    assert.deepEqual(await page.evaluate(()=>[
      Leitura.fonte({nome_documento:'Sintético.csv',localizador:{aba:'Despesas',celula:'B12'}}),
      Leitura.fonte({nome_documento:'Sintético.pdf',localizador:{tipo:'regiao',descricao:'Rodapé da tabela 2'}}),
      Leitura.fonte({nome_documento:'Sintético.txt',localizador:{tipo:'regiao'}})
    ]),['Sintético · aba Despesas · célula B12','Sintético · Rodapé da tabela 2','Sintético · localizador não informado']);
    checks.push('Localizadores estruturados legíveis no runtime do navegador; ausência informada sem posição inventada.');
    for(const width of [1365,390,320]){
      await page.setViewportSize({width,height:1000});assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth),false,`overflow ${width}`);
      if(width===390)await page.screenshot({path:path.join(output,'destino-mobile.png'),fullPage:true});
    }
    assert.deepEqual(errors,[]);assert.equal(calls.filter(c=>c.op==='codex-perguntar').length,1);
    await fs.writeFile(path.join(output,'navegador.json'),JSON.stringify({estado:'ok',navegador:await browser.version(),natureza:'Chrome headless real; HTML/JS reais; API inteiramente sintética; sem backend operacional, modelo ou documentos de casos',checks,erros_js:errors,perguntas_simuladas:1},null,2));
    console.log(`QA comportamentos: ${checks.length} grupos aprovados; sem erros JavaScript.`);
  } finally {
    for(const route of pending)await route.abort().catch(()=>{});
    if(browser)await browser.close();await new Promise(resolve=>server.close(resolve));
  }
})().catch(error=>{console.error(error);process.exitCode=1;});
