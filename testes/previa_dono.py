"""Prévia da Mesa para a confirmação visual do dono (Ondas 2 e 3). NÃO é um teste (não começa com test_): fica fora da suíte.

Sobe, só em 127.0.0.1, DOIS servidores sobre uma pasta de dados nova e sintética, e imprime endereços, contas, senhas e códigos:

  piloto        https://127.0.0.1:8800   duas redações, contas com fator, e-mail na tela, termos de uso com versão e endereço sintéticos
  local-contas  http://127.0.0.1:8801    a Mesa instalada: uma redação, sem termos, sem fator obrigatório

O piloto confere a origem e o Host (https) e marca o cookie Secure; por isso a porta 8800 é um retransmissor TLS (certificado autoassinado, gerado na pasta) na frente do servidor,
que escuta numa porta interna. O navegador avisa do certificado na primeira vez: Avançado, continuar para 127.0.0.1. Abra sempre 127.0.0.1, nunca localhost.

Piloto, redação Alfa (dona das duas apurações semeadas, com uma conversa, uma nota e um item na lixeira): Dona Alfa (dono, SEM segundo fator: entra pelos termos, que ela ainda não aceitou,
e depois pela pendência do fator em /conta/segundo-fator, para cadastrar com o celular pelo QR), Edu Editor (só a pendência dos termos), Rita Reporter, Leo Leitor e Cora Convidada, com os termos
já aceitos. Todos, menos a Dona Alfa, têm o segundo fator já cadastrado, com os códigos de reserva impressos. Redação Beta: Dono Beta e Rep Beta (com
fator) e uma apuração. Nada de chave de API: a Mesa não pergunta ao agente e mostra "Chave de API ausente no servidor" em Perguntar. A pasta só tem dados sintéticos; nunca use casos/, acesso/ ou segredos/ do projeto.

  .venv/Scripts/python.exe testes/previa_dono.py [--pasta PASTA] [--local-vazio] [--so-verificar]

--pasta        onde criar os dados (nova ou vazia; padrão: uma pasta nova no temporário do sistema)
--local-vazio  a Mesa instalada sem nenhuma conta, para ver o Primeiro acesso
--so-verificar sobe, confere que cada servidor responde e sai (sem esperar)
"""
from __future__ import annotations

import argparse
import datetime
import http.client
import os
from pathlib import Path
import secrets
import socket
import socketserver
import ssl
import sys
import tempfile
import threading
import time
import uuid

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ / 'scripts'))
sys.path.insert(0, str(Path(__file__).resolve().parent))

PORTA_PILOTO, PORTA_LOCAL = 8800, 8801
ORIGEM_PILOTO = f'https://127.0.0.1:{PORTA_PILOTO}'
TERMOS_VERSAO, TERMOS_ENDERECO = '2026-12-01', 'https://vlado.example/termos-sinteticos'
ALFABETO = 'abcdefghjkmnpqrstuvwxyz23456789'  # sem letras que se confundem (i, l, o, 0, 1)
# (chave, nome, login, papel, tem fator, apurações de que participa; o resto vem da responsabilidade)
ALFA = (('dona', 'Dona Alfa', 'dona.alfa', 'dono', False, ()),
        ('editor', 'Edu Editor', 'edu.editor', 'editor', True, ('vila_serena_sintetico', 'campo_verde_aditivo_sintetico')),
        ('reporter', 'Rita Reporter', 'rita.reporter', 'reporter', True, ('vila_serena_sintetico', 'campo_verde_aditivo_sintetico')),
        ('leitor', 'Leo Leitor', 'leo.leitor', 'leitor', True, ('vila_serena_sintetico',)),
        ('convidado', 'Cora Convidada', 'cora.convidada', 'convidado', True, ('vila_serena_sintetico',)))
BETA = (('dono_b', 'Dono Beta', 'dono.beta', 'dono', True, ()),
        ('reporter_b', 'Rep Beta', 'rep.beta', 'reporter', True, ('beta_sintetico',)))
# Sem aceitar os termos: a dona (termos primeiro, depois o fator) e o editor (só os termos).
SEM_ACEITE = ('dona', 'editor')
LOCAL = (('dono_l', 'Dona Local', 'dona.local', 'dono', False, ()),
         ('reporter_l', 'Rui Local', 'rui.local', 'reporter', False, ('vila_serena_sintetico',)))


def senha_nova() -> str:
    """Uma senha sintética de 16 caracteres (a Mesa pede de 12 a 256)."""
    return ''.join(secrets.choice(ALFABETO) for _ in range(16))


def conferir_pasta(pasta: Path) -> Path:
    """Nunca os dados do projeto, e nunca uma pasta com coisa dentro."""
    pasta = pasta.resolve()
    proibidas = [RAIZ] + [RAIZ / nome for nome in ('casos', 'acesso', 'segredos', 'conversas', 'execucoes', 'lixeira')]
    if pasta in proibidas or any(proibida in pasta.parents for proibida in proibidas[1:]):
        raise SystemExit(f'Recusado: {pasta} é (ou fica dentro de) casos/, acesso/ ou segredos/ do projeto.')
    if pasta.exists() and any(pasta.iterdir()):
        raise SystemExit(f'Recusado: {pasta} já tem arquivos. Use uma pasta nova ou vazia.')
    pasta.mkdir(parents=True, exist_ok=True)
    return pasta


def preparar(pasta: Path) -> Path:
    import vlado_lancador
    vlado_lancador.preparar_dados(pasta, RAIZ)
    # O catálogo de modelo vem do projeto: se houver apuração real nele, nada disto serve.
    import comum
    catalogo = pasta / 'casos' / 'catalogo.json'
    if catalogo.is_file() and comum.ler_json(catalogo).get('casos'):
        raise SystemExit('Recusado: o catálogo copiado do projeto não está vazio; isto parece um ambiente real.')
    return pasta


def semear_casos(pasta: Path, com_beta: bool) -> None:
    """Os dois casos sintéticos do semear_ambiente (conteúdo real de PDFs fictícios); com Beta, mais um caso curto."""
    import dados_sinteticos
    from cadastrar_documentos import cadastrar
    from criar_caso import criar_caso
    import semear_ambiente
    with tempfile.TemporaryDirectory(prefix='vlado_sintetico_') as lote:
        lotes = dados_sinteticos.gerar(Path(lote))
        cadastrar(pasta, semear_ambiente.CASO_A, lotes['lote1'], titulo='Vila Serena (sintética)', natureza='sinteticos', novo=True)
        cadastrar(pasta, semear_ambiente.CASO_B, lotes['lote2'], titulo='Aditivo Campo Verde (sintético)', natureza='sinteticos', novo=True)
    if com_beta:
        arquivo = pasta / 'entrada' / 'beta.txt'
        arquivo.parent.mkdir(exist_ok=True)
        arquivo.write_text('Documento sintético da redação Beta. Valor 456.\n', encoding='utf-8')
        criar_caso(pasta, 'beta_sintetico', 'Apuração Beta (sintética)', [arquivo], 'sinteticos')


def criar_contas(pasta: Path, redacao: str | None, contas) -> dict:
    """Contas com senha definida (como pela ativação). Dono e editor, e quem mais a lista marca, ganham o segundo fator pelo mesmo caminho da pessoa."""
    import acesso
    import fator_de_teste
    feitas = {}
    for chave, nome, login, papel, com_fator, casos in contas:
        senha = senha_nova()
        registro, token = acesso.criar_conta(pasta, nome, login, papel=papel, casos=list(casos), organizacao=redacao, por='operador')
        acesso.ativar(pasta, token, senha)
        informacao = {'id': registro['id'], 'nome': nome, 'login': login, 'papel': papel, 'senha': senha, 'segredo': None, 'codigos': []}
        if com_fator:
            informacao['segredo'] = fator_de_teste.cadastrar(pasta, registro['id'], senha)
            informacao['codigos'] = list(fator_de_teste._CADASTRADOS[str(pasta), registro['id']]['reserva'])
        # Os termos de uso já aceitos, menos para quem a prévia deixa com a pendência (para o dono ver a página de termos).
        informacao['termos_pendentes'] = chave in SEM_ACEITE
        if not informacao['termos_pendentes'] and os.environ.get('VLADO_TERMOS_VERSAO'):
            acesso.aceitar_termos(pasta, registro['id'], TERMOS_VERSAO, acesso.termos_vigentes())
        feitas[chave] = informacao
    return feitas


def conteudo_da_alfa(pasta: Path, contas: dict) -> None:
    """Responsáveis, uma conversa, uma nota e um item na lixeira."""
    import acesso
    import apuracao
    import lixeira
    from comum import escrever_json
    import semear_ambiente
    caso_a, caso_b = semear_ambiente.CASO_A, semear_ambiente.CASO_B
    organizacao = acesso.ver_conta(pasta, contas['dona']['id'])['organizacao']['id']
    for caso in (caso_a, caso_b):
        acesso.definir_responsavel(pasta, caso, contas['reporter']['id'], 'operador', organizacao)
    dona = {'id': contas['dona']['id'], 'nome': contas['dona']['nome']}
    apuracao.executar(pasta, 'apuracao-nota-salvar', {'caso': caso_a, 'requisicao_id': uuid.uuid4().hex, 'titulo': 'Pauta Vila Serena', 'texto': semear_ambiente.NOTA}, dona)
    identificador = uuid.uuid4().hex
    pasta_da_conversa = pasta / 'conversas' / identificador
    (pasta_da_conversa / 'workspace').mkdir(parents=True)
    escrever_json(pasta_da_conversa / 'conversa.json', {
        'id': identificador, 'caso': caso_a, 'titulo': 'Conversa sintética de Vila Serena', 'corpus_id': f'{caso_a}_v1',
        'criada_em_utc': datetime.datetime.now(datetime.timezone.utc).isoformat(), 'estado': 'pronto', 'thread_id': None, 'rodadas': [],
        'turn_id': None, 'modelo': None, 'dono': None, 'politica': 'read-only; on-request; sem web/conectores/shell'})
    lixeira.adicionar(pasta, 'rodada', caso_a, 'R999', rodada='R999')


def conteudo_da_beta(pasta: Path, contas: dict) -> None:
    import acesso
    organizacao = acesso.ver_conta(pasta, contas['dono_b']['id'])['organizacao']['id']
    acesso.definir_responsavel(pasta, 'beta_sintetico', contas['reporter_b']['id'], 'operador', organizacao)


# --- o retransmissor TLS do piloto ---------------------------------------------------------------------------------------------------------------------------------------

def gerar_certificado(pasta: Path) -> tuple[Path, Path]:
    """Certificado autoassinado para 127.0.0.1 (sete dias), só para esta prévia."""
    import ipaddress
    from cryptography import x509
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import ec
    from cryptography.x509.oid import NameOID
    chave = ec.generate_private_key(ec.SECP256R1())
    nome = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, '127.0.0.1')])
    agora = datetime.datetime.now(datetime.timezone.utc)
    certificado = (x509.CertificateBuilder().subject_name(nome).issuer_name(nome).public_key(chave.public_key()).serial_number(x509.random_serial_number())
                   .not_valid_before(agora - datetime.timedelta(minutes=5)).not_valid_after(agora + datetime.timedelta(days=7))
                   .add_extension(x509.SubjectAlternativeName([x509.IPAddress(ipaddress.ip_address('127.0.0.1')), x509.DNSName('localhost')]), critical=False)
                   .sign(chave, hashes.SHA256()))
    destino = pasta / 'tls'
    destino.mkdir(exist_ok=True)
    arquivo_chave, arquivo_certificado = destino / 'previa.key', destino / 'previa.crt'
    arquivo_chave.write_bytes(chave.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption()))
    arquivo_certificado.write_bytes(certificado.public_bytes(serialization.Encoding.PEM))
    return arquivo_certificado, arquivo_chave


class Retransmissor(socketserver.ThreadingTCPServer):
    """TLS na porta de fora, bytes crus para o servidor na porta de dentro (só 127.0.0.1)."""
    allow_reuse_address = True
    daemon_threads = True

    def __init__(self, porta: int, destino: int, certificado: Path, chave: Path):
        self.destino = destino
        self.contexto = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        self.contexto.load_cert_chain(str(certificado), str(chave))
        super().__init__(('127.0.0.1', porta), _Ponte)


class _Ponte(socketserver.BaseRequestHandler):
    def handle(self):
        try:
            de_fora = self.server.contexto.wrap_socket(self.request, server_side=True)
        except (ssl.SSLError, OSError):
            return  # o navegador recusou o certificado, ou fechou antes do aperto de mão
        try:
            de_dentro = socket.create_connection(('127.0.0.1', self.server.destino), timeout=10)
        except OSError:
            return
        de_dentro.settimeout(None)

        def copiar(origem, destino):
            try:
                while True:
                    dados = origem.recv(65536)
                    if not dados:
                        break
                    destino.sendall(dados)
            except (OSError, ssl.SSLError):
                pass
            finally:
                for ponta in (origem, destino):
                    try:
                        ponta.shutdown(socket.SHUT_RDWR)
                    except OSError:
                        pass
        ida = threading.Thread(target=copiar, args=(de_fora, de_dentro), daemon=True)
        ida.start()
        copiar(de_dentro, de_fora)
        ida.join(5)
        for ponta in (de_fora, de_dentro):
            try:
                ponta.close()
            except OSError:
                pass


# --- subir -------------------------------------------------------------------------------------------------------------------------------------------------------------

def subir(servidor) -> threading.Thread:
    fio = threading.Thread(target=servidor.serve_forever, daemon=True)
    fio.start()
    return fio


def responde(porta: int, tls: bool, caminho: str = '/entrar') -> int:
    if tls:
        contexto = ssl.create_default_context()
        contexto.check_hostname, contexto.verify_mode = False, ssl.CERT_NONE
        con = http.client.HTTPSConnection('127.0.0.1', porta, timeout=15, context=contexto)
    else:
        con = http.client.HTTPConnection('127.0.0.1', porta, timeout=15)
    try:
        con.request('GET', caminho, headers={'Host': f'127.0.0.1:{porta}'})
        return con.getresponse().status
    finally:
        con.close()


def imprimir(piloto: dict, local: dict | None, pasta: Path) -> None:
    def contas(titulo, grupo):
        print(f'\n{titulo}')
        for info in grupo.values():
            pendencias = []
            if info.get('termos_pendentes'):
                pendencias.append('termos a aceitar')
            if info['segredo'] is None and info['papel'] in ('dono', 'editor') and titulo.startswith('PILOTO'):
                pendencias.append('SEM segundo fator (cadastre pelo QR)')
            fator = ('· ao entrar: ' + ', depois '.join(pendencias)) if pendencias else ''
            print(f"  {info['nome']:<16} {info['papel']:<10} login {info['login']:<16} senha {info['senha']}  {fator}")
            if info['segredo']:
                print(f"      chave do aplicativo (base32): {info['segredo']}")
                print(f"      códigos de reserva (cada um vale uma vez): {' '.join(info['codigos'])}")
    print('\n' + '=' * 110)
    print('PRÉVIA DO DONO: dados sintéticos, só em 127.0.0.1. Não digite nenhuma chave real de API na Mesa.')
    print(f'Pasta dos dados: {pasta}')
    print(f'\nPiloto        {ORIGEM_PILOTO}   (certificado autoassinado: Avançado, continuar; e-mail na tela; termos {TERMOS_VERSAO} em {TERMOS_ENDERECO})')
    print(f'Local-contas  http://127.0.0.1:{PORTA_LOCAL}')
    contas('PILOTO · Redação Alfa', {k: v for k, v in piloto.items() if k in dict.fromkeys(c[0] for c in ALFA)})
    contas('PILOTO · Redação Beta', {k: v for k, v in piloto.items() if k in dict.fromkeys(c[0] for c in BETA)})
    if local:
        contas('LOCAL-CONTAS', local)
    else:
        print('\nLOCAL-CONTAS sem contas: abra o endereço e a Mesa pede o Primeiro acesso.')
    print('\nPergunta ao agente: não há chave de IA nem agente sintético. Em Perguntar a Mesa mostra "Chave de API ausente no servidor" e o painel Provedor e chave (só dono salva a chave; os outros recebem "Operação não permitida para esta conta"). Nada é chamado.')
    print('Encerre com Ctrl+C.')
    print('=' * 110 + '\n', flush=True)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--pasta', type=Path)
    parser.add_argument('--local-vazio', action='store_true')
    parser.add_argument('--so-verificar', action='store_true')
    args = parser.parse_args()
    for saida in (sys.stdout, sys.stderr):  # o terminal do Windows é cp1252: os acentos saem em UTF-8
        if hasattr(saida, 'reconfigure'):
            saida.reconfigure(encoding='utf-8')
    pasta = conferir_pasta(args.pasta or Path(tempfile.mkdtemp(prefix='vlado_previa_dono_')))
    # Tudo da prévia mora na pasta; nada de e-mail de verdade, de chave de verdade nem de proxy.
    os.environ.update({'VLADO_ACESSO': '', 'VLADO_SEGREDOS': '', 'VLADO_CONFIAR_PROXY': '', 'VLADO_AMBIENTE': 'homologacao', 'VLADO_CORREIO': 'tela',
                       'VLADO_TERMOS_VERSAO': TERMOS_VERSAO, 'VLADO_TERMOS_ENDERECO': TERMOS_ENDERECO})
    for variavel in ('ANTHROPIC_API_KEY', 'OPENAI_API_KEY', 'OPENROUTER_API_KEY'):
        os.environ.pop(variavel, None)
    import acesso
    from interface_pesquisa import Servidor

    dados_piloto, dados_local = pasta / 'piloto', pasta / 'local'
    for destino in (dados_piloto, dados_local):
        preparar(destino)
    # Piloto: Alfa e Beta
    semear_casos(dados_piloto, com_beta=True)
    alfa = acesso.criar_redacao(dados_piloto, 'Redação Alfa')['id']
    beta = acesso.criar_redacao(dados_piloto, 'Redação Beta')['id']
    import semear_ambiente
    for caso in (semear_ambiente.CASO_A, semear_ambiente.CASO_B):
        acesso.atribuir_caso(dados_piloto, caso, alfa)
    acesso.atribuir_caso(dados_piloto, 'beta_sintetico', beta)
    contas_piloto = {**criar_contas(dados_piloto, alfa, ALFA), **criar_contas(dados_piloto, beta, BETA)}
    conteudo_da_alfa(dados_piloto, contas_piloto)
    conteudo_da_beta(dados_piloto, contas_piloto)
    # Local-contas: a Mesa instalada, uma redação
    semear_casos(dados_local, com_beta=False)
    local = None
    if not args.local_vazio:
        redacao_local = acesso.criar_redacao(dados_local, 'Redação Local')['id']
        for caso in (semear_ambiente.CASO_A, semear_ambiente.CASO_B):
            acesso.atribuir_caso(dados_local, caso, redacao_local)
        local = criar_contas(dados_local, redacao_local, LOCAL)

    certificado, chave = gerar_certificado(pasta)
    servidor_piloto = Servidor(('127.0.0.1', 0), dados_piloto, modo='piloto', origem=ORIGEM_PILOTO)
    servidor_local = Servidor(('127.0.0.1', PORTA_LOCAL), dados_local, modo='local-contas')
    ponte = Retransmissor(PORTA_PILOTO, servidor_piloto.server_port, certificado, chave)
    fios = [subir(servidor_piloto), subir(servidor_local), subir(ponte)]
    try:
        imprimir(contas_piloto, local, pasta)
        if args.so_verificar:
            estados = {'piloto /entrar': responde(PORTA_PILOTO, True), 'local-contas /entrar': responde(PORTA_LOCAL, False)}
            print('Verificação:', estados, flush=True)
            return 0 if all(valor == 200 for valor in estados.values()) else 1
        while all(fio.is_alive() for fio in fios):
            time.sleep(1)
    except KeyboardInterrupt:
        print('\nEncerrando…', flush=True)
    finally:
        for servidor in (servidor_piloto, servidor_local):
            servidor.shutdown()
            servidor.server_close()
        ponte.shutdown()
        ponte.server_close()
    return 0


if __name__ == '__main__':
    sys.exit(main())
