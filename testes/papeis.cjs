'use strict';
// Papéis na Mesa (Sessao, app.js): o que cada papel alcança pelas `capacidades` de GET /api/sessao, nunca pelo nome do papel; o botão "Configurações"
// do cabeçalho; e o estado "Redação suspensa" para a Mesa inteira (403 redacao_suspensa). As listas de capacidades são as do servidor de verdade
// (testes/fixtures/capacidades_por_papel.json, conferida por test_capacidades_fixture.py). O servidor continua sendo a barreira.
const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const {criarMesa} = require('./dom_minimo.cjs');
const {SCRIPTS, ID, CATALOGO, recusa} = require('./contas_apoio.cjs');

const CAPACIDADES = JSON.parse(fs.readFileSync(path.join(__dirname, 'fixtures', 'capacidades_por_papel.json'), 'utf8'));
const sessaoDe = (papel, extra = {}) => ({conta: {id: ID.ana, nome: 'Ana Lima', email: 'ana@redacao.org', login: 'ana.lima', papel, casos: papel === 'dono' ? null : ['alfa']},
  organizacao: {id: 'o1', nome: 'Redação Serena'}, pendencias: [], capacidades: CAPACIDADES[papel], csrf: 'x', ambiente: 'homologacao', modo: 'piloto', expira_em: null, ...extra});

async function abrir({papel = 'dono', url = 'http://127.0.0.1:8765/', idioma = 'pt', api = () => undefined, desktop = true} = {}) {
  const respostas = {sessao: sessaoDe(papel), 'conta-ver': {conta: {id: ID.ana, nome: 'Ana Lima', papel, idioma: 'pt'}, organizacao: {id: 'o1', nome: 'Redação Serena'}},
    'conta-sessoes': {sessoes: []}, cota: {conta: {gasto_brl: '1.00', teto_brl: '50.00', saldo_brl: '49.00', esgotada: false}}};
  const mesa = criarMesa({modo: 'piloto', papel: papel === 'dono' ? 'admin' : papel, idioma, desktop, scripts: SCRIPTS, url, catalogo: CATALOGO,
    armazenamento: idioma === 'en' ? {'vlado-idioma': 'en'} : {},
    api: (operacao, dados) => {
      const propria = api(operacao, dados);
      if (propria !== undefined) { if (propria instanceof Error) throw propria; return propria; }
      const padrao = respostas[operacao];
      if (padrao instanceof Error) throw padrao;
      return padrao ?? {};
    }});
  await mesa.esperar(14);
  return mesa;
}
const semCapacidade = (mesa, id) => mesa.$(id).hasAttribute('data-sem-capacidade');
const area = mesa => mesa.avaliar('currentArea');

// O que cada controle estático exige (data-requer), conferido contra o papel: quem tem a capacidade vê; quem não tem, não.
const CONTROLES = {
  'inicio-nova': 'cadastrar', 'inicio-adicionar': 'cadastrar', 'documentos-zona': 'cadastrar', 'inicio-trocar': 'gerenciar-listar',
  'diligencias-nova': 'diligencias-criar', 'apuracao-nova': 'apuracao-nota-salvar', 'caderno-novo': 'caderno-salvar', 'caderno-cruzar': 'caderno-cruzar',
  'fontes-web-form': 'fontes-web-capturar', 'codex-desligar': 'codex-desligar', 'codex-continuar-documentos': 'codex-documentos-cadastrar',
  'revisao-form': 'achados-revisao-salvar', 'mesa-configuracoes': 'ia-config',
};

for (const papel of ['dono', 'editor', 'reporter', 'leitor']) {
  test(`${papel}: cada controle some ou fica pela capacidade da sessão, não pelo nome do papel`, async () => {
    const mesa = await abrir({papel});
    assert.deepEqual(mesa.erros, []);
    for (const [id, operacao] of Object.entries(CONTROLES)) {
      assert.equal(semCapacidade(mesa, id), !CAPACIDADES[papel].includes(operacao), `${id} (${operacao}) para ${papel}`);
    }
  });
}

test('as capacidades diferem de verdade entre os papéis (o teste acima não é vazio)', () => {
  const quem = op => Object.keys(CAPACIDADES).filter(p => CAPACIDADES[p].includes(op));
  assert.deepEqual(quem('cadastrar'), ['dono', 'reporter']);
  assert.deepEqual(quem('caderno-salvar'), ['dono', 'editor', 'reporter']);
  assert.deepEqual(quem('ia-config'), ['dono']);
});

test('o botão Configurações só aparece para o dono; o perfil, para toda pessoa com conta', async () => {
  for (const papel of ['dono', 'editor', 'reporter', 'leitor']) {
    const mesa = await abrir({papel});
    assert.equal(mesa.$('ver-configuracoes').hidden, false, `perfil de ${papel}`);
    assert.equal(mesa.$('acesso-painel'), null, 'a tela antiga de contas de acesso saiu (P30)');
    assert.equal(mesa.$('mesa-configuracoes').hidden, false, 'o botão existe; quem some com ele é a capacidade');
    assert.equal(semCapacidade(mesa, 'mesa-configuracoes'), papel !== 'dono');
  }
});

test('editor, repórter e leitor não herdam o dono nem ficam presos na pergunta: abrem as áreas que alcançam', async () => {
  for (const papel of ['editor', 'reporter', 'leitor']) {
    const mesa = await abrir({papel, url: 'http://127.0.0.1:8765/?area=apuracao'});
    assert.equal(area(mesa), 'apuracao', `${papel} abre o caderno`);
  }
});

test('uma área que o papel não alcança vira a Visão geral, também quando o endereço a pede', async () => {
  assert.equal(area(await abrir({papel: 'leitor', url: 'http://127.0.0.1:8765/?area=gerenciar'})), 'inicio');
  assert.equal(area(await abrir({papel: 'editor', url: 'http://127.0.0.1:8765/?area=cadastro'})), 'inicio');
  assert.equal(area(await abrir({papel: 'dono', url: 'http://127.0.0.1:8765/?area=gerenciar'})), 'gerenciar');
  assert.equal(area(await abrir({papel: 'reporter', url: 'http://127.0.0.1:8765/?area=cadastro'})), 'cadastro');
  const leitor = await abrir({papel: 'leitor'});
  leitor.avaliar("showArea('gerenciar')");
  assert.equal(area(leitor), 'inicio', 'a troca de área depois da carga também');
});

test('operações que o papel não alcança nem chegam ao servidor (a recusa local tem a forma da do servidor)', async () => {
  const mesa = await abrir({papel: 'leitor'});
  await assert.rejects(mesa.avaliar("api('ambiente', {})"), falha => falha.result.codigo === 'operacao_proibida');
  assert.ok(!mesa.chamadas.some(c => c.operacao === 'ambiente'));
  assert.equal(mesa.janela.Sessao.pode('lixeira-apagar'), false);
  assert.equal(mesa.janela.Sessao.pode('inventario'), true);
  assert.equal((await abrir({papel: 'dono'})).janela.Sessao.pode('lixeira-apagar'), true);
});

test('sem a lista de capacidades (modo local, sessão que não carregou) nada se esconde, e o perfil antigo continua só perguntando', async () => {
  const mesa = await abrir({papel: 'editor', api: operacao => (operacao === 'sessao' ? recusa('x', 'fora do ar', 'erro') : undefined)});
  assert.equal(mesa.janela.Sessao.pode('equipe-listar'), true);
  assert.equal(semCapacidade(mesa, 'mesa-configuracoes'), false);
  const convidado = await abrir({papel: 'convidado', api: operacao => (operacao === 'sessao' ? recusa('x', 'fora do ar', 'erro') : undefined)});
  assert.equal(convidado.janela.Sessao.pode('codex-perguntar'), true);
  assert.equal(convidado.janela.Sessao.pode('inventario'), false);
});

test('data-requer aceita várias operações (basta uma) e Sessao.aplicar vale para o que nasce depois da carga', async () => {
  const mesa = await abrir({papel: 'leitor'});
  const botao = mesa.doc.createElement('button');
  botao.dataset.requer = 'caderno-salvar inventario';
  mesa.doc.body.append(botao);
  mesa.janela.Sessao.aplicar();
  assert.equal(botao.hasAttribute('data-sem-capacidade'), false, 'o leitor alcança `inventario`');
  botao.dataset.requer = 'caderno-salvar equipe-listar';
  mesa.janela.Sessao.aplicar();
  assert.equal(botao.hasAttribute('data-sem-capacidade'), true);
});

test('o botão Configurações do cabeçalho abre a aba Configurações, de qualquer área', async () => {
  const mesa = await abrir({papel: 'dono', url: 'http://127.0.0.1:8765/?area=codex'});
  mesa.$('mesa-configuracoes').click(); await mesa.esperar(8);
  assert.equal(area(mesa), 'configuracoes');
  assert.equal(mesa.$('area-configuracoes').hidden, false);
  assert.equal(mesa.$('conta-aba-configuracoes').getAttribute('aria-pressed'), 'true');
  assert.equal(mesa.$('conta-aba-conta').getAttribute('aria-pressed'), 'false');
  mesa.$('ver-configuracoes').click(); await mesa.esperar(8);   // o perfil continua abrindo Minha conta
  assert.equal(mesa.$('conta-aba-conta').getAttribute('aria-pressed'), 'true');
});

// --- Redação suspensa -------------------------------------------------------------------------------------------------------------------
const suspensa = () => recusa('redacao_suspensa', 'Esta redação está suspensa.', 'proibido');
const bloco = mesa => mesa.doc.querySelector('.estado-suspensa');

test('403 redacao_suspensa em qualquer pedido: o estado vale para a Mesa inteira, com o texto, o aviso e "Sair"', async () => {
  const mesa = await abrir({papel: 'editor'});
  assert.equal(bloco(mesa), null);
  mesa.janela.Sessao.recusada({codigo: 'redacao_suspensa'});
  assert.equal(mesa.doc.body.dataset.suspensa, 'true');
  assert.ok(bloco(mesa));
  assert.equal(mesa.doc.querySelectorAll('.estado-suspensa').length, 1, 'um bloco só, mesmo com várias recusas');
  assert.equal(bloco(mesa).querySelector('h1').textContent, '!Redação suspensa');
  assert.equal(bloco(mesa).querySelector('.estado-sinal-texto').getAttribute('aria-hidden'), 'true');
  assert.ok(bloco(mesa).textContent.includes('Ninguém desta redação usa a Mesa enquanto a suspensão durar. Nada foi apagado: apurações, documentos e registros continuam guardados.'));
  assert.ok(bloco(mesa).textContent.includes('Fale com quem administra o serviço.'));
  assert.equal(bloco(mesa).getAttribute('role'), 'status');
  assert.ok(mesa.doc.activeElement === bloco(mesa), 'o foco vai ao aviso');
  assert.equal([...bloco(mesa).querySelectorAll('button')].map(b => b.textContent).join(), 'Sair');
});

test('a recusa chega pelo pedido do dia a dia (api) e pela sessão (GET /api/sessao)', async () => {
  const pedido = await abrir({papel: 'reporter', api: operacao => (operacao === 'inventario' ? suspensa() : undefined)});
  await assert.rejects(pedido.avaliar("api('inventario', {})"));
  assert.ok(bloco(pedido), 'por api()');
  const sessao = await abrir({papel: 'dono', api: operacao => (operacao === 'sessao' ? suspensa() : undefined)});
  assert.ok(bloco(sessao), 'por /api/sessao');
  assert.equal(sessao.janela.Sessao.dados(), null);
});

test('"Sair" do estado suspenso encerra a sessão como o botão do cabeçalho', async () => {
  const mesa = await abrir({papel: 'editor'});
  mesa.janela.Sessao.suspender();
  [...bloco(mesa).querySelectorAll('button')][0].click(); await mesa.esperar(8);
  assert.ok(mesa.chamadas.some(c => c.operacao === 'sessao-sair'));
});

test('em inglês, o estado suspenso fala inglês', async () => {
  const mesa = await abrir({papel: 'editor', idioma: 'en'});
  mesa.janela.Sessao.suspender();
  assert.equal(bloco(mesa).querySelector('h1').textContent, '!Newsroom suspended');
  assert.ok(bloco(mesa).textContent.includes('Nobody in this newsroom uses the desk while the suspension lasts.'));
  assert.ok(bloco(mesa).textContent.includes('Talk to whoever runs the service.'));
  assert.equal([...bloco(mesa).querySelectorAll('button')][0].textContent, 'Sign out');
});

test('o CSS esconde o resto da Mesa no estado suspenso e as cores são as de aviso, só com tokens', () => {
  const css = fs.readFileSync(path.join(__dirname, '..', 'interface', 'style.css'), 'utf8');
  assert.ok(css.includes('body[data-suspensa] #conteudo>:not(.estado-suspensa)'));
  assert.ok(css.includes('[data-sem-capacidade]{display:none!important}'));
  const regras = css.slice(css.indexOf('/* Papéis e estados da Mesa inteira'));
  assert.ok(regras.includes('var(--theme-warning-bg)') && regras.includes('var(--theme-warning-line)') && regras.includes('var(--theme-warning)'));
  assert.ok(!/#[0-9a-f]{3,8}\b|rgba?\(/i.test(regras), 'nenhuma cor solta');
});

// --- Ressalvas da Coruja sobre 29aeafa -----------------------------------------------------------------------------------------------------
test('P1: o convidado antigo abre Minha conta pelo perfil, só com o que o papel dele alcança', async () => {
  const mesa = await abrir({papel: 'convidado', url: 'http://127.0.0.1:8765/?area=codex'});
  assert.deepEqual(mesa.erros, []);
  assert.equal(mesa.$('ver-configuracoes').hidden, false, 'o perfil aparece também para ele');
  mesa.$('ver-configuracoes').click(); await mesa.esperar(10);
  assert.equal(area(mesa), 'configuracoes', 'não cai de volta em Perguntar');
  assert.equal(mesa.$('area-configuracoes').hidden, false);
  assert.equal(mesa.$('conta-aba-conta').getAttribute('aria-pressed'), 'true');
  assert.equal(mesa.$('conta-aba-equipe').hidden, true); assert.equal(mesa.$('conta-aba-configuracoes').hidden, true);
  assert.ok(mesa.chamadas.some(c => c.operacao === 'conta-ver'), 'Minha conta carrega os dados da própria conta');
  const proibidas = mesa.chamadas.map(c => c.operacao).filter(op => !CAPACIDADES.convidado.includes(op) && !['sessao', 'catalogo', 'integracao', 'cota'].includes(op));   // as quatro são leituras (GET) abertas a quem tem sessão
  assert.deepEqual(proibidas, [], 'só pede o que o papel alcança');
  mesa.$('ver-codex').click(); await mesa.esperar(4);
  assert.equal(area(mesa), 'codex', 'e volta a Perguntar');
});

test('P2: sem a capacidade a Mesa não chama continuidade-resumo (o leitor levava 403 a cada abertura)', async () => {
  const leitor = await abrir({papel: 'leitor', url: 'http://127.0.0.1:8765/?area=quadros&caso=alfa'});
  await assert.rejects(leitor.avaliar("api('continuidade-resumo', {caso: 'alfa'})"), falha => falha.result.codigo === 'operacao_proibida');
  assert.ok(!leitor.chamadas.some(c => c.operacao === 'continuidade-resumo'), 'nada vai ao servidor');
  const reporter = await abrir({papel: 'reporter', url: 'http://127.0.0.1:8765/?area=quadros&caso=alfa'});
  await reporter.avaliar("api('continuidade-resumo', {caso: 'alfa'})");
  assert.ok(reporter.chamadas.some(c => c.operacao === 'continuidade-resumo'), 'quem tem a capacidade chama');
});
