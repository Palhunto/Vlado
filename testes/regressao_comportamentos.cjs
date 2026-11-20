'use strict';
// Synthetic DOM contract tests, using the production scripts without private hooks.
const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const root = path.resolve(__dirname, '..');
const flush = async () => { await new Promise(setImmediate); await new Promise(setImmediate); };

function fixture() {
  const nodes = new Map(), calls = [], waiting = [], replies = [], windowEvents = new Map();
  let activeElement = null;
  class Element {
    constructor(tag, text='') { this.tagName=tag; this._text=text; this._value=''; this.children=[]; this.dataset={}; this.handlers={}; this.disabled=false; this.hidden=false; this.classList={toggle(){},add(){}}; }
    get textContent() { return this._text + this.children.map(n=>n.textContent).join(''); }
    set textContent(value) { this._text=String(value ?? ''); this.children=[]; }
    get options() { return this.children; }
    get value() { return this._value; }
    set value(value) { this._value=value; }
    get selectedOptions() { return this.children.filter(n=>n.value===this.value); }
    append(...items) { for (const n of items) { n.remove(); n.parent=this; this.children.push(n); } }
    replaceChildren(...items) { for(const n of this.children)n.parent=null; this.children=[]; this.append(...items); if(this.tagName==='select')this.value=items[0]?.value||''; }
    remove() { if(this.parent){this.parent.children=this.parent.children.filter(n=>n!==this);this.parent=null;} }
    addEventListener(type, fn) { (this.handlers[type] ||= []).push(fn); }
    async fire(type, event={}) { for(const fn of this.handlers[type]||[])await fn({preventDefault(){},...event}); }
    setAttribute(key,value) { this[key]=value; }
    focus() { activeElement=this; }
    scrollIntoView() {}
    querySelectorAll(selector) {
      const all=this.children.flatMap(n=>[n,...n.querySelectorAll('*')]);
      if(selector==='*')return all;
      if(selector==='input[data-observacao-achado]')return all.filter(n=>n.tagName==='input'&&n.dataset.observacaoAchado);
      return all.filter(n=>n.tagName===selector);
    }
  }
  const get=id=>{if(!nodes.has(id))nodes.set(id,new Element(id.includes('caso')||id==='codex-conversa'?'select':'div'));return nodes.get(id);};
  const context={console,Map,Set,JSON,Promise,structuredClone,setTimeout,clearTimeout,
    $:get,element:(tag,text)=>new Element(tag,text),
    Option:function(text,value){const n=new Element('option',text);n.value=value;return n;},
    document:{createElement:tag=>new Element(tag),getElementById:get,get activeElement(){return activeElement;}},
    window:{addEventListener(type,fn){windowEvents.set(type,fn);}},
    fetch:async()=>({ok:true,json:async()=>({casos:[{id:'alpha',titulo:'Pauta Alpha'},{id:'beta',titulo:'Pauta Beta'}]})}),
    findingResult:{registros_sha256:'hash-sintetico'},findingEpoch:1,showArea(){},
    api:async(operation,data)=>{
      calls.push({operation,data});
      if(operation==='codex-eventos')return new Promise((resolve,reject)=>{
        const finish=value=>value instanceof Error?reject(value):resolve(value);
        if(replies.length)finish(replies.shift());else waiting.push(finish);
      });
      if(operation==='codex-listar')return {conversas:[{id:'chat1',titulo:'Conversa 1',estado:'concluido'},{id:'chat2',titulo:'Conversa 2',estado:'concluido'}]};
      if(operation==='inventario')return {caso_id:data.caso,documentos:[],total_documentos:0};
      if(operation==='codex-perguntar')return {conversa:data.conversa||'chat-novo',estado:'executando'};
      return {};
    }};
  get('codex-caso').replaceChildren(new context.Option('Selecione',''),new context.Option('Pauta Alpha','alpha'),new context.Option('Pauta Beta','beta'));
  get('codex-conversa').replaceChildren(new context.Option('Nova conversa',''),new context.Option('Conversa 1','chat1'),new context.Option('Conversa 2','chat2'));
  vm.createContext(context);
  for(const name of ['leitura','codex','observacoes']) {
    vm.runInContext(fs.readFileSync(path.join(root,'interface',name+'.js'),'utf8'),context,{filename:name+'.js'});
    context.Leitura=context.window.Leitura;
  }
  const snapshot=(estado='concluido',aprovacoes=[],cursor=0,eventos=[])=>({conversa:{estado},aprovacoes,cursor,eventos});
  const deliver=async value=>{if(waiting.length)waiting.shift()(value);else replies.push(value);await flush();};
  async function caseSelect(value){get('codex-caso').value=value;await get('codex-caso').fire('change');}
  async function chatSelect(value){get('codex-conversa').value=value;await get('codex-conversa').fire('change');}
  async function write(text){get('codex-pergunta').value=text;await get('codex-pergunta').fire('input');}
  return {get,context,calls,deliver,snapshot,caseSelect,chatSelect,write,windowEvents,Element};
}

test('reconectar retoma cursor/conversa, sem reenviar; cancelar permanece disponível',async()=>{
  const f=fixture();await f.caseSelect('alpha');await f.chatSelect('chat1');
  await f.deliver(f.snapshot('executando',[],7,[{tipo:'aviso',dados:{mensagem:'Evento sintético único'}}]));
  await f.deliver(new Error('queda sintética'));
  assert.equal(f.get('codex-reconectar').hidden,false);assert.equal(f.get('codex-cancelar').disabled,false);
  assert.equal(f.get('codex-enviar').disabled,true);
  await f.get('codex-reconectar').fire('click');await f.get('codex-reconectar').fire('click');
  assert.deepEqual(f.calls.filter(c=>c.operation==='codex-eventos').map(c=>c.data.cursor),[0,7,7]);
  await f.deliver(f.snapshot('executando',[],8));
  assert.equal(f.get('codex-reconectar').hidden,true);assert.equal(f.get('codex-atividades').children.length,1);
  await f.get('codex-cancelar').fire('click');
  assert.equal(f.calls.find(c=>c.operation==='codex-cancelar').data.conversa,'chat1');
  assert.equal(f.calls.some(c=>c.operation==='codex-perguntar'),false);
  await f.deliver(f.snapshot('interrompido',[],9));
  assert.equal(f.get('codex-cancelar').disabled,true);
});

test('nova falha de reconexão permite nova tentativa sem executar pergunta',async()=>{
  const f=fixture();await f.caseSelect('alpha');await f.chatSelect('chat1');
  await f.deliver(new Error('primeira queda'));await f.get('codex-reconectar').fire('click');
  await f.deliver(new Error('segunda queda'));
  assert.equal(f.get('codex-reconectar').disabled,false);assert.equal(f.get('codex-cancelar').disabled,false);
  await f.get('codex-reconectar').fire('click');await f.deliver(f.snapshot());
  assert.equal(f.get('codex-reconectar').hidden,true);
  assert.equal(f.calls.some(c=>c.operation==='codex-perguntar'),false);
});

test('rascunhos separados por pauta, conversa e nova conversa; destino visível',async()=>{
  const f=fixture();await f.caseSelect('alpha');await f.write('Nova Alpha');
  await f.chatSelect('chat1');await f.deliver(f.snapshot());assert.equal(f.get('codex-pergunta').value,'');
  await f.write('Complemento Alpha 1');await f.chatSelect('chat2');await f.deliver(f.snapshot());
  await f.write('Complemento Alpha 2');await f.caseSelect('beta');assert.equal(f.get('codex-pergunta').value,'');
  await f.write('Nova Beta');await f.caseSelect('alpha');assert.equal(f.get('codex-pergunta').value,'Nova Alpha');
  await f.chatSelect('chat1');await f.deliver(f.snapshot());assert.equal(f.get('codex-pergunta').value,'Complemento Alpha 1');
  assert.match(f.get('codex-destino').textContent,/Pauta Alpha.*Conversa 1/);
  await f.chatSelect('chat2');await f.deliver(f.snapshot());assert.equal(f.get('codex-pergunta').value,'Complemento Alpha 2');
  await f.get('codex-nova').fire('click');assert.equal(f.get('codex-pergunta').value,'Nova Alpha');
  await f.caseSelect('beta');assert.equal(f.get('codex-pergunta').value,'Nova Beta');
  let warned=false;f.windowEvents.get('beforeunload')({preventDefault(){warned=true;}});assert.equal(warned,true);
});

test('envio confirmado limpa só o rascunho enviado; falha preserva texto e contexto',async()=>{
  const f=fixture();await f.caseSelect('beta');await f.write('Não enviar Beta');await f.caseSelect('alpha');await f.write('Enviar Alpha');
  const api=f.context.api;f.context.api=async(op,data)=>{if(op==='codex-perguntar')throw new Error('recusa sintética');return api(op,data);};
  await f.get('codex-form').fire('submit');assert.equal(f.get('codex-pergunta').value,'Enviar Alpha');
  f.context.api=api;await f.get('codex-form').fire('submit');await f.deliver(f.snapshot());
  const sent=f.calls.find(c=>c.operation==='codex-perguntar').data;assert.equal(sent.caso,'alpha');assert.equal(sent.pergunta,'Enviar Alpha');
  assert.equal(f.get('codex-pergunta').value,'');await f.caseSelect('beta');assert.equal(f.get('codex-pergunta').value,'Não enviar Beta');
});

test('continuação assistida recupera rascunho do destino sem sobrescrever outra pauta',async()=>{
  const f=fixture();await f.caseSelect('alpha');await f.chatSelect('chat1');await f.deliver(f.snapshot());await f.write('Rascunho alvo');
  await f.caseSelect('beta');await f.write('Rascunho Beta');
  f.context.window.mostrarObservacoes=()=>{};
  await f.context.window.continuarComObservacoes({caso:'alpha',conversa:'chat1',conteudo:{observacoes:[]}},{});
  await f.deliver(f.snapshot());assert.equal(f.get('codex-pergunta').value,'Rascunho alvo');
  await f.caseSelect('beta');assert.equal(f.get('codex-pergunta').value,'Rascunho Beta');
});

test('uso de tokens da API aparece nas atividades com total da análise',async()=>{
  const f=fixture();await f.caseSelect('alpha');await f.chatSelect('chat1');
  await f.deliver(f.snapshot('executando',[],3,[{tipo:'uso',dados:{etapa:'busca',modelo:'m',uso:{entrada:120,saida:30,cache_leitura:80},total:{entrada:300,saida:60,cache_leitura:200}}}]));
  const linha=f.get('codex-atividades').children.at(-1).textContent;
  assert.match(linha,/Uso da API · busca: entrada 120, saída 30, cache 80 tokens/);
  assert.match(linha,/total da análise: entrada 300, saída 60, cache 200/);
});

function observation(f,id='A001',event='e1') {
  return f.context.window.observacoesAchado({id,versao:1,redacao:'Achado sintético',revisao_humana:{evento_id:event}},
    {caso:'alpha',rodada:'R001',revisao:'r1',geracao_achados:'g1'});
}
test('limpar e atualizar observações não altera seleção/disabled do caderno ou formulários',async()=>{
  const f=fixture(),foreign=new f.Element('input');foreign.checked=true;foreign.disabled=true;f.get('caderno-resultados').append(foreign);
  const label=observation(f),input=label.children[0];f.get('achados-resultados').append(label);input.checked=true;await input.fire('change');
  assert.match(f.get('observacoes-contagem').textContent,/1 observação/);
  f.context.window.limparObservacoes();assert.equal(input.checked,false);assert.equal(foreign.checked,true);assert.equal(foreign.disabled,true);
  assert.equal(f.get('observacoes-continuar').disabled,true);
  input.checked=true;await input.fire('change');const revised=observation(f,'A001','e2');
  assert.equal(input.checked,false);assert.equal(revised.children[0].checked,false);assert.equal(f.get('observacoes-continuar').disabled,true);
});

test('seleção de observações permanece entre páginas e não afeta caixas externas durante envio',async()=>{
  const f=fixture(),foreign=new f.Element('input');foreign.checked=true;foreign.disabled=true;f.get('diligencias-documentos').append(foreign);
  const label=observation(f),input=label.children[0];f.get('achados-resultados').append(label);input.checked=true;await input.fire('change');
  f.get('achados-resultados').replaceChildren(observation(f,'A002'));
  const returned=observation(f);f.get('achados-resultados').replaceChildren(returned);assert.equal(returned.children[0].checked,true);
  let release;const api=f.context.api;f.context.api=async(op,data)=>op==='codex-observacoes'?new Promise(resolve=>release=resolve):api(op,data);
  f.context.window.continuarComObservacoes=async()=>{};
  const pending=f.get('observacoes-continuar').fire('click');await flush();
  assert.equal(returned.children[0].disabled,true);assert.equal(foreign.checked,true);assert.equal(foreign.disabled,true);
  release({});await pending;assert.equal(returned.children[0].disabled,false);assert.equal(foreign.disabled,true);
});

test('localizadores legíveis, completos ou parciais, sem serializar objetos ou inventar posição',()=>{
  const f=fixture(),format=f.context.window.Leitura.localizador;
  for(const [value,expected] of [
    [{pagina_pdf:3},'p. 3'],[{linha_inicio:2,linha_fim:8},'linhas 2–8'],[{linha_inicio:2},'linha 2'],
    [{localizador:'Tabela 4, rodapé'},'Tabela 4, rodapé'],
    [{localizador:{tipo:'regiao',descricao:'Canto superior direito'}},'Canto superior direito'],
    [{localizador:{pagina_pdf:6}},'p. 6'],[{localizador:{linha_inicio:4,linha_fim:4}},'linha 4'],
    [{localizador:{aba:'Despesas',celula:'B12'}},'aba Despesas · célula B12'],
    [{localizador:{tabela:2,regiao:'rodapé'}},'tabela 2 · região rodapé'],
    [{descricao:'Anexo IV'},'Anexo IV'],[{localizador:{tipo:'regiao'}},'localizador não informado'],
    [{localizador:{descricao:{texto:'não adivinhar'},celula:[]}},'localizador não informado'],[{},'localizador não informado'],
  ])assert.equal(format(value),expected);
  assert.equal(f.context.window.Leitura.fonte({nome_documento:'Sintético.csv',localizador:{celula:'C3'}}),'Sintético · célula C3');
});
