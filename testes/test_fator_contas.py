"""O segundo fator nas contas (``conta-fator-*`` e ``entrar-segundo-fator``; contrato de contas, seções 5.3, 5.4 e 8.2).

Cadastro em dois tempos (a semente só vale depois de um código do aplicativo), códigos de reserva de uso único,
entrada em dois passos para quem tem o fator, o código pedido na redefinição de senha por e-mail e o fator
retirado pela recuperação que um dono pediu. As contas de aritmética estão em ``test_segundo_fator.py``. No
armazenamento e pelo servidor (duas redações em modo ``piloto``). Sem modelo e sem rede.
"""
import json
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
sys.path.insert(0, str(Path(__file__).resolve().parent))
import acesso
import cenario_redacoes as cenario
import correio
import segundo_fator as fator
import test_acesso  # module import: its TestCases are not collected again here
from test_acesso import SENHA

ERRADA = 'senha-errada-de-teste'
NOVA = 'outra-senha-longa-2'


def codigo_de(segredo, desvio=0, momento=None):
    """The code an authenticator app would show now for the seed given in base32 (`desvio` steps away)."""
    semente = fator.base64.b32decode(segredo + '=' * (-len(segredo) % 8))
    return fator.codigo_do_passo(semente, fator.passo_de(momento or acesso.agora()) + desvio)


def cadastrar(root, cid, senha=SENHA):
    """Enrol a second factor for the account: (seed in base32, reserve codes)."""
    segredo = acesso.iniciar_fator(root, cid, senha)['segredo']
    return segredo, acesso.confirmar_fator(root, cid, codigo_de(segredo))


class ArmazenamentoTest(test_acesso.DuasRedacoes):
    def setUp(self):
        super().setUp()
        env = test_acesso.patch.dict(test_acesso.os.environ, {'VLADO_SEGREDOS': ''})
        env.start()
        self.addCleanup(env.stop)
        fator._CHAVES.clear()
        self.addCleanup(fator._CHAVES.clear)

    def test_cadastro_em_dois_tempos_e_a_semente_fica_cifrada(self):
        for senha, erro in ((None, acesso.SenhaNecessaria), (ERRADA, acesso.SenhaIncorreta)):
            with self.assertRaises(erro):
                acesso.iniciar_fator(self.root, self.rep_a, senha)
        inicio = acesso.iniciar_fator(self.root, self.rep_a, SENHA)
        self.assertRegex(inicio['segredo'], r'^[A-Z2-7]{32}$')
        self.assertTrue(inicio['otpauth'].startswith('otpauth://totp/Vlado%3Arep.a?secret=' + inicio['segredo']))
        self.assertEqual(acesso.ver_conta(self.root, self.rep_a)['segundo_fator'],
                         {'ativo': False, 'ativado_em': None, 'codigos_restantes': 0})  # nothing changed yet
        self.assertEqual(acesso.entrar(self.root, 'rep.a', SENHA)[2]['id'], self.rep_a)
        for ausente in ('', None, '   '):  # no code is not a wrong code: asked for, and nothing counted
            with self.assertRaises(acesso.CodigoNecessario):
                acesso.confirmar_fator(self.root, self.rep_a, ausente)
        self.assertEqual(self.linhas("SELECT 1 FROM tentativas WHERE chave LIKE '#fator|%'"), [])
        for errado in ('000000', 'abcdef'):
            with self.assertRaises(acesso.CodigoInvalido):
                acesso.confirmar_fator(self.root, self.rep_a, errado)
        codigos = acesso.confirmar_fator(self.root, self.rep_a, codigo_de(inicio['segredo']))
        self.assertEqual((len(codigos), len(set(codigos))), (10, 10))
        estado = acesso.ver_conta(self.root, self.rep_a)['segundo_fator']
        self.assertEqual((estado['ativo'], estado['codigos_restantes']), (True, 10))
        bruto = self.bruto()
        for segredo in (inicio['segredo'], *codigos, *(c.replace('-', '') for c in codigos)):
            self.assertNotIn(segredo, bruto)  # the seed is encrypted and the reserve codes are hashes
        self.assertTrue((self.root / 'segredos' / 'contas.chave').is_file())  # the key is not in the accounts folder
        self.assertFalse((self.root / 'acesso' / 'contas.chave').exists())
        self.assertIn('fator_ativado', self.tipos())
        with self.assertRaisesRegex(ValueError, 'Comece de novo'):
            acesso.confirmar_fator(self.root, self.rep_a, codigo_de(inicio['segredo']))  # nothing pending any more
        self.assertEqual(acesso.ver_conta(self.root, self.dono_a)['segundo_fator']['ativo'], False)  # nobody else's

    def test_ativar_o_fator_encerra_as_outras_sessoes_da_conta(self):
        # Reservation R5 of the review: as when the password changes, only the session that asks goes on.
        aqui, outra = (acesso.entrar(self.root, 'rep.a', SENHA)[0] for _ in range(2))
        de_outra_conta = acesso.entrar(self.root, 'dona.a', SENHA)[0]
        segredo = acesso.iniciar_fator(self.root, self.rep_a, SENHA)['segredo']
        self.assertTrue(acesso.sessao(self.root, outra))  # starting changes nothing
        acesso.confirmar_fator(self.root, self.rep_a, codigo_de(segredo), sessao_atual=acesso.sessao(self.root, aqui)['sessao'])
        self.assertIsNone(acesso.sessao(self.root, outra))
        self.assertEqual(acesso.sessao(self.root, aqui)['conta'], self.rep_a)
        self.assertEqual(acesso.sessao(self.root, de_outra_conta)['conta'], self.dono_a)

    def test_onde_o_fator_e_obrigatorio_dono_e_editor_sem_ele_ficam_com_a_pendencia(self):
        editor = acesso.criar_conta(self.root, 'Edu', 'edu.a', papel='editor', organizacao=self.a, por='operador')
        acesso.ativar(self.root, editor[1], SENHA)
        for login, cid, obrigado in (('dona.a', self.dono_a, True), ('edu.a', editor[0]['id'], True), ('rep.a', self.rep_a, False)):
            sid = acesso.entrar(self.root, login, SENHA)[0]
            self.assertEqual(acesso.sessao(self.root, sid)['pendencias'], [], login)  # the installed Mesa: optional
            esperado = ['segundo_fator'] if obrigado else []
            self.assertEqual(acesso.sessao(self.root, sid, obrigar_fator=True)['pendencias'], esperado, login)
            segredo = acesso.iniciar_fator(self.root, cid, SENHA)['segredo']
            self.assertEqual(acesso.sessao(self.root, sid, obrigar_fator=True)['pendencias'], esperado, login)  # started is not enrolled
            publico = acesso.sessao(self.root, sid)['sessao']
            acesso.confirmar_fator(self.root, cid, codigo_de(segredo), sessao_atual=publico)
            self.assertEqual(acesso.sessao(self.root, sid, obrigar_fator=True)['pendencias'], [], login)

    def test_cadastro_nao_confirmado_vence_e_cinco_codigos_errados_bloqueiam(self):
        segredo = acesso.iniciar_fator(self.root, self.rep_a, SENHA)['segredo']
        with self.depois(minutes=acesso.FATOR_PENDENTE_MINUTOS, seconds=1):
            with self.assertRaisesRegex(ValueError, 'Comece de novo'):
                acesso.confirmar_fator(self.root, self.rep_a, codigo_de(segredo, momento=acesso.agora()))
        segredo = acesso.iniciar_fator(self.root, self.rep_a, SENHA)['segredo']
        for _ in range(acesso.FALHAS_BLOQUEIO - 1):
            with self.assertRaises(acesso.CodigoInvalido):
                acesso.confirmar_fator(self.root, self.rep_a, '000000')
        with self.assertRaises(acesso.FatorBloqueado):  # the fifth in a row starts the block, and says who to tell
            acesso.confirmar_fator(self.root, self.rep_a, '000000')
        with self.assertRaises(acesso.Bloqueado):
            acesso.confirmar_fator(self.root, self.rep_a, codigo_de(segredo))  # even the right one, while blocked
        self.assertFalse(acesso.ver_conta(self.root, self.rep_a)['segundo_fator']['ativo'])
        self.assertEqual(acesso.entrar(self.root, 'rep.a', SENHA)[2]['id'], self.rep_a)  # signing in is another counter

    def test_entrada_em_dois_passos_para_quem_tem_o_fator(self):
        segredo, reserva = cadastrar(self.root, self.rep_a)
        with self.assertRaises(acesso.PedeSegundoFator) as passo:
            acesso.entrar(self.root, 'rep.a', SENHA, ip='198.51.100.7', aparelho='Firefox · Linux')
        bilhete = passo.exception.bilhete
        self.assertNotIn(bilhete, self.bruto())
        self.assertEqual(acesso.sessoes_da_conta(self.root, self.rep_a), [])  # the password alone opens nothing
        self.assertIsNone(acesso.sessao(self.root, bilhete))  # and the ticket is not a session
        with self.assertRaises(acesso.CredenciaisInvalidas):
            acesso.entrar(self.root, 'rep.a', ERRADA)
        with self.assertRaises(acesso.CodigoInvalido):
            acesso.entrar_segundo_fator(self.root, bilhete, '000000')
        with self.depois(seconds=31):  # the step used to enrol is spent: the app shows the next one
            agora = acesso.agora()
            sid, csrf, conta = acesso.entrar_segundo_fator(self.root, bilhete, codigo_de(segredo, momento=agora), ip='198.51.100.7')
            self.assertEqual((conta['id'], acesso.sessao(self.root, sid)['conta']), (self.rep_a, self.rep_a))
            self.assertEqual(acesso.sessoes_da_conta(self.root, self.rep_a)[0]['aparelho'], 'Firefox · Linux')
            with self.assertRaises(acesso.EntradaExpirada):
                acesso.entrar_segundo_fator(self.root, bilhete, codigo_de(segredo, 1, agora))  # the ticket works once
            # The same code does not open a second session, not even with a new ticket.
            with self.assertRaises(acesso.PedeSegundoFator) as outro:
                acesso.entrar(self.root, 'rep.a', SENHA)
            with self.assertRaises(acesso.CodigoInvalido):
                acesso.entrar_segundo_fator(self.root, outro.exception.bilhete, codigo_de(segredo, momento=agora))
            # A reserve code works instead of the app, once.
            self.assertEqual(acesso.entrar_segundo_fator(self.root, outro.exception.bilhete, reserva[0].lower())[2]['id'], self.rep_a)
            with self.assertRaises(acesso.PedeSegundoFator) as terceiro:
                acesso.entrar(self.root, 'rep.a', SENHA)
            with self.assertRaises(acesso.CodigoInvalido):
                acesso.entrar_segundo_fator(self.root, terceiro.exception.bilhete, reserva[0])
        self.assertEqual(acesso.ver_conta(self.root, self.rep_a)['segundo_fator']['codigos_restantes'], 9)
        self.assertIn('codigo_reserva_usado', self.tipos())
        self.assertEqual(acesso.entrar(self.root, 'dona.a', SENHA)[2]['id'], self.dono_a)  # who has no factor signs in as before

    def test_bilhete_vence_em_cinco_minutos_morre_com_cinco_erros_e_nao_serve_a_outra_conta(self):
        segredo, _ = cadastrar(self.root, self.rep_a)
        with self.assertRaises(acesso.PedeSegundoFator) as passo:
            acesso.entrar(self.root, 'rep.a', SENHA)
        bilhete = passo.exception.bilhete
        for invalido in (None, '', 'x' * 43, 5, bilhete[:-1] + ('A' if bilhete[-1] != 'A' else 'B')):
            with self.assertRaises(acesso.EntradaExpirada):
                acesso.entrar_segundo_fator(self.root, invalido, codigo_de(segredo, 1))
        with self.depois(minutes=acesso.ENTRADA_MINUTOS, seconds=1):
            with self.assertRaises(acesso.EntradaExpirada):
                acesso.entrar_segundo_fator(self.root, bilhete, codigo_de(segredo, momento=acesso.agora()))
        with self.assertRaises(acesso.PedeSegundoFator) as passo:
            acesso.entrar(self.root, 'rep.a', SENHA, ip='203.0.113.9')
        bilhete = passo.exception.bilhete
        for _ in range(acesso.ENTRADA_FALHAS - 1):
            with self.assertRaises(acesso.CodigoInvalido):
                acesso.entrar_segundo_fator(self.root, bilhete, '000000', ip='203.0.113.9')
        with self.assertRaises(acesso.FatorBloqueado):  # the fifth: the factor of the account is blocked too (R1)
            acesso.entrar_segundo_fator(self.root, bilhete, '000000', ip='203.0.113.9')
        with self.assertRaises(acesso.EntradaExpirada):
            acesso.entrar_segundo_fator(self.root, bilhete, codigo_de(segredo, 1), ip='203.0.113.9')  # dead at the fifth
        with self.assertRaises(acesso.Bloqueado):  # and the wrong codes counted on the sign-in counter of that address
            acesso.entrar(self.root, 'rep.a', SENHA, ip='203.0.113.9')
        self.assertEqual(acesso.sessoes_da_conta(self.root, self.rep_a), [])

    def test_codigos_novos_pedem_senha_e_codigo_e_os_antigos_param_de_valer(self):
        segredo, antigos = cadastrar(self.root, self.rep_a)
        with self.assertRaises(acesso.SenhaNecessaria):
            acesso.novos_codigos_do_fator(self.root, self.rep_a, None, antigos[0])
        with self.assertRaises(acesso.CodigoInvalido):
            acesso.novos_codigos_do_fator(self.root, self.rep_a, SENHA, '000000')
        novos = acesso.novos_codigos_do_fator(self.root, self.rep_a, SENHA, antigos[0])
        self.assertFalse(set(novos) & set(antigos))
        with self.assertRaises(acesso.CodigoInvalido):
            acesso.exigir_codigo(self.root, self.rep_a, antigos[1])
        self.assertIsNone(acesso.exigir_codigo(self.root, self.rep_a, novos[0]))
        self.assertIn('fator_codigos_gerados', self.tipos())
        with self.assertRaisesRegex(ValueError, 'não tem segundo fator'):
            acesso.remover_fator(self.root, self.dono_b, SENHA)

    def test_trocar_de_aparelho_pede_o_fator_atual_e_remover_pede_a_senha(self):
        segredo, reserva = cadastrar(self.root, self.rep_a)
        with self.assertRaises(acesso.CodigoNecessario):
            acesso.iniciar_fator(self.root, self.rep_a, SENHA)  # a session and the password are not enough for a new phone
        with self.assertRaises(acesso.CodigoInvalido):
            acesso.iniciar_fator(self.root, self.rep_a, SENHA, '000000')
        novo = acesso.iniciar_fator(self.root, self.rep_a, SENHA, reserva[0])['segredo']
        self.assertNotEqual(novo, segredo)
        self.assertIsNone(acesso.exigir_codigo(self.root, self.rep_a, reserva[1]))  # the old factor goes on until the new one is confirmed
        acesso.confirmar_fator(self.root, self.rep_a, codigo_de(novo))
        with self.depois(seconds=61):
            with self.assertRaises(acesso.CodigoInvalido):
                acesso.exigir_codigo(self.root, self.rep_a, codigo_de(segredo, momento=acesso.agora()))  # the old phone is out
            self.assertIsNone(acesso.exigir_codigo(self.root, self.rep_a, codigo_de(novo, momento=acesso.agora())))
        with self.assertRaises(acesso.SenhaNecessaria):
            acesso.remover_fator(self.root, self.rep_a, None)
        acesso.remover_fator(self.root, self.rep_a, SENHA)
        self.assertEqual(acesso.entrar(self.root, 'rep.a', SENHA)[2]['id'], self.rep_a)  # one step again
        self.assertEqual(self.linhas('SELECT 1 FROM fatores') + self.linhas('SELECT 1 FROM codigos_reserva'), [])
        self.assertEqual(self.linhas("SELECT tipo, conta, por FROM eventos WHERE tipo LIKE 'fator_removido%'"),
                         [{'tipo': 'fator_removido', 'conta': self.rep_a, 'por': self.rep_a}])  # her own doing

    def test_remover_a_conta_leva_o_fator_e_desativar_mata_o_bilhete(self):
        cadastrar(self.root, self.rep_a)
        with self.assertRaises(acesso.PedeSegundoFator) as passo:
            acesso.entrar(self.root, 'rep.a', SENHA)
        acesso.desativar(self.root, self.rep_a, por='cli')
        with self.assertRaises(acesso.EntradaExpirada):
            acesso.entrar_segundo_fator(self.root, passo.exception.bilhete, '000000')
        acesso.remover(self.root, self.rep_a, self.dono_a, self.a, SENHA)
        self.assertEqual(self.linhas('SELECT 1 FROM fatores') + self.linhas('SELECT 1 FROM codigos_reserva')
                         + self.linhas('SELECT 1 FROM entradas'), [])


class RedefinicaoComFatorTest(test_acesso.DuasRedacoes):
    def setUp(self):
        super().setUp()
        env = test_acesso.patch.dict(test_acesso.os.environ, {'VLADO_SEGREDOS': ''})
        env.start()
        self.addCleanup(env.stop)
        fator._CHAVES.clear()
        _, token, _ = acesso.convidar(self.root, self.a, self.dono_a, 'pessoa@exemplo.test', 'reporter', [])
        self.pessoa_a = acesso.aceitar_convite(self.root, token, 'Pessoa', SENHA)[2]['id']
        self.segredo, self.reserva = cadastrar(self.root, self.pessoa_a)

    def test_redefinir_por_email_pede_tambem_o_codigo(self):
        token, _ = acesso.pedir_redefinicao(self.root, 'pessoa@exemplo.test')
        # The page asks first without a code. That is not a wrong code (reservation S1 of the review): the answer
        # asks for it, nothing is counted and nothing goes to the audit log.
        with test_acesso.patch.object(acesso.registro_acesso, 'registrar') as registrar:
            for ausente in (None, '', '  '):
                with self.assertRaises(acesso.CodigoNecessario) as pedido:
                    acesso.redefinir_senha(self.root, token, NOVA, ausente)  # the mailbox alone is not enough
                self.assertEqual((pedido.exception.status, pedido.exception.codigo), (403, 'fator_necessario'))
        self.assertNotIn('fator_recusado', [c.args[0] for c in registrar.call_args_list])
        self.assertEqual(self.linhas("SELECT 1 FROM tentativas WHERE chave LIKE '#fator|%'"), [])
        with test_acesso.patch.object(acesso.registro_acesso, 'registrar') as registrar:
            with self.assertRaises(acesso.CodigoInvalido):
                acesso.redefinir_senha(self.root, token, NOVA, '000000')  # a code that came and is wrong: counted and recorded
        self.assertEqual([c.args[0] for c in registrar.call_args_list].count('fator_recusado'), 1)
        self.assertEqual(self.linhas("SELECT falhas FROM tentativas WHERE chave LIKE '#fator|%'"), [{'falhas': 1}])
        with self.assertRaises(acesso.PedeSegundoFator):
            acesso.entrar(self.root, 'pessoa@exemplo.test', SENHA)  # the password is still the old one
        self.assertEqual(acesso.redefinir_senha(self.root, token, NOVA, self.reserva[0])['id'], self.pessoa_a)
        with self.assertRaises(acesso.PedeSegundoFator):
            acesso.entrar(self.root, 'pessoa@exemplo.test', NOVA)  # the factor stays
        with self.assertRaises(acesso.CredenciaisInvalidas):
            acesso.entrar(self.root, 'pessoa@exemplo.test', SENHA)

    def test_conta_sem_fator_redefine_sem_codigo_e_nada_e_registrado_como_recusa(self):
        _, token, _ = acesso.convidar(self.root, self.a, self.dono_a, 'semfator@exemplo.test', 'leitor', [])
        acesso.aceitar_convite(self.root, token, 'Sem Fator', SENHA)
        token, _ = acesso.pedir_redefinicao(self.root, 'semfator@exemplo.test')
        with test_acesso.patch.object(acesso.registro_acesso, 'registrar') as registrar:
            self.assertEqual(acesso.redefinir_senha(self.root, token, NOVA)['email'], 'semfator@exemplo.test')
        self.assertNotIn('fator_recusado', [c.args[0] for c in registrar.call_args_list])
        self.assertEqual(self.linhas("SELECT 1 FROM tentativas WHERE chave LIKE '#fator|%'"), [])

    def test_sem_a_chave_das_sementes_o_codigo_de_reserva_ainda_entra_e_nenhuma_chave_nasce_em_silencio(self):
        # Reservation R2 of the review: a restore of the common backup brings the store without `segredos/`.
        arquivo = fator.arquivo_da_chave(self.root)
        self.assertIsNone(acesso.conferir_chave_do_fator(self.root))  # the key is there and opens the seeds
        arquivo.unlink()
        fator._CHAVES.clear()  # the server started again after the restore
        aviso = acesso.conferir_chave_do_fator(self.root)
        self.assertIn('segredos/contas.chave', aviso)
        self.assertIn('1 conta(s)', aviso)
        with test_acesso.patch.object(acesso.registro_acesso, 'registrar') as registrar:
            with self.assertRaises(acesso.FatorIndisponivel) as recusa:
                acesso.exigir_codigo(self.root, self.pessoa_a, codigo_de(self.segredo))  # the right code of the app
        self.assertEqual((recusa.exception.status, recusa.exception.codigo), (503, 'fator_indisponivel'))
        self.assertEqual([(c.args[0], c.kwargs.get('motivo')) for c in registrar.call_args_list],
                         [('fator_indisponivel', 'chave_ausente')])  # told to the operator, and not counted as a wrong code
        self.assertEqual(self.linhas("SELECT 1 FROM tentativas WHERE chave LIKE '#fator|%'"), [])
        with self.assertRaises(acesso.PedeSegundoFator) as passo:
            acesso.entrar(self.root, 'pessoa@exemplo.test', SENHA)
        with self.assertRaises(acesso.FatorIndisponivel):
            acesso.entrar_segundo_fator(self.root, passo.exception.bilhete, codigo_de(self.segredo, 1))
        # The reserve code needs neither the seed nor the key: the person still gets in, with the same ticket.
        self.assertEqual(acesso.entrar_segundo_fator(self.root, passo.exception.bilhete, self.reserva[0])[2]['id'], self.pessoa_a)
        acesso.exigir_codigo(self.root, self.pessoa_a, self.reserva[1])
        # Nobody enrols meanwhile, and no other key is made: it would leave the stored seeds unreadable for good.
        with self.assertRaises(acesso.FatorIndisponivel):
            acesso.iniciar_fator(self.root, self.dono_a, SENHA)
        self.assertFalse(arquivo.exists())
        # With another key in the place of the right one the seeds do not open either, and the warning says so.
        fator.cifrar(self.root, b'x' * 20, self.dono_a, criar_chave=True)
        self.assertIn('não é a que cifrou', acesso.conferir_chave_do_fator(self.root))
        with self.assertRaises(acesso.FatorIndisponivel):
            acesso.exigir_codigo(self.root, self.pessoa_a, codigo_de(self.segredo, 2))

    def test_sem_nenhum_fator_cadastrado_a_chave_que_falta_e_criada_no_primeiro_cadastro(self):
        acesso.recuperar(self.root, self.pessoa_a, por='cli')  # the operator takes the only factor away
        fator.arquivo_da_chave(self.root).unlink()
        fator._CHAVES.clear()
        self.assertIsNone(acesso.conferir_chave_do_fator(self.root))  # nothing would be lost: nothing to warn about
        segredo, _ = cadastrar(self.root, self.dono_a)
        self.assertTrue(fator.chave_presente(self.root))
        acesso.exigir_codigo(self.root, self.dono_a, codigo_de(segredo, 1))

    def test_recuperacao_pelo_operador_no_terminal_tambem_tira_o_fator(self):
        _, token = acesso.recuperar(self.root, self.pessoa_a, por='cli')
        self.assertEqual(self.linhas('SELECT 1 FROM fatores') + self.linhas('SELECT 1 FROM codigos_reserva'), [])
        acesso.ativar(self.root, token, NOVA)
        self.assertEqual(acesso.entrar(self.root, 'pessoa@exemplo.test', NOVA)[2]['id'], self.pessoa_a)  # one step
        # An event of its own, by the operator: not the `fator_removido` of who takes away the own factor.
        self.assertEqual(self.linhas("SELECT tipo, conta, por FROM eventos WHERE tipo LIKE 'fator_removido%'"),
                         [{'tipo': 'fator_removido_na_recuperacao', 'conta': self.pessoa_a, 'por': 'cli'}])

    def test_recuperacao_pedida_pelo_dono_tira_o_fator_que_a_pessoa_perdeu(self):
        feito = acesso.pedir_recuperacao(self.root, self.a, self.dono_a, self.pessoa_a, SENHA, com_envio=True)
        self.assertEqual(acesso.redefinir_senha(self.root, feito['token'], NOVA)['id'], self.pessoa_a)  # no code asked
        self.assertEqual(acesso.entrar(self.root, 'pessoa@exemplo.test', NOVA)[2]['id'], self.pessoa_a)  # one step: she enrols again
        self.assertFalse(acesso.ver_conta(self.root, self.pessoa_a)['segundo_fator']['ativo'])
        # The screen tells it apart from the person removing the own factor: the type is another one.
        self.assertEqual(self.linhas("SELECT tipo, conta, por FROM eventos WHERE tipo LIKE 'fator_removido%'"),
                         [{'tipo': 'fator_removido_na_recuperacao', 'conta': self.pessoa_a, 'por': self.pessoa_a}])


class ServidorTest(cenario.DuasRedacoes):
    numero = 0

    def setUp(self):
        acesso.limpar_limites()
        correio.limpar_caixa()
        type(self).numero += 1
        self.email = f'fator{self.numero}@exemplo.test'
        _, token, _ = acesso.convidar(self.root, self.a, self.ids['dono'], self.email, 'reporter', ['alpha'])
        self.conta = acesso.aceitar_convite(self.root, token, 'Pessoa do Fator', SENHA)[2]['id']
        status, corpo, cabecalhos, _ = self.publico('entrar', {'login': self.email, 'senha': SENHA})
        self.sessao = (cabecalhos['Set-Cookie'].split(';')[0], corpo['csrf'])

    def publico(self, operacao, dados, cookie=None):
        status, cabecalhos, corpo = self.pedir('POST', '/api/' + operacao, json.dumps(dados), {
            'Content-Type': 'application/json', 'Origin': cenario.ORIGEM, **({'Cookie': cookie} if cookie else {})})
        return status, json.loads(corpo or b'{}'), cabecalhos, corpo

    def cadastrar(self):
        status, inicio, bruto = self.post(self.sessao, 'conta-fator-iniciar', {'senha': SENHA})
        self.assertEqual(status, 200, bruto[:200])
        status, feito, bruto = self.post(self.sessao, 'conta-fator-confirmar', {'codigo': codigo_de(inicio['segredo'])})
        self.assertEqual((status, feito['estado'], len(feito['codigos_de_reserva'])), (200, 'fator_ativado', 10), bruto[:200])
        return inicio['segredo'], feito['codigos_de_reserva']

    def test_cadastrar_pelo_servidor_e_entrar_em_dois_passos(self):
        sem_senha = self.post(self.sessao, 'conta-fator-iniciar', {})
        self.assertEqual((sem_senha[0], sem_senha[1].get('codigo')), (403, 'senha_necessaria'))
        self.assertEqual(self.post(self.sessao, 'conta-fator-iniciar', {'senha': SENHA, 'conta': self.ids['dono']})[0], 400)
        status, corpo, cabecalhos, _ = self.publico('entrar', {'login': self.email, 'senha': SENHA})
        outra = (cabecalhos['Set-Cookie'].split(';')[0], corpo['csrf'])
        with correio.usar('simulado'):
            segredo, reserva = self.cadastrar()
            correio.aguardar()
        self.assertEqual([(m['tipo'], m['para']) for m in correio.caixa()], [('fator_alterado', self.email)])
        self.assertEqual(self.post(self.sessao, 'codex-status', {})[0], 200)  # the session that enrolled goes on
        self.assertEqual(self.post(outra, 'codex-status', {})[0], 401)  # the other one of the account ended (R5)
        perfil = self.post(self.sessao, 'conta-ver', {})
        self.assertEqual((perfil[1]['segundo_fator']['ativo'], perfil[1]['segundo_fator']['codigos_restantes']), (True, 10))
        for segredo_ou_codigo in (segredo, *reserva):
            self.assertNotIn(segredo_ou_codigo, perfil[2].decode('utf-8'))  # shown once, in the answer that made them
        # The password alone no longer opens a session: only the five-minute ticket, in a cookie of its own.
        status, corpo, cabecalhos, bruto = self.publico('entrar', {'login': self.email, 'senha': SENHA})
        self.assertEqual((status, corpo), (200, {'estado': 'segundo_fator'}), bruto[:200])
        cookie = cabecalhos['Set-Cookie']
        self.assertTrue(cookie.startswith('vlado_passo2='))
        self.assertIn('HttpOnly', cookie)
        self.assertIn('Max-Age=300', cookie)
        bilhete = cookie.split(';')[0]
        self.assertEqual(self.post((bilhete.replace('vlado_passo2', 'vlado_sessao'), 'x'), 'codex-status', {})[0], 401)  # not a session
        for ausente in ({}, {'codigo': ''}) * 4:  # no code: asked for, as often as it takes, and the ticket is not spent
            pedido = self.publico('entrar-segundo-fator', ausente, bilhete)
            self.assertEqual((pedido[0], pedido[1]['codigo']), (403, 'fator_necessario'))
        errado = self.publico('entrar-segundo-fator', {'codigo': '000000'}, bilhete)
        self.assertEqual((errado[0], errado[1]['codigo']), (403, 'codigo_invalido'))
        sem_bilhete = self.publico('entrar-segundo-fator', {'codigo': reserva[0]})
        self.assertEqual((sem_bilhete[0], sem_bilhete[1]['codigo']), (401, 'entrada_expirada'))
        status, corpo, cabecalhos, bruto = self.publico('entrar-segundo-fator', {'codigo': reserva[0]}, bilhete)
        self.assertEqual((status, corpo['conta']['id']), (200, self.conta), bruto[:200])
        nova = (cabecalhos['Set-Cookie'].split(';')[0], corpo['csrf'])
        self.assertTrue(nova[0].startswith('vlado_sessao='))
        self.assertEqual(self.post(nova, 'codex-status', {})[0], 200)
        usado = self.publico('entrar-segundo-fator', {'codigo': reserva[1]}, bilhete)
        self.assertEqual((usado[0], usado[1]['codigo']), (401, 'entrada_expirada'))  # the ticket works once
        self.assertEqual(self.post('dono', 'codex-status', {})[0], 200)

    def test_remover_o_fator_e_negado_a_dono_e_editor_e_pede_a_senha_dos_demais(self):
        for papel in ('dono', 'editor'):
            negado = self.post(papel, 'conta-fator-remover', {'senha': SENHA})
            self.assertEqual((negado[0], negado[1].get('codigo')), (403, 'operacao_proibida'), papel)
        self.cadastrar()
        sem_senha = self.post(self.sessao, 'conta-fator-remover', {})
        self.assertEqual((sem_senha[0], sem_senha[1].get('codigo')), (403, 'senha_necessaria'))
        self.assertEqual(self.post(self.sessao, 'conta-fator-remover', {'senha': SENHA})[1], {'estado': 'fator_removido'})
        self.assertEqual(self.publico('entrar', {'login': self.email, 'senha': SENHA})[1]['conta']['id'], self.conta)

    def test_codigos_novos_e_redefinicao_de_senha_com_o_codigo(self):
        segredo, reserva = self.cadastrar()
        sem_codigo = self.post(self.sessao, 'conta-fator-codigos', {'senha': SENHA})
        self.assertEqual((sem_codigo[0], sem_codigo[1].get('codigo')), (403, 'fator_necessario'))
        status, corpo, _ = self.post(self.sessao, 'conta-fator-codigos', {'senha': SENHA, 'codigo': reserva[0]})
        self.assertEqual((status, corpo['estado'], len(corpo['codigos_de_reserva'])), (200, 'codigos_gerados', 10))
        novos = corpo['codigos_de_reserva']
        with correio.usar('simulado'):
            self.publico('senha-esqueci', {'email': self.email})
            correio.aguardar()
        token = [m for m in correio.caixa() if m['tipo'] == 'redefinicao'][0]['link'].rsplit('/', 1)[1]
        pedido = self.publico('senha-redefinir', {'token': token, 'senha': NOVA})  # the page learns the account has a factor
        self.assertEqual((pedido[0], pedido[1]['codigo']), (403, 'fator_necessario'))
        for codigo in ({'codigo': reserva[1]}, {'codigo': '000000'}):  # an old reserve code, a wrong one
            recusa = self.publico('senha-redefinir', {'token': token, 'senha': NOVA, **codigo})
            self.assertEqual((recusa[0], recusa[1]['codigo']), (403, 'codigo_invalido'), codigo)
        self.assertEqual(self.publico('senha-redefinir', {'token': token, 'senha': NOVA, 'codigo': novos[0]})[0], 200)
        self.assertEqual(self.publico('entrar', {'login': self.email, 'senha': NOVA})[1], {'estado': 'segundo_fator'})


class ObrigacaoTest(cenario.DuasRedacoes):
    """In the hosted mode the second factor is mandatory for dono and editor (contract, 4.2 and 8.2; decision 3)."""
    numero = 0

    def setUp(self):
        acesso.limpar_limites()

    def chegar(self, papel):
        """A person accepts an invitation with this role: (session, account id, e-mail)."""
        type(self).numero += 1
        email = f'obrigada{self.numero}@exemplo.test'
        _, token, _ = acesso.convidar(self.root, self.a, self.ids['dono'], email, papel, [] if papel == 'dono' else ['alpha'],
                                      senha=SENHA)
        status, cabecalhos, corpo = self.pedir('POST', '/api/convite-aceitar', json.dumps(
            {'token': token, 'nome': 'Pessoa Obrigada', 'senha': SENHA}), {'Content-Type': 'application/json', 'Origin': cenario.ORIGEM})
        self.assertEqual(status, 200, corpo[:200])
        aceite = json.loads(corpo)
        return (cabecalhos['Set-Cookie'].split(';')[0], aceite['csrf']), aceite['conta']['id'], email

    def pagina(self, sessao, caminho='/'):
        status, cabecalhos, corpo = self.pedir('GET', caminho, cabecalhos={'Cookie': sessao[0]} if sessao else None)
        return status, cabecalhos.get('Location'), corpo

    def test_dono_e_editor_sem_o_fator_so_alcancam_o_cadastro_dele(self):
        for papel in ('dono', 'editor'):
            with self.subTest(papel=papel):
                sessao, conta, email = self.chegar(papel)
                status, corpo, _ = self.get(sessao, '/api/sessao')
                self.assertEqual((status, corpo['pendencias'], corpo['conta']['papel']), (200, ['segundo_fator'], papel))
                self.assertEqual(self.pagina(sessao)[:2], (303, '/conta/segundo-fator'))  # the Mesa does not open
                antes = self.retrato()
                for operacao, dados in (('codex-status', {}), ('equipe-listar', {}), ('conta-sessoes', {}), ('gerenciar-listar', {}),
                                        ('conta-senha-trocar', {'senha_atual': SENHA, 'senha_nova': NOVA}),
                                        ('conta-fator-codigos', {'senha': SENHA}), ('conta-fator-remover', {'senha': SENHA}),
                                        ('codex-listar', {'caso': 'alpha'}), ('conta-atualizar', {'nome': 'Outro Nome'})):
                    status, corpo, _ = self.post(sessao, operacao, dados)
                    self.assertEqual((status, corpo.get('codigo'), corpo.get('pendencias')),
                                     (403, 'pendencia_de_conta', ['segundo_fator']), operacao)
                for caminho in ('/api/catalogo', '/api/cota', '/api/fila', '/api/integracao'):
                    status, corpo, _ = self.get(sessao, caminho)
                    self.assertEqual((status, corpo.get('codigo')), (403, 'pendencia_de_conta'), caminho)
                self.assertEqual(antes, self.retrato())
                # What resolves it: the own profile and the two steps of the enrolment. And leaving.
                perfil = self.post(sessao, 'conta-ver', {})
                self.assertEqual((perfil[0], perfil[1]['segundo_fator']['ativo']), (200, False))
                descartavel = cenario.fator_de_teste.entrar(self.pedir, self.root, conta, email, SENHA, cenario.ORIGEM)
                self.assertEqual(self.post(descartavel, 'sessao-sair', {})[0], 200)
                status, inicio, bruto = self.post(sessao, 'conta-fator-iniciar', {'senha': SENHA})
                self.assertEqual(status, 200, bruto[:200])
                status, feito, bruto = self.post(sessao, 'conta-fator-confirmar', {'codigo': codigo_de(inicio['segredo'])})
                self.assertEqual((status, feito['estado'], len(feito['codigos_de_reserva'])), (200, 'fator_ativado', 10), bruto[:200])
                self.assertEqual(self.get(sessao, '/api/sessao')[1]['pendencias'], [])
                self.assertEqual(self.pagina(sessao)[0], 200)
                self.assertEqual(self.post(sessao, 'codex-status', {})[0], 200)
                # Nor does who must have it take it away afterwards.
                negado = self.post(sessao, 'conta-fator-remover', {'senha': SENHA})
                self.assertEqual((negado[0], negado[1].get('codigo')), (403, 'operacao_proibida'))
                self.assertTrue(self.post(sessao, 'conta-ver', {})[1]['segundo_fator']['ativo'])

    def test_a_pagina_da_pendencia_e_estatica_e_nao_leva_dado_de_conta(self):
        sessao, conta, email = self.chegar('editor')
        for quem in (sessao, None):  # with the session and without one: the same page, which reads the session by itself
            status, _, corpo = self.pagina(quem, '/conta/segundo-fator')
            self.assertEqual(status, 200)
            texto = corpo.decode('utf-8')
            for dado in (conta, email, 'Pessoa Obrigada', 'Redação Alfa'):
                self.assertNotIn(dado, texto)
        self.assertEqual(corpo, self.pagina(None, '/entrar')[2])

    def test_reporter_e_leitor_nao_tem_a_obrigacao_e_quem_e_promovido_passa_a_ter(self):
        for papel in ('reporter', 'leitor'):
            sessao, conta, _ = self.chegar(papel)
            self.assertEqual(self.get(sessao, '/api/sessao')[1]['pendencias'], [], papel)
            self.assertEqual(self.post(sessao, 'codex-status', {})[0], 200, papel)
        sessao, conta, _ = self.chegar('reporter')
        promovida = self.post('dono', 'equipe-papel', {'conta': conta, 'papel': 'editor', 'senha': SENHA})
        self.assertEqual(promovida[0], 200, promovida[2][:200])
        self.assertEqual(self.get(sessao, '/api/sessao')[1]['pendencias'], ['segundo_fator'])  # at her next request
        self.assertEqual(self.post(sessao, 'codex-status', {})[1].get('codigo'), 'pendencia_de_conta')
        self.assertEqual(self.post('dono', 'equipe-papel', {'conta': conta, 'papel': 'leitor', 'senha': SENHA})[0], 200)
        self.assertEqual(self.post(sessao, 'codex-status', {})[0], 200)


if __name__ == '__main__':
    unittest.main()
