"""Apagamento definitivo de itens da lixeira, com casos sintéticos. Sem modelo, rede ou navegador."""
import json
import os
from pathlib import Path
import sys
import threading
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from fixture_achados import Ambiente
import apagamento
import lixeira
from comum import escrever_json, ler_json

CHAT = 'a' * 32
CHAT_B = 'b' * 32
SEGREDO = 'CONTEUDO-SECRETO-DO-DOCUMENTO'


class Gerenciador:
    def __init__(self):
        self.lock = threading.RLock()
        self.contexts = {}
        self.loaded = set()


class ApagamentoTest(unittest.TestCase):
    def setUp(self):
        self.fx = Ambiente()
        self.addCleanup(self.fx.cleanup)
        self.root = self.fx.root
        self.fx.caso('beta')
        # Texto derivado extra, como o produzido por OCR, dentro do cadastro.
        derivados = next((self.root / 'casos/alpha/cadastros').glob('*/derivados'))
        (derivados / 'D002_texto_ocr.md').write_text(SEGREDO, encoding='utf-8')
        self.conversa('alpha', CHAT, ['R001'])

    def conversa(self, caso, identificador, rodadas):
        meta = {'id': identificador, 'caso': caso, 'titulo': 'Pergunta sintética',
                'estado': 'concluido', 'rodadas': rodadas, 'criada_em_utc': '2026-01-01T00:00:00Z'}
        escrever_json(self.root / f'conversas/{identificador}/conversa.json', meta)
        (self.root / f'conversas/{identificador}/eventos.jsonl').write_text(SEGREDO + '\n', encoding='utf-8')
        (self.root / f'conversas/{identificador}/api_historico.json').write_text('[]', encoding='utf-8')
        (self.root / f'conversas/{identificador}/workspace').mkdir(exist_ok=True)
        return meta

    def lixo(self, tipo, caso='alpha', **kw):
        return lixeira.adicionar(self.root, tipo, caso, 'Título ' + caso, **kw)

    def arquivos(self, caso):
        return [p for base in (f'casos/{caso}', f'execucoes/{caso}') for p in (self.root / base).rglob('*')]

    def test_alcance_do_caso_conta_categorias_e_nao_apaga(self):
        self.fx.completo()
        quadro = self.root / ('casos/alpha/quadros/hipoteses/H' + '0' * 32)
        quadro.mkdir(parents=True)
        (quadro / f'00000001_{"0" * 32}.json').write_text('{}', encoding='utf-8')
        item = self.lixo('caso')
        antes = len(self.arquivos('alpha'))
        alc = lixeira.alcance(self.root, item['id'])
        self.assertEqual(len(self.arquivos('alpha')), antes)
        for categoria in ('originais', 'derivados', 'corpus', 'rodadas', 'indice_documental',
                          'indice_achados', 'registros_achados', 'conversas', 'quadros_evidencia'):
            self.assertGreater(alc['categorias'][categoria]['arquivos'], 0, categoria)
        self.assertEqual(alc['categorias']['originais']['arquivos'], 3)  # a cópia congelada na rodada conta em 'rodadas'
        self.assertEqual(alc['totais']['arquivos'], sum(c['arquivos'] for c in alc['categorias'].values()))
        self.assertEqual(alc['totais']['bytes'], sum(c['bytes'] for c in alc['categorias'].values()))
        self.assertEqual(alc['conversas'], [CHAT])
        self.assertEqual(alc['registros']['catalogo'], 1)
        self.assertIn('backup', alc['aviso_backup'])
        self.assertEqual(alc['nome_para_confirmar'], 'Título alpha')
        self.assertFalse(any(k.startswith('_') for k in alc))
        self.assertFalse(any('beta' in r for r in alc['raizes']))

    def test_alcance_de_conversa_e_de_rodada(self):
        chat = self.lixo('conversa', conversa=CHAT, rodadas=['R001'])
        alc = lixeira.alcance(self.root, chat['id'])
        self.assertEqual(alc['rodadas'], ['R001'])
        self.assertEqual(alc['conversas'], [CHAT])
        self.assertEqual(alc['raizes'], [f'conversas/{CHAT}', 'execucoes/alpha/R001'])
        self.assertNotIn('originais', alc['categorias'])  # originais do caso não entram
        self.assertGreater(alc['categorias']['rodadas']['arquivos'], 0)
        rodada = self.lixo('rodada', caso='beta', rodada='R001')
        alc2 = lixeira.alcance(self.root, rodada['id'])
        self.assertEqual(alc2['raizes'], ['execucoes/beta/R001'])
        self.assertEqual(alc2['conversas'], [])
        self.assertNotIn('conversas', alc2['categorias'])

    def test_conversa_preserva_rodada_compartilhada(self):
        self.conversa('alpha', CHAT_B, ['R001'])
        chat = self.lixo('conversa', conversa=CHAT, rodadas=['R001'])
        alc = lixeira.alcance(self.root, chat['id'])
        self.assertEqual(alc['rodadas'], [])
        self.assertEqual(alc['rodadas_preservadas'], ['R001'])

    def test_recusa_item_fora_da_lixeira_e_ids_invalidos(self):
        item = self.lixo('caso')
        lixeira.restaurar(self.root, item['id'])
        for ident in (item['id'], 'x' * 32, '../..', None):
            with self.assertRaises(ValueError):
                lixeira.alcance(self.root, ident)
        with self.assertRaisesRegex(ValueError, 'lixeira'):
            apagamento.apagar(self.root, item['id'], 'a' * 64, quem='admin')
        self.assertTrue((self.root / 'casos/alpha').is_dir())

    def test_confirmacao_errada_ou_vencida_e_recusada(self):
        item = self.lixo('caso')
        with self.assertRaisesRegex(ValueError, 'Confirmação'):
            apagamento.apagar(self.root, item['id'], '', quem='admin')
        with self.assertRaisesRegex(ValueError, 'mudou'):
            apagamento.apagar(self.root, item['id'], 'f' * 64, quem='admin')
        token = lixeira.alcance(self.root, item['id'])['confirmacao']
        (self.root / 'casos/alpha/arquivo_novo.txt').write_text('novo', encoding='utf-8')
        with self.assertRaisesRegex(ValueError, 'mudou'):
            apagamento.apagar(self.root, item['id'], token, quem='admin')
        self.assertTrue((self.root / 'casos/alpha/manifesto.json').exists())
        self.assertEqual(len(lixeira.ativos(self.root)), 1)
        novo = lixeira.alcance(self.root, item['id'])['confirmacao']
        self.assertNotEqual(novo, token)
        apagamento.apagar(self.root, item['id'], novo, quem='admin')
        self.assertFalse((self.root / 'casos/alpha').exists())

    def test_recusa_com_execucao_ativa(self):
        item = self.lixo('conversa', conversa=CHAT, rodadas=['R001'])
        token = lixeira.alcance(self.root, item['id'])['confirmacao']
        ger = Gerenciador()
        ger.contexts[CHAT] = {'meta': {'id': CHAT, 'caso': 'alpha', 'estado': 'executando'}, 'busy': True}
        with self.assertRaisesRegex(ValueError, 'execução em andamento'):
            apagamento.apagar(self.root, item['id'], token, quem='admin', gerenciador=ger)
        with self.assertRaisesRegex(ValueError, 'execução em andamento'):
            apagamento.apagar(self.root, item['id'], token, quem='admin', ativa=lambda caso, conversa: True)
        self.assertTrue((self.root / f'conversas/{CHAT}').is_dir())
        # Execução de outra conversa não impede apagar esta.
        ger.contexts[CHAT] = {'meta': {'id': CHAT_B, 'caso': 'alpha', 'estado': 'executando'}, 'busy': True}
        apagamento.apagar(self.root, item['id'], token, quem='admin', gerenciador=ger,
                          ativa=lambda caso, conversa: False)
        self.assertFalse((self.root / f'conversas/{CHAT}').exists())

    def test_apaga_caso_inteiro_sem_tocar_em_outros(self):
        beta_antes = sorted(str(p.relative_to(self.root)) for p in self.arquivos('beta'))
        beta_bytes = {p: p.stat().st_size for p in self.arquivos('beta') if p.is_file()}
        catalogo_beta = [c for c in ler_json(self.root / 'casos/catalogo.json')['casos'] if c['id'] == 'beta']
        outra = self.conversa('beta', CHAT_B, ['R001'])
        restante = self.lixo('rodada', caso='beta', rodada='R001')
        self.fx.completo()
        item = self.lixo('caso')
        subitem = self.lixo('rodada', rodada='R001')  # registro de rodada do mesmo caso
        selecionado = apagamento.alcance(self.root, item['id'])
        resultado = apagamento.apagar(self.root, item['id'], selecionado['confirmacao'], quem='gestor')
        self.assertEqual(resultado['estado'], 'apagado')
        for pasta in ('casos/alpha', 'execucoes/alpha', f'conversas/{CHAT}'):
            self.assertFalse((self.root / pasta).exists(), pasta)
        self.assertEqual(sorted(str(p.relative_to(self.root)) for p in self.arquivos('beta')), beta_antes)
        self.assertEqual({p: p.stat().st_size for p in self.arquivos('beta') if p.is_file()}, beta_bytes)
        self.assertTrue((self.root / f'conversas/{CHAT_B}/conversa.json').exists())
        catalogo = ler_json(self.root / 'casos/catalogo.json')['casos']
        self.assertEqual([c['id'] for c in catalogo], ['beta'])
        self.assertEqual(catalogo, catalogo_beta)
        ids = [i['id'] for i in lixeira.registros(self.root)]
        self.assertEqual(ids, [restante['id']])
        self.assertNotIn(subitem['id'], ids)
        self.assertEqual(outra['caso'], 'beta')

    def test_apagar_conversa_remove_pasta_e_rodadas_sem_afetar_o_caso(self):
        item = self.lixo('conversa', conversa=CHAT, rodadas=['R001'])
        ger = Gerenciador()
        ger.contexts[CHAT] = {'meta': {'id': CHAT, 'caso': 'alpha', 'estado': 'concluido'}, 'busy': False}
        token = lixeira.alcance(self.root, item['id'])['confirmacao']
        apagamento.apagar(self.root, item['id'], token, quem='admin', gerenciador=ger)
        self.assertFalse((self.root / f'conversas/{CHAT}').exists())
        self.assertFalse((self.root / 'execucoes/alpha/R001').exists())
        self.assertTrue((self.root / 'casos/alpha/manifesto.json').exists())
        self.assertNotIn(CHAT, ger.contexts)
        self.assertEqual(lixeira.registros(self.root), [])

    def test_apagar_rodada_avulsa(self):
        item = self.lixo('rodada', caso='beta', rodada='R001')
        token = lixeira.alcance(self.root, item['id'])['confirmacao']
        apagamento.apagar(self.root, item['id'], token, quem='admin')
        self.assertFalse((self.root / 'execucoes/beta/R001').exists())
        self.assertTrue((self.root / 'casos/beta/manifesto.json').exists())
        self.assertTrue((self.root / 'execucoes/alpha/R001').is_dir())

    def test_configuracao_do_caso_ativo_e_limpa(self):
        from selecionar_caso import selecionar
        selecionar(self.root, 'alpha')
        item = self.lixo('caso')
        apagamento.apagar(self.root, item['id'], lixeira.alcance(self.root, item['id'])['confirmacao'], quem='admin')
        config = ler_json(self.root / 'configuracao.json')
        self.assertIsNone(config['caso_ativo'])
        self.assertIsNone(config['manifesto_ativo'])

    def test_registro_de_apagamento_sem_conteudo_e_somente_acrescimo(self):
        primeiro = self.lixo('rodada', caso='beta', rodada='R001')
        apagamento.apagar(self.root, primeiro['id'], lixeira.alcance(self.root, primeiro['id'])['confirmacao'],
                          quem='gestor@exemplo')
        segundo = self.lixo('caso')
        apagamento.apagar(self.root, segundo['id'], lixeira.alcance(self.root, segundo['id'])['confirmacao'],
                          quem='gestor@exemplo')
        texto = (self.root / apagamento.REGISTRO_APAGAMENTOS).read_text(encoding='utf-8')
        linhas = [json.loads(x) for x in texto.splitlines()]
        self.assertEqual([x['tipo'] for x in linhas], ['rodada', 'caso'])
        self.assertEqual(linhas[1]['quem'], 'gestor@exemplo')
        self.assertEqual(linhas[1]['item_id'], segundo['id'])
        self.assertGreater(linhas[1]['totais']['arquivos'], 0)
        self.assertGreater(linhas[1]['totais']['bytes'], 0)
        self.assertTrue(linhas[1]['em_utc'])
        for proibido in (SEGREDO, 'Título alpha', 'Pergunta sintética', 'Alfabeto', 'valor 12'):
            self.assertNotIn(proibido, texto)

    def test_nao_segue_link_para_fora_da_raiz(self):
        alvo = Path(self.fx.temp.name + '_fora')
        alvo.mkdir()
        self.addCleanup(lambda: __import__('shutil').rmtree(alvo, ignore_errors=True))
        (alvo / 'precioso.txt').write_text('fora da raiz', encoding='utf-8')
        elo = self.root / 'execucoes/beta/R001/saidas/elo'
        try:
            os.symlink(alvo, elo, target_is_directory=True)
        except (OSError, NotImplementedError):
            self.skipTest('Links simbólicos indisponíveis neste ambiente.')
        item = self.lixo('rodada', caso='beta', rodada='R001')
        alc = lixeira.alcance(self.root, item['id'])
        apagamento.apagar(self.root, item['id'], alc['confirmacao'], quem='admin')
        self.assertFalse((self.root / 'execucoes/beta/R001').exists())
        self.assertEqual((alvo / 'precioso.txt').read_text(encoding='utf-8'), 'fora da raiz')

    def test_falha_de_permissao_persistente_mantem_item_na_lixeira(self):
        # With the quarantine, a file in use blocks the rename of its folder (Windows): nothing changes.
        item = self.lixo('rodada', caso='beta', rodada='R001')
        token = lixeira.alcance(self.root, item['id'])['confirmacao']
        from unittest.mock import patch
        with patch('apagamento.ESPERA_S', 0), patch('apagamento.os.rename', side_effect=PermissionError('uso')):
            with self.assertRaisesRegex(ValueError, 'continua na lixeira'):
                apagamento.apagar(self.root, item['id'], token, quem='admin')
        self.assertEqual(len(lixeira.ativos(self.root)), 1)
        self.assertFalse((self.root / apagamento.REGISTRO_APAGAMENTOS).exists())
        self.assertTrue((self.root / 'execucoes/beta/R001').is_dir())
        self.assertEqual(list((self.root / apagamento.MANIFESTOS).glob('*.json')), [])

    def test_tentativa_transitoria_de_permissao_e_repetida(self):
        item = self.lixo('rodada', caso='beta', rodada='R001')
        token = lixeira.alcance(self.root, item['id'])['confirmacao']
        from unittest.mock import patch
        real = os.unlink
        chamadas = {'n': 0}

        def instavel(caminho):
            partes = Path(caminho).parts  # the item's files in quarantine (an antivirus holds one a moment)
            if apagamento.QUARENTENA in partes and 'lixeira' not in partes:
                chamadas['n'] += 1
                if chamadas['n'] == 1:
                    raise PermissionError('antivírus')
            return real(caminho)
        with patch('apagamento.ESPERA_S', 0), patch('apagamento.os.unlink', side_effect=instavel):
            apagamento.apagar(self.root, item['id'], token, quem='admin')
        self.assertFalse((self.root / 'execucoes/beta/R001').exists())
        self.assertGreater(chamadas['n'], 1)
        self.assertFalse((self.root / 'execucoes' / apagamento.QUARENTENA).exists())


class ApagamentoHttpTest(unittest.TestCase):
    """Operações lixeira-alcance/lixeira-apagar pelo servidor local (papel de administração)."""

    def setUp(self):
        import http.client
        from interface_pesquisa import Servidor
        self.http = http.client
        self.fx, _ = Ambiente.copia_completa()
        self.addCleanup(self.fx.cleanup)
        self.root = self.fx.root
        self.server = Servidor(('127.0.0.1', 0), self.root)
        thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        thread.start()
        self.addCleanup(lambda: (self.server.shutdown(), self.server.server_close(), thread.join(3)))
        self.item = lixeira.adicionar(self.root, 'caso', 'alpha', 'Título alpha')

    def post(self, operation, data):
        con = self.http.HTTPConnection('127.0.0.1', self.server.server_port, timeout=15)
        con.request('POST', '/api/' + operation, json.dumps(data),
                    {'Content-Type': 'application/json', 'Origin': self.server.origin,
                     'X-Session-Token': self.server.token})
        response = con.getresponse()
        status, body = response.status, json.loads(response.read() or b'{}')
        con.close()
        return status, body

    def test_alcance_nao_expoe_caminhos_internos_e_apagar_exige_nome_e_confirmacao(self):
        status, alc = self.post('lixeira-alcance', {'item': self.item['id']})
        self.assertEqual(status, 200, alc)
        self.assertFalse([k for k in alc if k.startswith('_')])
        self.assertEqual(alc['nome_para_confirmar'], 'Título alpha')
        self.assertTrue(alc['aviso_backup'])
        base = {'item': self.item['id'], 'confirmacao': alc['confirmacao']}
        status, erro = self.post('lixeira-apagar', {**base, 'nome': 'outro'})
        self.assertEqual(status, 400)
        self.assertIn('Digite o nome', erro['erro'])
        status, erro = self.post('lixeira-apagar', {**base, 'nome': 'Título alpha', 'confirmacao': '0' * 64})
        self.assertEqual((status, erro['codigo']), (400, 'alcance_alterado'))
        self.assertTrue((self.root / 'casos/alpha').exists())
        status, feito = self.post('lixeira-apagar', {**base, 'nome': '  título ALPHA '})
        self.assertEqual(status, 200, feito)
        self.assertEqual(feito['estado'], 'apagado')
        self.assertFalse((self.root / 'casos/alpha').exists())
        self.assertFalse((self.root / 'execucoes/alpha').exists())
        self.assertEqual(self.post('lixeira-alcance', {'item': self.item['id']})[0], 400)


if __name__ == '__main__':
    unittest.main()
