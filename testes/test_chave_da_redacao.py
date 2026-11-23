"""A chave de IA própria da redação (contrato de contas, seções 5.5 e 8.5).

No armazenamento (``segredos.py``): a chave de uma redação fica à parte da chave do serviço, vem antes dela para
aquela redação e nunca aparece para outra. Pelo servidor (duas redações em modo ``piloto``): ``ia-config`` mostra só
a chave da própria redação, ``ia-config-salvar`` só grava ou remove essa chave, e provedor e modelo continuam com
quem opera o serviço. Chaves sintéticas, em pasta temporária; sem modelo e sem rede.
"""
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
sys.path.insert(0, str(Path(__file__).resolve().parent))
import acesso
import cenario_redacoes as cenario
from cenario_redacoes import SENHA
import segredos
from inferencia_api import resumo_inferencia

SEM_AMBIENTE = {'VLADO_SEGREDOS': '', 'ANTHROPIC_API_KEY': '', 'OPENAI_API_KEY': ''}
DO_SERVICO = 'sk-sintetica-do-servico-0000000000SERV'
DE_ALFA = 'sk-sintetica-da-redacao-alfa-00000ALFA'
DE_BETA = 'sk-sintetica-da-redacao-beta-00000BETA'
A, B = 'org' + 'a' * 16, 'org' + 'b' * 16


class ArmazenamentoTest(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        env = patch.dict(os.environ, SEM_AMBIENTE)
        env.start()
        self.addCleanup(env.stop)

    def test_a_chave_da_redacao_vem_antes_da_do_servico_so_para_ela(self):
        segredos.salvar_chave(self.root, 'anthropic', DO_SERVICO)
        segredos.salvar_chave(self.root, 'anthropic', DE_ALFA, A)
        self.assertEqual(segredos.ler_chave(self.root, 'anthropic', A), DE_ALFA)
        self.assertEqual(segredos.ler_chave(self.root, 'anthropic', B), DO_SERVICO)  # another newsroom: the service's
        self.assertEqual(segredos.ler_chave(self.root, 'anthropic'), DO_SERVICO)  # no newsroom: as ever
        self.assertEqual([segredos.origem_da_chave(self.root, 'anthropic', r) for r in (A, B, None)], ['redacao', 'salva', 'salva'])
        self.assertIsNone(segredos.ler_chave(self.root, 'openai', A))  # one provider's key is not the other's
        with patch.dict(os.environ, {'ANTHROPIC_API_KEY': 'sk-sintetica-do-ambiente-000000000AMBI'}):
            self.assertEqual(segredos.ler_chave(self.root, 'anthropic', A), DE_ALFA)  # its own key still comes first
            self.assertEqual(segredos.origem_da_chave(self.root, 'anthropic', B), 'ambiente')
        # Kept apart: saving a newsroom's key never rewrites the file of the service's key.
        do_servico, das_redacoes = segredos.caminho(self.root), segredos.caminho_das_redacoes(self.root)
        self.assertEqual(json.loads(do_servico.read_text(encoding='utf-8')), {'anthropic': DO_SERVICO})
        self.assertEqual(json.loads(das_redacoes.read_text(encoding='utf-8')), {A: {'anthropic': DE_ALFA}})
        self.assertEqual(das_redacoes.parent, do_servico.parent)
        self.assertIn(DE_ALFA, segredos.conhecidas())  # so that error messages can strip it

    def test_o_que_uma_redacao_fica_sabendo_das_chaves(self):
        vazio = {'configurada': False, 'origem': None, 'final': None}
        self.assertEqual(segredos.resumo(self.root, A), {'anthropic': vazio, 'openai': vazio})
        segredos.salvar_chave(self.root, 'anthropic', DO_SERVICO)
        # Of the service's key a newsroom learns that it exists: not its last characters.
        self.assertEqual(segredos.resumo(self.root, A)['anthropic'], {'configurada': True, 'origem': 'servico', 'final': None})
        segredos.salvar_chave(self.root, 'anthropic', DE_ALFA, A)
        self.assertEqual(segredos.resumo(self.root, A)['anthropic'], {'configurada': True, 'origem': 'redacao', 'final': 'ALFA'})
        self.assertEqual(segredos.resumo(self.root, B)['anthropic'], {'configurada': True, 'origem': 'servico', 'final': None})
        self.assertEqual(segredos.resumo(self.root)['anthropic'], {'configurada': True, 'origem': 'salva', 'final': 'SERV'})
        for resumo in (segredos.resumo(self.root, A), segredos.resumo(self.root, B), segredos.resumo(self.root)):
            for chave in (DO_SERVICO, DE_ALFA):
                self.assertNotIn(chave, json.dumps(resumo))

    def test_remover_a_chave_da_redacao_devolve_a_do_servico_e_nao_toca_em_mais_nada(self):
        segredos.salvar_chave(self.root, 'anthropic', DO_SERVICO)
        segredos.salvar_chave(self.root, 'anthropic', DE_ALFA, A)
        segredos.salvar_chave(self.root, 'anthropic', DE_BETA, B)
        segredos.remover_chave(self.root, 'anthropic', A)
        segredos.remover_chave(self.root, 'anthropic', A)  # nothing left to remove: no error
        self.assertEqual([segredos.ler_chave(self.root, 'anthropic', r) for r in (A, B, None)], [DO_SERVICO, DE_BETA, DO_SERVICO])
        self.assertEqual(json.loads(segredos.caminho_das_redacoes(self.root).read_text(encoding='utf-8')), {B: {'anthropic': DE_BETA}})
        segredos.remover_chave(self.root, 'anthropic')  # the service's: the newsroom's stays
        self.assertEqual([segredos.ler_chave(self.root, 'anthropic', r) for r in (A, B, None)], [None, DE_BETA, None])

    def test_id_de_redacao_que_nao_e_id_nao_vira_caminho_nem_chave(self):
        for invalido in ('', 'instalacao', '../chaves', 'org' + 'a' * 15, 'ORG' + 'a' * 16, A + '/x', 7, ['x'], {}):
            for acao in (lambda r: segredos.salvar_chave(self.root, 'anthropic', DE_ALFA, r),
                         lambda r: segredos.ler_chave(self.root, 'anthropic', r),
                         lambda r: segredos.remover_chave(self.root, 'anthropic', r),
                         lambda r: segredos.resumo(self.root, r),
                         lambda r: segredos.origem_da_chave(self.root, 'anthropic', r)):
                with self.assertRaises(ValueError, msg=repr(invalido)):
                    acao(invalido)
        self.assertFalse((self.root / 'segredos').exists())  # nothing was written
        for chave in ('curta', None, 'com espaço ' + 'x' * 30, 'x' * 301):
            with self.assertRaises(ValueError) as recusa:
                segredos.salvar_chave(self.root, 'anthropic', chave, A)
            self.assertNotIn(str(chave), str(recusa.exception))  # the value sent is never echoed
        with self.assertRaises(ValueError):
            segredos.salvar_chave(self.root, 'outro', DE_ALFA, A)

    def test_arquivo_das_redacoes_ilegivel_nao_derruba_a_chave_do_servico(self):
        segredos.salvar_chave(self.root, 'anthropic', DO_SERVICO)
        segredos.caminho_das_redacoes(self.root).write_text('{ isto não é json', encoding='utf-8')
        self.assertEqual(segredos.ler_chave(self.root, 'anthropic'), DO_SERVICO)
        with self.assertRaisesRegex(ValueError, 'chaves das redações está ilegível'):
            segredos.ler_chave(self.root, 'anthropic', A)
        segredos.caminho_das_redacoes(self.root).write_text(json.dumps({'../x': {'anthropic': DE_ALFA}, A: 'texto', B: {'outro': 'x'}}),
                                                            encoding='utf-8')
        self.assertEqual([segredos.ler_chave(self.root, 'anthropic', r) for r in (A, B)], [DO_SERVICO, DO_SERVICO])  # only what is well formed


class SemRedacaoTest(unittest.TestCase):
    """In the hosted mode, a caller without a newsroom never falls on the key of the service: it fails closed."""

    def test_no_piloto_quem_nao_tem_redacao_nao_le_nem_grava_chave(self):
        from types import SimpleNamespace
        import rotas_gestao
        with tempfile.TemporaryDirectory() as pasta, patch.dict(os.environ, SEM_AMBIENTE):
            root = Path(pasta)
            segredos.salvar_chave(root, 'anthropic', DO_SERVICO)
            rotas = SimpleNamespace(server=SimpleNamespace(modo='piloto', root=root))
            for principal in ({'papel': 'dono', 'conta': 'c' * 32, 'organizacao': None},
                              {'papel': 'dono', 'conta': 'c' * 32, 'organizacao': {'id': None}}):
                for operacao, dados in (('ia-config', {}), ('ia-config-salvar', {'provedor': 'anthropic', 'chave': DE_ALFA})):
                    with self.assertRaisesRegex(ValueError, 'somente a própria chave'):
                        rotas_gestao.RotasGestao._gestao(rotas, operacao, dados, principal)
            self.assertEqual(segredos.ler_chave(root, 'anthropic'), DO_SERVICO)
            self.assertFalse(segredos.caminho_das_redacoes(root).exists())


class ServidorTest(cenario.DuasRedacoes):
    """Two newsrooms in the hosted mode: each dono and the own key."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls._pilha.enter_context(patch.dict(os.environ, SEM_AMBIENTE))
        configuracao = cls.root / 'configuracao.json'  # the synthetic folder comes without a provider: the operator's choice
        dados = json.loads(configuracao.read_text(encoding='utf-8')) if configuracao.is_file() else {}
        configuracao.write_text(json.dumps({**dados, 'provedor': 'anthropic', 'modelo_preferido': None}), encoding='utf-8')
        cls.provedor = resumo_inferencia(cls.root)['provedor']

    def setUp(self):
        for arquivo in (segredos.caminho(self.root), segredos.caminho_das_redacoes(self.root)):
            arquivo.unlink(missing_ok=True)

    def chaves(self, quem):
        status, corpo, bruto = self.post(quem, 'ia-config', {})
        self.assertEqual(status, 200, bruto[:200])
        return corpo['chaves'][self.provedor], bruto.decode('utf-8')

    def salvar(self, quem, **campos):
        return self.post(quem, 'ia-config-salvar', {'provedor': self.provedor, 'senha': SENHA, **campos})

    def test_cada_dono_grava_e_ve_so_a_chave_da_propria_redacao(self):
        segredos.salvar_chave(self.root, self.provedor, DO_SERVICO)  # the operator's doing
        self.assertEqual(self.chaves('dono')[0], {'configurada': True, 'origem': 'servico', 'final': None})
        status, corpo, bruto = self.salvar('dono', chave=DE_ALFA)
        self.assertEqual((status, corpo['chaves'][self.provedor]), (200, {'configurada': True, 'origem': 'redacao', 'final': 'ALFA'}),
                         bruto[:200])
        self.assertNotIn(DE_ALFA, bruto.decode('utf-8'))  # write-only: the key never comes back
        de_alfa, bruto_alfa = self.chaves('dono')
        de_beta, bruto_beta = self.chaves('dono_b')
        self.assertEqual((de_alfa, de_beta), ({'configurada': True, 'origem': 'redacao', 'final': 'ALFA'},
                                              {'configurada': True, 'origem': 'servico', 'final': None}))
        for texto in (bruto_alfa, bruto_beta):
            for segredo in (DE_ALFA, DO_SERVICO, 'SERV'):
                self.assertNotIn(segredo, texto)
        self.assertNotIn('ALFA', bruto_beta)  # nor the four characters of the neighbour
        self.assertEqual(self.salvar('dono_b', chave=DE_BETA)[0], 200)
        self.assertEqual([segredos.ler_chave(self.root, self.provedor, r) for r in (self.a, self.b, None)],
                         [DE_ALFA, DE_BETA, DO_SERVICO])  # what the call to the provider will use, and the service's is as it was
        self.assertEqual(json.loads(segredos.caminho(self.root).read_text(encoding='utf-8')), {self.provedor: DO_SERVICO})
        # Removing gives the newsroom back to the key of the service, and touches nobody else's.
        status, corpo, _ = self.salvar('dono', remover_chave=True)
        self.assertEqual((status, corpo['chaves'][self.provedor]), (200, {'configurada': True, 'origem': 'servico', 'final': None}))
        self.assertEqual([segredos.ler_chave(self.root, self.provedor, r) for r in (self.a, self.b)], [DO_SERVICO, DE_BETA])

    def test_provedor_e_modelo_do_servico_nao_mudam_pela_mesa(self):
        antes = resumo_inferencia(self.root)
        outro = next(p for p in segredos.CHAVES_AMBIENTE if p != self.provedor)
        for corpo in ({'provedor': outro, 'chave': DE_ALFA}, {'provedor': self.provedor, 'modelo_preferido': 'outro-modelo', 'chave': DE_ALFA},
                      {'provedor': self.provedor}, {'provedor': self.provedor, 'remover_chave': 'sim'},
                      {'provedor': self.provedor, 'chave': 'curta'}, {'provedor': self.provedor, 'chave': DE_ALFA, 'redacao': self.b},
                      {'chave': DE_ALFA}):
            status, resposta, bruto = self.post('dono', 'ia-config-salvar', {**corpo, 'senha': SENHA})
            self.assertEqual(status, 400, (corpo, bruto[:200]))
            self.assertNotIn(DE_ALFA, bruto.decode('utf-8'))
        self.assertFalse(segredos.caminho_das_redacoes(self.root).exists())  # refused whole: nothing was written
        depois = resumo_inferencia(self.root)
        self.assertEqual((depois['provedor'], depois['modelo_preferido']), (antes['provedor'], antes['modelo_preferido']))
        self.assertFalse((self.root / 'ajustes' / 'inferencia.json').exists())
        # The page of today sends the model it read: the same model is not a change.
        igual = self.salvar('dono', modelo_preferido=antes['modelo_preferido'], chave=DE_ALFA)
        self.assertEqual(igual[0], 200, igual[2][:200])

    def test_sem_a_senha_nada_e_gravado(self):
        # Seção 5.15: the password of who does it, checked before anything; it never reaches the newsroom's key.
        status, corpo, bruto = self.post('dono', 'ia-config-salvar', {'provedor': self.provedor, 'chave': DE_ALFA})
        self.assertEqual((status, corpo.get('codigo')), (403, 'senha_necessaria'), bruto[:200])
        self.assertNotIn(DE_ALFA, bruto.decode('utf-8'))
        self.assertFalse(segredos.caminho_das_redacoes(self.root).exists())
        self.assertEqual(self.salvar('dono', chave=DE_ALFA)[0], 200)  # the password left the body: not a field
        self.assertEqual(segredos.ler_chave(self.root, self.provedor, self.a), DE_ALFA)

    def test_so_o_dono_e_a_troca_fica_na_atividade_da_propria_redacao_sem_a_chave(self):
        for papel in ('editor', 'reporter', 'leitor', 'convidado'):
            for operacao, corpo in (('ia-config', {}), ('ia-config-salvar', {'provedor': self.provedor, 'chave': DE_ALFA})):
                status, resposta, _ = self.post(papel, operacao, corpo)
                self.assertEqual((status, resposta.get('codigo')), (403, 'operacao_proibida'), (papel, operacao))
        self.assertFalse(segredos.caminho_das_redacoes(self.root).exists())

        def da_chave(quem):
            resposta = self.post(quem, 'equipe-atividade', {'limite': 200})
            return sorted((e['tipo'], e['conta'], e['por']) for e in resposta[1]['eventos'] if e['tipo'].startswith('chave_ia_')), resposta

        antes = da_chave('dono')[0]  # the other tests of this class share the store
        with patch.object(acesso.registro_acesso, 'registrar', wraps=acesso.registro_acesso.registrar) as registrar:
            self.assertEqual(self.salvar('dono', chave=DE_ALFA)[0], 200)
            self.assertEqual(self.salvar('dono', remover_chave=True)[0], 200)
            self.assertEqual(self.salvar('dono', remover_chave=True)[0], 200)  # nothing to remove: no second event
        tipos, de_alfa = da_chave('dono')
        self.assertEqual(tipos, sorted(antes + [('chave_ia_removida', self.ids['dono'], self.ids['dono']),
                                                ('chave_ia_salva', self.ids['dono'], self.ids['dono'])]))
        de_beta = self.post('dono_b', 'equipe-atividade', {'limite': 200})
        self.assertFalse([e for e in de_beta[1]['eventos'] if e['conta'] == self.ids['dono']])  # nothing of Alfa in Beta's activity
        gravado = json.dumps([[repr(c.args), repr(c.kwargs)] for c in registrar.call_args_list])
        for texto in (de_alfa[2].decode('utf-8'), de_beta[2].decode('utf-8'), gravado):
            self.assertNotIn(DE_ALFA, texto)
            self.assertNotIn('ALFA', texto)


if __name__ == '__main__':
    unittest.main()
