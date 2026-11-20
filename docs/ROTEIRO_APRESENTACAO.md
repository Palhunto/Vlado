# Roteiro da apresentação em sala

Ambiente: **demonstração** (dados e contas sintéticos). Nada da redação entra neste ambiente.

| Campo | Preencher |
| --- | --- |
| Endereço da demonstração | `https://______________________` |
| APK da sala (versão e SHA-256) | ver [ANDROID.md](ANDROID.md) e `android/saidas/` |
| Canal de instalação do APK | ______ (ex.: link privado, cabo USB) |
| Conta sintética de administração | login `demo.admin` — senha entregue em mãos no dia |
| Contas sintéticas de convidado | `demo.convidado1` (caso Vila Serena), `demo.convidado2` (outro caso) |
| Responsável pela apresentação / contato técnico | ______ |

## Antes (D-1)

1. Subir o ambiente de demonstração (guia técnico, seção Ambientes) e semear os dados sintéticos (`scripts/semear_ambiente.py`, que recusa o ambiente editorial).
2. Instalar o APK da sala no aparelho de apresentação; conferir o SHA-256 antes de instalar.
3. Entrar uma vez com cada conta; fazer uma pergunta de ensaio e deixar a conversa pronta (economiza tempo e custo no dia).
4. Gravar o **vídeo de contingência** (60–90 s) com o roteiro abaixo, em tela de celular, com dados sintéticos.
5. Conferir bateria, Wi-Fi da sala, espelhamento de tela e tema (o claro é mais legível no projetor).

## Roteiro (5 minutos)

1. **Entrar** — abrir o app "Vlado Sala" e entrar com `demo.admin`. Mostrar a faixa "Demonstração — dados sintéticos".
2. **Perguntar** — na apuração "Vila Serena (sintética)": *"Qual o valor do contrato 041/2025 e houve aditivo?"*. Mostrar o acompanhamento das etapas.
3. **Abrir a página original** — tocar na citação do valor; mostrar a página do PDF (inclusive a medição digitalizada, lida por OCR local) e o trecho.
4. **Inserir a referência no Caderno** — selecionar o trecho, "Inserir em nota", escolher a nota "Pauta Vila Serena".
5. **Voltar à nota** — abrir o original pela fonte da nota e voltar: a edição continua no mesmo ponto. Marcar a tarefa "Conferir medição nº 3" sem digitar e mostrar "Nota salva".
6. (Opcional) Pergunta sem suporte: *"Quem é o dono da construtora?"* — a resposta declara que os documentos não sustentam.

## Se algo falhar

- Sem internet ou API lenta: usar a conversa de ensaio já pronta; se o servidor cair, passar o vídeo de contingência.
- App não abre: usar o navegador do celular no mesmo endereço.
- Não improvisar com documentos reais.
