"""Teto de tentativas por identificador, modo protegido e aparelho conhecido (contrato de contas, seção 8.2 e a
segunda ressalva de P28), no armazenamento.

Todo contador é do identificador digitado, exista a conta ou não. Dez falhas de um identificador em uma hora, de
quaisquer endereços, o põem em modo protegido por uma hora: toda tentativa recebe a mesma recusa, sem conta de
senha para ninguém, salvo a que traz a marca de um aparelho que aquela conta já usou. A marca atravessa o modo
protegido, mas não desliga a contagem. Todo identificador, com conta ou sem, conta numa tabela de tamanho fixo. As regras no
armazenamento; o cookie da marca, pelo servidor (``ServidorTest``). Sem modelo e sem rede.
"""
import http.client
import json
from pathlib import Path
import re
import secrets
import sys
import unittest
from unittest.mock import patch

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


def marca():
    return secrets.token_urlsafe(32)


class Base(test_acesso.DuasRedacoes):
    endereco = 0

    def ip(self):
        """A fresh address each time: the per-address block (five from one address) stays out of the way."""
        type(self).endereco += 1
        return f'198.51.{100 + self.endereco // 250}.{1 + self.endereco % 250}'

    def tentar(self, login, senha=ERRADA, **mais):
        """The name of what a sign-in raised, or 'entrou'."""
        try:
            acesso.entrar(self.root, login, senha, ip=mais.pop('ip', None) or self.ip(), **mais)
            return 'entrou'
        except (ValueError, acesso.PedeSegundoFator) as exc:
            return type(exc).__name__

    def falhar(self, login, vezes, **mais):
        return [self.tentar(login, **mais) for _ in range(vezes)]


class ModoProtegidoTest(Base):
    def test_dez_falhas_de_varios_enderecos_dao_a_mesma_sequencia_com_conta_e_sem_conta(self):
        sequencias = {login: self.falhar(login, acesso.PROTECAO_FALHAS + 2) for login in ('rep.a', 'ninguem.aqui')}
        self.assertEqual(sequencias['rep.a'], sequencias['ninguem.aqui'])
        self.assertEqual(sequencias['rep.a'], ['CredenciaisInvalidas'] * acesso.PROTECAO_FALHAS + ['Bloqueado'] * 2)
        with patch.object(acesso, '_HASHER') as hasher:  # protected: no hash is computed, for an account or for none
            self.assertEqual([self.tentar('rep.a', SENHA), self.tentar('ninguem.aqui', SENHA)], ['Bloqueado', 'Bloqueado'])
        hasher.verify.assert_not_called()
        self.assertEqual(self.tentar('dona.a', SENHA), 'entrou')  # another identifier is not touched
        chaves = {l['chave'] for l in self.linhas("SELECT chave FROM tentativas WHERE bloqueado_ate IS NOT NULL")}
        # The two of them in the same fixed table, and the identifier typed is not kept in it.
        self.assertTrue(chaves and all(re.fullmatch(r'#balde\|\d+', c) for c in chaves), chaves)
        for texto in ('ninguem.aqui', 'rep.a', self.rep_a):
            self.assertNotIn(texto, ' '.join(chaves))
        self.assertIn('login_protegido', self.tipos())

    def test_tentativa_durante_o_modo_protegido_nao_conta_nem_estende_e_a_protecao_acaba_em_uma_hora(self):
        self.falhar('rep.a', acesso.PROTECAO_FALHAS)
        ate, = self.linhas("SELECT bloqueado_ate FROM tentativas WHERE chave LIKE '#balde|%'")
        with self.depois(minutes=30):
            self.assertEqual(self.falhar('rep.a', 6), ['Bloqueado'] * 6)
        self.assertEqual(self.linhas("SELECT bloqueado_ate FROM tentativas WHERE chave LIKE '#balde|%'"), [ate])
        with self.depois(minutes=acesso.PROTECAO_MINUTOS, seconds=1):
            self.assertEqual(self.tentar('rep.a'), 'CredenciaisInvalidas')  # an ordinary refusal again
            self.assertEqual(self.tentar('rep.a', SENHA), 'entrou')

    def test_a_janela_e_de_uma_hora_e_a_entrada_do_dono_nao_da_folego_novo_a_quem_ataca(self):
        self.assertEqual(self.falhar('rep.a', acesso.PROTECAO_FALHAS - 1), ['CredenciaisInvalidas'] * (acesso.PROTECAO_FALHAS - 1))
        self.assertEqual(self.tentar('rep.a', SENHA), 'entrou')  # the owner signs in: the counter is not cleared
        self.assertEqual(self.falhar('rep.a', 2), ['CredenciaisInvalidas', 'Bloqueado'])
        self.assertEqual(self.falhar('rep.b', acesso.PROTECAO_FALHAS - 1), ['CredenciaisInvalidas'] * (acesso.PROTECAO_FALHAS - 1))
        with self.depois(minutes=acesso.PROTECAO_JANELA_MINUTOS, seconds=1):  # nine failures, and the window ran out
            self.assertEqual(self.falhar('rep.b', 2), ['CredenciaisInvalidas'] * 2)
            self.assertEqual(self.tentar('rep.b', SENHA), 'entrou')

    def test_identificador_fora_do_formato_nao_cria_contador(self):
        for texto in ('X', '', 'a b c', 'ana@', '@exemplo.test', 'ana@exemplo', '#id|rep.a', 'rep.a|198.51.100.7', 'x' * 300):
            self.assertEqual(self.falhar(texto, 3), ['CredenciaisInvalidas'] * 3, texto)
        self.assertEqual(self.linhas('SELECT chave FROM tentativas'), [])
        self.assertEqual(self.tentar(None), 'CredenciaisInvalidas')

    def test_identificador_com_conta_leva_o_vizinho_de_balde_igual_a_um_sem_conta(self):
        # B1 of the review: with an exact counter for the identifiers that have an account, their protected mode
        # never spread to a neighbour of bucket, and the ones without an account did: enough requests told that one
        # person has an account. Every identifier counts in the bucket of its HMAC.
        vistos = {}
        for atacado, horas in (('rep.a', 0), ('ninguem.aqui', 3)):  # the second one after the first protection ended
            with patch.object(acesso, 'BALDES', 1), self.depois(hours=horas):  # one bucket: everybody is a neighbour
                sequencia = self.falhar(atacado, acesso.PROTECAO_FALHAS)
                vizinhos = [self.tentar('rep.b', SENHA), self.tentar('outro.ninguem'), self.tentar('rep.b@exemplo.test', SENHA)]
                vistos[atacado] = (sequencia, vizinhos)
        self.assertEqual(vistos['rep.a'], vistos['ninguem.aqui'])
        self.assertEqual(vistos['rep.a'], (['CredenciaisInvalidas'] * acesso.PROTECAO_FALHAS, ['Bloqueado'] * 3))
        chaves = [l['chave'] for l in self.linhas("SELECT chave FROM tentativas WHERE chave LIKE '#%'")]
        self.assertEqual(chaves, ['#balde|0'])  # one counter for all of them, and none of an account

    def test_todo_identificador_conta_numa_tabela_de_tamanho_fixo(self):
        navegador = marca()
        self.assertEqual(self.tentar('rep.a', SENHA, marca=navegador), 'entrou')
        with patch.object(acesso, 'BALDES', 3):
            respostas = [self.tentar(f'ninguem{numero}@exemplo.test') for numero in range(120)]
            self.assertEqual(set(respostas), {'CredenciaisInvalidas', 'Bloqueado'})
            self.assertEqual(respostas[:acesso.PROTECAO_FALHAS], ['CredenciaisInvalidas'] * acesso.PROTECAO_FALHAS)  # no counter can have ten yet
            self.assertLessEqual(respostas.count('CredenciaisInvalidas'), 3 * acesso.PROTECAO_FALHAS)  # ten for each counter, no more
            baldes = self.linhas("SELECT chave, bloqueado_ate FROM tentativas WHERE chave LIKE '#balde|%'")
            self.assertEqual({b['chave'] for b in baldes}, {'#balde|0', '#balde|1', '#balde|2'})  # 120 identifiers, three counters
            self.assertTrue(all(b['bloqueado_ate'] for b in baldes))
            # A collision makes an identifier inherit the protected mode of another, with an account or without.
            self.assertEqual(self.tentar('nunca.tentado@exemplo.test'), 'Bloqueado')
            self.assertEqual(self.tentar('rep.a'), 'Bloqueado')
            self.assertEqual(self.tentar('rep.a', SENHA), 'Bloqueado')
            # The way through is the same as ever: a device the account already used.
            self.assertEqual(self.tentar('rep.a', SENHA, marca=navegador), 'entrou')
        self.assertEqual(self.linhas("SELECT 1 FROM tentativas WHERE chave LIKE '#id|%'"), [])
        self.assertNotIn('ninguem', ' '.join(l['chave'] for l in self.linhas('SELECT chave FROM tentativas WHERE chave LIKE ?', '#%')))

    def test_nenhum_contador_sai_antes_do_prazo(self):
        agora = acesso.agora()
        ha = lambda minutos: acesso._iso(agora - test_acesso.timedelta(minutes=minutos))  # noqa: E731
        futuro = acesso._iso(agora + test_acesso.timedelta(minutes=30))
        acesso.listar(self.root)
        # Buckets above BALDES: counters the sign-in of this test cannot land on.
        for chave, em, ate in (('#balde|900005', ha(30), None), ('#balde|900006', ha(61), None), ('#balde|900007', ha(59), None),
                               ('#balde|900008', ha(200), futuro), ('ana|198.51.100.7', ha(16), None), ('bia|198.51.100.7', ha(5), None),
                               ('#senha|' + 'a' * 16, ha(16), None), ('#marca|x|y', ha(3), None)):
            self.gravar('INSERT INTO tentativas (chave, falhas, bloqueado_ate, em) VALUES (?, 1, ?, ?)', chave, ate, em)
        with patch.object(acesso, 'MAX_TENTATIVAS_GUARDADAS', 1):
            self.assertEqual(self.tentar('rep.a'), 'CredenciaisInvalidas')  # any failure prunes
        chaves = {l['chave'] for l in self.linhas('SELECT chave FROM tentativas')}
        self.assertLessEqual({'#balde|900005', '#balde|900007', '#balde|900008', '#marca|x|y'}, chaves)
        self.assertEqual(len([c for c in chaves if c.startswith('#balde|')]), 4)  # those three and the one of this failure
        self.assertFalse({'#balde|900006', 'ana|198.51.100.7', '#senha|' + 'a' * 16} & chaves)
        # The ceiling of the table is only for the per-address counters, which an attacker can multiply.
        self.assertEqual(len([c for c in chaves if not c.startswith('#')]), 1)


class AparelhoConhecidoTest(Base):
    def test_a_marca_de_um_aparelho_da_conta_atravessa_o_modo_protegido_e_nenhuma_outra(self):
        minha, alheia = marca(), marca()
        self.assertEqual(self.tentar('rep.a', SENHA, marca=minha), 'entrou')
        self.assertEqual(self.tentar('dona.a', SENHA, marca=alheia), 'entrou')  # known, but of another account
        self.falhar('rep.a', acesso.PROTECAO_FALHAS)
        self.assertEqual([self.tentar('rep.a', SENHA), self.tentar('rep.a', SENHA, marca=alheia), self.tentar('rep.a', SENHA, marca=marca()),
                          self.tentar('rep.a', SENHA, marca='curta')], ['Bloqueado'] * 4)
        self.assertEqual(self.tentar('rep.a', SENHA, marca=minha), 'entrou')
        bruto = self.bruto()
        self.assertNotIn(minha, bruto)  # only the hash of the mark is kept
        self.assertEqual(self.tentar('ninguem.aqui', SENHA, marca=minha), 'CredenciaisInvalidas')  # a mark is of an account

    def test_a_marca_nao_desliga_a_contagem_cinco_erros_com_ela_a_bloqueiam(self):
        minha = marca()
        self.tentar('rep.a', SENHA, marca=minha)
        self.falhar('rep.a', acesso.PROTECAO_FALHAS)  # protected
        self.assertEqual(self.falhar('rep.a', acesso.FALHAS_BLOQUEIO, marca=minha), ['CredenciaisInvalidas'] * acesso.FALHAS_BLOQUEIO)
        self.assertEqual(self.tentar('rep.a', SENHA, marca=minha), 'Bloqueado')  # the copied cookie bought five guesses, not more
        with self.depois(minutes=acesso.BLOQUEIO_MINUTOS, seconds=1):
            self.assertEqual(self.tentar('rep.a', SENHA, marca=minha), 'entrou')  # the mark is good again; the identifier is still protected
            self.assertEqual(self.tentar('rep.a', SENHA), 'Bloqueado')

    def test_so_a_entrada_que_deu_certo_torna_o_aparelho_conhecido_e_o_segundo_aparelho_e_avisado(self):
        primeira, segunda = marca(), marca()
        self.assertEqual(self.tentar('rep.a', ERRADA, marca=primeira), 'CredenciaisInvalidas')
        self.assertEqual(self.linhas('SELECT 1 FROM aparelhos'), [])  # a refusal never marks anything
        entrou = acesso.entrar(self.root, 'rep.a', SENHA, ip=self.ip(), marca=primeira)
        self.assertEqual(entrou[2]['aparelho_novo'], False)  # the first device of the account: nothing to tell
        self.assertEqual(acesso.entrar(self.root, 'rep.a', SENHA, ip=self.ip(), marca=primeira)[2]['aparelho_novo'], False)
        self.assertEqual(acesso.entrar(self.root, 'rep.a', SENHA, ip=self.ip(), marca=segunda)[2]['aparelho_novo'], True)
        self.assertEqual(acesso.entrar(self.root, 'rep.a', SENHA, ip=self.ip())[2]['aparelho_novo'], False)  # no mark, no tracking
        self.assertEqual(self.tipos().count('aparelho_novo'), 1)
        self.assertEqual(len(self.linhas('SELECT 1 FROM aparelhos WHERE conta = ?', self.rep_a)), 2)

    def test_cada_conta_guarda_vinte_aparelhos_e_descarta_o_usado_ha_mais_tempo(self):
        marcas = [marca() for _ in range(acesso.APARELHOS_MAX + 2)]
        for numero, valor in enumerate(marcas):
            with self.depois(minutes=numero):
                self.assertEqual(self.tentar('rep.a', SENHA, marca=valor), 'entrou')
        with self.depois(minutes=100):
            self.assertEqual(self.tentar('rep.a', SENHA, marca=marcas[2]), 'entrou')  # used again: it is the newest now
        guardadas = {l['resumo'] for l in self.linhas('SELECT resumo FROM aparelhos WHERE conta = ?', self.rep_a)}
        self.assertEqual(len(guardadas), acesso.APARELHOS_MAX)
        self.assertFalse({acesso._hash(marcas[0]), acesso._hash(marcas[1])} & guardadas)  # the two least recently used
        self.assertIn(acesso._hash(marcas[2]), guardadas)

    def test_senha_nova_esquece_os_outros_aparelhos_e_fica_so_o_navegador_que_fez(self):
        # If the account had been broken into, the intruder's browser became a known device when it signed in.
        _, token, _ = acesso.convidar(self.root, self.a, self.dono_a, 'pessoa@exemplo.test', 'leitor', [])
        do_convite, do_invasor, da_troca, do_link = marca(), marca(), marca(), marca()
        conta = acesso.aceitar_convite(self.root, token, 'Pessoa', SENHA, marca=do_convite)[2]['id']
        conhecidas = lambda: {l['resumo'] for l in self.linhas('SELECT resumo FROM aparelhos WHERE conta = ?', conta)}  # noqa: E731
        self.assertEqual(conhecidas(), {acesso._hash(do_convite)})  # who accepted the invitation is the first known device
        self.assertEqual(self.tentar('pessoa@exemplo.test', SENHA, marca=do_invasor), 'entrou')
        acesso.trocar_senha(self.root, conta, SENHA, NOVA, marca=da_troca)
        self.assertEqual(conhecidas(), {acesso._hash(da_troca)})
        token, _ = acesso.pedir_redefinicao(self.root, 'pessoa@exemplo.test')
        acesso.redefinir_senha(self.root, token, SENHA, marca=do_link)
        self.assertEqual(conhecidas(), {acesso._hash(do_link)})
        acesso.trocar_senha(self.root, conta, SENHA, NOVA)  # no mark at all: nothing is left
        self.assertEqual(conhecidas(), set())
        _, ativacao = acesso.recuperar(self.root, self.rep_a, por='cli')
        acesso.ativar(self.root, ativacao, NOVA, marca=do_link)
        self.assertEqual({l['resumo'] for l in self.linhas('SELECT resumo FROM aparelhos WHERE conta = ?', self.rep_a)}, {acesso._hash(do_link)})

    def test_o_link_que_so_o_dono_da_caixa_recebe_e_a_saida_de_quem_foi_trancado(self):
        # Whoever knows an e-mail can keep its account in protected mode for ever. The way out is something only
        # the owner of the mailbox has: the link of the reset marks that browser as a known device.
        _, token, _ = acesso.convidar(self.root, self.a, self.dono_a, 'trancada@exemplo.test', 'leitor', [])
        acesso.aceitar_convite(self.root, token, 'Trancada', SENHA)  # accepted on another browser, long ago
        self.falhar('trancada@exemplo.test', acesso.PROTECAO_FALHAS)
        self.assertEqual(self.tentar('trancada@exemplo.test', SENHA), 'Bloqueado')
        navegador = marca()
        token, _ = acesso.pedir_redefinicao(self.root, 'trancada@exemplo.test')
        acesso.redefinir_senha(self.root, token, NOVA, marca=navegador)
        self.assertEqual(self.tentar('trancada@exemplo.test', NOVA), 'Bloqueado')  # still protected for everybody else
        self.assertEqual(self.tentar('trancada@exemplo.test', NOVA, marca=navegador), 'entrou')

    def test_remover_a_conta_esquece_os_aparelhos_dela(self):
        self.tentar('rep.a', SENHA, marca=marca())
        acesso.remover(self.root, self.rep_a, self.dono_a, self.a, SENHA)
        self.assertEqual(self.linhas('SELECT 1 FROM aparelhos'), [])


class SegundoPassoTest(Base):
    def setUp(self):
        super().setUp()
        env = patch.dict(test_acesso.os.environ, {'VLADO_SEGREDOS': ''})
        env.start()
        self.addCleanup(env.stop)
        fator._CHAVES.clear()
        self.segredo = acesso.iniciar_fator(self.root, self.rep_a, SENHA)['segredo']
        semente = fator.base64.b32decode(self.segredo + '=' * (-len(self.segredo) % 8))
        self.codigo = lambda desvio=0: fator.codigo_do_passo(semente, fator.passo_de(acesso.agora()) + desvio)
        acesso.confirmar_fator(self.root, self.rep_a, self.codigo())

    def bilhete(self):
        with self.assertRaises(acesso.PedeSegundoFator) as passo:
            acesso.entrar(self.root, 'rep.a', SENHA, ip=self.ip())  # the password is right every time
        return passo.exception.bilhete

    def errar(self, vezes):
        """The names of what `vezes` wrong codes raised, each with a new ticket and from a new address."""
        nomes = []
        for _ in range(vezes):
            with self.assertRaises(ValueError) as recusa:
                acesso.entrar_segundo_fator(self.root, self.bilhete(), '000000', ip=self.ip())
            nomes.append(type(recusa.exception).__name__)
        return nomes

    def test_codigo_errado_conta_na_conta_de_qualquer_endereco_e_o_quinto_bloqueia_e_avisa(self):
        # Reservation R1 of the review: with the password leaked and many addresses, the wrong codes were counted
        # only per identifier and address, and eight addresses gave forty guesses in a row. They count on the account.
        with self.assertRaises(acesso.CodigoInvalido):
            acesso.entrar_segundo_fator(self.root, self.bilhete(), '000000', ip=self.ip())
        self.assertEqual(self.errar(3), ['CodigoInvalido'] * 3)
        with self.assertRaises(acesso.FatorBloqueado) as quinto:
            acesso.entrar_segundo_fator(self.root, self.bilhete(), '000000', ip=self.ip())
        self.assertEqual((quinto.exception.aviso['id'], set(quinto.exception.aviso)), (self.rep_a, {'id', 'email', 'nome', 'idioma'}))
        self.assertEqual(self.tipos().count('fator_bloqueado'), 1)
        self.assertEqual(self.errar(35), ['Bloqueado'] * 35)  # the other 35 of the forty: not even tried
        self.assertEqual(self.tipos().count('fator_bloqueado'), 1)  # told once, not at every attempt
        bilhete = self.bilhete()
        for certo in (self.codigo(1), ):  # blocked for the right code too, from anywhere, and the ticket is not spent
            with self.assertRaises(acesso.Bloqueado):
                acesso.entrar_segundo_fator(self.root, bilhete, certo, ip=self.ip())
        with self.assertRaises(acesso.Bloqueado):
            acesso.exigir_codigo(self.root, self.rep_a, self.codigo(1))  # the same counter of the operations that ask the code
        self.assertEqual(self.linhas('SELECT falhas FROM entradas WHERE id_sha256 = ?', acesso._hash(bilhete)), [{'falhas': 0}])
        self.assertEqual(self.linhas('SELECT 1 FROM sessoes WHERE conta = ?', self.rep_a), [])
        with self.depois(minutes=acesso.BLOQUEIO_MINUTOS + 1):
            self.assertEqual(acesso.entrar_segundo_fator(self.root, self.bilhete(), self.codigo(1), ip=self.ip())[2]['id'], self.rep_a)
        self.assertEqual(self.linhas('SELECT 1 FROM tentativas WHERE chave = ?', acesso.CHAVE_FATOR + self.rep_a), [])

    def test_o_codigo_de_reserva_atravessa_o_bloqueio_do_fator_e_tem_contador_proprio(self):
        # T1 of the review: who has somebody's password renews the block of the factor every 15 minutes. The
        # reserve code (80 bits, not to be guessed) is the way in of the person, and it is never blocked itself.
        reserva = acesso.novos_codigos_do_fator(self.root, self.rep_a, SENHA, self.codigo(1))
        self.assertEqual(self.errar(5), ['CodigoInvalido'] * 4 + ['FatorBloqueado'])
        with self.assertRaises(acesso.Bloqueado):
            acesso.exigir_codigo(self.root, self.rep_a, self.codigo(2))  # the authenticator: blocked
        self.assertIsNone(acesso.exigir_codigo(self.root, self.rep_a, reserva[0]))  # a reserve code: through
        self.assertEqual(acesso.entrar_segundo_fator(self.root, self.bilhete(), reserva[1], ip=self.ip())[2]['id'], self.rep_a)
        self.assertTrue(self.linhas('SELECT 1 FROM tentativas WHERE chave = ? AND bloqueado_ate IS NOT NULL',
                                    acesso.CHAVE_FATOR + self.rep_a))  # and the block of the authenticator stays
        errada = 'ABCD-EFGH-JKLM-NPQR'
        for _ in range(acesso.FALHAS_BLOQUEIO - 1):
            with self.assertRaises(acesso.CodigoInvalido):
                acesso.exigir_codigo(self.root, self.rep_a, errada)
        for _ in range(3):  # the fifth wrong one and the ones after it: the answer of a block, with nobody to tell
            with self.assertRaises(acesso.Bloqueado) as recusa:
                acesso.exigir_codigo(self.root, self.rep_a, errada)
            self.assertNotIsInstance(recusa.exception, acesso.FatorBloqueado)
        self.assertIsNone(acesso.exigir_codigo(self.root, self.rep_a, reserva[2]))  # a right one still passes
        self.assertEqual(self.tipos().count('fator_bloqueado'), 1)
        with self.depois(minutes=acesso.BLOQUEIO_MINUTOS + 1):  # the wrong reserve codes never blocked the authenticator
            self.assertIsNone(acesso.exigir_codigo(self.root, self.rep_a, self.codigo(1)))

    def test_poucos_codigos_errados_de_cada_vez_tambem_somam_ate_o_bloqueio(self):
        # T2 of the review: the counter of the factor was forgotten after 15 quiet minutes, so four wrong codes every
        # quarter of an hour never blocked nor told anybody. It is remembered for a day.
        self.assertEqual(self.errar(4), ['CodigoInvalido'] * 4)
        with self.depois(minutes=acesso.BLOQUEIO_MINUTOS + 5):
            self.assertEqual(self.tentar('ninguem.aqui'), 'CredenciaisInvalidas')  # any failure prunes the stale counters
            self.assertEqual(self.errar(1), ['FatorBloqueado'])
        self.assertEqual(self.tipos().count('fator_bloqueado'), 1)
        with self.depois(hours=1):  # the block ended; a right code clears the counter
            acesso.exigir_codigo(self.root, self.rep_a, self.codigo(1))
            self.assertEqual(self.errar(4), ['CodigoInvalido'] * 4)
        with self.depois(hours=acesso.FATOR_CONTADOR_HORAS + 2):  # and a counter nobody touched for a day is forgotten
            self.assertEqual(self.tentar('ninguem.aqui'), 'CredenciaisInvalidas')
            self.assertEqual(self.linhas('SELECT 1 FROM tentativas WHERE chave = ?', acesso.CHAVE_FATOR + self.rep_a), [])

    def test_codigos_errados_do_segundo_fator_contam_no_mesmo_teto_do_identificador(self):
        self.assertEqual(self.errar(5), ['CodigoInvalido'] * 4 + ['FatorBloqueado'])
        with self.depois(minutes=acesso.BLOQUEIO_MINUTOS + 1):  # the block of the factor ended; the hour of the identifier did not
            self.assertEqual(self.errar(5), ['CodigoInvalido'] * 4 + ['FatorBloqueado'])
            self.assertEqual(self.tentar('rep.a', SENHA), 'Bloqueado')  # ten wrong codes: protected, like ten wrong passwords

    def test_o_aparelho_so_fica_conhecido_depois_do_segundo_passo(self):
        navegador = marca()
        with self.assertRaises(acesso.PedeSegundoFator) as passo:
            acesso.entrar(self.root, 'rep.a', SENHA, ip=self.ip(), marca=navegador)
        self.assertEqual(self.linhas('SELECT 1 FROM aparelhos'), [])  # the password alone proves nothing yet
        entrou = acesso.entrar_segundo_fator(self.root, passo.exception.bilhete, self.codigo(1), marca=navegador)
        self.assertEqual((entrou[2]['id'], entrou[2]['aparelho_novo']), (self.rep_a, False))
        self.assertEqual([l['resumo'] for l in self.linhas('SELECT resumo FROM aparelhos')], [acesso._hash(navegador)])


class ServidorTest(cenario.DuasRedacoes):
    """The device mark as a cookie, through the server (hosted mode)."""
    numero = 0

    def setUp(self):
        acesso.limpar_limites()
        type(self).numero += 1
        self.email = f'aparelho{self.numero}@exemplo.test'
        _, token, _ = acesso.convidar(self.root, self.a, self.ids['dono'], self.email, 'leitor', ['alpha'])
        self.conta = acesso.aceitar_convite(self.root, token, 'Pessoa do Aparelho', SENHA)[2]['id']

    def pedir_tudo(self, operacao, dados, cookies=()):
        """(status, body, every Set-Cookie of the answer) of a public operation."""
        con = http.client.HTTPConnection('127.0.0.1', self.server.server_port, timeout=30)
        try:
            con.request('POST', '/api/' + operacao, json.dumps(dados), {
                'Host': 'vlado.test', 'Content-Type': 'application/json', 'Origin': cenario.ORIGEM,
                **({'Cookie': '; '.join(cookies)} if cookies else {})})
            resposta = con.getresponse()
            return resposta.status, json.loads(resposta.read() or b'{}'), resposta.msg.get_all('Set-Cookie') or []
        finally:
            con.close()

    def do_aparelho(self, cookies):
        return [c for c in cookies if c.startswith('vlado_aparelho=')]

    def test_entrada_que_deu_certo_poe_a_marca_e_a_recusa_nunca_poe(self):
        status, _, cookies = self.pedir_tudo('entrar', {'login': self.email, 'senha': ERRADA})
        self.assertEqual((status, cookies), (401, []))  # a refusal sets nothing
        status, corpo, cookies = self.pedir_tudo('entrar', {'login': self.email, 'senha': SENHA})
        self.assertEqual(status, 200)
        marca, = self.do_aparelho(cookies)
        for atributo in ('HttpOnly', 'Secure', 'SameSite=Lax', 'Path=/', 'Max-Age=31536000'):
            self.assertIn(atributo, marca)
        self.assertRegex(marca.split(';')[0], r'^vlado_aparelho=[A-Za-z0-9_-]{43}$')
        self.assertTrue(cookies[-1].startswith('vlado_sessao='))  # the session goes last
        self.assertNotIn(marca.split(';')[0].split('=', 1)[1], json.dumps(corpo))  # the mark is a cookie, never in a body
        self.assertNotIn('aparelho_novo', json.dumps(corpo))
        # The same browser signs in again: the same mark, and it is the one that crosses the protected mode.
        status, _, de_novo = self.pedir_tudo('entrar', {'login': self.email, 'senha': SENHA}, [marca.split(';')[0]])
        self.assertEqual(self.do_aparelho(de_novo)[0].split(';')[0], marca.split(';')[0])
        for numero in range(acesso.PROTECAO_FALHAS - 1):  # with the refusal above, the ten of the hour
            with self.assertRaises(acesso.CredenciaisInvalidas):
                acesso.entrar(self.root, self.email, ERRADA, ip=f'203.0.113.{numero + 1}')
        acesso.limpar_limites()
        self.assertEqual(self.pedir_tudo('entrar', {'login': self.email, 'senha': SENHA})[0], 429)
        self.assertEqual(self.pedir_tudo('entrar', {'login': self.email, 'senha': SENHA}, [marca.split(';')[0]])[0], 200)
        self.assertEqual(self.pedir_tudo('entrar', {'login': self.email, 'senha': SENHA}, ['vlado_aparelho=' + 'x' * 43])[0], 429)

    def test_o_link_de_redefinir_poe_a_marca_e_o_segundo_aparelho_e_avisado_por_email(self):
        with correio.usar('simulado'):
            self.pedir_tudo('senha-esqueci', {'email': self.email})
            correio.aguardar()
            token = [m for m in correio.caixa() if m['tipo'] == 'redefinicao' and m['para'] == self.email][0]['link'].rsplit('/', 1)[1]
            recusado = self.pedir_tudo('senha-redefinir', {'token': 'x' * 43, 'senha': NOVA})
            self.assertEqual((recusado[0], recusado[2]), (400, []))  # a dead link marks nothing
            status, _, cookies = self.pedir_tudo('senha-redefinir', {'token': token, 'senha': NOVA})
            self.assertEqual((status, len(self.do_aparelho(cookies)), len(cookies)), (200, 1, 1))  # the mark, and no session
            do_link = self.do_aparelho(cookies)[0].split(';')[0]
            correio.aguardar()
            correio.limpar_caixa()
            # The browser of the link is the account's known device: signing in from it tells nobody anything ...
            self.assertEqual(self.pedir_tudo('entrar', {'login': self.email, 'senha': NOVA}, [do_link])[0], 200)
            correio.aguardar()
            self.assertEqual([m for m in correio.caixa() if m['tipo'] == 'novo_acesso'], [])
            # ... and from another one the person is told, at the account's own address.
            self.assertEqual(self.pedir_tudo('entrar', {'login': self.email, 'senha': NOVA})[0], 200)
            correio.aguardar()
        aviso, = [m for m in correio.caixa() if m['tipo'] == 'novo_acesso']
        self.assertEqual(aviso['para'], self.email)
        self.assertNotIn('http', aviso['corpo'])
        atividade = self.post('dono', 'equipe-atividade', {'limite': 200})[1]['eventos']
        self.assertIn(('aparelho_novo', self.conta), {(e['tipo'], e['conta']) for e in atividade})
        self.assertNotIn('127.0.0.1', json.dumps(atividade))  # the dono sees "a new device", never the address


    def test_cinco_codigos_errados_no_segundo_passo_bloqueiam_o_fator_e_a_pessoa_e_avisada_por_email(self):
        env = patch.dict(test_acesso.os.environ, {'VLADO_SEGREDOS': ''})
        env.start()
        self.addCleanup(env.stop)
        segredo = acesso.iniciar_fator(self.root, self.conta, SENHA)['segredo']
        semente = fator.base64.b32decode(segredo + '=' * (-len(segredo) % 8))
        acesso.confirmar_fator(self.root, self.conta, fator.codigo_do_passo(semente, fator.passo_de(acesso.agora())))
        respostas = []
        with correio.usar('simulado'):
            correio.limpar_caixa()
            for _ in range(5):
                _, _, cookies = self.pedir_tudo('entrar', {'login': self.email, 'senha': SENHA})
                bilhete = cookies[0].split(';')[0]
                status, corpo, _ = self.pedir_tudo('entrar-segundo-fator', {'codigo': '000000'}, [bilhete])
                respostas.append((status, corpo.get('codigo')))
            certo = fator.codigo_do_passo(semente, fator.passo_de(acesso.agora()) + 1)
            bloqueado = self.pedir_tudo('entrar-segundo-fator', {'codigo': certo}, [bilhete])
            correio.aguardar()
        self.assertEqual(respostas, [(403, 'codigo_invalido')] * 4 + [(429, 'bloqueado')])
        self.assertEqual((bloqueado[0], bloqueado[2]), (429, []))  # the right code too, and no cookie of any kind
        avisos = [m for m in correio.caixa() if m['tipo'] == 'fator_bloqueado']
        self.assertEqual([m['para'] for m in avisos], [self.email])  # told once, at the account's own address
        self.assertNotIn('http', avisos[0]['corpo'])
        atividade = self.post('dono', 'equipe-atividade', {'limite': 200})[1]['eventos']
        self.assertIn(('fator_bloqueado', self.conta), {(e['tipo'], e['conta']) for e in atividade})


    def test_o_cookie_do_segundo_passo_sai_do_navegador_quando_a_sessao_abre_ou_o_bilhete_morre(self):
        # F2 of the review: the ticket's cookie was left in the browser until its five minutes ran out.
        env = patch.dict(test_acesso.os.environ, {'VLADO_SEGREDOS': ''})
        env.start()
        self.addCleanup(env.stop)
        segredo = acesso.iniciar_fator(self.root, self.conta, SENHA)['segredo']
        semente = fator.base64.b32decode(segredo + '=' * (-len(segredo) % 8))
        reserva = acesso.confirmar_fator(self.root, self.conta, fator.codigo_do_passo(semente, fator.passo_de(acesso.agora())))

        def bilhete():
            status, corpo, cookies = self.pedir_tudo('entrar', {'login': self.email, 'senha': SENHA})
            self.assertEqual((status, corpo, len(cookies)), (200, {'estado': 'segundo_fator'}, 1))
            return cookies[0].split(';')[0]

        def apagado(cookies):
            return [c for c in cookies if c.startswith('vlado_passo2=;') and 'Max-Age=0' in c and 'HttpOnly' in c]

        primeiro = bilhete()
        status, _, cookies = self.pedir_tudo('entrar-segundo-fator', {'codigo': '000000'}, [primeiro])
        self.assertEqual((status, cookies), (403, []))  # a wrong code: the ticket still stands, and so does its cookie
        status, corpo, cookies = self.pedir_tudo('entrar-segundo-fator', {'codigo': reserva[0]}, [primeiro])
        self.assertEqual((status, len(apagado(cookies)), len(cookies)), (200, 1, 3))  # the session opened: the ticket's cookie goes
        self.assertTrue(cookies[-1].startswith('vlado_sessao='))
        # A ticket that is unknown, used or expired: the answer takes its cookie away too.
        status, corpo, cookies = self.pedir_tudo('entrar-segundo-fator', {'codigo': reserva[1]}, [primeiro])
        self.assertEqual((status, corpo['codigo'], len(apagado(cookies)), len(cookies)), (401, 'entrada_expirada', 1, 1))
        self.assertEqual(self.pedir_tudo('entrar-segundo-fator', {'codigo': reserva[1]})[2], [])  # no cookie came: none to clear
        # A ticket killed by its fifth wrong code (which also blocks the factor of the account).
        acesso.limpar_limites()
        segundo = bilhete()
        respostas = [self.pedir_tudo('entrar-segundo-fator', {'codigo': '000000'}, [segundo]) for _ in range(acesso.ENTRADA_FALHAS)]
        self.assertEqual([(r[0], len(r[2])) for r in respostas], [(403, 0)] * 4 + [(429, 1)])
        self.assertEqual(len(apagado(respostas[-1][2])), 1)
        # While the factor is only blocked a new ticket stands, cookie and all: the reserve code gets in with it.
        acesso.limpar_limites()
        with acesso._bd(self.root, escrever=True) as tx:  # only the block of the factor is left
            tx.ex("DELETE FROM tentativas WHERE chave NOT LIKE '#fator|%'")
        terceiro = bilhete()
        status, _, cookies = self.pedir_tudo('entrar-segundo-fator', {'codigo': '000000'}, [terceiro])
        self.assertEqual((status, cookies), (429, []))
        status, _, cookies = self.pedir_tudo('entrar-segundo-fator', {'codigo': reserva[1]}, [terceiro])
        self.assertEqual((status, len(apagado(cookies))), (200, 1))
        # A sign-in in one step, with no ticket around, clears nothing.
        outra = self.pedir_tudo('entrar', {'login': 'leo.leitor', 'senha': SENHA})
        self.assertEqual((outra[0], len(outra[2]), apagado(outra[2])), (200, 2, []))


if __name__ == '__main__':
    unittest.main()
