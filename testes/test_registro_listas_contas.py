"""Listas fechadas do registro de auditoria com o que o contrato de contas traz (Onda 2, P4).

O registro descarta todo evento, papel, código, motivo e campo fora das suas listas: sem estas
entradas, o que as entregas E1 a E4 da Tranca gravam sumiria em silêncio. Confere também que a
redação só entra como id (nunca o nome), pelo contexto da requisição ou pelos eventos do cadastro
de contas, e que a recusa sai como acesso_negado com motivo (o nome antigo continua aceito para as
linhas de antes). Sem rede nem servidor.
"""
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import registro_acesso as r  # noqa: E402

CONTA = '0123456789abcdef'
ORG = 'org' + 'fedcba9876543210'
EVENTOS = ('acesso_negado', 'caso_criado', 'caso_atribuido', 'participacao_incluida', 'participacao_retirada',
           'responsavel_alterado', 'redacao_criada', 'redacao_suspensa', 'redacao_reativada', 'redacao_encerrada',
           'migracao_contas', 'senha_trocada', 'senha_redefinida', 'papel_alterado', 'teto_alterado',
           'conta_atualizada', 'conta_excluida', 'conta_exportada', 'conta_expirada', 'sessao_encerrada_a_distancia',
           'convite_enviado', 'convite_reenviado', 'convite_cancelado', 'convite_aceito', 'fator_ativado',
           'fator_removido', 'fator_recusado', 'codigo_reserva_usado', 'recuperacao_pedida', 'recuperacao_confirmada',
           'termos_aceitos', 'chave_redacao_alterada')
PAPEIS = ('dono', 'editor', 'reporter', 'leitor')
CODIGOS = ('caso_indisponivel', 'conversa_indisponivel', 'lote_inexistente', 'redacao_suspensa', 'pendencia_de_conta',
           'operacao_inexistente', 'acesso_indisponivel', 'senha_atual_incorreta', 'ultimo_dono')
MOTIVOS = ('sem_participacao', 'outra_redacao', 'inexistente', 'redacao_suspensa', 'senha_incorreta', 'ultimo_dono')


class ListasDoContratoTest(unittest.TestCase):
    def tearDown(self):
        r.encerrar_requisicao()

    def test_eventos_do_contrato_sao_gravados(self):
        for evento in EVENTOS:
            with self.subTest(evento=evento):
                linha = r.montar(evento, 'ok', CONTA, organizacao=ORG)
                self.assertIsNotNone(linha, evento)
                self.assertEqual((linha['evento'], linha['organizacao']), (evento, ORG))

    def test_acesso_negado_leva_motivo_codigo_e_redacao(self):
        for motivo in MOTIVOS:
            for codigo in CODIGOS:
                with self.subTest(motivo=motivo, codigo=codigo):
                    linha = r.montar('acesso_negado', 'negado', CONTA, motivo=motivo, codigo=codigo, organizacao=ORG)
                    self.assertEqual((linha['resultado'], linha['motivo'], linha['codigo'], linha['organizacao']),
                                     ('negado', motivo, codigo, ORG))

    def test_nome_antigo_da_recusa_continua_aceito(self):
        # Linhas antigas e tipo_original de eventos arquivados ainda usam operacao_negada.
        self.assertEqual(r.montar('operacao_negada', 'negado', CONTA)['evento'], 'operacao_negada')
        self.assertEqual(r.montar('evento_arquivado', 'ok', CONTA, tipo_original='operacao_negada')['tipo_original'],
                         'operacao_negada')

    def test_papeis_da_redacao_e_os_antigos(self):
        for papel in (*PAPEIS, 'admin', 'convidado'):
            with self.subTest(papel=papel):
                self.assertEqual(r.montar('participacao_incluida', 'ok', CONTA, papel=papel, alvo=CONTA)['papel'], papel)
        self.assertNotIn('papel', r.montar('participacao_incluida', 'ok', CONTA, papel='chefe'))

    def test_campos_de_acesso_novos(self):
        linha = r.montar('acesso_alterado', 'ok', CONTA, campos=['teto', 'idioma', 'email', 'papel'], papel='dono')
        self.assertEqual((linha['campos'], linha['papel']), (['email', 'idioma', 'papel', 'teto'], 'dono'))
        self.assertNotIn('campos', r.montar('acesso_alterado', 'ok', CONTA, campos=['teto', 'senha']))

    def test_redacao_so_como_id_nunca_nome(self):
        self.assertEqual(r.montar('redacao_criada', 'ok', CONTA, organizacao='instalacao')['organizacao'], 'instalacao')
        for nome in ('Redação Sintética', 'org-redacao-sintetica', 'org0123', ORG.upper(), ORG + '0', CONTA, '', None, 7):
            with self.subTest(nome=nome):
                self.assertNotIn('organizacao', r.montar('redacao_criada', 'ok', CONTA, organizacao=nome))

    def test_redacao_do_contexto_sai_em_toda_linha_da_requisicao(self):
        r.iniciar_requisicao()
        r.definir(conta=CONTA, organizacao=ORG, operacao=None)
        self.assertEqual(r.montar('acesso_negado', 'negado', CONTA, codigo='caso_indisponivel')['organizacao'], ORG)
        self.assertEqual(r.montar('download', 'ok', CONTA, tipo='original')['organizacao'], ORG)
        r.encerrar_requisicao()
        r.iniciar_requisicao()
        r.definir(conta=CONTA, organizacao='Redação Sintética')  # um nome no contexto também é descartado
        self.assertNotIn('organizacao', r.montar('download', 'ok', CONTA, tipo='original'))
        r.encerrar_requisicao()
        r.iniciar_requisicao()
        r.definir(conta=CONTA, organizacao=None)  # modo local: sem redação, sem campo
        self.assertNotIn('organizacao', r.montar('download', 'ok', CONTA, tipo='original'))

    def test_eventos_do_cadastro_de_contas_levam_a_redacao(self):
        with tempfile.TemporaryDirectory() as pasta, mock.patch.dict(os.environ, {'VLADO_REGISTRO': pasta}):
            r.do_acesso('participacao_incluida', CONTA, 'operador', organizacao=ORG, papel='reporter', alvo=CONTA)
            linha, = [json.loads(l) for f in r.arquivos(Path(pasta)) for l in f.read_text(encoding='ascii').splitlines()]
        self.assertEqual((linha['evento'], linha['organizacao'], linha['papel'], linha['por']),
                         ('participacao_incluida', ORG, 'reporter', 'operador'))

    def test_operador_como_autor(self):
        linha = r.montar('redacao_suspensa', 'ok', CONTA, por='operador', organizacao=ORG)
        self.assertEqual(linha['por'], 'operador')
        self.assertNotIn('por', r.montar('redacao_suspensa', 'ok', CONTA, por='Fulano'))

    def test_fora_das_listas_continua_descartado(self):
        linha = r.montar('acesso_negado', 'negado', CONTA, motivo='porque sim', codigo='inventado', nome_caso='Caso X')
        self.assertFalse({'motivo', 'codigo', 'nome_caso'} & set(linha))
        self.assertIsNone(r.montar('redacao_apagada', 'ok', CONTA))


if __name__ == '__main__':
    unittest.main()
