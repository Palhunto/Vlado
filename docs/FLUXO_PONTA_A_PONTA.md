# Fluxo de ponta a ponta: do caso à revisão humana

Este guia segue o percurso que `testes/test_ponta_a_ponta_fases.py` executa num caso temporário, sem chave, sem modelo e sem internet. Ele serve para entender como as áreas se encadeiam; não é piloto editorial nem avaliação de qualidade. Os formatos de cada passo estão no contrato de evidência (`.maestro/equipe/CONTRATO_EVIDENCIA.md`).

## 1. Criar a apuração

Cadastre os documentos numa nova apuração (`scripts/cadastrar_documentos.py --novo` ou a tela de cadastro). Para usar páginas da web, escolha na criação o modo **Documentos + web** e informe o único site permitido. O modo fica no manifesto e não muda depois.

## 2. Capturar uma fonte web (só no modo com web)

A pedido do jornalista, capture a página indicada por ele (painel "Fontes web desta apuração" ou `python scripts/fontes_web.py --caso ID --url https://…`). A captura recebe um ID `W001`, guarda o conteúdo como recebido, a cópia de texto, o endereço, o horário e o hash. O que o HTML esconde (`hidden`, `aria-hidden`, `display:none`) fica fora da cópia de texto, e a captura é marcada com `contem_texto_oculto`. Ocultação por CSS não é detectada (ver as pendências no README).

## 3. Congelar a rodada e registrar evidências

Ao enviar a pergunta, a rodada congela documentos e capturas e monta o índice. Os achados publicados citam cada evidência com documento (`D001`, `W001`…), localizador e trecho; a captura é citada com o endereço e o horário do acesso. Uma evidência só é aceita depois de conferida contra o original por hash.

## 4. Hipóteses e tabela de apuração

Em **Quadros de evidência → Hipóteses**, registre a hipótese com as evidências que a sustentam e as lacunas que faltam. A hipótese só aparece "com evidência" quando há suporte conferido, avaliado como sustentado e de natureza documental. Em **Tabelas**, cada célula aponta para uma evidência da tabela; os cálculos declarados mostram as células usadas, a operação e o resultado.

## 5. Rascunho e retomada

A pergunta em preparo e os formulários dos quadros são salvos enquanto se digita. Ao voltar, a Mesa oferece restaurar ou descartar o rascunho, e o resumo da entrada do caso lista documentos pendentes, a rodada atual, quadros com pendências e rascunhos abertos, sem o texto deles.

## 6. Conferência da redação

Em **Conferência do texto**, cole o texto. Ele é dividido em afirmações; cada uma recebe as evidências que a sustentam. A afirmação sem vínculo aparece **sem suporte**, e os sinais automáticos apontam números, quantificadores, causalidade e certeza que vão além da fonte. Os sinais nunca mudam um vínculo nem um estado declarado.

## 7. Pergunta e pauta

Em **Entrevistas e pedidos**, a lacuna da hipótese (ou a afirmação sem suporte) vira uma pergunta por modelo fixo, ligada a uma diligência com destinatário, tipo e prazo. A pauta interna sai em Markdown com o motivo e as evidências; o texto do pedido leva só as perguntas.

## 8. Revisão humana

A revisão de uma afirmação (**Conferida no original**, **Precisa de ajuste** ou **Sem suporte suficiente**) só é registrada por uma conta autenticada da Mesa. Sem conta, inclusive no modo local, o pedido é recusado. A revisão pela IA nunca é registrada como humana.

## Como conferir

```powershell
python -m unittest discover -s testes -p "test_ponta_a_ponta_fases.py" -v
```

O teste serve a página da fonte web por `http.server` em `127.0.0.1`, com a chave de teste `fontes_web.TESTE_LOCAL` ligada só durante a execução.
