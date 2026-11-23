"""Teto de tentativas por identificador, modo protegido e aparelho conhecido (contrato de contas, seção 8.2 e a
segunda ressalva de P28), no armazenamento.

Todo contador é do identificador digitado, exista a conta ou não. Dez falhas de um identificador em uma hora, de
quaisquer endereços, o põem em modo protegido por uma hora: toda tentativa recebe a mesma recusa, sem conta de
senha para ninguém, salvo a que traz a marca de um aparelho que aquela conta já usou. A marca atravessa o modo
protegido, mas não desliga a contagem. Identificador sem conta conta numa tabela de tamanho fixo. As regras no
armazenamento; o cookie da marca, pelo servidor (``ServidorTest``). Sem modelo e sem rede.
"""
import http.client
import json
from pathlib import Path
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
        self.assertIn(acesso.CHAVE_IDENTIFICADOR + 'rep.a', chaves)  # an account: its own counter
        self.assertEqual(len([c for c in chaves if c.startswith(acesso.CHAVE_BALDE)]), 1)  # none: one of the fixed table
        self.assertNotIn('ninguem.aqui', ' '.join(chaves))  # and the identifier typed is not kept in it
        self.assertIn('login_protegido', self.tipos())

    def test_tentativa_durante_o_modo_protegido_nao_conta_nem_estende_e_a_protecao_acaba_em_uma_hora(self):
        self.falhar('rep.a', acesso.PROTECAO_FALHAS)
        ate = self.linhas('SELECT bloqueado_ate FROM tentativas WHERE chave = ?', acesso.CHAVE_IDENTIFICADOR + 'rep.a')[0]
        with self.depois(minutes=30):
            self.assertEqual(self.falhar('rep.a', 6), ['Bloqueado'] * 6)
        self.assertEqual(self.linhas('SELECT bloqueado_ate FROM tentativas WHERE chave = ?', acesso.CHAVE_IDENTIFICADOR + 'rep.a')[0], ate)
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

    def test_identificadores_sem_conta_contam_numa_tabela_de_tamanho_fixo(self):
        with patch.object(acesso, 'BALDES', 3):
            respostas = [self.tentar(f'ninguem{numero}@exemplo.test') for numero in range(120)]
            self.assertEqual(set(respostas), {'CredenciaisInvalidas', 'Bloqueado'})
            self.assertEqual(respostas[:acesso.PROTECAO_FALHAS], ['CredenciaisInvalidas'] * acesso.PROTECAO_FALHAS)  # no counter can have ten yet
            self.assertLessEqual(respostas.count('CredenciaisInvalidas'), 3 * acesso.PROTECAO_FALHAS)  # ten for each counter, no more
            baldes = self.linhas("SELECT chave, bloqueado_ate FROM tentativas WHERE chave LIKE '#balde|%'")
            self.assertEqual({b['chave'] for b in baldes}, {'#balde|0', '#balde|1', '#balde|2'})  # 120 identifiers, three counters
            self.assertTrue(all(b['bloqueado_ate'] for b in baldes))
            # A collision only makes an identifier without an account inherit the protected mode of another.
            self.assertEqual(self.tentar('nunca.tentado@exemplo.test'), 'Bloqueado')
            # An identifier WITH an account keeps its exact counter, whatever happens to the fixed table.
            self.assertEqual(self.tentar('rep.a'), 'CredenciaisInvalidas')
            self.assertEqual(self.tentar('rep.a', SENHA), 'entrou')
        self.assertEqual(len(self.linhas("SELECT 1 FROM tentativas WHERE chave LIKE '#id|%'")), 1)
        self.assertNotIn('ninguem', ' '.join(l['chave'] for l in self.linhas('SELECT chave FROM tentativas WHERE chave LIKE ?', '#%')))

    def test_nenhum_contador_sai_antes_do_prazo(self):
        agora = acesso.agora()
        ha = lambda minutos: acesso._iso(agora - test_acesso.timedelta(minutes=minutos))  # noqa: E731
        futuro = acesso._iso(agora + test_acesso.timedelta(minutes=30))
        acesso.listar(self.root)
        for chave, em, ate in (('#id|vivo', ha(30), None), ('#id|vencido', ha(61), None), ('#balde|7', ha(59), None),
                               ('#balde|8', ha(200), futuro), ('ana|198.51.100.7', ha(16), None), ('bia|198.51.100.7', ha(5), None),
                               ('#senha|' + 'a' * 16, ha(16), None), ('#marca|x|y', ha(3), None)):
            self.gravar('INSERT INTO tentativas (chave, falhas, bloqueado_ate, em) VALUES (?, 1, ?, ?)', chave, ate, em)
        with patch.object(acesso, 'MAX_TENTATIVAS_GUARDADAS', 1):
            self.assertEqual(self.tentar('rep.a'), 'CredenciaisInvalidas')  # any failure prunes
        chaves = {l['chave'] for l in self.linhas('SELECT chave FROM tentativas')}
        self.assertLessEqual({'#id|vivo', '#balde|7', '#balde|8', '#marca|x|y', '#id|rep.a'}, chaves)
        self.assertFalse({'#id|vencido', 'ana|198.51.100.7', '#senha|' + 'a' * 16} & chaves)
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

    def test_codigos_errados_do_segundo_fator_contam_no_mesmo_teto_do_identificador(self):
        for _ in range(acesso.PROTECAO_FALHAS):
            with self.assertRaises(acesso.PedeSegundoFator) as passo:
                acesso.entrar(self.root, 'rep.a', SENHA, ip=self.ip())  # the password is right every time
            with self.assertRaises(acesso.CodigoInvalido):
                acesso.entrar_segundo_fator(self.root, passo.exception.bilhete, '000000')
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


if __name__ == '__main__':
    unittest.main()
