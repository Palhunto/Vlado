'use strict';
// Os dados da própria conta (E4b de Contas; docs/design/componentes.md#minha-conta e #excluir-conta): exportar o que o Vlado guarda sobre a pessoa e excluir a conta. Servem a Minha conta
// (conta.js) e à página dos termos (termos.js), que é a do Entrar e por isso não depende de conta.js nem de estados.js; o diálogo de excluir pede dialogo.js.
//
//   DadosConta.exportar({chamarBruto})            baixa o JSON de conta-exportar com o nome que o servidor manda; devolve {nome, incompleto} (o que o arquivo ainda não traz, já em frases na língua da interface)
//   DadosConta.excluir({nome, gatilho, chamar, aoExcluir})   o diálogo "Excluir a sua conta?" (nome, depois senha); devolve true se a conta foi excluída
//   DadosConta.chamadorBruto()                    `chamarBruto` para quem não tem o `api` da Mesa: a sessão aberta e o token CSRF de GET /api/sessao
//   DadosConta.endereco(texto)                    o endereço dos termos, só se for https:// (nunca javascript: nem outro esquema)
(() => {
  const t = (pt, vars) => (window.I18N ? window.I18N.t(pt, vars) : String(pt).replace(/\{(\w+)\}/g, (todo, nome) => vars?.[nome] ?? todo));
  const NOME_PADRAO = 'vlado-meus-dados.json';
  // O arquivo diz o que ainda não traz em códigos fixos (contrato de contas, 4b-2, ressalva E4); a tela os traduz. Código que a Mesa não conhece aparece como veio.
  const NAO_TRAZ = {itens_criados: 'notas, revisões e conversas que você criou', registro_de_acesso: 'acessos do registro de auditoria'};
  // `conversas_anteriores` (4b-2b): as conversas de antes de `conversas_desde` (data) não trazem quem as criou; sem a data, o arquivo não a sabe.
  function dataDoArquivo(texto) {
    const dia = new Date(texto);
    if (typeof texto !== 'string' || Number.isNaN(dia.getTime())) return null;
    return dia.toLocaleDateString(window.I18N?.idioma?.() === 'en' ? 'en-US' : 'pt-BR', {day: 'numeric', month: 'short', year: 'numeric', timeZone: 'UTC'});
  }
  function frasesDoQueFalta(codigos, desde) {
    return codigos.map(String).map(codigo => {
      if (NAO_TRAZ[codigo]) return t(NAO_TRAZ[codigo]);
      if (codigo === 'conversas_anteriores') { const dia = dataDoArquivo(desde); return dia ? t('conversas criadas antes de {dia}', {dia}) : t('conversas criadas antes de uma data que o arquivo não informa'); }
      return codigo;
    });
  }
  const ULTIMO_DONO = 'A redação precisa de ao menos um dono ativo. Antes de excluir a sua conta, torne outra pessoa dono na Equipe.';
  const TEXTO_DA_EXCLUSAO = 'Você sai da Mesa agora e não entra mais com esta conta. Suas notas, revisões e conversas ficam com a redação, e a Mesa passa a mostrar o autor como «Conta excluída». O seu nome continua gravado nos registros já feitos e nos backups, que não podem ser reescritos.';

  // O servidor responde ao navegador com o token da sessão em X-Session-Token; a Mesa o tem (app.js); a página dos termos o lê de GET /api/sessao.
  function chamadorBruto() {
    let csrf = typeof token === 'string' ? token : null;
    return async (operacao, dados = {}) => {
      if (!csrf) {
        const sessao = await fetch('/api/sessao', {headers: {Accept: 'application/json'}, credentials: 'same-origin'});
        if (!sessao.ok) throw Object.assign(new Error(t('Sessão expirada ou encerrada. Entre novamente.')), {result: {codigo: 'sessao_expirada'}});
        csrf = (await sessao.json()).csrf;
      }
      return fetch(`/api/${operacao}`, {method: 'POST', credentials: 'same-origin', headers: {'Content-Type': 'application/json', 'X-Session-Token': csrf}, body: JSON.stringify(dados)});
    };
  }
  // `chamar` para quem não tem o `api` da Mesa (a página dos termos): como o `api`, devolve o corpo ou lança com `result`.
  function chamadorDaSessao() {
    const bruto = chamadorBruto();
    return async (operacao, dados = {}) => {
      const resposta = await bruto(operacao, dados);
      let corpo = {};
      try { corpo = await resposta.json(); } catch (_) { /* sem corpo */ }
      if (!resposta.ok) throw Object.assign(new Error(textoDoErro(corpo)), {result: corpo});
      return corpo;
    };
  }
  // O texto de uma recusa do servidor, na língua da interface quando o dicionário a tem; senão, a mensagem que veio.
  function textoDoErro(corpo, padrao) {
    const original = corpo?.erro;
    if (window.I18N?.idioma?.() === 'en') {
      // Pelo código estável, quando o dicionário o tem (429 limite_de_exportacoes); senão pelo texto do servidor.
      if (corpo?.codigo && window.VLADO_I18N_EN?.erros?.[corpo.codigo]) return window.I18N.erro(corpo);
      if (original) { const traduzido = window.I18N.traduzir?.(original); if (traduzido) return traduzido; }
    }
    return original || padrao || t('Não foi possível completar a operação.');
  }
  // O nome do arquivo de Content-Disposition: filename*=UTF-8''… ou filename="…"; nunca um caminho (só o último pedaço, sem barras).
  function nomeDoArquivo(cabecalho) {
    if (!cabecalho) return NOME_PADRAO;
    const estendido = /filename\*\s*=\s*UTF-8''([^;]+)/i.exec(cabecalho), simples = /filename\s*=\s*"?([^";]+)"?/i.exec(cabecalho);
    let nome = estendido ? estendido[1] : simples ? simples[1] : '';
    try { nome = decodeURIComponent(nome); } catch (_) { /* fica como veio */ }
    nome = nome.split(/[\\/]/).pop().replace(/[\x00-\x1f]/g, '').trim();
    return nome || NOME_PADRAO;
  }
  async function exportar({chamarBruto = chamadorBruto()} = {}) {
    const resposta = await chamarBruto('conta-exportar', {});
    if (!resposta.ok) {
      let corpo = {};
      try { corpo = await resposta.json(); } catch (_) { /* sem corpo */ }
      throw Object.assign(new Error(textoDoErro(corpo)), {result: corpo});
    }
    const arquivo = await resposta.blob();
    const nome = nomeDoArquivo(resposta.headers?.get?.('Content-Disposition'));
    let incompleto = [];
    try { const lido = JSON.parse(await arquivo.text()); if (Array.isArray(lido?.incompleto)) incompleto = frasesDoQueFalta(lido.incompleto, lido.conversas_desde); } catch (_) { /* o arquivo vale mesmo assim */ }
    // Gerado no navegador: o arquivo baixado é o do servidor, sem rede a mais.
    const endereco = URL.createObjectURL(arquivo), ancora = document.createElement('a');
    ancora.href = endereco; ancora.download = nome; ancora.rel = 'noopener';
    document.body.append(ancora); ancora.click(); ancora.remove();
    setTimeout(() => URL.revokeObjectURL(endereco), 1000);
    return {nome, incompleto};
  }

  // "Excluir a sua conta?": o nome antes da senha (o servidor confere o nome primeiro, e o erro não conta como senha errada). Sucesso: a sessão acaba na mesma resposta e a Mesa vai ao Entrar.
  async function excluir({nome, gatilho, chamar, aoExcluir}) {
    const enviar = chamar || ((operacao, dados) => api(operacao, dados));
    let excluida = false;
    await window.Dialogo.confirmar({variante: 'campo', titulo: 'Excluir a sua conta?', texto: TEXTO_DA_EXCLUSAO, nome, rotuloDoNome: 'Digite o seu nome, «{nome}», para confirmar',
      acao: 'Excluir a conta', ocupado: 'Excluindo…', gatilho,
      campos: [{id: 'senha', rotulo: 'Sua senha', apoio: 'A senha com que você entra na Mesa.', autocomplete: 'current-password', exigido: true}],
      async executar(ctx) {
        try { await enviar('conta-excluir', {senha: ctx.valores().senha, nome: ctx.valor()}); }
        catch (falha) {
          const codigo = falha?.result?.codigo, texto = falha?.result?.erro || falha?.message || '';
          if (codigo === 'ultimo_dono') throw new Error(t(ULTIMO_DONO));
          // O nome que não confere: o erro vai ao campo do nome, com o texto do servidor, e o foco volta a ele.
          if (codigo === 'nome_confirmacao_divergente' || /^Digite o nome/.test(texto)) throw Object.assign(new Error(textoDoErro(falha?.result, falha?.message)), {campoNome: true});
          const recusa = window.Dialogo.recusaDaSenha(falha);
          throw recusa === falha ? new Error(textoDoErro(falha?.result, falha?.message)) : recusa;
        }
        excluida = true;
      }});
    if (!excluida) return false;
    (aoExcluir || (() => location.replace('/entrar?aviso=conta_excluida')))();
    return true;
  }

  const endereco = texto => (typeof texto === 'string' && /^https:\/\/[^\s]+$/i.test(texto) ? texto : null);

  window.DadosConta = {exportar, excluir, chamadorBruto, chamadorDaSessao, endereco, nomeDoArquivo};
})();
