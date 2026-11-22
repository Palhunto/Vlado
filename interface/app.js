'use strict';
const $ = id => document.getElementById(id);
const token = document.querySelector('meta[name="session-token"]').content;
let cases = [], catalogLoaded = false, epoch = 0, searchSequence = 0, lastQuery = null, lastResult = null;
const selection = () => ({caso: $('caso').value, rodada: $('rodada').value, geracao: $('geracao').value});
const element = (tag, text, className) => {
  const node = document.createElement(tag);
  if (text !== undefined) node.textContent = text;
  if (className) node.className = className;
  return node;
};
function options(id, items, placeholder) {
  const select = $(id);
  select.replaceChildren(new Option(placeholder, ''), ...items.map(item => new Option(item.label, item.value)));
  select.disabled = !items.length;
}
function error(message = '') { $('erro').textContent = message; $('erro').hidden = !message; }
function empty(title, message) {
  $('inicio').hidden = false;
  $('inicio').querySelector('h2').textContent = title;
  $('inicio').querySelector('p').textContent = message;
}
function reset() {
  epoch++; searchSequence++;
  lastQuery = null; lastResult = null;
  $('saida').hidden = true; $('cobertura').hidden = true;
  $('busca-limitacoes').hidden = true;
  $('resultados').replaceChildren();
  $('consulta').disabled = true; $('buscar').disabled = true;
  $('documento').replaceChildren(new Option('Todos os documentos', ''));
  $('pagina').value = ''; $('status').textContent = ''; error();
  resetFindings();
}
// A failure marked `rede` never reached the application: no network, or a gateway answering for
// an unreachable server. Callers may retry it; the operation itself may still be running.
function networkFailure(message, cause) {
  const failure = new Error(message);
  failure.rede = true; failure.cause = cause;
  return failure;
}
async function api(operation, data, binary = false) {
  let response;
  try {
    response = await fetch(`/api/${operation}`, {method: 'POST',
      headers: {'Content-Type': 'application/json', 'X-Session-Token': token}, body: JSON.stringify(data)});
  } catch (cause) { throw networkFailure('Sem conexão com o servidor.', cause); }
  if (binary && response.ok) return response.blob();
  let result;
  try { result = await response.json(); }
  catch (cause) {
    if ([502, 503, 504].includes(response.status)) throw networkFailure('Sem conexão com o servidor.', cause);
    throw new Error(window.I18N?.erro ? window.I18N.erro({}) : 'Não foi possível completar a operação.');
  }
  if (!response.ok) {
    // One place turns server errors into the interface language (by `codigo` in English).
    const failure = new Error(window.I18N?.erro ? window.I18N.erro(result) : result.erro || 'Não foi possível completar a operação.');
    failure.result = result;
    throw failure;
  }
  return result;
}
async function loadCatalog() {
  const previous = selection();
  reset();
  const version = epoch;
  options('caso', [], 'Carregando casos…');
  options('rodada', [], 'Selecione uma análise'); options('geracao', [], 'Selecione a versão');
  updateScopeHeading();
  empty('Selecione um caso para começar', 'A pesquisa usa os documentos preservados de uma análise existente.');
  try {
    const response = await fetch('/api/catalogo');
    const data = await response.json();
    if (!response.ok) throw new Error(data.erro || 'Erro ao carregar os casos.');
    if (version !== epoch) return;
    cases = data.casos;
    const previousUploadCase = $('cadastro-caso').value;
    $('cadastro-caso').replaceChildren(new Option('Novo caso', ''), ...cases.map(c => new Option(c.titulo, c.id)));
    if (cases.some(c => c.id === previousUploadCase)) $('cadastro-caso').value = previousUploadCase;
    toggleNewCase();
    options('caso', cases.map(c => ({value:c.id, label:c.titulo})), 'Selecione um caso');
    $('acervo-escolha').open = true;
    updateScopeHeading();
    $('status').textContent = `${cases.length} caso(s) cadastrado(s). Escolha o acervo que deseja consultar.`;
    if (!cases.length) empty('Comece sua primeira apuração', 'Abra Cadastrar documentos ou use Começar uma apuração na tela inicial.');
    if(cases.some(c=>c.id===previous.caso)){
      $('caso').value=previous.caso; $('caso').dispatchEvent(new Event('change'));
      if([...$('rodada').options].some(o=>o.value===previous.rodada)){
        $('rodada').value=previous.rodada; $('rodada').dispatchEvent(new Event('change'));
        if([...$('geracao').options].some(o=>o.value===previous.geracao)){ $('geracao').value=previous.geracao; $('geracao').dispatchEvent(new Event('change')); }
      }
    }
    catalogLoaded = true;
    window.dispatchEvent(new Event('catalogo-carregado'));
  } catch (failure) { if (version === epoch) error(failure.message); }
}
$('atualizar').addEventListener('click', loadCatalog);
$('caso').addEventListener('change', () => {
  reset();
  const current = cases.find(c => c.id === $('caso').value);
  options('rodada', (current?.rodadas || []).map(r => ({value:r.id, label:`Análise ${parseInt(r.id.slice(1), 10)} · documentos preservados (${r.id})`})), 'Selecione uma análise');
  options('geracao', [], 'Selecione a versão');
  if (!current) empty('Selecione um caso para começar', 'A pesquisa usa os documentos preservados de uma análise existente.');
  else if (!current.rodadas.length) empty('Esta apuração ainda não tem análises', 'Abra Perguntar à IA e envie sua pergunta. Os documentos já cadastrados serão preservados nesta análise.');
  else empty('Escolha uma análise', 'Cada análise mantém sua própria versão dos documentos e da busca.');
  if (current) {
    const captured = epoch;
    api('analises',{caso:current.id}).then(result=>{
      if($('caso').value!==current.id || !cases.includes(current))return;
      for(const analysis of result.analises){
        const option=[...$('rodada').options].find(o=>o.value===analysis.id);
        if(!option)continue;
        const date=analysis.data?new Date(analysis.data).toLocaleDateString('pt-BR'):'';
        option.textContent=analysis.pergunta?`${date} · ${analysis.pergunta.replace(/\s+/g,' ').slice(0,160)} (${analysis.id})`:`Análise ${analysis.id} · metadados indisponíveis`;
        option.dataset.descricao=analysis.pergunta?`${analysis.pergunta} · Documentos: ${analysis.documentos} · ${date}`:analysis.aviso;
        option.dataset.dia=analysis.data?new Date(analysis.data).toLocaleDateString('pt-BR',{day:'2-digit',month:'2-digit'}):'';
      }
      updateScopeHeading();versionChip();
    }).catch(failure=>{if(captured===epoch)$('status').textContent=`Não foi possível carregar os títulos das análises: ${failure.message}`;});
  }
});
$('rodada').addEventListener('change', () => {
  reset();
  const current = cases.find(c => c.id === $('caso').value)?.rodadas.find(r => r.id === $('rodada').value);
  options('geracao', (current?.geracoes || []).map(g => ({value:g, label:`Versão ${g.replace(/^g/,'')} (${g})`})), 'Selecione a versão');
  $('busca-tecnica').open = Boolean(current);
  empty(current && !current.geracoes.length ? 'Análise sem busca disponível' : 'Escolha a versão da busca',
    current && !current.geracoes.length ? 'A busca desta análise ainda não foi construída. A tela não a constrói nem sobrescreve.' : 'A cobertura será conferida antes da pesquisa.');
});
function updateScopeHeading() {
  const current = cases.find(c => c.id === $('caso').value);
  $('contexto-pauta').textContent = current?.titulo || 'Selecione uma apuração';
  $('contexto-rodada').textContent = current
    ? `${current.titulo} · ${$('rodada').value ? `Análise ${parseInt($('rodada').value.slice(1),10)} (${$('rodada').value})` : 'Nenhuma análise selecionada.'} · Versão da busca: ${$('geracao').value || 'não selecionada'}`
    : 'Nenhuma análise selecionada.';
  if($('rodada').selectedOptions[0]?.dataset.descricao)$('contexto-rodada').textContent+=' · '+$('rodada').selectedOptions[0].dataset.descricao;
}
for (const id of ['caso','rodada','geracao']) $(id).addEventListener('change', updateScopeHeading);
$('rodada').addEventListener('change', () => { if ($('rodada').value) $('acervo-escolha').open = true; });
$('geracao').addEventListener('change', async () => {
  reset();
  const version = epoch;
  if (!$('geracao').value) { empty('Escolha a versão da busca', 'A cobertura será conferida antes da pesquisa.'); return; }
  $('busca-tecnica').open = true;
  $('status').textContent = 'Conferindo índice e cobertura…';
  try {
    const result = await api('cobertura', selection());
    if (version !== epoch) return;
    const coverage = result.cobertura;
    options('documento', coverage.documentos.map(d => ({value:d.documento_id,
      label:`${Leitura.nome(d)}${d.pesquisavel ? '' : ' · sem texto pesquisável'}`})), 'Todos os documentos');
    $('cobertura-resumo').textContent = `Texto pesquisável: ${coverage.documentos_pesquisaveis} de ${coverage.total_documentos} documento(s) · ver cobertura e limitações`;
    const list = element('ul');
    for (const doc of coverage.documentos) {
      const item = element('li', `${Leitura.nome(doc)} — ${doc.pesquisavel ? 'com texto pesquisável' : 'sem texto pesquisável'}`);
      const sources = element('ul');
      for (const source of doc.fontes) {
        const missing = source.unidades.filter(u => !u.trechos);
        const count = source.unidades.filter(u => u.trechos).length;
        const sourceItem = element('li', `${count} unidade(s) pesquisável(is)`);
        sourceItem.append(Leitura.tecnicos(`${source.arquivo} · ${source.metodo}`));
        if (missing.length) {
          const gaps = element('ul');
          for (const unit of missing) gaps.append(element('li', `${unit.pagina_pdf ? `Página PDF ${unit.pagina_pdf}` : `Unidade ${unit.ordem}`}: ${unit.motivo || unit.estado}`));
          sourceItem.append(gaps);
        }
        sources.append(sourceItem);
      }
      item.append(sources); list.append(item);
    }
    $('cobertura-dados').replaceChildren(list, Leitura.tecnicos(coverage.aviso, `Registro: ${result.arquivo_log}`));
    const gaps = [];
    for (const doc of coverage.documentos) {
      const sources = doc.fontes.filter(s => s.tipo === 'derivado' || !doc.pesquisavel);
      const missing = sources.flatMap(s => s.unidades.filter(u => !u.trechos));
      if (missing.length) gaps.push(`${Leitura.nome(doc)}: ${missing.filter(u => u.pagina_pdf).length ? 'páginas sem texto pesquisável: ' + [...new Set(missing.filter(u => u.pagina_pdf).map(u => u.pagina_pdf))].join(', ') : 'sem texto pesquisável'}. Consulte o original.`);
    }
    $('busca-limitacoes').replaceChildren(...gaps.map(g => element('p', g)));
    $('busca-limitacoes').hidden = !gaps.length;
    $('cobertura').hidden = false;
    const ready = coverage.documentos_pesquisaveis > 0;
    $('consulta').disabled = !ready; $('buscar').disabled = !ready;
    $('status').textContent = 'Acervo conferido e pronto para consulta.';
    empty(ready ? 'Acervo pronto para pesquisar' : 'Não há texto pesquisável neste índice', ready
      ? 'Digite um termo ou uma expressão. Abra os filtros para restringir por documento ou página.'
      : 'Consulte a cobertura. PDFs e imagens precisam de cópias textuais autorizadas ou leitura direta pela IA.');
  } catch (failure) {
    if (version === epoch) { $('status').textContent = 'Índice indisponível.'; error(failure.message); empty('Não foi possível consultar este índice', 'Confira o erro antes de continuar. Uma falha no índice não equivale a uma pesquisa sem resultados.'); }
  }
});
$('modo').addEventListener('change', () => {
  $('ajuda-modo').textContent = {
    comum:'Busca todas as palavras; use aspas para manter uma expressão junta. Ignora diferenças de caixa e acentos.',
    literal:'Procura o texto exato, inclusive maiúsculas, acentos e pontuação. Útil para códigos e identificadores.',
    fts:'Sintaxe FTS5: use OR para alternativas e * para prefixos. Exemplo: contrato OR aditiv*.'
  }[$('modo').value];
});
function download(blob, name) {
  // App Android: o WebMessageListener injeta window.VladoAndroid só na origem autorizada
  // ({nome, tipo, base64}); a WebView não grava `blob:` sozinha. Ver docs/ANDROID.md.
  const ponte = window.VladoAndroid;
  if (ponte && typeof ponte.postMessage === 'function') {
    if (blob.size > 25 * 1024 * 1024) { window.alert?.('Arquivo grande demais para baixar pelo app (limite de 25 MB). Use a Mesa no navegador.'); return; }
    const leitor = new FileReader();
    leitor.onload = () => {
      const dados = String(leitor.result);
      ponte.postMessage(JSON.stringify({nome: name, tipo: blob.type || '', base64: dados.slice(dados.indexOf(',') + 1)}));
    };
    leitor.onerror = () => window.alert?.('Não foi possível preparar o arquivo para download.');
    leitor.readAsDataURL(blob);
    return;
  }
  const url = URL.createObjectURL(blob), anchor = element('a');
  anchor.href = url; anchor.download = name; document.body.append(anchor); anchor.click(); anchor.remove();
  setTimeout(() => URL.revokeObjectURL(url), 120000); // slow WebViews may still be reading a large file
}
function renderHit(hit, scope, version) {
  const card = element('article', undefined, 'result');
  const filename = hit.original.split('/').pop();
  card.append(element('h3', Leitura.fonte(hit)),
    element('pre', hit.trecho));
  const actions = element('div', undefined, 'actions');
  const contextButton = element('button', 'Ver contexto completo', 'secondary');
  const originalButton = element('button', Leitura.rotuloOriginal(Leitura.pagina(hit)), 'secondary');
  const copy = element('button', 'Copiar referência', 'secondary');
  const context = element('div', undefined, 'context'); context.hidden = true;
  const feedback = element('p', '', 'small'); feedback.setAttribute('role', 'status');
  let loaded = false;
  contextButton.addEventListener('click', async () => {
    if (loaded) { context.hidden = !context.hidden; contextButton.textContent = context.hidden ? 'Ver contexto completo' : 'Ocultar contexto'; return; }
    contextButton.disabled = true;
    try {
      const result = await api('ler', {...scope, referencia:hit.referencia});
      if (version !== epoch) return;
      context.append(element('p', result.aviso, 'small'));
      for (const line of result.unidade_completa) context.append(element('p', `L${line.linha}  ${line.texto}`));
      context.append(Leitura.tecnicos(`Registro: ${result.arquivo_log}`));
      context.hidden = false; loaded = true; contextButton.textContent = 'Ocultar contexto';
    } catch (failure) { feedback.textContent = failure.message; }
    finally { contextButton.disabled = false; }
  });
  originalButton.addEventListener('click', async () => {
    originalButton.disabled = true;
    try {
      const blob = await api('original', {...scope, referencia:hit.referencia}, true);
      if (version === epoch) await window.abrirOriginal(blob, filename, hit.pagina_pdf, hit.trecho);
    } catch (failure) { feedback.textContent = failure.message; }
    finally { originalButton.disabled = false; }
  });
  copy.addEventListener('click', async () => {
    const text = `${scope.caso}/${scope.rodada}/${scope.geracao} · ${hit.documento_id} · ${hit.pagina_pdf ? `p. PDF ${hit.pagina_pdf}, ` : ''}linhas ${hit.linha_inicio}–${hit.linha_fim}\nReferência: ${hit.referencia}\nFonte textual: ${hit.fonte_textual}\n${hit.trecho}`;
    try { await navigator.clipboard.writeText(text); feedback.textContent = 'Referência e trecho copiados.'; }
    catch { feedback.textContent = 'Não foi possível copiar automaticamente. Selecione a referência abaixo.'; }
  });
  actions.append(contextButton, originalButton, copy);
  const notebook = element('button','Registrar trecho com fonte','secondary'); notebook.type='button';
  notebook.addEventListener('click',()=>window.abrirRegistroCaderno({...scope,documento_id:hit.documento_id,
    pagina_pdf:hit.pagina_pdf,localizador:`Linhas ${hit.linha_inicio}–${hit.linha_fim}`,
    trecho:window.trechoSelecionadoCaderno(card.querySelector('pre'),hit.trecho)}));
  actions.append(notebook);
  actions.append(window.botaoAdicionarApuracao({...scope,tipo:'pesquisa',referencia:hit.referencia},card.querySelector('pre'),hit.trecho));
  const technical = element('details', undefined, 'technical');
  technical.append(element('summary','Detalhes técnicos'),
    element('p', `${scope.caso}/${scope.rodada}/${scope.geracao} · ${hit.documento_id}`, 'meta'),
    element('p', `Fonte textual: ${hit.fonte_textual} · Método: ${hit.metodo}`, 'meta'),
    element('p', `Referência: ${hit.referencia} · SHA-256 do original: ${hit.original_sha256}`, 'meta'),
    element('p', `Linhas ${hit.linha_inicio}–${hit.linha_fim} · ${hit.linhas_referem_se_a}`, 'meta'));
  card.append(actions, context, technical, feedback);
  return card;
}
async function search(query) {
  const version = epoch, sequence = ++searchSequence;
  error(); $('buscar').disabled = true; $('anterior').disabled = true; $('proximo').disabled = true;
  $('saida').hidden = true; $('inicio').hidden = true; lastResult = null;
  $('status').textContent = 'Pesquisando no acervo selecionado…';
  try {
    const result = await api('buscar', query);
    if (version !== epoch || sequence !== searchSequence) return;
    lastQuery = {...query}; lastResult = result;
    $('resultados').replaceChildren(...result.resultados.map(hit => renderHit(hit, query, version)));
    $('total').textContent = `${result.total_correspondencias} trecho(s) encontrado(s)`;
    $('saida').hidden = false;
    $('anterior').disabled = !result.deslocamento;
    $('proximo').disabled = result.proximo_deslocamento === null;
    $('intervalo').textContent = result.retornados ? `${result.deslocamento + 1}–${result.deslocamento + result.retornados} de ${result.total_correspondencias}` : '0 resultados';
    $('log').textContent = `Registro bruto: ${result.arquivo_log} · Consulta: ${result.consulta_recebida}`;
    $('status').textContent = 'Pesquisa concluída.';
    window.registrarPaginaMesa?.('documentos', result.deslocamento);
    if (!result.retornados) empty('Nenhum trecho encontrado', 'Tente outros termos, retire filtros ou consulte a cobertura do acervo. A busca não inclui conteúdo visual sem texto autorizado.');
    $('total').focus();
  } catch (failure) {
    if (version !== epoch || sequence !== searchSequence) return;
    error(failure.message);
    $('status').textContent = failure.result?.arquivo_log ? `Erro registrado em ${failure.result.arquivo_log}` : 'Não foi possível pesquisar.';
    empty('A pesquisa não foi concluída', 'Confira o erro e ajuste a consulta ou a seleção do índice.');
  } finally { if (version === epoch && sequence === searchSequence) $('buscar').disabled = false; }
}
$('pesquisa').addEventListener('submit', event => {
  event.preventDefault();
  if ($('buscar').disabled) return;
  const doc = $('documento').value;
  search({...selection(), consulta:$('consulta').value, modo:$('modo').value,
    documentos:doc ? [doc] : [], pagina:$('pagina').value ? Number($('pagina').value) : null,
    limite:Number($('limite').value), deslocamento:window.paginaRestauradaMesa?.('documentos') || 0});
});
$('anterior').addEventListener('click', () => { if (lastQuery) search({...lastQuery, deslocamento:Math.max(0, lastQuery.deslocamento - lastQuery.limite)}); });
$('proximo').addEventListener('click', () => { if (lastResult?.proximo_deslocamento != null) search({...lastQuery, deslocamento:lastResult.proximo_deslocamento}); });
$('exportar').addEventListener('click', () => {
  if (lastResult) window.exportarEditorial(lastResult,`pesquisa_${lastResult.caso_id}_${lastResult.rodada}_${lastResult.geracao}`,$('pesquisa-formato').value);
});
let inventorySequence = 0, draftCaseId = '', pdfAvailable = false, ocrAvailable = false, cadastroBusy = false;
async function loadPdfEnvironment() {
  try {
    const environment = await api('ambiente', {});
    pdfAvailable = Boolean(environment.extracao_pdf?.disponivel);
    ocrAvailable = Boolean(environment.ocr?.disponivel);
    $('pdf-ambiente-aviso').textContent = pdfAvailable ? '' : 'O extrator de PDF está indisponível nesta instância. Encerre a Mesa e reabra pelo iniciador atualizado. Os arquivos enviados serão preservados, mas os PDFs ficarão sem texto preparado.';
    $('pdf-ambiente-aviso').hidden = pdfAvailable;
    $('pdf-ambiente-tecnico').replaceChildren(Leitura.tecnicos(element('pre', JSON.stringify(environment, null, 2), 'raw-briefing')));
  } catch (failure) {
    pdfAvailable = false;
    $('pdf-ambiente-aviso').textContent = 'Não foi possível verificar o extrator de PDF. Encerre e reabra a Mesa pelo iniciador atualizado.';
    $('pdf-ambiente-aviso').hidden = false;
  }
  $('cadastro-preparar').disabled = !pdfAvailable || cadastroBusy;
}
function uploadError(message = '') {
  $('cadastro-erro').textContent = message;
  $('cadastro-erro').hidden = !message;
}
function toggleNewCase() {
  const isNew = !$('cadastro-caso').value;
  $('novo-caso-campos').hidden = !isNew;
  for (const id of ['cadastro-titulo-input']) {
    $(id).required = isNew;
    $(id).disabled = !isNew;
  }
  window.FontesWeb?.alternarNovo(isNew);
}
function extractionMessage(info) {
  if (!info) return '';
  const labels = {extraido:'Texto extraído', parcial:'Extração parcial',
    sem_texto: info.ocr_tentado ? 'Sem texto extraível, mesmo após OCR' : 'Sem texto extraível; pode precisar de OCR',
    erro: info.protegido ? 'PDF protegido por senha; texto não extraído; original preservado' : 'Falha na extração; original preservado'};
  let message = labels[info.estado] || 'Extração não informada';
  if (info.paginas_pdf != null) message += ` · ${info.paginas_com_texto} de ${info.paginas_pdf} página(s) com texto`;
  if (info.paginas_sem_texto?.length) message += ` · Sem texto: página(s) ${info.paginas_sem_texto.join(', ')}`;
  if (info.paginas_com_erro?.length) message += ` · Com erro: página(s) ${info.paginas_com_erro.map(p => p.pagina_pdf).join(', ')}`;
  return message;
}
function extractionDetails(info) {
  // One short line per fact so each line can be translated as a whole.
  const lines = [], pages = list => list.join(', ');
  if (!info || info.paginas_pdf == null) return lines;
  const native = info.paginas_texto_nativo;
  if (native?.length) lines.push(`Texto nativo: ${native.length} página(s)`);
  if (info.paginas_ocr?.length) {
    lines.push(`Reconhecidas por OCR: página(s) ${pages(info.paginas_ocr)}`);
    const engine = info.ocr_motor;
    if (engine) lines.push(`Motor de OCR: ${engine.motor} ${Object.entries(engine.versoes || {}).filter(([, v]) => v).map(([k, v]) => `${k} ${v}`).join(', ')} · idiomas ${engine.idiomas}`);
    lines.push('O texto de OCR é reconhecimento automático e pode conter erros; confira o original.');
  }
  const ocrFailures = (info.paginas_com_erro || []).filter(p => p.etapa === 'ocr').map(p => p.pagina_pdf);
  if (ocrFailures.length) lines.push(`Falha no OCR: página(s) ${pages(ocrFailures)}`);
  if (info.ocr_indisponivel && info.paginas_sem_texto?.length) lines.push(`OCR não executado: ${info.ocr_indisponivel}`);
  return lines;
}
function appendExtraction(row, info, limited) {
  if (!info) return;
  row.append(element('p', extractionMessage(info), limited ? 'limitation' : 'small'));
  for (const line of extractionDetails(info)) row.append(element('p', line, 'small'));
}
function ocrNeeded(doc) {
  const info = doc.extracao_pdf;
  return Boolean(ocrAvailable && info && info.estado !== 'erro'
    && ((info.paginas_sem_texto?.length && !info.ocr_tentado) || (info.paginas_com_erro || []).some(p => p.etapa === 'ocr')));
}
function pageSummary(result) {
  const s = result.extracao_pdf_resumo;
  if (!s || s.paginas_ocr === undefined) return null;
  return `Páginas: ${s.paginas_texto_nativo} com texto nativo · ${s.paginas_ocr} por OCR · ${s.paginas_sem_texto} sem texto · ${s.paginas_com_erro} com falha`;
}
function showInventory(data) {
  const list = element('ul', undefined, 'document-list');
  for (const doc of data.documentos) {
    const row = element('li');
    row.append(element('strong', Leitura.nome(doc)));
    appendExtraction(row, doc.extracao_pdf, Leitura.lacunas(doc).length);
    row.append(Leitura.tecnicos(element('pre', JSON.stringify(doc, null, 2), 'raw-briefing')));
    list.append(row);
  }
  $('cadastro-inventario').replaceChildren(element('h3', `${Leitura.quantidade(data.total_documentos, 'documento')} nesta apuração`), list,
    Leitura.tecnicos(`Apuração: ${data.caso_id} · Corpus: ${data.corpus_id}`));
  $('cadastro-inventario').hidden = false;
  const pending = data.documentos.filter(doc => /\.pdf$/i.test(doc.nome_recebido || doc.arquivo || '') && (!doc.extracao_pdf || doc.extracao_pdf.estado === 'erro' || ocrNeeded(doc)));
  $('cadastro-preparacao').hidden = !pending.length;
  $('cadastro-preparacao-resumo').textContent = `${Leitura.quantidade(pending.length, 'PDF pendente de preparação', 'PDFs pendentes de preparação')}. Você pode tentar extrair o texto sem enviar os arquivos novamente.`;
  $('cadastro-preparar').disabled = !pdfAvailable || cadastroBusy;
  window.FontesWeb?.mostrar(data);
}
function renderReceipt(result, preparation = false) {
  const list = element('ul', undefined, 'document-list');
  for (const item of result.arquivos) {
    const row = element('li', `${Leitura.nome(item)} · ${preparation ? 'original já cadastrado' : item.estado === 'duplicado' ? 'duplicata identificada' : 'cadastrado'}`);
    appendExtraction(row, item.extracao_pdf, Leitura.lacunas(item).length);
    row.append(Leitura.tecnicos(element('pre', JSON.stringify(item, null, 2), 'raw-briefing')));
    list.append(row);
  }
  $('cadastro-recibo').replaceChildren(element('h3', preparation ? `Preparação conferida: ${Leitura.quantidade(result.recebidos, 'PDF')}` : `Envio conferido: ${result.recebidos} de ${result.arquivos.length} arquivo(s)`),
    element('p', preparation ? 'Novos derivados registrados, sem alterar os originais.' : `${result.novos} novo(s) · ${result.duplicados} duplicado(s) · ${result.total_documentos} documento(s) no caso.`),
    ...(pageSummary(result) ? [element('p', pageSummary(result), 'small')] : []),
    list, Leitura.tecnicos(`Apuração: ${result.caso_id} · Corpus: ${result.corpus_id} · Recibo: ${result.arquivo_recibo}`));
  $('cadastro-recibo').hidden = false;
}
$('cadastro-preparar').addEventListener('click', async () => {
  const caso = $('cadastro-caso').value;
  if (!caso || cadastroBusy || !pdfAvailable) return;
  cadastroBusy = true; ++inventorySequence; uploadError();
  $('cadastro-preparar').disabled = true;
  for (const control of $('cadastro').elements) control.disabled = true;
  $('cadastro-status').textContent = 'Preparando o texto dos PDFs já cadastrados…';
  try {
    const result = await api('preparar-pdfs', {caso});
    renderReceipt(result, true); showInventory(result.inventario);
    const pdf = result.extracao_pdf_resumo;
    $('cadastro-status').textContent = pdf.erro || pdf.parcial || pdf.sem_texto
      ? 'Preparação concluída com limitações. Confira as páginas sem texto e os erros no recibo.'
      : 'PDFs preparados. Aguardando sua pergunta.';
  } catch (failure) {
    uploadError(failure.message);
    $('cadastro-status').textContent = 'A preparação não foi confirmada. Os originais continuam preservados.';
  } finally {
    cadastroBusy = false;
    for (const control of $('cadastro').elements) control.disabled = false;
    toggleNewCase(); $('cadastro-preparar').disabled = !pdfAvailable;
  }
});
$('cadastro-caso').addEventListener('change', async () => {
  const sequence = ++inventorySequence;
  toggleNewCase(); uploadError();
  $('cadastro-recibo').hidden = true; $('cadastro-inventario').hidden = true;
  $('cadastro-preparacao').hidden = true;
  $('cadastro-status').textContent = '';
  const caso = $('cadastro-caso').value;
  if (!caso) return;
  $('cadastro-status').textContent = 'Conferindo os documentos já cadastrados…';
  try {
    const data = await api('inventario', {caso});
    if (sequence !== inventorySequence) return;
    showInventory(data); $('cadastro-status').textContent = 'Pronto para receber outro lote neste caso.';
  } catch (failure) { if (sequence === inventorySequence) uploadError(failure.message); }
});
$('cadastro-arquivos').addEventListener('change', () => {
  const files = Array.from($('cadastro-arquivos').files);
  $('arquivos-selecionados').textContent = files.length
    ? `${files.length} arquivo(s) selecionado(s): ${files.map(f => f.name).join(', ')}`
    : 'Selecione todos os arquivos do lote. Até 50 MB por envio.';
});
$('cadastro-titulo-input').addEventListener('input', () => { draftCaseId = ''; });
function encodeFile(file) {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => resolve({nome:file.name, base64:reader.result.split(',')[1]});
    reader.onerror = () => reject(new Error(`Não foi possível ler ${file.name}. Nenhum envio iniciado.`));
    reader.readAsDataURL(file);
  });
}
$('cadastro').addEventListener('submit', async event => {
  event.preventDefault(); uploadError();
  if (cadastroBusy) return;
  const files = Array.from($('cadastro-arquivos').files);
  if (!files.length) return;
  if (files.reduce((sum, file) => sum + file.size, 0) > 50 * 1024 * 1024) {
    uploadError('O lote excede 50 MB. Divida o envio em lotes menores; nenhum arquivo foi enviado.'); return;
  }
  const isNew = !$('cadastro-caso').value;
  if (isNew && !draftCaseId) draftCaseId = 'apuracao_' + crypto.randomUUID().replaceAll('-', '');
  const scope = {novo:isNew, caso:isNew ? draftCaseId : $('cadastro-caso').value,
    titulo:$('cadastro-titulo-input').value, natureza:$('cadastro-natureza').value,
    ...(isNew ? window.FontesWeb?.escopoNovo() : {})};
  cadastroBusy = true; $('cadastro-preparar').disabled = true;
  ++inventorySequence;
  for (const control of $('cadastro').elements) control.disabled = true;
  $('cadastro-recibo').hidden = true; $('cadastro-perguntar').hidden=true;
  $('cadastro-status').textContent = `Enviando e cadastrando ${files.length} arquivo(s)…`;
  try {
    const arquivos = await Promise.all(files.map(encodeFile));
    const result = await api('cadastrar', {...scope, arquivos});
    if (result.recebidos !== files.length || result.arquivos.length !== files.length) {
      throw new Error('Recibo incompleto. Confira o inventário antes de considerar o lote confirmado.');
    }
    renderReceipt(result);
    showInventory(result.inventario);
    await loadCatalog();
    $('cadastro-caso').value = result.caso_id;
    window.definirContextoCaso?.(result.caso_id);
    $('cadastro-perguntar').dataset.caso=result.caso_id; $('cadastro-perguntar').hidden=false;
    draftCaseId = '';
    toggleNewCase();
    $('cadastro-arquivos').value = '';
    $('arquivos-selecionados').textContent = 'Pronto para selecionar outro lote.';
    const pdf = result.extracao_pdf_resumo;
    $('cadastro-status').textContent = pdf && (pdf.erro || pdf.parcial || pdf.sem_texto)
      ? 'Originais registrados. Confira as limitações de extração no recibo antes da pergunta.'
      : 'Documentos registrados. Aguardando sua pergunta.';
  } catch (failure) {
    uploadError(failure.message);
    $('cadastro-status').textContent = 'Envio sem confirmação nesta tela. Consulte o inventário antes de continuar; um reenvio identifica arquivos duplicados.';
  } finally {
    cadastroBusy = false;
    for (const control of $('cadastro').elements) control.disabled = false;
    toggleNewCase();
    $('cadastro-preparar').disabled = !pdfAvailable;
  }
});
// Findings open on the latest analysis, step and results version. The chip names what is
// selected and reopens the selectors; an address that names a version wins over the default.
let findingEpoch = 0, findingSequence = 0, findingCatalog = null, findingQuery = null, findingResult = null;
let selectedFindingId = null, briefingSequence = 0, citationSequence = 0, findingCatalogSequence = 0;
let versionCollapsed = false, versionKey = '';
const stepNames = {r1:'Análise inicial', r2:'Revisão do suporte', r3_sintese:'Síntese'};
const namedByRoute = id => Boolean(window.restaurandoRota?.()) && new URL(location.href).searchParams.has(id);
function latestOption(id, allowed = () => true) {
  return [...$(id).options].map(option => option.value).filter(value => value && allowed(value))
    .sort((a, b) => a.localeCompare(b, undefined, {numeric:true})).at(-1) || '';
}
function choose(id, value) { $(id).value = value; $(id).dispatchEvent(new Event('change')); }
function defaultAnalysis() {
  if ($('area-achados').hidden || !$('caso').value || $('rodada').value || namedByRoute('rodada')) return false;
  const value = latestOption('rodada');
  if (!value) { $('achados-status').textContent = 'Esta apuração ainda não tem análises. Faça uma pergunta em Perguntar à IA.'; return false; }
  choose('rodada', value);
  return true;
}
function versionChip() {
  const chip = $('achados-versao-chip'), ready = Boolean(findingResult && findingQuery);
  if (!ready) versionCollapsed = false;
  chip.hidden = !ready;
  chip.setAttribute('aria-expanded', String(ready && !versionCollapsed));
  $('achados-versoes').classList.toggle('versao-recolhida', versionCollapsed);
  $('selecao-acervo').classList.toggle('versao-recolhida', versionCollapsed && !$('area-achados').hidden);
  if (!ready) return;
  // Analysis id and date are data; the words around them follow the interface language.
  const day = [...$('rodada').options].find(option => option.value === findingQuery.rodada)?.dataset.dia;
  const data = text => { const span = element('span', text); span.setAttribute('translate', 'no'); return span; };
  const step = stepNames[findingQuery.revisao];
  chip.replaceChildren(element('span', 'Análise'), ' ', data([findingQuery.rodada, day].filter(Boolean).join(' · ')), ' · ',
    step ? element('span', step) : data(findingQuery.revisao.replaceAll('_', ' ')), ' · ',
    element('span', versionCollapsed ? 'trocar' : 'fechar', 'chip-action'));
}
$('achados-versao-chip').addEventListener('click', () => {
  versionCollapsed = !versionCollapsed;
  if (!versionCollapsed) { $('acervo-escolha').open = true; $('achados-versoes').open = true; }
  versionChip();
});
const humanReviewStates = {
  pendente:['Pendente','Ainda não houve conferência humana.'],
  conferida_no_original:['Conferida no original','O jornalista verificou que a fonte sustenta a afirmação.'],
  precisa_de_ajuste:['Precisa de ajuste','Há erro, exagero ou contexto faltando.'],
  sem_suporte_suficiente:['Sem suporte suficiente','Os documentos consultados não permitem sustentar a afirmação.']
};
// Human checks are solid marks; only a check against the original carries ✓ (text, not color).
// Sinais dos selos como SVG embutido (a fonte da Mesa não tem ✕ ✎ ◐ e a CSP não aceita imagem data:); desenhos de docs/design/icones/.
const SINAIS = {'sem-suporte': 'M7 7l10 10M17 7L7 17', parcial: 'M20 12a8 8 0 11-16 0 8 8 0 0116 0zM12 4v16M12 8h3M12 12h4M12 16h3', corrigido: 'M5 19l1-4L16 5l3 3L9 18zM14 7l3 3'};
function sinalSvg(nome) {
  const svg = document.createElementNS('http://www.w3.org/2000/svg', 'svg');
  svg.setAttribute('viewBox', '0 0 24 24'); svg.setAttribute('aria-hidden', 'true'); svg.classList.add('mesa-sinal');
  const caminho = document.createElementNS('http://www.w3.org/2000/svg', 'path'); caminho.setAttribute('d', SINAIS[nome]); svg.append(caminho);
  return svg;
}
function humanReviewBadge(item) {
  const state = item.revisao_humana?.estado || 'pendente';
  const badge = element('span', undefined, `human-review-badge human-${state}`);
  if (state === 'conferida_no_original') {
    const mark = element('span', '✓'); mark.setAttribute('aria-hidden', 'true'); badge.append(mark, ' ');
  }
  if (state === 'sem_suporte_suficiente') badge.append(sinalSvg('sem-suporte'), ' ');
  badge.append(humanReviewStates[state][0]);
  return badge;
}
function findingsError(message = '') {
  $('achados-erro').textContent = message; $('achados-erro').hidden = !message;
}
function clearFindings() {
  window.limparObservacoes?.();
  findingEpoch++; findingSequence++; findingQuery = null; findingResult = null; window.barraMesa?.definir('achados', '', 'pendencia');
  $('achados-resultados').replaceChildren(); $('achados-total').textContent = '';
  $('achados-inspecao').replaceChildren(); $('achados-inspecao').hidden = true;
  $('achados-briefings').replaceChildren(); selectedFindingId = null;
  $('achados-filtros-ativos').hidden = true;
  $('achados-intervalo').textContent = ''; findingsError();
  $('achados-progresso-humano').hidden = true;
  clearFindingDetails();
  for (const name of ['buscar', 'exportar', 'anterior', 'proximo']) $('achados-' + name).disabled = true;
  versionKey = ''; versionChip();
}
function resetFindings() {
  clearFindings(); findingCatalog = null;
  options('achados-revisao', [], 'Selecione a etapa');
  options('achados-geracao', [], 'Selecione a versão');
  options('achados-documento', [], 'Todos');
  $('achados-form').reset();
  $('achados-so-pendentes').setAttribute('aria-pressed', 'false');
  $('achados-revisao-feedback').textContent = '';
  $('achados-versoes').open = true;
  $('achados-versoes-resumo').textContent = 'Etapa da análise e versão dos resultados';
  $('achados-status').textContent = 'Escolha uma apuração para ver os achados da análise mais recente.';
}
// Each view opens with its area name as the only h1 and the investigation as context.
const areaNames = {inicio:'Visão geral',cadastro:'Cadastrar arquivos',documentos:'Documentos',codex:'Perguntar à IA',
  achados:'Conferir achados',apuracao:'Caderno',caderno:'Caderno',diligencias:'Diligências',quadros:'Quadros de evidência',gerenciar:'Apurações e lixeira',configuracoes:'Configurações'};
let currentArea = 'inicio';
function areaHeading() {
  $('area-titulo').textContent = areaNames[currentArea];
  const title = cases.find(c => c.id === window.contextoCaso?.())?.titulo, context = $('area-descricao');
  // A case title is data: it keeps its own language.
  if (title) { context.setAttribute('translate', 'no'); context.textContent = title; }
  else { context.removeAttribute('translate'); context.textContent = 'Nenhuma apuração selecionada'; }
}
window.addEventListener('mesa-contexto-alterado', areaHeading);
window.addEventListener('catalogo-carregado', areaHeading);
// A única função de troca de área. Os módulos que precisam reagir a ela não a reatribuem: registram
// ganchos, na ordem em que as camadas se empilhavam antes (o último a registrar fica por fora).
//   antes(nome) -> nome: ajusta o nome pedido; o último registrado roda primeiro.
//   forcar(nome) -> nome: troca só a tela que o núcleo mostra; os ganchos de depois seguem com o nome pedido.
//   depois(nome): roda depois do núcleo, na ordem de registro.
const ganchosArea = {antes: [], forcar: null, depois: []};
function registrarGanchoArea({antes, forcar, depois}) {
  if (antes) ganchosArea.antes.unshift(antes);
  if (forcar) ganchosArea.forcar = forcar;
  if (depois) ganchosArea.depois.push(depois);
}
function showArea(pedida) {
  let nome = pedida;
  for (const gancho of ganchosArea.antes) nome = gancho(nome);
  mostrarAreaBase(ganchosArea.forcar ? ganchosArea.forcar(nome) : nome);
  for (const gancho of ganchosArea.depois) gancho(nome);
}
// Núcleo: mostra a área, atualiza título e avisa o módulo dela. Quem não precisa dos ganchos pode chamá-lo direto.
function mostrarAreaBase(area) {
  for (const name of Object.keys(areaNames)) {
    $('area-' + name).hidden = area !== name;
    $('ver-' + name).setAttribute('aria-pressed', String(area === name));
  }
  $('selecao-acervo').hidden = ['inicio','cadastro','codex','gerenciar','configuracoes','caderno','apuracao','diligencias','quadros'].includes(area);
  currentArea = area; areaHeading(); versionChip();
  if (area === 'achados' && !defaultAnalysis() && !findingCatalog) loadFindingsCatalog();
  if (area === 'achados' && window.achadosDesatualizados && findingQuery) {
    window.achadosDesatualizados = false;  // a human mark was saved elsewhere: reload badges and counter
    searchFindings({...findingQuery});
  }
  if (area === 'gerenciar') window.dispatchEvent(new Event('gerenciar-abrir'));
  if (area === 'caderno') window.dispatchEvent(new Event('caderno-abrir'));
  if (area === 'apuracao') window.dispatchEvent(new Event('apuracao-abrir'));
  if (area === 'diligencias') window.dispatchEvent(new Event('diligencias-abrir'));
  if (area === 'quadros') window.dispatchEvent(new Event('quadros-abrir'));
  if (area === 'codex') {
    window.dispatchEvent(new Event('codex-abrir'));
    fetch('/api/integracao').then(response => {
      if (!response.ok) {
        $('codex-conta').textContent = 'O servidor aberto está desatualizado. Encerre as instâncias anteriores e inicie a Mesa novamente.';
      }
    }).catch(() => { $('codex-conta').textContent = 'Servidor desconectado. Inicie a Mesa novamente.'; });
  }
}
for (const area of ['inicio','cadastro','documentos','achados','codex','gerenciar','configuracoes','caderno','apuracao','diligencias','quadros']) $('ver-' + area).addEventListener('click', () => showArea(area));
window.addEventListener('acervo-alterado', () => {
  $('cadastro-recibo').hidden = true; $('cadastro-perguntar').hidden=true;
  $('cadastro-inventario').hidden = true;
  $('cadastro-preparacao').hidden = true;
  loadCatalog();
});
for (const id of ['caso', 'rodada', 'geracao']) $(id).addEventListener('change', () => {
  if ($('area-achados').hidden) return;
  // A new case opens on its latest analysis, which then loads its own catalog.
  if (id === 'caso' && defaultAnalysis()) return;
  loadFindingsCatalog();
});
async function loadFindingsCatalog() {
  const scope = selection(), version = findingEpoch, request = ++findingCatalogSequence;
  if (!scope.caso || !scope.rodada) return;
  $('achados-status').textContent = 'Consultando as etapas da análise…';
  try {
    const result = await api('achados-catalogo', scope);
    if (version !== findingEpoch || request !== findingCatalogSequence) return;
    findingCatalog = result;
    options('achados-revisao', result.revisoes.map(r => ({value:r, label:({r1:'Análise inicial',r2:'Revisão do suporte',r3_sintese:'Síntese'}[r] || r.replaceAll('_',' ')) + ` (${r})`})), 'Selecione a etapa');
    $('achados-status').textContent = result.estado === 'nao_produzidos'
      ? 'Esta análise ainda não produziu achados. Markdown antigo não é importado automaticamente.'
      : `${result.revisoes.length} etapa(s) disponível(is). Escolha a etapa da análise e a versão dos resultados.`;
    const indexed = new Set((result.indices || []).map(index => index.revisao));
    if (!$('achados-revisao').value && !namedByRoute('achados-revisao')) {
      const revision = latestOption('achados-revisao', value => indexed.has(value));
      if (revision) choose('achados-revisao', revision);
    }
  } catch (failure) { if (version === findingEpoch && request === findingCatalogSequence) { findingsError(failure.message); $('achados-status').textContent = 'Erro ao consultar registros; não equivale a nenhum achado.'; } }
}
$('achados-revisao').addEventListener('change', () => {
  clearFindings();
  $('achados-versoes').open = true;
  $('achados-versoes-resumo').textContent = 'Etapa da análise e versão dos resultados';
  const revision = $('achados-revisao').value;
  const generations = (findingCatalog?.indices || []).filter(g => g.revisao === revision);
  options('achados-geracao', generations.map(g => ({value:g.geracao, label:`Versão ${g.geracao.replace(/^g/,'')} (${g.geracao})`})), 'Selecione a versão');
  $('achados-status').textContent = !revision ? 'Selecione a etapa.' : generations.length
    ? 'Escolha a versão dos resultados desta etapa.' : 'Esta etapa ainda não tem versão de resultados para consulta. Os registros continuam preservados.';
  if (generations.length && !namedByRoute('achados-geracao')) choose('achados-geracao', latestOption('achados-geracao'));
});
const findingScope = () => ({caso:$('caso').value, rodada:$('rodada').value,
  revisao:$('achados-revisao').value, geracao_achados:$('achados-geracao').value});
function findingFilters() {
  return {...Object.fromEntries(['texto','documento','natureza','suporte','humana','destino','briefing'].map(k => [k, $('achados-' + k).value])), revisao_humana:$('achados-marcacao').value};
}
function pretty(value) {
  return ({declaracao_documental:'declaração documental',alegacao_atribuida:'alegação atribuída',
    inferencia:'inferência',pendencia:'pendência',nao_revisado:'não revisado',nao_sustentado:'não sustentado',
    ilegivel:'ilegível',nao_realizada:'não realizada',contradicao:'contradição',substituido:'substituído',
    incluido:'incluído',confirmacao:'confirmação',correcao:'correção'})[value] || value.replaceAll('_', ' ');
}
// "Label: value · data": the label and the value are interface words; record text keeps its language.
function labelled(label, value, data, className = 'small') {
  const line = element('p', undefined, className);
  line.append(element('span', label), ' ');
  if (value) line.append(element('span', value));
  if (data) { const text = element('span', value ? ` · ${data}` : data); text.setAttribute('translate', 'no'); line.append(text); }
  return line;
}
function clearFindingDetails() {
  briefingSequence++; citationSequence++;
  $('leitor-briefing').hidden = true;
  $('mesa-achados').hidden = false;
  for (const id of ['achados-briefing-painel','achados-detalhe-painel']) { $(id).replaceChildren(); $(id).hidden = true; }
}
async function openBriefing(artifact, scope, version) {
  const seq = findingSequence, request = ++briefingSequence;
  citationSequence++;
  findingsError();
  $('achados-status').textContent = 'Abrindo o briefing preservado nesta revisão…';
  try {
    const result = await api('achados-briefing', {...scope, artefato_sha256:artifact.sha256});
    if (version !== findingEpoch || seq !== findingSequence || request !== briefingSequence) return;
    const panel = $('achados-briefing-painel'), title = element('h3','Briefing da apuração');
    title.tabIndex = -1;
    const source = $('achados-detalhe-painel');
    source.replaceChildren(element('div','Selecione uma referência no texto para ler o achado e suas evidências.','source-placeholder'));
    source.hidden = false;
    const text = element('div',undefined,'briefing-text');
    const citationButtons = [];
    // Markdown subset rendered with DOM nodes only (never innerHTML): headings, lists, quotes,
    // rules, bold/italic/code, finding markers and [fonte:sha256] tags. Source HTML/URLs stay inert.
    const citation = marker => {
        const id = marker.slice(1,-1).split('@')[0];
        const button = element('button',marker,'citation'); button.type = 'button';
        button.setAttribute('aria-label',`Abrir achado ${marker}`);
        button.setAttribute('aria-controls','achados-detalhe-painel');
        button.setAttribute('aria-pressed','false'); citationButtons.push({button,marker});
        button.addEventListener('click',async () => {
          const citationRequest = ++citationSequence;
          findingsError();
          source.replaceChildren(element('p',`Carregando ${marker}…`,'source-placeholder'));
          citationButtons.forEach(c => c.button.setAttribute('aria-pressed',String(c.marker === marker)));
          $('achados-status').textContent = `Abrindo a referência ${marker}…`;
        try {
          const detail = await api('achados-detalhe',{...scope,achado_id:id});
          if (version !== findingEpoch || seq !== findingSequence || request !== briefingSequence || citationRequest !== citationSequence) return;
          const target = $('achados-detalhe-painel'), heading = element('h3',`Referência ${marker} · ${scope.caso}/${scope.rodada}/${scope.revisao}`);
          heading.tabIndex = -1;
          const card = renderFinding(detail.achado,scope,version,false);
          card.removeAttribute('id'); // This detail can coexist with the filtered result card.
          const back = element('button','Voltar à referência no texto','secondary'); back.type = 'button';
          back.addEventListener('click',() => button.focus());
          target.replaceChildren(heading,back);
          if (`${detail.achado.id}@v${detail.achado.versao}` !== marker.slice(1,-1)) {
            target.append(element('p',`A referência cita ${marker}, mas a ficha desta revisão está em ${detail.achado.id}@v${detail.achado.versao}. As evidências abaixo pertencem à ficha disponível. Consulte o histórico antes de atribuí-las à versão citada.`,'notice'));
            card.querySelector('.history').open = true;
          }
          target.append(card); target.hidden = false; heading.focus();
          $('achados-status').textContent = `Fonte aberta para ${marker}. Conferir a versão e o alcance do suporte.`;
        } catch (failure) {
          if (version === findingEpoch && seq === findingSequence && request === briefingSequence && citationRequest === citationSequence) {
            source.replaceChildren(element('p','Não foi possível abrir esta referência. Confira o erro antes de continuar.','notice'));
            findingsError(failure.message);
          }
        }
        });
        return button;
    };
    const INLINE = /\*\*(.+?)\*\*|__(.+?)__|\[A[0-9]{3,}@v[1-9][0-9]*\]|\[fonte:([a-f0-9]{8,64})\]|`([^`]+)`|\*([^*\s](?:[^*]*?[^*\s])?)\*|(?<![\w])_([^_\s](?:[^_]*?[^_\s])?)_(?![\w])/g;
    function inline(target, content) {
      let offset = 0;
      for (const match of content.matchAll(INLINE)) {
        target.append(document.createTextNode(content.slice(offset, match.index)));
        const [whole, bold, bold2, source, code, italic, italic2] = match;
        if (bold !== undefined || bold2 !== undefined) {
          const strong = element('strong'); inline(strong, bold ?? bold2); target.append(strong);
        } else if (source) {
          const tag = element('span', 'fonte', 'briefing-source');
          tag.title = `Fonte preservada · SHA-256 ${source}`;
          tag.setAttribute('translate', 'no');
          target.append(tag);
        } else if (code !== undefined) {
          target.append(element('code', code));
        } else if (italic !== undefined || italic2 !== undefined) {
          const em = element('em'); inline(em, italic ?? italic2); target.append(em);
        } else {
          target.append(citation(whole));
        }
        offset = match.index + whole.length;
      }
      target.append(document.createTextNode(content.slice(offset)));
    }
    let list = null, listKind = '', quote = null;
    const closeBlocks = () => { list = null; listKind = ''; quote = null; };
    for (const raw of result.texto.split(/\r?\n/)) {
      const line = raw.trimEnd();
      if (!line.trim()) { closeBlocks(); continue; }
      const heading = line.match(/^(#{1,6})\s+(.*)$/);
      const bullet = line.match(/^\s*[-*+]\s+(.*)$/);
      const numbered = line.match(/^\s*(\d{1,3})[.)]\s+(.*)$/);
      const quoted = line.match(/^\s*>\s?(.*)$/);
      if (/^\s*([-*_])(\s*\1){2,}\s*$/.test(line)) { closeBlocks(); text.append(element('hr')); continue; }
      if (heading) {
        closeBlocks();
        const node = element(heading[1].length <= 2 ? 'h4' : 'h5'); inline(node, heading[2]); text.append(node);
      } else if (bullet || numbered) {
        const kind = bullet ? 'ul' : 'ol';
        if (!list || listKind !== kind) {
          quote = null; list = element(kind, undefined, 'briefing-list'); listKind = kind;
          if (numbered && numbered[1] !== '1') list.start = Number(numbered[1]);
          text.append(list);
        }
        const item = element('li'); inline(item, bullet ? bullet[1] : numbered[2]); list.append(item);
      } else if (quoted) {
        list = null; listKind = '';
        if (!quote) { quote = element('blockquote', undefined, 'briefing-quote'); text.append(quote); }
        const node = element('p'); inline(node, quoted[1]); quote.append(node);
      } else if (list && /^\s{2,}\S/.test(raw)) {
        const last = list.lastElementChild; last.append(' '); inline(last, line.trim());
      } else {
        closeBlocks();
        const node = element('p'); inline(node, line); text.append(node);
      }
    }
    const raw = element('details',undefined,'technical');
    raw.append(element('summary','Detalhes técnicos'),element('p',`${scope.caso}/${scope.rodada}/${scope.revisao} · ${result.artefato.arquivo} · SHA-256: ${artifact.sha256}`,'small path'),element('pre',result.texto,'raw-briefing'));
    panel.replaceChildren(title,element('p','Arquivo preservado nesta revisão. As referências abrem o achado e suas evidências. Revisão da IA não equivale a conferência humana.','small briefing-caption'),text,raw);
    const actions = element('div',undefined,'actions');
    const close = element('button','Fechar briefing','secondary'); close.type = 'button';
    close.addEventListener('click',() => {
      clearFindingDetails(); $('achados-total').focus();
      $('achados-status').textContent = 'Briefing fechado. Selecione um achado para conferir suas evidências.';
    });
    actions.append(close); panel.prepend(actions); panel.hidden = false;
    $('leitor-briefing').hidden = false; $('mesa-achados').hidden = true;
    $('achados-status').textContent = citationButtons.length ? 'Briefing aberto. Selecione uma referência para conferir a fonte.' : 'Briefing aberto sem referências de achados neste texto.';
    title.focus();
  } catch (failure) {
    if (version === findingEpoch && seq === findingSequence && request === briefingSequence) {
      findingsError(failure.message); $('achados-status').textContent = 'Não foi possível abrir o briefing. Confira o erro antes de continuar.';
    }
  }
}
// The AI's own support verdict: outlined pill, always prefixed "IA".
function supportBadge(item) {
  const badge = element('span', undefined, `support-badge ai-support support-${item.suporte}`);
  badge.title = 'Suporte documental avaliado pela IA';
  badge.append(element('span', 'IA', 'badge-origin'), ' · ', element('span', pretty(item.suporte)));
  return badge;
}
function selectFinding(item, scope, version, focus = false) {
  selectedFindingId = item.id;
  const target = $('achados-inspecao'), card = renderFinding(item,scope,version);
  const back = element('button','Voltar à lista de achados','secondary'); back.type = 'button';
  back.addEventListener('click',() => {
    $('mesa-achados').classList.remove('detail-open');
    if($('achados-voltar-lista'))$('achados-voltar-lista').hidden=true;
    $('achados-resultados').querySelector('[aria-pressed="true"]')?.focus();
  });
  target.replaceChildren(back,card); target.hidden = false;
  for (const button of $('achados-resultados').querySelectorAll('.finding-open')) button.setAttribute('aria-pressed',String(button.dataset.achado === selectedFindingId));
  if (focus) { const heading = card.querySelector('h3'); heading.tabIndex = -1; heading.focus(); }
}
function renderFindingChoice(item, scope, version) {
  const row = element('article',undefined,'finding-choice'), button = element('button',undefined,'finding-open');
  button.type = 'button'; button.dataset.achado = item.id;
  button.setAttribute('aria-pressed',String(item.id === selectedFindingId));
  button.setAttribute('aria-controls','achados-inspecao');
  button.append(element('span',pretty(item.natureza),'meta'),element('span',item.redacao,'claim-title'),supportBadge(item));
  button.addEventListener('click',() => selectFinding(item,scope,version,true));
  const actions = element('div',undefined,'human-review-actions'), review = element('button','Conferir','secondary');
  review.type = 'button'; review.setAttribute('aria-label', `Conferir: ${item.redacao}`);
  review.addEventListener('click', () => window.conferirAchado(item, scope, version));
  actions.append(humanReviewBadge(item), review); row.append(button, actions);
  const choice = window.observacoesAchado?.(item, scope);
  if (choice) row.append(choice);
  return row;
}
// Quote, locator and the original page lead each evidence; provenance details follow.
function renderEvidence(item, link, scope, version) {
  const ev = item.evidencias.find(e => e.id === link.evidencia_id);
  const block = element('section', undefined, 'evidence');
  const loc = ev.localizador, page = Leitura.pagina(ev);
  const position = `${loc.pagina_pdf ? `Página PDF ${loc.pagina_pdf} · ` : ''}${loc.tipo === 'linhas' ? `Linhas ${loc.linha_inicio}–${loc.linha_fim}` : loc.descricao || loc.tipo}`;
  const quote = element('blockquote', ev.trecho || 'Sem transcrição literal; leitura visual registrada.');
  const actions = element('div', undefined, 'actions'), feedback = element('p', '', 'small');
  feedback.setAttribute('role','status');
  const context = element('div', undefined, 'context'); context.hidden = true;
  const original = element('button', Leitura.rotuloOriginal(page)); original.type = 'button';
  original.addEventListener('click', async () => {
    original.disabled = true;
    try {
      const blob = await api('achados-original', {...scope, evidencia_id:ev.id}, true);
      if (version !== findingEpoch) return;
      await window.abrirOriginal(blob, ev.original.split('/').pop(), page, item.redacao + '\n\n' + (ev.trecho || 'Fonte visual: confira o original.'));
      window.registrarOriginalConferido?.(scope, ev.id);
    } catch (failure) { if (version === findingEpoch) feedback.textContent = failure.message; }
    finally { if (version === findingEpoch) original.disabled = false; }
  });
  const view = element('button', 'Ver contexto', 'secondary'); view.type = 'button';
  view.disabled = ev.modo === 'visual';
  view.addEventListener('click', async () => {
    view.disabled = true;
    try {
      const result = await api('achados-evidencia', {...scope, evidencia_id:ev.id});
      if (version !== findingEpoch) return;
      context.replaceChildren(element('p', result.aviso), ...(result.contexto || []).map(l => element('p', `L${l.linha} ${l.texto}`)));
      context.hidden = false;
    } catch (failure) { if (version === findingEpoch) feedback.textContent = failure.message; }
    finally { if (version === findingEpoch) view.disabled = false; }
  });
  const reference = `${scope.caso}/${scope.rodada}/${scope.revisao}/${item.id}@v${item.versao} · ${ev.id} · ${ev.documento_id}\n${position}\nOriginal: ${ev.original}\nSHA-256: ${ev.original_sha256}\nFonte textual: ${ev.fonte_textual || 'indisponível'} · SHA-256: ${ev.fonte_sha256 || 'não se aplica'}\nÍndice documental: ${JSON.stringify(ev.indice)}\n${ev.trecho}`;
  const copy = element('button','Copiar referência completa','secondary'); copy.type = 'button';
  copy.addEventListener('click', async () => {
    try { await navigator.clipboard.writeText(reference); if (version === findingEpoch) feedback.textContent = 'Referência copiada.'; }
    catch { if (version === findingEpoch) feedback.textContent = reference; }
  });
  const notebook=element('button','Registrar trecho com fonte','secondary');notebook.type='button';
  notebook.addEventListener('click',()=>window.abrirRegistroCaderno({caso:scope.caso,rodada:scope.rodada,
    documento_id:ev.documento_id,pagina_pdf:ev.localizador.pagina_pdf,
    localizador:ev.localizador.descricao||(ev.localizador.linha_inicio?`Linhas ${ev.localizador.linha_inicio}–${ev.localizador.linha_fim}`:''),
    trecho:window.trechoSelecionadoCaderno(quote,ev.trecho)}));
  actions.append(original,view,copy,notebook);
  if(ev.trecho)actions.append(window.botaoAdicionarApuracao({...scope,tipo:'ia',achado_id:item.id,achado_versao:item.versao,evidencia_id:ev.id},quote,ev.trecho));
  const role = element('p', undefined, 'small'), reason = element('span', ` · ${link.justificativa}`);
  reason.setAttribute('translate', 'no'); role.append(element('span', pretty(link.papel)), reason);
  block.append(element('h4', Leitura.fonte({...ev, ...loc})), quote, actions, context, feedback, role);
  if (ev.modo === 'visual') block.append(element('p', 'Contexto textual indisponível; consulte o original.', 'small'));
  if (ev.limitacoes) block.append(element('p', `Limitações da evidência: ${ev.limitacoes}`, 'small'));
  const metadata = element('details',undefined,'evidence-details');
  metadata.append(element('summary','Atribuição e contexto da fonte'),element('p',`Atribuição: ${ev.atribuicao} · Contexto: ${ev.contexto}`,'small'));
  block.append(metadata, Leitura.tecnicos(`${ev.id} · ${ev.documento_id} · ${position} · Original: ${ev.original} · SHA-256: ${ev.original_sha256}`));
  return block;
}
function renderFinding(item, scope, version, allowBriefing = true) {
  const card = element('article', undefined, 'finding-detail');
  card.id = item.id;
  const statuses = element('div',undefined,'claim-status');
  statuses.append(element('span',pretty(item.natureza),'meta claim-nature'),supportBadge(item),humanReviewBadge(item));
  card.append(element('h3',item.redacao),statuses,
    element('h4',item.vinculos.length ? 'Onde está o suporte e o contexto' : 'Sem evidência vinculada a esta redação'));
  for (const link of item.vinculos) card.append(renderEvidence(item, link, scope, version));
  if (item.limitacoes) card.append(element('p', `Limitações: ${item.limitacoes}`, 'limitation'));
  const actions = element('div', undefined, 'actions finding-actions');
  const review = element('button','Conferir','secondary'); review.type = 'button';
  review.addEventListener('click', () => window.conferirAchado(item,scope,version));
  const followup=element('button','Criar diligência','secondary');followup.type='button';
  followup.addEventListener('click',()=>window.abrirDiligencia({caso:scope.caso,redacao:item.redacao,
    origem:{tipo:'ia',rodada:scope.rodada,revisao:scope.revisao,registros_sha256:findingResult.registros_sha256,
      achado_id:item.id,achado_versao:item.versao}}));
  actions.append(review,window.botaoAdicionarApuracao({...scope,tipo:'ia',achado_id:item.id,achado_versao:item.versao},card.querySelector('h3'),item.redacao),followup);
  card.append(actions);
  if (item.revisao_humana?.observacao) card.append(element('p', `Observação do jornalista: ${item.revisao_humana.observacao}`, 'human-review-note'));
  if (item.conferencia_humana === 'retorno_recebido') card.append(element('p','Há retorno humano anterior nos registros; consulte seu alcance no histórico.','small'));
  for (const h of item.historico.conferencias_humanas.filter(h => h.versao === item.versao)) {
    card.append(element('p',`Alcance do retorno humano: ${h.alcance} · Decisão: ${pretty(h.decisao)} · Retorno: ${h.retorno_literal_ou_referencia}`,'human-scope'));
  }
  card.append(labelled('Pergunta relacionada:', '', item.subquestao), labelled('Destino editorial:', pretty(item.destino)),
    labelled('Verificação externa:', pretty(item.verificacao_externa.estado), item.verificacao_externa.limitacao));
  if (item.briefing) {
    card.append(element('p', 'Incluído no briefing.', 'small'));
    const artifact = findingResult?.artefatos.find(a => a.arquivo === item.briefing);
    if (artifact && allowBriefing) {
      const view = element('button','Ver briefing e referências','secondary'); view.type = 'button';
      view.addEventListener('click',() => openBriefing(artifact,scope,version)); card.append(view);
    }
  }
  card.append(Leitura.tecnicos(`${scope.caso}/${scope.rodada}/${scope.revisao} · consulta ${scope.geracao_achados} · ${item.id}@v${item.versao}`));
  const history = element('details',undefined,'history'), summary = element('summary','Detalhes técnicos e histórico');
  history.append(summary);
  for (const v of item.historico.versoes) history.append(element('p', `v${v.versao} · ${v.redacao} · ${pretty(v.natureza)} · ${v.limitacoes}`));
  for (const r of item.historico.revisoes_assistidas) history.append(element('p', `Revisão pela IA · v${r.versao} · ${pretty(r.suporte)} · ${r.motivo} · ${r.limitacoes}`));
  for (const d of item.historico.destinos) history.append(element('p', `Destino · v${d.versao} · ${pretty(d.destino)} · ${d.motivo} · ${d.briefing || ''}`));
  for (const h of item.historico.conferencias_humanas) history.append(element('p', `Retorno humano · v${h.versao} · ${h.decisao} · Alcance: ${h.alcance} · ${h.retorno_literal_ou_referencia} · Responsável: ${h.responsavel || 'não informado'} · Fontes informadas: ${h.fontes_informadas.join(', ') || 'não informadas'}`));
  if (!item.historico.conferencias_humanas.length) history.append(element('p','Conferência humana não realizada.'));
  card.append(history); return card;
}
async function searchFindings(query) {
  const version = findingEpoch, seq = ++findingSequence;
  const previousSelection = selectedFindingId;
  findingsError(); findingQuery = null; findingResult = null;
  clearFindingDetails();
  $('achados-resultados').replaceChildren(); $('achados-total').textContent = ''; $('achados-intervalo').textContent = '';
  $('achados-inspecao').replaceChildren(); $('achados-inspecao').hidden = true;
  $('achados-briefings').replaceChildren(); selectedFindingId = null;
  $('achados-filtros-ativos').hidden = true;
  for (const name of ['buscar','exportar','anterior','proximo']) $('achados-' + name).disabled = true;
  $('achados-status').textContent = 'Conferindo registros e consultando achados…';
  try {
    const result = await api('achados-buscar', query);
    if (version !== findingEpoch || seq !== findingSequence) return;
    if (!result.retornados && result.total_correspondencias && query.deslocamento >= result.total_correspondencias) {
      return searchFindings({...query, deslocamento:Math.floor((result.total_correspondencias - 1) / query.limite) * query.limite});
    }
    findingQuery = query; findingResult = result;
    const key = [query.caso, query.rodada, query.revisao, query.geracao_achados].join('/');
    if (key !== versionKey) { versionKey = key; versionCollapsed = true; }
    versionChip();
    const filterLabels = {texto:'Texto',documento:'Documento',natureza:'Natureza',suporte:'Suporte (IA)',humana:'Retorno anterior',destino:'Destino',briefing:'No briefing',revisao_humana:'Conferência do jornalista'};
    const applied = Object.entries(query.filtros || {}).filter(([,value]) => value).map(([key,value]) => `${filterLabels[key]}: ${key === 'revisao_humana' ? humanReviewStates[value][0] : pretty(value)}`);
    $('achados-filtros-ativos').textContent = `Filtros aplicados: ${applied.join(' · ')}`;
    $('achados-filtros-ativos').hidden = !applied.length;
    const selectedDoc = $('achados-documento').value;
    options('achados-documento', result.documentos.map(d => ({value:d,label:d})), 'Todos');
    $('achados-documento').value = selectedDoc;
    $('achados-resultados').replaceChildren(...result.resultados.map(item => renderFindingChoice(item,query,version)));
    if (result.resultados.length) selectFinding(result.resultados.find(item => item.id === previousSelection) || result.resultados[0],query,version);
    const progress = result.progresso_revisao_humana;
    if (progress) {
      $('achados-progresso-texto').textContent = `${progress.revisados} de ${progress.total} achados revisados`;
      $('achados-progresso').max = progress.total || 1; $('achados-progresso').value = progress.revisados;
      $('achados-progresso-humano').hidden = false; window.barraMesa?.definir('achados', progress.total > progress.revisados ? String(progress.total - progress.revisados) : '', 'pendencia');
    }
    $('achados-so-pendentes').setAttribute('aria-pressed', String($('achados-marcacao').value === 'pendente'));
    for (const artifact of result.artefatos.filter(a => a.tipo === 'briefing')) {
      const button = element('button','Ler briefing','secondary'); button.type = 'button';
      button.addEventListener('click',() => openBriefing(artifact,query,version));
      $('achados-briefings').append(button);
    }
    $('achados-total').textContent = `${result.total_correspondencias} achado(s) nesta seleção`;
    const states = {sem_achados_apos_revisao:'Conjunto sem achados após revisão.',sem_achados_iniciais:'Registro inicial sem achados.',somente_pendencias:'Somente pendências; não há conclusão sustentada.',disponivel:'Consulta concluída.'};
    $('achados-status').textContent = `${states[result.estado]} ${!result.retornados && result.estado === 'disponivel' ? 'Nenhum achado corresponde aos filtros.' : ''}${result.revisoes_sucessoras.length ? ` Revisão mais recente disponível: ${result.revisoes_sucessoras.join(', ')}. A seleção foi mantida.` : ''}`;
    $('achados-intervalo').textContent = result.retornados ? `${result.deslocamento+1}–${result.deslocamento+result.retornados} de ${result.total_correspondencias}` : '0 resultados';
    $('achados-anterior').disabled = !result.deslocamento;
    $('achados-proximo').disabled = result.proximo_deslocamento === null;
    $('achados-exportar').disabled = false; $('achados-total').focus();
    window.registrarPaginaMesa?.('achados', result.deslocamento);
  } catch (failure) {
    if (version === findingEpoch && seq === findingSequence) { findingsError(failure.message); $('achados-status').textContent = 'Registro inválido, fonte divergente ou banco indisponível. A consulta falhou; não equivale a nenhum achado.'; }
  } finally { if (version === findingEpoch && seq === findingSequence) $('achados-buscar').disabled = false; }
}
$('achados-geracao').addEventListener('change', () => {
  clearFindings();
  $('achados-versoes-resumo').textContent = 'Etapa da análise e versão dos resultados';
  $('achados-versoes').open = true;
  // While an address is being restored, the version it names is searched by the restore itself.
  if ($('achados-geracao').value && !(window.restaurandoMesa?.() && namedByRoute('achados-geracao'))) searchFindings({...findingScope(), filtros:findingFilters(), limite:Number($('achados-limite').value), deslocamento:0});
});
$('achados-form').addEventListener('submit', event => {
  event.preventDefault();
  if ($('achados-buscar').disabled) return;
  searchFindings({...findingScope(), filtros:findingFilters(), limite:Number($('achados-limite').value), deslocamento:window.paginaRestauradaMesa?.('achados') || 0});
});
$('achados-anterior').addEventListener('click', () => { if (findingQuery) searchFindings({...findingQuery, deslocamento:Math.max(0,findingQuery.deslocamento-findingQuery.limite)}); });
$('achados-proximo').addEventListener('click', () => { if (findingResult?.proximo_deslocamento != null) searchFindings({...findingQuery, deslocamento:findingResult.proximo_deslocamento}); });
$('achados-exportar').addEventListener('click', async () => {
  if (!findingQuery) return;
  const query = findingQuery, version = findingEpoch, sequence = findingSequence;
  $('achados-exportar').disabled = true;
  try {
    const result = await api('achados-exportar', query);
    if (version !== findingEpoch || sequence !== findingSequence) return;
    window.exportarEditorial(result,`achados_${query.caso}_${query.rodada}_${query.revisao}_${query.geracao_achados}_completo`,$('achados-formato').value);
    $('achados-status').textContent = `Exportados ${result.retornados} achado(s): seleção filtrada inteira, todas as páginas.`;
  } catch (failure) { if (version === findingEpoch && sequence === findingSequence) findingsError(failure.message); }
  finally { if (version === findingEpoch && sequence === findingSequence) $('achados-exportar').disabled = false; }
});
loadCatalog();
loadPdfEnvironment();
$('ver-cadastro').addEventListener('click', loadPdfEnvironment);
