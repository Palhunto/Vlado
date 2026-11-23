'use strict';
// A pendência de termos novos (E4b-1 de Contas, só no `piloto`; docs/design/componentes.md#pendencia-termos): a página GET /conta/termos, da família do Entrar (marca, cartão de 440 px e rodapé).
// Quem não aceita ainda leva os próprios dados e pode excluir a conta (ressalva B2 do contrato); com a pendência do segundo fator também aberta, o servidor recusa as duas (403
// pendencia_de_conta): então os dois links só aparecem sem ela, e no lugar fica a frase "Depois de cadastrar o segundo fator, ..." (B1 da Coruja). Não depende de conta.js nem de estados.js; "Excluir a conta" pede dialogo.js e dados_conta.js (que vêm antes).
//
//   Termos.pagina(alvo, {chamar, sair, abrirMesa, pendencias})   o conteúdo do cartão. `pendencias` é o de GET /api/sessao (sem a lista, os links de dados não aparecem); `chamar` é como o `api` da Mesa (padrão: a sessão aberta);
//                                                               `abrirMesa()` vai a "/" (o servidor manda à pendência seguinte); `sair()` vai ao Entrar depois de sessao-sair
(() => {
  const t = (pt, vars) => (window.I18N ? window.I18N.t(pt, vars) : String(pt).replace(/\{(\w+)\}/g, (todo, nome) => vars?.[nome] ?? todo));

  function no(etiqueta, classe, texto) {
    const elemento = document.createElement(etiqueta);
    if (classe) elemento.className = classe;
    if (texto !== undefined && texto !== null) elemento.textContent = texto;
    return elemento;
  }
  function botao(rotulo, classe, aoClicar) {
    const controle = no('button', classe, t(rotulo)); controle.type = 'button';
    if (aoClicar) controle.addEventListener('click', aoClicar);
    return controle;
  }
  // O texto do servidor na língua da interface, quando o dicionário o tem.
  function textoDoErro(falha) {
    const corpo = falha?.result || {};
    if (corpo.erro && window.I18N?.idioma?.() === 'en') { const traduzido = window.I18N.traduzir?.(corpo.erro); if (traduzido) return traduzido; }
    return corpo.erro || falha?.message || t('Não foi possível completar a operação.');
  }
  // "Prefere não aceitar? Você pode {baixar} ou {excluir}.": os dois pedaços são links, no meio da frase traduzida.
  function frase(modelo, partes) {
    const resultado = document.createDocumentFragment();
    for (const pedaco of t(modelo).split(/(\{\w+\})/)) {
      const chave = /^\{(\w+)\}$/.exec(pedaco)?.[1];
      if (chave && partes[chave]) resultado.append(partes[chave]); else if (pedaco) resultado.append(pedaco);
    }
    return resultado;
  }

  function pagina(alvo, {chamar = window.DadosConta.chamadorDaSessao(), sair, abrirMesa, pendencias} = {}) {
    alvo.classList.add('fator-pagina', 'termos-pagina');
    // Sem a lista de pendências (quem chama não a leu), vale o lado seguro: trata-se como pendência do fator desconhecida e os links de dados não aparecem (V1 da Coruja).
    const fatorPendente = !Array.isArray(pendencias) || pendencias.includes('segundo_fator');
    const comSaidas = !fatorPendente && !!window.DadosConta && !!window.Dialogo;
    let enviando = false;

    const sairDaConta = botao('Sair', 'fator-link', async () => { try { await chamar('sessao-sair', {}); } catch (_) { /* a sessão cai de qualquer jeito */ } sair?.(); });
    const rodape = no('p', 'fator-rodape'); rodape.append(sairDaConta);

    async function carregar(aviso) {
      alvo.replaceChildren(no('p', 'fator-rubrica-pagina', t('ANTES DE CONTINUAR')), no('p', 'fator-texto', t('Carregando…')), rodape);
      let resposta;
      try { resposta = await chamar('conta-ver', {}); }
      catch (falha) {
        const erro = no('p', 'fator-erro', textoDoErro(falha)); erro.setAttribute('role', 'alert');
        const outra = botao('Tentar de novo', 'secondary', () => carregar());
        alvo.replaceChildren(no('p', 'fator-rubrica-pagina', t('ANTES DE CONTINUAR')), erro, outra, rodape);
        return;
      }
      desenhar(resposta, aviso);
    }

    function desenhar(resposta, aviso) {
      const vigente = resposta.termos_vigente;
      if (!vigente?.versao) { abrirMesa?.(); return; }  // nada a aceitar (já aceitos em outra aba, ou esta instalação não tem termos)
      const titulo = no('h1', 'fator-titulo-pagina', t(resposta.termos ? 'Os termos de uso mudaram' : 'Aceite os termos de uso'));
      const texto = no('p', 'fator-texto', t('Para continuar usando o Vlado, leia e aceite os termos de uso e a política de privacidade do teste (versão {versao}).', {versao: vigente.versao}));
      const partes = [no('p', 'fator-rubrica-pagina', t('ANTES DE CONTINUAR')), titulo, texto];

      const enderecoDosTermos = window.DadosConta?.endereco(vigente.endereco);
      if (enderecoDosTermos) {
        const ler = document.createElement('a'); ler.href = enderecoDosTermos; ler.target = '_blank'; ler.rel = 'noopener noreferrer'; ler.className = 'conta-link termos-ler'; ler.textContent = t('Ler os termos');
        const linhaDoLink = no('p', 'fator-texto'); linhaDoLink.append(ler); partes.push(linhaDoLink);
      }

      // A caixa de aviso da página: o que mudou enquanto se lia (neutro) ou o que o servidor recusou (erro).
      const avisoDaPagina = no('p', 'fator-texto termos-aviso', aviso || ''); avisoDaPagina.setAttribute('role', 'alert'); avisoDaPagina.hidden = !aviso;
      const caixa = document.createElement('input'); caixa.type = 'checkbox'; caixa.id = 'termos-aceito'; caixa.setAttribute('aria-describedby', 'termos-erro');
      const rotuloDaCaixa = no('label', 'termos-caixa'); rotuloDaCaixa.append(caixa, no('span', '', t('Li e aceito os termos de uso e a política de privacidade do teste.')));
      const erroDaCaixa = no('p', 'fator-erro termos-erro', ''); erroDaCaixa.id = 'termos-erro'; erroDaCaixa.hidden = true;
      const status = no('p', 'fator-apoio termos-estado', ''); status.setAttribute('role', 'status'); status.setAttribute('aria-live', 'polite'); status.hidden = true;
      const aceitar = botao('Aceitar e abrir a Mesa', 'fator-principal', null);
      aceitar.addEventListener('click', () => enviar(aceitar, caixa, erroDaCaixa, avisoDaPagina, vigente.versao));
      caixa.addEventListener('change', () => { if (caixa.checked) { erroDaCaixa.hidden = true; caixa.removeAttribute('aria-invalid'); } });
      const acoes = no('div', 'fator-acoes fator-acoes-fim'); acoes.append(aceitar);
      partes.push(avisoDaPagina, rotuloDaCaixa, erroDaCaixa, acoes);

      if (comSaidas) {
        const baixar = botao('baixar seus dados', 'fator-link termos-saida', () => baixarArquivo(baixar, status));
        const excluir = botao('excluir a conta', 'fator-link termos-saida', () => window.DadosConta.excluir({nome: resposta.conta?.nome || '', gatilho: excluir, chamar}));
        const preferencia = no('p', 'fator-apoio termos-nao-aceitar'); preferencia.append(frase('Prefere não aceitar? Você pode {baixar} ou {excluir}.', {baixar, excluir}));
        partes.push(preferencia, status);
      } else if (fatorPendente) {  // o servidor recusa as duas saídas com a pendência do fator (403 pendencia_de_conta): no lugar dos links, o aviso
        partes.push(no('p', 'fator-apoio termos-nao-aceitar', t('Depois de cadastrar o segundo fator, você poderá baixar seus dados ou excluir a conta.')));
      }
      partes.push(rodape);
      alvo.replaceChildren(...partes);
    }

    async function baixarArquivo(controle, status) {
      controle.disabled = true; status.hidden = false; status.classList.remove('fator-erro'); status.textContent = t('Preparando o arquivo…');
      try {
        const feito = await window.DadosConta.exportar();
        status.textContent = feito.incompleto.length ? `${t('Arquivo baixado.')} ${t('Ainda não traz: {itens}.', {itens: feito.incompleto.map(item => t(item)).join('; ')})}` : t('Arquivo baixado.');
      } catch (falha) { status.textContent = textoDoErro(falha); status.classList.add('fator-erro'); }
      controle.disabled = false;
    }

    async function enviar(aceitar, caixa, erroDaCaixa, avisoDaPagina, versao) {
      if (enviando) return;
      if (!caixa.checked) {
        erroDaCaixa.textContent = t('Falta aceitar os termos. Marque a caixa para continuar.'); erroDaCaixa.hidden = false; caixa.setAttribute('aria-invalid', 'true'); caixa.focus(); return;
      }
      avisoDaPagina.hidden = true;
      enviando = true; aceitar.disabled = true; aceitar.textContent = t('Aceitando…');
      try { await chamar('conta-termos-aceitar', {versao}); }
      catch (falha) {
        enviando = false;
        if (falha?.result?.codigo === 'termos_desatualizados') { carregar(t('Os termos mudaram enquanto você lia. Confira a versão nova e marque de novo.')); return; }
        aceitar.disabled = false; aceitar.textContent = t('Aceitar e abrir a Mesa');
        avisoDaPagina.textContent = textoDoErro(falha); avisoDaPagina.className = 'fator-erro termos-aviso'; avisoDaPagina.hidden = false;
        return;
      }
      enviando = false; abrirMesa?.();
    }

    carregar();
  }

  window.Termos = {pagina};
})();
