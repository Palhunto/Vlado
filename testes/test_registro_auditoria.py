"""SEG-02, parte do registro: formato da linha, lista fechada de campos (nada sensível), referências com chave, rotação por
dia, retenção, teto diário, falha sem derrubar o pedido e a janela de eventos do acesso.json que deixa de cortar em silêncio.
Só scripts/registro_acesso.py e scripts/acesso.py; os eventos de ponta a ponta (HTTP) estão em test_auditoria_eventos.py."""
from datetime import datetime, timedelta, timezone
import json
import os
from pathlib import Path
import re
import sys
import tempfile
import threading
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
sys.path.insert(0, str(Path(__file__).resolve().parent))
import acesso
import registro_acesso as reg
from relogio_fixo import fixar
from test_acesso import SENHA, hasher_rapido


class Base(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.base = Path(temp.name)
        self.pasta = self.base / 'registro'
        self.chave = self.base / 'segredos' / 'registro_ref.chave'  # fora da pasta do registro, como em produção
        env = patch.dict(os.environ, {'VLADO_REGISTRO': str(self.pasta), 'VLADO_REGISTRO_RETENCAO_DIAS': '',
                                      'VLADO_REGISTRO_DIA_MAX_MB': '', 'VLADO_REGISTRO_CHAVE': str(self.chave)})
        env.start()
        self.addCleanup(env.stop)
        reg._ESTADO.update(limpeza=0.0, aviso=0.0)
        antigas = set(reg.OPERACOES_PERMITIDAS)
        self.addCleanup(lambda: (reg.OPERACOES_PERMITIDAS.clear(), reg.OPERACOES_PERMITIDAS.update(antigas)))
        reg.permitir_operacoes(['contas-atualizar', 'apuracao-exportar', 'contas-criar'])
        reg._ESTADO['cheio'].clear()
        reg._ESTADO['chave'].clear()
        reg._AGREGADOS.clear()
        self.addCleanup(reg._AGREGADOS.clear)
        self.addCleanup(reg.encerrar_requisicao)

    def linhas(self) -> list[dict]:
        saida = []
        for arquivo in reg.arquivos(self.pasta):
            for linha in arquivo.read_text(encoding='ascii').splitlines():
                saida.append(json.loads(linha))
        return saida

    def texto(self) -> str:
        return ''.join(a.read_text(encoding='ascii') for a in reg.arquivos(self.pasta))


class FormatoDaLinhaTest(Base):
    def test_uma_linha_json_por_evento_com_horario_utc_conta_ip_e_resultado(self):
        reg.iniciar_requisicao(lambda: '203.0.113.9', raiz=self.base)
        reg.registrar('login_ok', 'ok', 'a1b2c3d4e5f60718', cliente='web')
        reg.registrar('login_falha', 'falha', None, motivo='credenciais', login_ref='0123456789ab')
        linhas = self.linhas()
        self.assertEqual(len(linhas), 2)
        ok, falha = linhas
        self.assertRegex(ok['em'], r'^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$')
        self.assertEqual((ok['evento'], ok['resultado'], ok['conta'], ok['ip'], ok['origem'], ok['cliente']),
                         ('login_ok', 'ok', 'a1b2c3d4e5f60718', '203.0.113.9', 'web', 'web'))
        self.assertEqual((falha['evento'], falha['resultado'], falha['conta'], falha['motivo'], falha['login_ref']),
                         ('login_falha', 'falha', None, 'credenciais', '0123456789ab'))
        self.assertEqual(self.texto().count('\n'), 2, 'exatamente uma linha por evento')

    def test_horario_e_sempre_utc_mesmo_com_fuso(self):
        fuso = timezone(timedelta(hours=-3))
        reg.registrar('logout', 'ok', 'a1b2c3d4e5f60718', momento=datetime(2026, 11, 21, 23, 30, tzinfo=fuso))
        self.assertEqual(self.linhas()[0]['em'], '2026-11-22T02:30:00Z')
        self.assertTrue((self.pasta / 'auditoria-2026-11-22.jsonl').is_file(), 'o arquivo é o do dia UTC')

    def test_fora_de_uma_requisicao_a_origem_e_cli_e_o_ip_vazio(self):
        reg.registrar('conta_criada', 'ok', 'a1b2c3d4e5f60718', por='cli')
        linha = self.linhas()[0]
        self.assertEqual((linha['origem'], linha['ip']), ('cli', None))

    def test_ip_invalido_ou_ilegivel_vira_nulo_nunca_texto(self):
        for ruim in ('nao-e-ip', '1.2.3.4; rm -rf', 'Cookie: sessao=abc'):
            reg.iniciar_requisicao(lambda ruim=ruim: ruim)
            reg.registrar('logout', 'ok', 'a1b2c3d4e5f60718')
        reg.iniciar_requisicao(lambda: (_ for _ in ()).throw(RuntimeError('quebrou')))
        reg.registrar('logout', 'ok', 'a1b2c3d4e5f60718')
        self.assertTrue(all(l['ip'] is None for l in self.linhas()))
        self.assertEqual(len(self.linhas()), 4)

    def test_evento_ou_resultado_desconhecido_nao_grava_nada(self):
        reg.registrar('qualquer_coisa', 'ok', 'a1b2c3d4e5f60718')
        reg.registrar('login_ok', 'talvez', 'a1b2c3d4e5f60718')
        self.assertEqual(reg.arquivos(self.pasta), [])

    def test_ip_dado_por_quem_chama_vale_mais_que_o_do_contexto(self):
        reg.iniciar_requisicao(lambda: '203.0.113.9')
        reg.registrar('login_falha', 'falha', None, motivo='limite_ip', ip='198.51.100.4')
        self.assertEqual(self.linhas()[0]['ip'], '198.51.100.4')


class NadaSensivelTest(Base):
    """Lista fechada de campos + formato estrito por campo: texto livre e segredos não cabem."""

    SEGREDOS = ('senha-longa-de-teste-1', 'x' * 43, 'Contrato 041/2025 de pavimentação', 'relatorio_final.pdf',
                'Qual o valor do aditivo?', 'vila_serena_sintetico', 'sk-ant-segredo', 'Cookie: vlado_sessao=abcdef',
                'AGE-SECRET-KEY-1ABCDEF', 'https://vlado.example.org/ativar/' + 'T' * 43)

    def test_nenhum_campo_aceita_texto_livre_ou_segredo(self):
        reg.iniciar_requisicao(lambda: '203.0.113.9')
        for segredo in self.SEGREDOS:
            reg.registrar('download', 'ok', segredo, por=segredo, alvo=segredo, motivo=segredo, tipo=segredo, papel=segredo,
                          cliente=segredo, operacao=segredo, caso_ref=segredo, login_ref=segredo, codigo=segredo,
                          tipo_original=segredo, em_original=segredo, campos=[segredo], bytes=segredo, quantidade=segredo,
                          senha=segredo, token=segredo, cookie=segredo, nome_do_arquivo=segredo, pergunta=segredo,
                          caso=segredo, login=segredo, documento=segredo, conteudo=segredo, link=segredo, chave=segredo)
        texto = self.texto()
        for segredo in self.SEGREDOS:
            self.assertNotIn(segredo, texto)
        for linha in self.linhas():
            self.assertEqual(set(linha), {'em', 'evento', 'resultado', 'conta', 'ip', 'origem'}, linha)

    def test_campos_validos_passam_e_so_eles(self):
        reg.iniciar_requisicao(lambda: '203.0.113.9')
        reg.registrar('acesso_alterado', 'ok', 'a1b2c3d4e5f60718', por='f0e1d2c3b4a59687', campos=['papel', 'casos', 'papel'],
                      papel='admin', operacao='contas-atualizar')
        reg.registrar('download', 'ok', 'a1b2c3d4e5f60718', tipo='exportacao', bytes=1234, caso_ref='abcdef012345',
                      operacao='apuracao-exportar')
        alterado, baixado = self.linhas()
        self.assertEqual((alterado['campos'], alterado['papel'], alterado['por'], alterado['operacao']),
                         (['casos', 'papel'], 'admin', 'f0e1d2c3b4a59687', 'contas-atualizar'))
        self.assertEqual((baixado['tipo'], baixado['bytes'], baixado['caso_ref']), ('exportacao', 1234, 'abcdef012345'))

    def test_id_de_conta_com_formato_de_token_e_descartado(self):
        for ruim in ('T' * 43, 'alpha', 'ana.silva', 'a1', 'A1B2C3D4E5F60718'):
            reg.registrar('logout', 'ok', ruim)
        reg.registrar('logout', 'ok', 'a1b2c3d4e5f60718')
        self.assertEqual([l['conta'] for l in self.linhas()], [None] * 5 + ['a1b2c3d4e5f60718'])

    def test_conteudo_de_contexto_so_entra_validado_e_o_caso_so_como_referencia(self):
        reg.iniciar_requisicao(lambda: None)
        reg.definir(operacao='senha-longa-de-teste-1', conta='qualquer')
        reg.referenciar_caso('vila_serena_sintetico')
        reg.registrar('download', 'ok', 'a1b2c3d4e5f60718', tipo='original')
        linha = self.linhas()[0]
        self.assertNotIn('operacao', linha, 'um nome fora da lista de operações do servidor é descartado')
        self.assertRegex(linha['caso_ref'], r'^[0-9a-f]{12}$')
        self.assertNotIn('vila_serena', self.texto())


class ReferenciasTest(Base):
    def test_referencia_estavel_com_chave_do_volume_e_nao_e_um_hash_simples(self):
        a = reg.referencia('caso', 'vila_serena')
        self.assertRegex(a, r'^[0-9a-f]{12}$')
        self.assertEqual(a, reg.referencia('caso', 'vila_serena'))
        self.assertNotEqual(a, reg.referencia('caso', 'outro_caso'))
        self.assertNotEqual(a, reg.referencia('login', 'vila_serena'), 'espaços diferentes não se confundem')
        import hashlib
        self.assertNotEqual(a, hashlib.sha256(b'caso:vila_serena').hexdigest()[:12], 'sem a chave não dá para conferir um palpite')
        chave = self.chave
        self.assertRegex(chave.read_text(encoding='ascii').strip(), r'^[0-9a-f]{64}$')
        self.assertNotEqual(chave.parent, self.pasta, 'a chave não fica no volume do registro')
        self.assertFalse(list(self.pasta.glob('*chave*')) if self.pasta.exists() else [], 'nada de chave junto do registro')
        if os.name != 'nt':
            self.assertEqual(chave.stat().st_mode & 0o777, 0o600)

    def test_a_chave_mora_em_segredos_ao_lado_de_chaves_json_e_nunca_na_pasta_do_registro(self):
        with patch.dict(os.environ, {'VLADO_REGISTRO_CHAVE': ''}):
            reg.lembrar_raiz(self.base / 'dados')
            self.assertEqual(reg.arquivo_da_chave(), self.base / 'dados' / 'segredos' / 'registro_ref.chave')
            with patch.dict(os.environ, {'VLADO_SEGREDOS': str(self.base / 'vol' / 'chaves.json')}):
                self.assertEqual(reg.arquivo_da_chave(), self.base / 'vol' / 'registro_ref.chave')
            self.assertNotEqual(reg.arquivo_da_chave().parent, self.pasta)
        reg.referencia('caso', 'x')
        self.assertFalse([p for p in self.pasta.rglob('*') if 'chave' in p.name] if self.pasta.exists() else [])

    def test_outra_instalacao_tem_outra_chave(self):
        a = reg.referencia('caso', 'vila_serena')
        reg._ESTADO['chave'].clear()
        outra = self.base / 'outra' / 'registro_ref.chave'
        self.assertNotEqual(a, reg.referencia('caso', 'vila_serena', outra))

    def test_login_digitado_nunca_aparece_so_a_referencia(self):
        reg.registrar('login_falha', 'falha', None, motivo='credenciais', login_ref=reg.referencia_do_login('  Fulano.Silva '))
        self.assertNotIn('fulano', self.texto().lower())
        self.assertEqual(reg.referencia_do_login('FULANO.silva'), reg.referencia_do_login(' fulano.silva'))
        self.assertIsNone(reg.referencia_do_login(None))
        self.assertIsNone(reg.referencia_do_login(''))


class RotacaoERetencaoTest(Base):
    def test_um_arquivo_por_dia_utc(self):
        for dia in (20, 21, 22):
            reg.registrar('logout', 'ok', 'a1b2c3d4e5f60718', momento=datetime(2026, 11, dia, 12, 0, tzinfo=timezone.utc))
        self.assertEqual([a.name for a in reg.arquivos(self.pasta)],
                         [f'auditoria-2026-11-{d}.jsonl' for d in (20, 21, 22)])

    def test_retencao_padrao_30_dias_apaga_so_os_arquivos_do_registro(self):
        self.pasta.mkdir(parents=True)
        hoje = datetime.now(timezone.utc)
        for dias in (0, 5, 29, 30, 31, 90):
            dia = (hoje - timedelta(days=dias)).strftime('%Y-%m-%d')
            (self.pasta / f'auditoria-{dia}.jsonl').write_text('{}\n', encoding='ascii')
        (self.pasta / 'leia-me.txt').write_text('não é do registro', encoding='utf-8')
        (self.pasta / '.chave_ref').write_text('0' * 64 + '\n', encoding='ascii')
        removidos = reg.podar(self.pasta, hoje)
        self.assertEqual(len(removidos), 2, removidos)  # 31 e 90 dias
        restantes = {a.name for a in reg.arquivos(self.pasta)}
        self.assertEqual(len(restantes), 4)
        self.assertTrue((self.pasta / 'leia-me.txt').exists() and (self.pasta / '.chave_ref').exists())

    def test_retencao_configuravel_e_a_poda_roda_ao_gravar(self):
        self.pasta.mkdir(parents=True)
        agora = datetime.now(timezone.utc)
        velho = (self.pasta / f'auditoria-{(agora - timedelta(days=10)).strftime("%Y-%m-%d")}.jsonl')
        velho.write_text('{}\n', encoding='ascii')
        with patch.dict(os.environ, {'VLADO_REGISTRO_RETENCAO_DIAS': '7'}):
            reg.registrar('logout', 'ok', 'a1')
        self.assertFalse(velho.exists(), 'passou de 7 dias: apagado na primeira gravação do processo')
        with patch.dict(os.environ, {'VLADO_REGISTRO_RETENCAO_DIAS': 'abc'}):
            self.assertEqual(reg.retencao_dias(), 30, 'valor inválido volta ao padrão, alinhado aos 30 dias do Caddy')
        with patch.dict(os.environ, {'VLADO_REGISTRO_RETENCAO_DIAS': '0'}):
            self.assertEqual(reg.retencao_dias(), 1)

    def test_teto_por_dia_das_falhas_anonimas_nao_enche_o_disco_e_avisa_uma_vez(self):
        with patch.dict(os.environ, {'VLADO_REGISTRO_DIA_MAX_MB': '1'}):
            reg.iniciar_requisicao(lambda: '203.0.113.9')
            for _ in range(20000):
                reg.registrar('login_falha', 'falha', None, motivo='credenciais', login_ref='0123456789ab')
        tamanho = sum(a.stat().st_size for a in reg.arquivos(self.pasta))
        self.assertLess(tamanho, (1 << 20) + 2000, 'não passa do teto do dia (mais uma linha)')
        cheios = [l for l in self.linhas() if l['evento'] == 'registro_cheio']
        self.assertEqual([c['classe'] for c in cheios], ['anonimo'], 'um único aviso, da classe das falhas anônimas')
        # No dia seguinte volta a gravar.
        amanha = datetime.now(timezone.utc) + timedelta(days=1)
        reg.registrar('logout', 'ok', 'a1b2c3d4e5f60718', momento=amanha)
        self.assertEqual(len(reg.arquivos(self.pasta)), 2)

    def test_gravacoes_simultaneas_nao_misturam_linhas(self):
        def escreve(n):
            for i in range(200):
                reg.registrar('login_falha', 'falha', None, motivo='credenciais', login_ref=f'{n:06x}{i:06x}')
        fios = [threading.Thread(target=escreve, args=(n,)) for n in range(8)]
        [f.start() for f in fios]
        [f.join() for f in fios]
        self.assertEqual(len(self.linhas()), 1600, 'toda linha é um JSON inteiro')

    def test_arquivo_do_registro_nasce_privado(self):
        reg.registrar('logout', 'ok', 'a1')
        if os.name != 'nt':
            self.assertEqual(reg.arquivos(self.pasta)[0].stat().st_mode & 0o777, 0o600)
            self.assertEqual(self.pasta.stat().st_mode & 0o777, 0o700)


class FalhaNaoDerrubaOPedidoTest(Base):
    def test_pasta_impossivel_nao_levanta_e_avisa_sem_conteudo(self):
        arquivo_no_lugar_da_pasta = self.base / 'nao-e-pasta'
        arquivo_no_lugar_da_pasta.write_text('x', encoding='utf-8')
        with patch.dict(os.environ, {'VLADO_REGISTRO': str(arquivo_no_lugar_da_pasta / 'sub')}):
            with self.assertLogs('vlado.auditoria', level='WARNING') as capturado:
                reg.registrar('login_ok', 'ok', 'a1b2c3d4e5f60718', momento=datetime.now(timezone.utc))
                reg.registrar('login_ok', 'ok', 'a1b2c3d4e5f60718')
        self.assertEqual(len(capturado.records), 1, 'no máximo um aviso por minuto')
        self.assertNotIn('a1b2c3d4e5f60718', capturado.output[0])

    def test_o_login_funciona_mesmo_com_o_registro_quebrado(self):
        hasher_rapido(self)
        acesso.limpar_limites()
        raiz = self.base / 'dados'
        conta, token = acesso.criar_conta(raiz, 'Ana', 'ana.silva', casos=['alpha'])
        acesso.ativar(raiz, token, SENHA)
        (self.base / 'bloqueio').write_text('x', encoding='utf-8')
        with patch.dict(os.environ, {'VLADO_REGISTRO': str(self.base / 'bloqueio' / 'sub')}):
            sid, csrf, publica = acesso.entrar(raiz, 'ana.silva', SENHA, ip='198.51.100.4')
        self.assertEqual(publica['id'], conta['id'])


class JanelaDeEventosDoAcessoTest(Base):
    """acesso.json guarda os 1000 mais novos para a tela de administração; o que sai da janela é copiado ao registro."""

    def test_evento_que_sai_da_janela_vai_para_o_registro_em_vez_de_sumir(self):
        hasher_rapido(self)
        raiz = self.base / 'dados'
        acesso.criar_conta(raiz, 'Ana', 'ana.silva', casos=['alpha'])
        arquivo = acesso.caminho(raiz)
        dados = json.loads(arquivo.read_text(encoding='utf-8'))
        dados['eventos'] = [{'em': f'2026-01-01T00:00:{i % 60:02d}Z', 'tipo': 'conta_criada', 'conta': 'b1b2b3b4b5b6b7b8', 'por': 'cli'}
                            for i in range(1200)]
        arquivo.write_text(json.dumps(dados), encoding='utf-8')
        antes = len(self.linhas())
        cid = next(iter(dados['contas']))
        acesso.desativar(raiz, cid, por='cli')
        armazenados = json.loads(arquivo.read_text(encoding='utf-8'))['eventos']
        self.assertEqual(len(armazenados), acesso.MAX_EVENTOS)
        arquivados = [l for l in self.linhas()[antes:] if l['evento'] == 'evento_arquivado']
        self.assertEqual(len(arquivados), 201, '1200 + o novo - 1000 = 201 saíram da janela e foram guardados')
        self.assertEqual({(l['tipo_original'], l['conta'], l['por']) for l in arquivados}, {('conta_criada', 'b1b2b3b4b5b6b7b8', 'cli')})
        self.assertTrue(all(re.fullmatch(r'\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z', l['em_original']) for l in arquivados))

    def test_todo_evento_do_cadastro_de_contas_tambem_vai_ao_registro(self):
        hasher_rapido(self)
        raiz = self.base / 'dados'
        conta, token = acesso.criar_conta(raiz, 'Ana', 'ana.silva', casos=['alpha'])
        acesso.ativar(raiz, token, SENHA)
        acesso.atualizar(raiz, conta['id'], por='cli', casos=['beta'])
        acesso.desativar(raiz, conta['id'], por='cli')
        acesso.reativar(raiz, conta['id'], por='cli')
        acesso.recuperar(raiz, conta['id'], por='cli')
        eventos = [l['evento'] for l in self.linhas()]
        self.assertEqual(eventos, ['conta_criada', 'senha_definida', 'acesso_alterado', 'conta_desativada',
                                   'conta_reativada', 'recuperacao_emitida'])
        alterado = self.linhas()[2]
        self.assertEqual((alterado['papel'], alterado['campos']), ('convidado', ['casos']))
        self.assertNotIn(token, self.texto())


class DiaCheioDeFalhasTest(Base):
    """B1: um anônimo não pode encher o dia e fazer a auditoria descartar o que importa (entrada de administrador, criação de
    conta). O teto do dia vale só para a falha que qualquer um gera; o resto tem cota própria; e o excesso de tentativas do
    mesmo IP vira uma linha por IP e por minuto."""

    def encher_com_falhas_anonimas(self, mb='1'):
        with patch.dict(os.environ, {'VLADO_REGISTRO_DIA_MAX_MB': mb}):
            reg.iniciar_requisicao(lambda: '203.0.113.9')
            for i in range(10000):  # cada linha ~200 bytes: passa de 1 MB
                reg.registrar('login_falha', 'falha', None, motivo='credenciais', login_ref=f'{i:012x}')
        return mb

    def test_dia_cheio_de_falhas_ainda_grava_login_e_criacao_de_administrador(self):
        mb = self.encher_com_falhas_anonimas()
        antes = len(self.linhas())
        admin, nova = 'a1b2c3d4e5f60718', 'f0e1d2c3b4a59687'
        with patch.dict(os.environ, {'VLADO_REGISTRO_DIA_MAX_MB': mb}):
            reg.iniciar_requisicao(lambda: '198.51.100.20')
            reg.registrar('login_falha', 'falha', None, motivo='credenciais', login_ref='ffffffffffff')  # anônimo: descartado
            reg.registrar('login_ok', 'ok', admin, cliente='web')
            reg.registrar('conta_criada', 'ok', nova, por=admin)
            reg.registrar('acesso_alterado', 'ok', nova, por=admin, campos=['papel'], papel='admin')
            reg.registrar('recuperacao_emitida', 'ok', nova, por=admin)
            reg.registrar('download', 'ok', admin, tipo='original', bytes=10)
        novas = self.linhas()[antes:]
        self.assertEqual([l['evento'] for l in novas],
                         ['login_ok', 'conta_criada', 'acesso_alterado', 'recuperacao_emitida', 'download'],
                         'o login e a criação do administrador estão gravados; a falha anônima, não')
        self.assertEqual(novas[1]['por'], admin)
        avisos = [l for l in self.linhas() if l['evento'] == 'registro_cheio']
        self.assertEqual([a['classe'] for a in avisos], ['anonimo'], 'um único aviso, só da classe das falhas')

    def test_o_resto_tem_cota_propria_de_quatro_vezes_e_tambem_avisa_uma_vez(self):
        with patch.dict(os.environ, {'VLADO_REGISTRO_DIA_MAX_MB': '1'}):
            reg.iniciar_requisicao(lambda: '203.0.113.9')
            for _ in range(30000):  # ~ 5 MB de eventos legítimos: passa dos 4 MB da cota total
                reg.registrar('login_ok', 'ok', 'a1b2c3d4e5f60718', cliente='web')
        tamanho = sum(a.stat().st_size for a in reg.arquivos(self.pasta))
        self.assertLess(tamanho, 4 * (1 << 20) + 2000)
        self.assertEqual([l['classe'] for l in self.linhas() if l['evento'] == 'registro_cheio'], ['total'])

    def test_excesso_de_tentativas_do_mesmo_ip_vira_uma_linha_por_ip_e_por_minuto(self):
        fixar(self)  # a linha é por minuto: nada de cruzar a virada no meio do teste
        reg.iniciar_requisicao(lambda: None)
        for _ in range(5000):
            reg.registrar_limite_ip('login_falha', '203.0.113.9', '203.0.113.9', cliente='web')
        for _ in range(7):
            reg.registrar_limite_ip('login_falha', '198.51.100.4', '198.51.100.4', cliente='web')
        for _ in range(3):
            reg.registrar_limite_ip('ativacao_falha', '203.0.113.9', '203.0.113.9', acesso_operacao='ativar')
        self.assertEqual(self.linhas(), [], 'a janela do minuto só fecha no fim do minuto (ou ao encerrar)')
        self.assertEqual(reg.descarregar(tudo=True), 3)
        linhas = {(l['evento'], l['ip']): l for l in self.linhas()}
        self.assertEqual(len(linhas), 3)
        a = linhas[('login_falha', '203.0.113.9')]
        self.assertEqual((a['quantidade'], a['motivo'], a['resultado'], a['cliente']), (5000, 'limite_ip', 'falha', 'web'))
        self.assertEqual(linhas[('login_falha', '198.51.100.4')]['quantidade'], 7)
        self.assertEqual(linhas[('ativacao_falha', '203.0.113.9')]['quantidade'], 3)
        self.assertLess(len(self.texto()), 1500, '5010 pedidos, três linhas pequenas')

    def test_a_janela_fecha_no_proximo_evento_depois_do_minuto(self):
        reg.iniciar_requisicao(lambda: None)
        reg.registrar_limite_ip('login_falha', '203.0.113.9', '203.0.113.9')
        reg.registrar_limite_ip('login_falha', '203.0.113.9', '203.0.113.9')
        depois = datetime.now(timezone.utc) + timedelta(minutes=2)
        self.assertEqual(reg.descarregar(agora=depois), 1)
        linha, = self.linhas()
        self.assertEqual((linha['quantidade'], linha['em'][-4:]), (2, ':00Z'), 'o horário é o começo da janela do minuto')
        self.assertEqual(reg.descarregar(agora=depois), 0, 'não grava duas vezes')

    def test_um_evento_qualquer_tambem_fecha_janelas_vencidas(self):
        reg.iniciar_requisicao(lambda: None)
        reg.registrar_limite_ip('login_falha', '203.0.113.9', '203.0.113.9')
        with reg._AGREGA:
            for janela in reg._AGREGADOS.values():
                janela['minuto'] -= timedelta(minutes=2)
        reg.registrar('logout', 'ok', 'a1b2c3d4e5f60718')
        self.assertEqual([l['evento'] for l in self.linhas()], ['logout', 'login_falha'])

    def test_registrar_limite_so_aceita_falhas_anonimas_e_nunca_levanta(self):
        reg.registrar_limite_ip('login_ok', '203.0.113.9')
        reg.registrar_limite_ip('login_falha', 'nao-e-ip', 'nao-e-ip')
        reg.registrar_limite_ip('login_falha', None, None)
        reg.descarregar(tudo=True)
        self.assertTrue(all(l['evento'] == 'login_falha' and l['ip'] is None for l in self.linhas()))

    def test_acesso_entrar_agrega_o_que_passa_do_limite(self):
        fixar(self)  # a linha é por minuto: nada de cruzar a virada no meio do teste
        hasher_rapido(self)
        acesso.limpar_limites()
        raiz = self.base / 'dados'
        for numero in range(300):  # 20 por minuto passam como credenciais, o resto é o excesso
            with self.assertRaises(ValueError):
                acesso.entrar(raiz, f'ninguem{numero}', SENHA, ip='203.0.113.9')
        reg.descarregar(tudo=True)
        linhas = self.linhas()
        credenciais = [l for l in linhas if l.get('motivo') == 'credenciais']
        limite = [l for l in linhas if l.get('motivo') == 'limite_ip']
        self.assertEqual(len(credenciais), 20)
        self.assertEqual([l['quantidade'] for l in limite], [280])
        self.assertEqual(len(linhas), 21, '300 pedidos: 20 linhas de falha e uma agregada')


class ComposeEBackupTest(unittest.TestCase):
    """O Compose monta o volume do registro só no app; o backup não o vê (decisão registrada em deploy/BACKUP.md)."""

    RAIZ = Path(__file__).resolve().parents[1]

    def servicos(self) -> dict[str, str]:
        texto = (self.RAIZ / 'docker-compose.yml').read_text(encoding='utf-8')
        corpo = texto.split('\nservices:\n', 1)[1].split('\nvolumes:\n', 1)[0]
        partes = re.split(r'(?m)^  ([a-z_]+):\s*$', corpo)
        return dict(zip(partes[1::2], partes[2::2]))

    def test_so_o_app_monta_o_volume_do_registro_e_as_variaveis_estao_no_compose(self):
        servicos = self.servicos()
        self.assertIn('      - registro:/app/registro\n', servicos['vlado'])
        for nome in ('backup', 'restauracao', 'caddy'):
            self.assertNotIn('/app/registro', servicos[nome], nome)
        for linha in ('VLADO_REGISTRO: /app/registro', 'VLADO_REGISTRO_RETENCAO_DIAS: ${VLADO_REGISTRO_RETENCAO_DIAS:-30}',
                      'VLADO_REGISTRO_DIA_MAX_MB: ${VLADO_REGISTRO_DIA_MAX_MB:-50}',
                      'VLADO_PROXIES_CONFIAVEIS: ${VLADO_REDE_SUBNET:-172.29.99.0/24}${VLADO_PROXIES_CONFIAVEIS:+,${VLADO_PROXIES_CONFIAVEIS}}',
                      'VLADO_PROXIES_CONFIAVEIS_AMPLAS: ${VLADO_PROXIES_CONFIAVEIS_AMPLAS:-}'):
            self.assertIn(linha, servicos['vlado'], linha)
        volumes = (self.RAIZ / 'docker-compose.yml').read_text(encoding='utf-8').split('\nvolumes:\n', 1)[1]
        self.assertRegex(volumes, r'(?m)^  registro:$')

    def test_backup_nunca_inclui_o_registro(self):
        import backup
        import shutil
        import tarfile
        self.assertNotIn('registro', backup.PASTAS)
        self.assertNotIn('registro', backup._pastas(True))
        raiz = Path(tempfile.mkdtemp())
        self.addCleanup(lambda: shutil.rmtree(raiz, ignore_errors=True))
        for pasta in backup.PASTAS:
            (raiz / pasta).mkdir()
        (raiz / 'acesso' / 'acesso.json').write_text('{"versao": 2}', encoding='utf-8')
        (raiz / 'registro').mkdir()
        (raiz / 'registro' / 'auditoria-2026-11-22.jsonl').write_text('{"ip": "203.0.113.9"}\n', encoding='ascii')
        arquivo = backup.criar(raiz, raiz / 'copias')
        with tarfile.open(arquivo) as pacote:
            nomes = pacote.getnames()
        self.assertFalse([n for n in nomes if n.startswith('registro') or 'auditoria' in n], nomes)

    def test_documentos_registram_a_decisao_o_que_entra_e_como_configurar(self):
        backup = (self.RAIZ / 'deploy' / 'BACKUP.md').read_text(encoding='utf-8')
        self.assertIn('Registro de auditoria (`registro/`, SEG-02): FORA do backup', backup)
        monitoramento = (self.RAIZ / 'deploy' / 'MONITORAMENTO.md').read_text(encoding='utf-8')
        for trecho in ('## Registro de auditoria da Mesa (SEG-02)', 'login_falha', 'sessao_expirada', 'recuperacao_emitida',
                       'operacao_negada', '`download`', 'login_ref', 'caso_ref', 'VLADO_REGISTRO_RETENCAO_DIAS',
                       '## IP do cliente atrás do Caddy e de CDN ou WAF (SEG-05, CONF-03)', 'VLADO_PROXIES_CONFIAVEIS', 'trusted_proxies',
                       'primeiro salto que não está na'):
            self.assertIn(trecho, monitoramento, trecho)
        for nome in ('homologacao', 'editorial', 'demonstracao'):
            exemplo = (self.RAIZ / 'deploy' / 'ambientes' / f'{nome}.env.example').read_text(encoding='utf-8')
            for variavel in ('VLADO_REGISTRO_RETENCAO_DIAS', 'VLADO_REGISTRO_DIA_MAX_MB', 'VLADO_PROXIES_CONFIAVEIS'):
                self.assertIn(f'# {variavel}=', exemplo, f'{nome}: {variavel}')
        for trecho in ('fora do volume do registro', 'segredos/registro_ref.chave', 'cota própria, 4 vezes maior', 'uma única linha por IP e por minuto',
                       'VLADO_PROXIES_CONFIAVEIS_AMPLAS=1', 'Modo local (sem Docker)', '<pasta de dados>/registro/'):
            self.assertIn(trecho, monitoramento, trecho)
        self.assertIn('segredos/registro_ref.chave', backup)
        local = (self.RAIZ / 'deploy' / 'LOCAL.md').read_text(encoding='utf-8')
        self.assertIn('Fora do Docker', local)
        self.assertIn('`registro/` dentro da pasta de dados', local)
        self.assertIn('registro de auditoria', (self.RAIZ / 'deploy' / 'INCIDENTE.md').read_text(encoding='utf-8').lower())

    def test_imagem_do_app_cria_a_pasta_e_o_contexto_do_docker_nao_a_leva(self):
        dockerfile = (self.RAIZ / 'Dockerfile').read_text(encoding='utf-8')
        app = dockerfile.split('AS vlado', 1)[1]
        self.assertRegex(app, r'mkdir -p [^\n]*\bregistro\b')
        self.assertRegex(app, r'chown -R vlado:vlado [^\n]*\bregistro\b')
        self.assertIn('scripts/registro_acesso.py', app)
        self.assertIn('scripts/proxies_confiaveis.py', app)
        regras = (self.RAIZ / '.dockerignore').read_text(encoding='utf-8').splitlines()
        self.assertIn('registro', regras)


if __name__ == '__main__':
    unittest.main()
