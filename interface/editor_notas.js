'use strict';
// Vditor (about 4 MB) is fetched from this same origin only when the notebook editor
// first opens; every other area loads without it. Ids match the ones Vditor checks
// before adding its own copies of Lute and the icon sprite.
window.CarregadorVditor = (() => {
  // Same as vendor/vditor/manifesto.json (a test keeps them equal). Versioned URLs let the
  // server cache these files as immutable; a new Vditor version means new URLs.
  const VERSAO = '4.0.1';
  const base = '/vendor/vditor/dist';
  const versioned = file => `${base}${file}?v=${VERSAO}`;
  // The content theme carries Vditor's own id, so Vditor does not add an unversioned copy.
  const sheets = [[versioned('/index.css')], [versioned('/css/content-theme/light.css'), 'vditorContentTheme']];
  const scripts = [[versioned('/index.min.js')], [versioned('/js/lute/lute.min.js'), 'vditorLuteScript'],
    [versioned('/js/i18n/pt_BR.js')], [versioned('/js/icons/ant.js'), 'vditorIconScript']];
  const requests = new Map();
  let pending = null;
  const ready = () => Boolean(window.Vditor && window.Lute && window.VditorI18n);
  function addSheet([href, id]) {
    if (document.querySelector(`link[href="${href}"]`)) return;
    const link = document.createElement('link');
    link.rel = 'stylesheet'; link.href = href;
    if (id) link.id = id;
    // Keep the application's stylesheet last, as when both were static.
    const app = document.querySelector('link[href^="/style.css"]');
    if (app) app.before(link); else document.head.append(link);
  }
  function addScript([src, id]) {
    return new Promise((resolve, reject) => {
      const tag = document.createElement('script');
      tag.src = src; tag.async = false;
      if (id) tag.id = id;
      tag.addEventListener('load', resolve);
      tag.addEventListener('error', () => { tag.remove(); reject(new Error(`Falha ao carregar ${src}.`)); });
      document.head.append(tag);
    });
  }
  // A retry re-requests only what failed; loaded or in-flight files are reused.
  function request(entry) {
    const [src] = entry;
    if (!requests.has(src)) requests.set(src, addScript(entry).catch(error => { requests.delete(src); throw error; }));
    return requests.get(src);
  }
  function load() {
    if (ready()) return Promise.resolve();
    if (!pending) {
      sheets.forEach(addSheet);
      pending = Promise.all(scripts.map(request))
        .then(() => { if (!ready()) throw new Error('Arquivos do editor indisponíveis.'); })
        .finally(() => { pending = null; });
    }
    return pending;
  }
  return {load, ready};
})();

// Task markers in the saved Markdown are "- [ ] " and "- [x] " (contract, section 3); Lute writes
// the checked box as "[X]", so only its case is normalised. List markers are left untouched.
const tr=(text,vars)=>window.I18N?window.I18N.t(text,vars):text;
// Typing is read back into the Markdown field after a short pause (drafts stay current).
const SYNC_TYPING=300;
const NAVIGATION=new Set(['Shift','Control','Alt','Meta','CapsLock','Escape','ArrowUp','ArrowDown','ArrowLeft','ArrowRight','Home','End','PageUp','PageDown']);
const isTaskBox=node=>Boolean(node?.matches?.('.vditor-task>input[type="checkbox"]'));
window.normalizarTarefas=text=>String(text).replace(/^(\s*(?:[-*+]|\d+[.)])[ \t]+)\[X\]/gm,'$1[x]');
// Lute's sanitize removes scripts, on* attributes and javascript: links but keeps <iframe>, <object>
// and <embed>. Every HTML the editor renders (preview, visual and split modes) passes through Lute,
// so each Lute instance Vditor creates drops those tags too, even when they point at this origin.
// Escaped text (&lt;iframe) is left as text; the Markdown field keeps what the writer typed.
const EMBUTIDOS=/<\/?(?:iframe|object|embed)\b[^>]*>/gi;
// Repeated until nothing changes, so a tag rebuilt by the removal itself (<ifr<iframe>ame>) also goes.
// Past the limit, any "<" left is escaped: the result is shown as text rather than risk markup.
const VOLTAS_EMBUTIDOS=10;
window.semEmbutidos=html=>{
  let atual=String(html);
  for(let volta=0;volta<VOLTAS_EMBUTIDOS;volta++){
    const limpo=atual.replace(EMBUTIDOS,'');
    if(limpo===atual)return limpo;
    atual=limpo;
  }
  return atual.replace(/</g,'&lt;');
};
window.protegerLute=lute=>{
  for(const name in lute){
    if(typeof lute[name]!=='function'||!/(?:DOM|HTML)$/.test(name))continue;
    const original=lute[name];
    lute[name]=(...args)=>window.semEmbutidos(original.apply(lute,args));
  }
  return lute;
};
function protegerLuteGlobal(){
  if(!window.Lute||window.Lute.semEmbutidos)return;
  const nova=window.Lute.New;
  window.Lute.New=(...args)=>window.protegerLute(nova.apply(window.Lute,args));
  window.Lute.semEmbutidos=true;
}

// Vditor edits Markdown; the existing field remains the persistence boundary.
// Every change (typing, paste, style, task box, inserted reference) reaches the one onInput,
// which feeds the existing autosave. onState reports the block style and mode for the style bar.
window.EditorNotas=class {
  constructor(onInput,onState=()=>{}){
    this.field=document.getElementById('apuracao-texto');
    this.host=document.getElementById('apuracao-vditor');
    this.notice=document.getElementById('apuracao-editor-aviso');
    this.retryButton=document.getElementById('apuracao-editor-tentar');
    this.fallbackLabel=document.getElementById('apuracao-texto-alternativo');
    this.onInput=onInput;
    this.onState=onState;
    this.ready=false;
    this.locked=false;
    this.mark=null;
    this.field.addEventListener('input',onInput);
    this.host.addEventListener('input',event=>{
      if(this.locked||!event.target.matches('.vditor-sv,[contenteditable="true"]'))return;
      this.edited=true;
      this.onInput();
      this.syncSoon(SYNC_TYPING);
    });
    // Vditor reports changes late (after its render delay) and may still report after a note was
    // replaced; only changes the writer started since open() count. Paste, cut, drop, hotkeys and
    // toolbar buttons change the text without a native input event, so they mark it here.
    const touched=()=>{if(!this.locked)this.edited=true;};
    // Capture phase: Vditor may report an input from its own (target) listener before it bubbles here.
    for(const type of ['input','beforeinput','paste','cut','drop'])this.host.addEventListener(type,touched,true);
    // Keys that only move, select or copy change nothing; a late callback after them must stay ignored.
    this.host.addEventListener('keydown',event=>{
      if(NAVIGATION.has(event.key)||((event.ctrlKey||event.metaKey)&&/^[ac]$/i.test(event.key)))return;
      touched();this.syncSoon(0);
    },true);
    // Toolbar buttons and task boxes change the text without a native input event: the change is
    // read right away, so a switch of note, export or reload right after cannot miss it.
    this.host.addEventListener('click',event=>{if(event.target.closest?.('.vditor-toolbar button,.vditor-task>input')){touched();this.syncSoon(0);}},true);
    this.retryButton.addEventListener('click',()=>this.start());
    // Notes may be prefetched while the notebook is hidden; the editor waits until it is shown.
    window.addEventListener('apuracao-abrir',()=>{if(this.wanted&&!this.instance&&!this.failed)this.start();});
  }
  open(text){
    this.field.value=text;
    this.edited=false;
    this.mark=null;
    clearTimeout(this.syncTimer);this.syncTimer=null;
    if(this.ready){this.instance.setValue(text,true);this.report();return;}
    this.wanted=true;
    if(!this.instance&&!this.failed&&!this.host.closest('[hidden]'))this.start();
  }
  status(message,retry=false){
    this.notice.textContent=message;this.notice.hidden=!message;this.retryButton.hidden=!retry;
  }
  start(){
    if(this.loading||this.instance)return;
    this.loading=true;this.failed=false;
    this.status('Carregando o editor de notas…');
    window.CarregadorVditor.load()
      .then(()=>{this.loading=false;this.create();})
      .catch(()=>{this.loading=false;this.fallback();});
  }
  fallback(){
    // The Markdown field keeps editing and saving while the visual editor is missing.
    this.failed=true;this.host.hidden=true;this.fallbackLabel.hidden=false;
    this.status('O editor visual não carregou. Você pode editar e salvar o Markdown abaixo ou tentar de novo.',true);
  }
  create(){
    try{
      if(!window.CarregadorVditor.ready())throw new Error('Arquivos do editor indisponíveis.');
      this.host.hidden=false;this.fallbackLabel.hidden=true;this.status('');
      protegerLuteGlobal();
      this.instance=new Vditor(this.host,{
        cdn:'/vendor/vditor',lang:'pt_BR',i18n:{...window.VditorI18n,wysiwyg:'Edição visual',splitView:'Markdown e prévia'},
        mode:'wysiwyg',value:this.field.value,cache:{enable:false},
        minHeight:360,height:'auto',placeholder:'Escreva sua nota…',
        // The first five stay hidden behind the Caderno's own bar (style, bold, italic, lists);
        // the rest, including the switch to Markdown, open under "Mais".
        toolbar:['headings','bold','italic','list','check','strike','link','ordered-list','quote','line','table','|','undo','redo','edit-mode'],
        toolbarConfig:{pin:false},
        link:{isOpen:false},image:{isPreview:false},hint:{parse:false},
        preview:{
          delay:150,actions:[],mode:'both',hljs:{enable:false},
          // The versioned content theme is already on the page; an empty theme stops Vditor adding its own.
          theme:{current:'',path:''},
          markdown:{sanitize:true,autoSpace:false,fixTermTypo:false,codeBlockPreview:false,mathBlockPreview:false,inlineMath:false},
          render:{media:{enable:false}},
          // Display diagram/formula code literally, without optional renderers or services.
          transform:html=>{
            const template=document.createElement('template');template.innerHTML=html;
            for(const block of template.content.querySelectorAll('[class*="language-"]')){
              if(block.tagName==='CODE'){block.removeAttribute('class');continue;}
              const pre=document.createElement('pre'),code=document.createElement('code');
              code.textContent=block.textContent;pre.append(code);block.replaceWith(pre);
            }
            return window.semEmbutidos(template.innerHTML);
          }
        },
        input:value=>{
          if(!this.ready||this.locked||!this.edited)return;
          const markdown=window.normalizarTarefas(value);
          if(markdown===this.field.value)return;  // a repeat of what the field already holds
          this.field.value=markdown;
          this.onInput();
        },
        after:()=>this.connected()
      });
    }catch(failure){
      this.instance=null;this.fallback();
    }
  }
  connected(){
    this.ready=true;
    // Initialization may finish after another note/case has been selected.
    this.instance.setValue(this.field.value,true);
    for(const field of this.host.querySelectorAll('[contenteditable],textarea')){
      field.setAttribute('aria-label','Texto da nota');
      field.setAttribute('aria-describedby','apuracao-editor-ajuda');
      if(field.hasAttribute('contenteditable')){
        field.setAttribute('role','textbox');field.setAttribute('aria-multiline','true');
      }
    }
    const toolbar=this.host.querySelector('.vditor-toolbar');
    if(toolbar)toolbar.id='apuracao-vditor-barra';
    const decorate=()=>{
      for(const button of this.host.querySelectorAll('button:not([type])'))button.type='button';
      // Task boxes are reachable by keyboard and toggled with Space, like any checkbox.
      for(const box of this.host.querySelectorAll('.vditor-task>input[type="checkbox"]')){
        if(box.getAttribute('tabindex')!=='0')box.setAttribute('tabindex','0');
        if(!box.hasAttribute('aria-label'))box.setAttribute('aria-label',tr('Tarefa concluída'));
      }
    };
    decorate();
    this.buttons=new MutationObserver(decorate);
    this.buttons.observe(this.host,{childList:true,subtree:true});
    this.listen();
    this.disabled(this.locked);
    this.report();
  }
  listen(){
    document.addEventListener('selectionchange',()=>{if(this.remember())this.report();});
    // A click on a task box keeps the writer's caret and selection where they were.
    this.host.addEventListener('pointerdown',event=>{if(isTaskBox(event.target)){this.remember();this.keep=this.mark;}},true);
    this.host.addEventListener('click',event=>{
      if(isTaskBox(event.target)){
        const mark=this.keep||this.mark;this.keep=null;
        setTimeout(()=>{this.restoreRange(mark);this.report();},0);
        return;
      }
    });
    // Vditor stops the click on its mode buttons, so the switch is caught on the way down.
    this.host.addEventListener('click',event=>{
      if(event.target.closest?.('[data-mode]'))setTimeout(()=>{this.mark=null;this.report();},50);
    },true);
    this.host.addEventListener('focusin',()=>this.report());
    this.host.addEventListener('keydown',event=>this.taskKey(event),true);
    this.host.addEventListener('keyup',()=>this.report());
  }
  // Space on a focused box, Space right after the box (start of the item) or Ctrl+Enter anywhere
  // in the item toggles it through Vditor's own click handling, so the Markdown follows.
  taskKey(event){
    if(this.locked||event.altKey)return;
    let box=null;
    if(isTaskBox(event.target)){
      if(event.key===' '||event.key==='Enter')box=event.target;
    }else if(event.key===' '&&!event.ctrlKey&&!event.metaKey&&!event.shiftKey)box=this.caretTask(true);
    else if(event.key==='Enter'&&(event.ctrlKey||event.metaKey))box=this.caretTask(false);
    if(!box)return;
    event.preventDefault();event.stopPropagation();
    if(!isTaskBox(event.target)){this.remember();this.keep=this.mark;}
    box.click();
  }
  caretTask(atStart){
    const selection=window.getSelection?.();
    if(!selection||!selection.rangeCount||!selection.isCollapsed)return null;
    const node=selection.anchorNode,element=node?.nodeType===3?node.parentElement:node;
    const item=element?.closest?.('.vditor-task');
    if(!item||!this.host.contains(item))return null;
    const box=[...item.children].find(isTaskBox);
    if(!box||!atStart)return box||null;
    const before=document.createRange();
    try{before.setStartAfter(box);before.setEnd(selection.anchorNode,selection.anchorOffset);}catch{return null;}
    return before.toString().trim()===''?box:null;
  }
  mode(){return this.instance?.getCurrentMode?.()||'wysiwyg';}
  editable(){
    const selector={wysiwyg:'.vditor-wysiwyg>.vditor-reset',ir:'.vditor-ir>.vditor-reset',sv:'.vditor-sv'}[this.mode()];
    return selector?this.host.querySelector(selector):null;
  }
  // Last caret/selection inside the text, kept while the writer uses the bars, panels or a source.
  remember(){
    const selection=window.getSelection?.(),area=this.editable();
    if(!area||!selection||!selection.rangeCount)return false;
    const range=selection.getRangeAt(0);
    if(!area.contains(range.startContainer)||!area.contains(range.endContainer))return false;
    this.mark=range.cloneRange();
    return true;
  }
  restoreRange(range=this.mark){
    const area=this.editable();
    if(!area||this.locked)return false;
    area.focus({preventScroll:true});
    if(range&&area.contains(range.startContainer)&&area.contains(range.endContainer)){
      const selection=window.getSelection();selection.removeAllRanges();selection.addRange(range);
    }
    return true;
  }
  // Back to the writing point (after the original or a drawer); the page scroll is the caller's.
  resume(){return this.ready&&this.restoreRange(this.mark);}
  style(){
    if(!this.ready||this.mode()==='sv')return '';
    const area=this.editable(),selection=window.getSelection?.();
    let node=this.mark?.startContainer;
    if(selection?.rangeCount&&area?.contains(selection.anchorNode))node=selection.anchorNode;
    const element=node?.nodeType===3?node.parentElement:node;
    const heading=element&&area?.contains(element)?element.closest('h1,h2,h3,h4,h5,h6'):null;
    return heading&&area.contains(heading)?heading.localName:'p';
  }
  report(){this.onState({ready:this.ready&&!this.failed,mode:this.mode(),style:this.style(),locked:this.locked});}
  tool(type){return this.host.querySelector(`.vditor-toolbar [data-type="${type}"]`);}
  hideHint(){for(const hint of this.host.querySelectorAll('.vditor-toolbar .vditor-hint'))hint.style.display='none';}
  // p, h2, h3 (and legacy levels): Vditor removes the heading the caret is in when its button is
  // pressed, and applies a level from its own panel; both keep the caret in the block.
  setStyle(tag){
    if(!this.ready||this.locked||this.mode()==='sv'||!/^(p|h[1-6])$/.test(tag))return false;
    this.edited=true;
    this.restoreRange();
    const current=this.style(),headings=this.tool('headings');
    if(current===tag||!headings)return current===tag;
    // Vditor rebuilds the block and leaves a collapsed caret; the selection is put back by offsets.
    const kept=this.blockOffsets();
    // Vditor's headings button removes the heading only when marked current, a state it refreshes
    // later and only after its own clicks; the caret's real block decides here.
    headings.classList.toggle('vditor-menu--current',current!=='p');
    if(current!=='p')headings.click();
    if(tag!=='p')this.host.querySelector(`.vditor-toolbar .vditor-hint button[data-tag="${tag}"]`)?.click();
    this.hideHint();
    if(kept)this.selectOffsets(kept);
    this.remember();this.report();this.syncSoon(0);
    return true;
  }
  block(node){
    const element=node?.nodeType===3?node.parentElement:node,area=this.editable();
    const block=element?.closest?.('p,li,h1,h2,h3,h4,h5,h6');
    return block&&area?.contains(block)?block:null;
  }
  blockOffsets(){
    const selection=window.getSelection?.();
    if(!selection?.rangeCount)return null;
    const range=selection.getRangeAt(0),block=this.block(range.startContainer);
    if(!block||!block.contains(range.endContainer))return null;
    const measure=(node,offset)=>{const part=document.createRange();part.setStart(block,0);part.setEnd(node,offset);return part.toString().length;};
    return {start:measure(range.startContainer,range.startOffset),end:measure(range.endContainer,range.endOffset),text:block.textContent};
  }
  selectOffsets({start,end,text}){
    const selection=window.getSelection(),block=selection.rangeCount?this.block(selection.anchorNode):null;
    if(!block||block.textContent!==text)return;
    const point=offset=>{
      const walker=document.createTreeWalker(block,NodeFilter.SHOW_TEXT);let seen=0;
      for(let node=walker.nextNode();node;node=walker.nextNode()){if(seen+node.data.length>=offset)return [node,offset-seen];seen+=node.data.length;}
      return [block,block.childNodes.length];
    };
    const range=document.createRange();range.setStart(...point(start));range.setEnd(...point(end));
    selection.removeAllRanges();selection.addRange(range);
  }
  command(type){
    if(!this.ready||this.locked)return;
    this.edited=true;
    this.restoreRange();
    this.tool(type)?.click();
    this.remember();this.report();this.syncSoon(0);
  }
  // A new unchecked item at the writing point, ready for typing: inside a task list, a new item
  // after the current one; elsewhere Vditor turns the current line into a task.
  insertTask(){
    if(!this.ready||this.locked)return;
    this.edited=true;
    this.restoreRange();
    const item=this.currentItem();
    if(item?.classList.contains('vditor-task')&&this.mode()!=='sv')this.newItemAfter(item);
    else this.tool('check')?.click();
    const created=this.currentItem(),list=created?.parentElement;
    // Vditor starts new lists with "*"; the contract writes tasks as "- [ ] ".
    if(created&&list?.dataset.marker==='*'&&list.children.length===1){list.dataset.marker='-';created.dataset.marker='-';}
    this.remember();this.report();this.syncSoon(0);
  }
  currentItem(){
    const selection=window.getSelection?.(),node=selection?.rangeCount?selection.anchorNode:null;
    const item=(node?.nodeType===3?node.parentElement:node)?.closest?.('li');
    return item&&this.host.contains(item)?item:null;
  }
  newItemAfter(item){
    const created=document.createElement('li');
    created.className='vditor-task';created.dataset.marker=item.dataset.marker||'-';
    const box=document.createElement('input');box.type='checkbox';
    const text=document.createTextNode(' ');
    created.append(box,text);item.after(created);
    const selection=window.getSelection(),range=document.createRange();
    range.setStart(text,1);range.collapse(true);selection.removeAllRanges();selection.addRange(range);
    // Vditor re-reads the edited block on input and writes the Markdown through onInput.
    this.editable()?.dispatchEvent(new InputEvent('input',{bubbles:true,inputType:'insertParagraph'}));
  }
  toggleMore(force){
    const open=this.host.classList.toggle('caderno-mais-aberto',force);
    this.hideHint();
    return open;
  }
  // Brings the backing field up to date with the editor and reports a difference through onInput
  // (the same path as typing). Called before any save, note switch, export or unload.
  sync(){
    clearTimeout(this.syncTimer);this.syncTimer=null;
    if(!this.ready||!this.edited||this.locked)return false;
    const value=window.normalizarTarefas(this.instance.getValue());
    if(value===this.field.value)return false;
    this.field.value=value;this.onInput();
    return true;
  }
  syncSoon(delay){clearTimeout(this.syncTimer);this.syncTimer=setTimeout(()=>this.sync(),delay);}
  flush(){
    // Read pending browser input before locking the editor for a save.
    // Untouched notes retain their original Markdown, including whitespace.
    if(this.ready&&this.edited)this.field.value=window.normalizarTarefas(this.instance.getValue());
  }
  disabled(value){
    if(this.locked===value&&this.appliedLock===value)return;
    this.locked=value;
    this.host.inert=value;
    this.host.setAttribute('aria-busy',String(value));
    if(this.ready){
      if(value)this.instance.disabled();else this.instance.enable();
      this.appliedLock=value;
    }
    this.report();
  }
};
