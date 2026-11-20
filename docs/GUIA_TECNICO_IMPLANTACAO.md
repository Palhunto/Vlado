# Guia técnico: implantação, contas e recuperação

Para quem instala e mantém o Vlado hospedado. Substitui o antigo guia de implantação por convites. Contrato de sessões e permissões: [CONTRATOS_ENTREGA.md](CONTRATOS_ENTREGA.md). Dados enviados ao provedor de IA: [DADOS_NA_INFERENCIA.md](DADOS_NA_INFERENCIA.md).

| Campo | Preencher |
| --- | --- |
| Domínio editorial | `______________________` |
| Domínio da demonstração | `______________________` |
| Domínio de homologação | `______________________` |
| Servidor(es) / provedor de hospedagem | ______ |
| Conta de API (provedor, responsável, teto de gasto) | ______ |
| Quem recebe o primeiro administrador editorial | nome: ______ canal seguro: ______ |
| Responsável pela chave de assinatura Android | ______ |
| Contato técnico de plantão | ______ |

## 1. Ambientes

São três instalações independentes, cada uma com seu `.env`, projeto Compose, volumes, contas e domínio. Nunca compartilham volume nem conta.

| Ambiente | `VLADO_AMBIENTE` | Dados | Quem usa |
| --- | --- | --- | --- |
| Homologação técnica | `homologacao` | sintéticos | equipe técnica |
| Piloto editorial privado | `editorial` | reportagem real | redação do Intercept |
| Demonstração em sala | `demonstracao` | sintéticos | apresentação; o APK `sala` aponta para cá |

A interface mostra uma faixa "Homologação — dados sintéticos" ou "Demonstração — dados sintéticos"; o editorial não tem faixa. Recomendação: o editorial num servidor só dele; homologação e demonstração podem dividir outro servidor desde que usem portas diferentes ou outro proxy na frente.

```bash
cp deploy/ambientes/editorial.env.example deploy/ambientes/editorial.env
```

Edite o domínio e a tag da imagem. Para uma primeira publicação com convidados e documentos públicos ou sintéticos, use o exemplo de `demonstracao` e mantenha os volumes dessa instância separados. Reserve um servidor Linux com Docker Compose v2, confirme o IP público e aponte o DNS para ele. Publique as portas 80 e 443 do Caddy e acesse pelo domínio para validar o certificado. Para um acervo pequeno, o ponto de partida é 2 vCPU, 4 GB de RAM e pelo menos 20 GB de disco.

Em toda operação, passe o mesmo nome de projeto e o mesmo arquivo de ambiente. O primeiro comando abaixo valida a configuração sem mostrar chaves do provedor.

```bash
docker compose -p vlado-editorial --env-file deploy/ambientes/editorial.env config --quiet
docker compose -p vlado-editorial --env-file deploy/ambientes/editorial.env up -d --build
```

O `-p` prefixa os volumes (`vlado-editorial_casos`, …). Troque `editorial` por `homologacao` ou `demonstracao` para os outros. Para homologar só na própria máquina, configure `VLADO_DOMINIO=localhost`, `VLADO_CADDYFILE=deploy/Caddyfile.interno`, `VLADO_PORTA_HTTP=127.0.0.1:8080`, `VLADO_PORTA_HTTPS=127.0.0.1:8443` e `VLADO_ORIGEM=https://localhost:8443`. Abra diretamente a URL HTTPS e use a CA da instância para verificar o certificado. No servidor com HTTPS padrão (443), deixe `VLADO_ORIGEM` ausente.

Semear dados sintéticos (só homologação e demonstração; o script recusa o editorial):

```bash
docker compose -p vlado-demonstracao --env-file deploy/ambientes/demonstracao.env exec vlado python scripts/semear_ambiente.py --origem https://SEU_DOMINIO_DEMO --saida /app/acesso/links_demo.txt
```

Os links de ativação das contas `demo.admin`, `demo.convidado1` e `demo.convidado2` ficam nesse arquivo 0600; entregue-os e apague o arquivo.

## 2. Conferir depois de subir

```bash
docker compose -p vlado-editorial --env-file deploy/ambientes/editorial.env ps
```

O serviço `vlado` deve estar `healthy`. Depois, de fora do servidor:

```bash
curl -sS -o /dev/null -w "%{http_code} %{redirect_url}\n" https://SEU_DOMINIO/
```

Esperado: `303 https://SEU_DOMINIO/entrar` (sem sessão não há dados).

```bash
curl -sS -o /dev/null -w "%{http_code}\n" https://SEU_DOMINIO/api/catalogo
```

Esperado: `401`. Confira também o certificado (cadeado válido) e o cabeçalho `Strict-Transport-Security`.

Antes de distribuir os convites, use um corpus público ou sintético para conferir o login, o acesso aos casos por conta, o cadastro e a abertura de um PDF. Reinicie os contêineres e confira que os dados continuam disponíveis. Faça um backup e teste a restauração em volumes de homologação separados. Configure a chave no servidor e os limites de uso antes da primeira pergunta pela API.

Em 15/11/2026, a homologação local da base `9b8f38e` com os ajustes de implantação confirmou o build, HTTPS com CA interna validada, HSTS, recusa do catálogo sem sessão e o login de três contas sintéticas. Cada convidado viu apenas seu caso. As contas e os casos persistiram após reiniciar o serviço. O backup sintético estava legível e excluiu segredos. O teste rodou com portas restritas a `127.0.0.1`. DNS, certificado público e operação fora da máquina serão conferidos no servidor escolhido.

## 3. Primeiro administrador

Só a administração cria contas. O primeiro administrador é criado no servidor, e o link de ativação sai **uma única vez**:

```bash
docker compose -p vlado-editorial --env-file deploy/ambientes/editorial.env exec vlado python scripts/acesso.py criar-admin --nome "Nome da pessoa" --login nome.sobrenome --origem https://SEU_DOMINIO
```

- Entregue o link por canal seguro (pessoalmente ou mensageiro com criptografia de ponta a ponta), nunca por e-mail aberto, chamado, planilha ou captura de tela.
- O link vale 72 h (`--horas 1–168`) e uma vez. A pessoa define a senha (mínimo 12 caracteres) e entra por `/entrar`.
- Para gravar o link num arquivo em vez da tela: `--saida /caminho/link.txt` (permissão 0600; apague depois de entregar).
- Os links e as senhas não vão para logs. O servidor não registra o caminho das requisições.

## 4. Contas, papéis e permissões

Pela Mesa (área **Apurações e lixeira › Contas**) ou pela linha de comando:

```bash
docker compose -p vlado-editorial --env-file deploy/ambientes/editorial.env exec vlado python scripts/acesso.py criar-conta --nome "Convidada" --login convidada.a --casos caso_x --cota 20 --origem https://SEU_DOMINIO
```

```bash
docker compose -p vlado-editorial --env-file deploy/ambientes/editorial.env exec vlado python scripts/acesso.py listar
```

| Papel | Pode |
| --- | --- |
| `admin` | contas e permissões, cadastro de documentos, casos, Mesa completa, conferência de achados, Caderno, exportações, provedor de IA |
| `convidado` | só os casos liberados e as próprias conversas: perguntar e abrir as fontes citadas nelas; sem Caderno, sem exportação, sem administração |

- Alterar casos: `acesso.py casos ID --casos a,b`. Desativar: `acesso.py desativar ID`. Reativar: `acesso.py reativar ID`. O efeito vale na requisição seguinte da pessoa.
- O último administrador ativo não pode ser desativado nem rebaixado.
- Sessões: 12 h no máximo, 2 h sem uso. Cinco senhas erradas seguidas (mesmo login e IP) bloqueiam por 15 min; há também um limite de 20 tentativas por minuto por IP.

## 5. Recuperação de acesso

Senha esquecida, link vencido ou suspeita de vazamento:

```bash
docker compose -p vlado-editorial --env-file deploy/ambientes/editorial.env exec vlado python scripts/acesso.py recuperar ID --origem https://SEU_DOMINIO
```

Isso encerra todas as sessões da conta, apaga a senha e emite um link novo (mesmas regras de entrega do item 3). Se a única conta de administração se perder, a recuperação acima pelo servidor é o caminho.

**Migração da versão com convites:** na primeira leitura, cada convite vira uma conta com o mesmo identificador (autoria de notas e conversas preservada). Ninguém tem senha depois da migração: rode `recuperar` para cada administrador e entregue os links. O arquivo anterior fica em `acesso/acesso.v1.json`.

## 6. Provedor de IA

Na Mesa, **Perguntar à IA › Conexão e opções**: provedor, modelo (opcional) e chave. A chave vai para o volume `segredos` e o navegador só vê os 4 últimos caracteres. Alternativa: `ANTHROPIC_API_KEY`/`OPENAI_API_KEY` no `.env` do ambiente. Configure um teto de gasto na conta do provedor; o Vlado tem limites próprios em `configuracao.json` (`limites`).

## 7. Backup, restauração e reversão

O backup leva casos, conversas, rodadas, lixeira, entrada, contas (`acesso/`, com os hashes de senha) e ajustes. As chaves de API só entram com `--incluir-segredos`. **O arquivo é sensível**: contém material de reportagem e os hashes de senha; guarde-o cifrado e fora do servidor.

```bash
docker compose -p vlado-editorial --env-file deploy/ambientes/editorial.env exec -T vlado python scripts/backup.py criar --destino - > vlado-editorial-AAAAMMDD.tar.gz
```

Restaurar (pare o uso durante a restauração; ela troca o conteúdo **dentro** de cada pasta, então funciona com volumes Docker montados, inclusive volumes novos):

```bash
docker compose -p vlado-editorial --env-file deploy/ambientes/editorial.env exec -T vlado python scripts/backup.py restaurar - --substituir < vlado-editorial-AAAAMMDD.tar.gz
```

- A restauração apaga as sessões (todos entram de novo) e restaura contas e senhas do momento do backup.
- Ensaie a restauração num ambiente separado (`-p vlado-restauracao`) antes de depender dela, conferindo hashes dos documentos, contas, permissões, revisões humanas, referências do Caderno e históricos (registro do ensaio em `docs/VERIFICACAO.md`).

Atualizar: backup → novo código → `VLADO_VERSAO` nova no `.env` → `up -d --build`. Reverter: `VLADO_VERSAO` anterior e `up -d` sem `--build`; se a versão nova mudou dados de forma incompatível, restaure o backup feito antes da atualização.

## 8. Android

Ver [ANDROID.md](ANDROID.md): build das variantes `sala` (aponta para a demonstração) e `redacao` (aponta para o editorial), assinatura com chave fora do pacote, SHA-256 e distribuição.

## 9. Limitações conhecidas

- Dados em texto claro nos volumes; proteja o servidor (disco cifrado, acesso SSH restrito) e defina a retenção.
- O cancelamento de uma pergunta interrompe entre eventos; uma chamada já presa no provedor termina pelo prazo do SDK.
- O processamento pelo modelo é online, no provedor escolhido (ver DADOS_NA_INFERENCIA.md).
- Com CDN ou outro proxy na frente do Caddy, o limite por IP passa a ver o IP desse proxy.
