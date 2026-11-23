'use strict';
// Apoio dos testes de Minha conta (conta.cjs) e Equipe (equipe.cjs): a Mesa de teste com a pilha de scripts de conta.js e equipe.js, as respostas
// do servidor nos formatos de testes/test_sessoes_conta.py e testes/test_equipe.py, e pequenos auxiliares. Não tem testes.
const {criarMesa, Evento, PILHA} = require('./dom_minimo.cjs');

const SCRIPTS = PILHA.flatMap(nome => (nome === 'gerenciar.js' ? [nome, 'fator.js', 'conta.js', 'equipe.js'] : [nome]));
const DIA = 86400000;
const ID = {ana: 'a'.repeat(16), rui: 'b'.repeat(16), cora: 'c'.repeat(16), davi: 'd'.repeat(16), eva: 'e'.repeat(16)};
const CAPACIDADES_DONO = ['conta-ver', 'conta-atualizar', 'conta-sessoes', 'equipe-listar', 'equipe-atividade', 'equipe-convidar', 'equipe-convite-reenviar', 'equipe-convite-cancelar', 'equipe-recuperar', 'equipe-recuperar-confirmar', 'conta-fator-iniciar', 'conta-fator-confirmar', 'conta-fator-codigos', 'ia-config'];
const CAPACIDADES_REPORTER = ['conta-ver', 'conta-atualizar', 'conta-sessoes', 'conta-fator-iniciar', 'conta-fator-confirmar', 'conta-fator-codigos'];

const sessaoDe = (papel = 'dono', extra = {}) => ({
  conta: {id: ID.ana, nome: 'Ana Lima', email: 'ana@redacao.org', login: 'ana.lima', papel, casos: papel === 'dono' ? null : ['alfa'], ...extra},
  organizacao: {id: 'o1', nome: 'Redação Serena'}, pendencias: [], capacidades: papel === 'dono' ? CAPACIDADES_DONO : CAPACIDADES_REPORTER,
  csrf: 'x', ambiente: 'homologacao', modo: 'piloto', expira_em: null});
const contaVer = (papel = 'dono', extra = {}, definidaHa = 12) => ({
  conta: {id: ID.ana, nome: 'Ana Lima', email: 'ana@redacao.org', login: 'ana.lima', papel, idioma: 'pt',
    senha_definida_em: new Date(Date.now() - definidaHa * DIA).toISOString(), criada_em: '2026-01-01T00:00:00+00:00', ...extra},
  organizacao: {id: 'o1', nome: 'Redação Serena'}, segundo_fator: {ativo: false, ativado_em: null, codigos_restantes: 0}, termos: null});
const sessaoItem = (id, aparelho, atual, ultimoUso = new Date(Date.now() - DIA).toISOString(), ip = '189.40.12.7') => ({id, aparelho, cliente: 'web', criada_em: ultimoUso, ultimo_uso: ultimoUso, expira_em: null, ip, ip_criacao: ip, atual});

const ALFA = {id: 'alfa', titulo: 'Pauta Alfa', rodadas: []};
const BETA = {id: 'beta', titulo: 'Campo Verde', rodadas: []};
const GAMA = {id: 'gama', titulo: 'Pauta Gama', rodadas: []};
const DELTA = {id: 'delta', titulo: 'Pauta Delta', rodadas: []};
const CATALOGO = [ALFA, BETA, GAMA, DELTA];

const pessoa = (id, nome, papel, extra = {}) => ({id, nome, login: nome.toLowerCase().replace(/\W+/g, '.'), email: `${nome.split(' ')[0].toLowerCase()}@redacao.org`, papel,
  organizacao: 'o1', casos: papel === 'dono' ? null : [], cota_diaria: null, teto_mensal_brl: null, idioma: 'pt', ativa: true, situacao: 'ativa',
  criada_em: '2026-01-01T00:00:00+00:00', senha_definida_em: '2026-01-02T00:00:00+00:00', ativacao_expira_em: null, ativacao_vencida: false,
  migrada_de_convite: false, responsavel_de: [], sessao_aberta: true, ultimo_uso: null,
  gasto: {mes: '2026-11', gasto_brl: '18.40', teto_brl: '50.00', saldo_brl: '31.60', esgotada: false}, ...extra});
const equipeListar = (pessoas, extra = {}) => ({redacao: {id: 'o1', nome: 'Redação Serena', situacao: 'ativa', cota_mensal_brl: '150', teto_por_pessoa_brl: '50.00'},
  pessoas, gasto: {mes: '2026-11', gasto_brl: '24.50', teto_brl: '150.00', saldo_brl: '125.50', esgotada: false}, convites: [], ...extra});

// Um convite pendente como `equipe-listar` o devolve (acesso._convite_publico).
const convite = (id, email, extra = {}) => ({id, email, papel: 'leitor', casos: [], idioma: 'pt', estado: 'pendente', criado_em: new Date(Date.now() - 2 * DIA).toISOString(),
  enviado_em: new Date(Date.now() - 2 * DIA).toISOString(), expira_em: new Date(Date.now() + 5 * DIA).toISOString(), envio: 'enviado', convidado_por: ID.ana, convidado_por_nome: 'Ana Lima', ...extra});

// A resposta de uma operação: função ou valor; `Error` com `result` é a recusa do servidor.
const recusa = (codigo, erro, estado = 'erro') => Object.assign(new Error(erro), {result: {estado, codigo, erro}});

function abrir({papel = 'dono', sessao, idioma = 'pt', desktop = true, api = () => undefined, catalogo = CATALOGO, url = 'http://127.0.0.1:8765/?area=configuracoes', armazenamento} = {}) {
  const respostas = {sessao: sessao || sessaoDe(papel), cota: {conta: {gasto_brl: '18.40', teto_brl: '50.00', saldo_brl: '31.60', esgotada: false}},
    'conta-ver': contaVer(papel), 'conta-sessoes': {sessoes: [sessaoItem('s'.repeat(16), 'Edge · Windows', true, new Date().toISOString(), '127.0.0.1')]},
    'equipe-listar': equipeListar([pessoa(ID.ana, 'Ana Lima', 'dono'), pessoa(ID.rui, 'Rui Castro', 'reporter')]), 'equipe-atividade': {eventos: [], proximo: null}};
  const mesa = criarMesa({modo: 'piloto', papel: papel === 'dono' ? 'admin' : papel, idioma, desktop, scripts: SCRIPTS, url, catalogo, armazenamento: armazenamento || (idioma === 'en' ? {'vlado-idioma': 'en'} : {}),
    api: (operacao, dados) => {
      const personalizada = api(operacao, dados);
      if (personalizada !== undefined) { if (personalizada instanceof Error) throw personalizada; return personalizada; }
      const padrao = respostas[operacao];
      if (padrao instanceof Error) throw padrao;
      return typeof padrao === 'function' ? padrao(dados) : (padrao ?? {});
    }});
  return {mesa, respostas};
}
const esperar = mesa => mesa.esperar(30);
const texto = no => (no?.textContent || '').replace(/\s+/g, ' ').trim();
const digitar = (entrada, valor) => { entrada.value = valor; entrada.dispatchEvent(new Evento('input', {bubbles: true})); };
const mudar = (caixa, valor) => { caixa.value = valor; caixa.dispatchEvent(new Evento('change', {bubbles: true})); };
const botaoPorTexto = (raiz, rotulo) => [...raiz.querySelectorAll('button')].find(b => b.textContent.trim() === rotulo);
const dialogo = mesa => mesa.doc.querySelector('dialog.dialogo');
const dados = valor => JSON.parse(JSON.stringify(valor));
const tecla = (alvo, key) => { const evento = new Evento('keydown', {key, bubbles: true, cancelable: true}); alvo.dispatchEvent(evento); return evento; };

module.exports = {convite, SCRIPTS, abrir, esperar, texto, digitar, mudar, botaoPorTexto, dialogo, dados, tecla, recusa, sessaoDe, contaVer, sessaoItem, equipeListar, pessoa, ID, CATALOGO, ALFA, BETA, GAMA, DELTA,
  DIA, Evento, CAPACIDADES_DONO, CAPACIDADES_REPORTER};
