"""E-mail transacional (``scripts/correio.py``; contrato de contas, seção 8.1): modelos só de texto e três transportes.

Nenhum teste abre conexão: o transporte ``smtp`` roda contra um servidor de mentira posto no lugar de
``smtplib.SMTP``. O registro de auditoria é observado por um substituto de ``registro_acesso.registrar``.
"""
import os
from pathlib import Path
import re
import smtplib
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import correio
import registro_acesso

ORIGEM = 'https://vlado.test'
LINK = ORIGEM + '/aceitar/' + 'T' * 43
DADOS = {'redacao': 'Redação Alfa', 'convidado_por': 'Dona Alfa', 'papel': 'reporter', 'validade': '2026-11-29',
         'link': LINK, 'origem': ORIGEM, 'minutos': 60}
SMTP = {'VLADO_CORREIO': 'smtp', 'VLADO_SMTP_HOST': 'smtp.exemplo.test', 'VLADO_SMTP_PORTA': '587',
        'VLADO_SMTP_USUARIO': 'vlado', 'VLADO_SMTP_SENHA': 'senha-do-smtp-de-teste', 'VLADO_SMTP_REMETENTE': 'nao-responda@vlado.test'}
SEM_CORREIO = {chave: '' for chave in SMTP}


class ServidorDeMentira:
    """Stands for ``smtplib.SMTP``: keeps what was asked of it, opens no connection."""
    instancias, falhar = [], None

    def __init__(self, host, porta, timeout=None):
        self.host, self.porta, self.timeout, self.passos, self.mensagem = host, porta, timeout, [], None
        type(self).instancias.append(self)

    def __enter__(self):
        return self

    def __exit__(self, *_):
        self.passos.append('fim')

    def starttls(self, context=None):
        self.passos.append('tls')

    def login(self, usuario, senha):
        self.passos.append(('login', usuario, senha))

    def send_message(self, mensagem):
        if type(self).falhar:
            raise type(self).falhar
        self.mensagem = mensagem
        self.passos.append('enviada')


class Base(unittest.TestCase):
    def setUp(self):
        env = patch.dict(os.environ, SEM_CORREIO)
        env.start()
        self.addCleanup(env.stop)
        correio.limpar_caixa()
        self.addCleanup(correio.limpar_caixa)
        registrar = patch.object(registro_acesso, 'registrar')
        self.registrar = registrar.start()
        self.addCleanup(registrar.stop)

    def registrados(self):
        return [(c.args[0], c.args[1], c.kwargs.get('mensagem')) for c in self.registrar.call_args_list]


class ModelosTest(Base):
    def test_convite_em_portugues_e_em_ingles_so_texto_com_o_link_da_instalacao(self):
        assunto, corpo = correio.montar('convite', 'pt', DADOS)
        self.assertEqual(assunto, 'Convite para a redação Redação Alfa no Vlado')
        for trecho in ('Dona Alfa convidou você', 'papel de repórter', LINK, '29/11/2026', 'uma vez'):
            self.assertIn(trecho, corpo)
        assunto_en, corpo_en = correio.montar('convite', 'en', DADOS)
        self.assertIn('Invitation to the newsroom', assunto_en)
        for trecho in ('as reporter', LINK, '2026-11-29'):
            self.assertIn(trecho, corpo_en)
        for texto in (corpo, corpo_en):
            self.assertNotIn('<', texto)  # text only
            self.assertEqual(texto.count('http'), 1)  # the only link is the installation's
        self.assertEqual(correio.montar('convite', 'fr', DADOS), (assunto, corpo))  # unknown language: Portuguese

    def test_convite_para_email_que_ja_tem_conta_explica_e_nao_leva_link(self):
        for idioma, trecho in (('pt', 'já tem uma conta'), ('en', 'already has an account')):
            assunto, corpo = correio.montar('convite_sem_efeito', idioma, DADOS)
            self.assertIn(trecho, corpo)
            self.assertNotIn('http', corpo)
            self.assertEqual(assunto, correio.montar('convite', idioma, DADOS)[0])  # the subject tells nothing apart

    def test_nome_de_pessoa_e_de_redacao_entram_numa_linha_so(self):
        hostil = {**DADOS, 'redacao': 'Alfa\r\nBcc: alvo@exemplo.test', 'convidado_por': 'Dona\nAlfa\x00\x1b[31m ' + 'x' * 500}
        assunto, corpo = correio.montar('convite', 'pt', hostil)
        self.assertNotIn('\n', assunto)
        self.assertNotIn('\r', assunto + corpo)
        self.assertNotIn('\x00', corpo)
        self.assertIn('Alfa Bcc alvo exemplo test', assunto)  # one line, and no address: it cannot become a header
        self.assertLessEqual(len(assunto), 150)
        self.assertLess(len(corpo), 1200)

    def test_nome_digitado_por_alguem_nunca_vira_endereco_em_tipo_nenhum_de_mensagem(self):
        # A dono renames herself "Veja https://golpe.example" and invites any address: the message would leave from
        # the Vlado's sender with the other address clickable before the invitation's link.
        endereco = re.compile(r'\S+\.\S+|\S*://\S*|\S+@\S+|\S+/\S+|\bwww\b\S*\.')
        nomes = ('Veja https://golpe.example', 'www.golpe.example', 'golpe.example/entrar', 'fale com golpe@golpe.example',
                 'mailto:golpe@golpe.example', 'HTTPS://GOLPE.EXAMPLE', 'golpe。example', 'golpe．example', 'tel:+5511999999999',
                 'h​ttps://golpe.example', 'golpe . example', 'https:\\\\golpe.example', '//golpe.example')
        for tipo in correio.MODELOS:
            for idioma in correio.IDIOMAS:
                for campo in ('convidado_por', 'redacao', 'papel', 'validade', 'minutos'):
                    for nome in nomes:
                        with self.subTest(tipo=tipo, idioma=idioma, campo=campo, nome=nome):
                            assunto, corpo = correio.montar(tipo, idioma, {**DADOS, campo: nome})
                            permitidos = [LINK] if '{link}' in correio.MODELOS[tipo][1][idioma][1] else []
                            data = ['29/11/2026'] if idioma == 'pt' and campo != 'validade' else []
                            self.assertEqual([a for a in endereco.findall(corpo) if a not in data], permitidos)
                            self.assertEqual(endereco.findall(assunto), [])
                            for sinal in ('://', '@', 'golpe.', '.example', '。', '．'):
                                self.assertNotIn(sinal, (assunto + corpo).replace(LINK, ''))
        assunto, corpo = correio.montar('convite', 'pt', {**DADOS, 'convidado_por': 'Veja https://golpe.example'})
        self.assertIn('Veja https golpe example convidou você', corpo)  # the name is still there, as words
        self.assertIn("Maria d'Ávila-Souza (editora), Jr", correio.montar('convite', 'pt', {**DADOS, 'convidado_por': "Maria d'Ávila-Souza (editora), Jr."})[1])

    def test_redefinicao_e_aviso_de_senha_trocada(self):
        for idioma, trecho in (('pt', 'vale por 60 minutos'), ('en', 'valid for 60 minutes')):
            assunto, corpo = correio.montar('redefinicao', idioma, {'link': ORIGEM + '/redefinir/' + 'T' * 43, 'origem': ORIGEM, 'minutos': 60})
            self.assertIn(trecho, corpo)
            self.assertIn(ORIGEM + '/redefinir/' + 'T' * 43, corpo)
            self.assertEqual(corpo.count('http'), 1)
            aviso = correio.montar('senha_trocada', idioma, {})[1]
            self.assertNotIn('http', aviso)  # a notice carries no link: nothing to click in a message nobody asked for
        self.assertIn('foi trocada', correio.montar('senha_trocada', 'pt', {})[0])

    def test_enviar_depois_nao_faz_quem_chamou_esperar_e_guarda_o_transporte_do_pedido(self):
        with correio.usar('simulado'):
            correio.enviar_depois('senha_trocada', 'ana@exemplo.test', 'pt', {}, conta='a' * 16)
        correio.aguardar()  # the block ended before the thread ran: the transport is the one of when it was asked
        self.assertEqual([(m['tipo'], m['para']) for m in correio.caixa()], [('senha_trocada', 'ana@exemplo.test')])
        self.assertIn(('email_enviado', 'ok', 'senha_trocada'), self.registrados())
        correio.limpar_caixa()
        correio.enviar_depois('senha_trocada', 'ana@exemplo.test', 'pt', {})  # the link on the screen: nothing leaves
        correio.aguardar()
        self.assertEqual(correio.caixa(), [])
        with correio.usar('simulado'), self.assertRaises(ValueError):
            correio.enviar_depois('promocao', 'ana@exemplo.test', 'pt', {})  # a programming error shows in the caller

    def test_link_de_fora_da_instalacao_tipo_desconhecido_e_campo_faltando_sao_recusados(self):
        for link in ('https://outro.test/aceitar/abc', 'javascript:alert(1)', LINK + '\nhttps://outro.test/', LINK + '?x=1', ''):
            with self.assertRaises(ValueError, msg=link):
                correio.montar('convite', 'pt', {**DADOS, 'link': link})
        with self.assertRaises(ValueError):
            correio.montar('promocao', 'pt', DADOS)
        with self.assertRaises(ValueError):
            correio.montar('convite', 'pt', {'redacao': 'Alfa', 'link': LINK})
        self.assertIn('A administração convidou', correio.montar('convite', 'pt', {**DADOS, 'convidado_por': None})[1])


class TransportesTest(Base):
    def test_padrao_e_tela_que_nao_envia_nada(self):
        self.assertEqual(correio.transporte(), 'tela')
        self.assertEqual(correio.enviar('convite', 'ana@exemplo.test', 'pt', DADOS), 'tela')
        self.assertEqual(correio.caixa(), [])
        self.assertEqual(self.registrados(), [])  # nothing was sent: nothing to audit as sent

    def test_simulado_guarda_a_mensagem_e_o_registro_recebe_so_o_tipo(self):
        with correio.usar('simulado'):
            self.assertEqual(correio.enviar('convite', ' Ana@Exemplo.Test ', 'en', DADOS, conta='a' * 16), 'simulado')
        mensagem, = correio.caixa()
        self.assertEqual((mensagem['tipo'], mensagem['para'], mensagem['idioma'], mensagem['link']),
                         ('convite', 'ana@exemplo.test', 'en', LINK))
        self.assertIn(LINK, mensagem['corpo'])
        self.assertEqual(self.registrados(), [('email_enviado', 'ok', 'convite')])
        chamada = self.registrar.call_args_list[0]
        self.assertNotIn('ana@exemplo.test', repr(chamada))  # never the address, the link or the text
        self.assertNotIn(LINK, repr(chamada))
        self.assertEqual(correio.transporte(), 'tela')  # the forced transport ends with the block

    def test_endereco_invalido_nao_e_enviado(self):
        with correio.usar('simulado'):
            for para in ('', None, 'sem-arroba', 'ana@exemplo.test\nBcc: outro@exemplo.test', 'a@b', 'x' * 250 + '@exemplo.test'):
                with self.assertRaises(ValueError, msg=para):
                    correio.enviar('convite', para, 'pt', DADOS)
        self.assertEqual(correio.caixa(), [])

    def test_smtp_envia_com_tls_e_credenciais_do_ambiente(self):
        ServidorDeMentira.instancias, ServidorDeMentira.falhar = [], None
        with patch.dict(os.environ, SMTP), patch.object(smtplib, 'SMTP', ServidorDeMentira):
            self.assertEqual(correio.enviar('convite', 'ana@exemplo.test', 'pt', DADOS), 'smtp')
        servidor, = ServidorDeMentira.instancias
        self.assertEqual((servidor.host, servidor.porta, servidor.timeout), ('smtp.exemplo.test', 587, correio.ESPERA_SMTP_S))
        self.assertEqual(servidor.passos, ['tls', ('login', 'vlado', 'senha-do-smtp-de-teste'), 'enviada', 'fim'])
        mensagem = servidor.mensagem
        self.assertEqual((mensagem['To'], mensagem['From'], mensagem['Subject']),
                         ('ana@exemplo.test', 'nao-responda@vlado.test', 'Convite para a redação Redação Alfa no Vlado'))
        self.assertEqual(mensagem.get_content_type(), 'text/plain')
        self.assertIn(LINK, mensagem.get_content())
        self.assertEqual(self.registrados(), [('email_enviado', 'ok', 'convite')])

    def test_falha_do_smtp_vira_falha_de_envio_sem_endereco_nem_resposta_do_servidor(self):
        ServidorDeMentira.instancias = []
        ServidorDeMentira.falhar = smtplib.SMTPRecipientsRefused({'ana@exemplo.test': (550, b'caixa inexistente')})
        self.addCleanup(setattr, ServidorDeMentira, 'falhar', None)
        with patch.dict(os.environ, SMTP), patch.object(smtplib, 'SMTP', ServidorDeMentira):
            with self.assertRaises(correio.FalhaDeEnvio) as falha:
                correio.enviar('convite', 'ana@exemplo.test', 'pt', DADOS)
        self.assertNotIn('ana@', str(falha.exception))
        self.assertNotIn('caixa', str(falha.exception))
        self.assertEqual(self.registrados(), [('email_falhou', 'falha', 'convite')])
        with patch.dict(os.environ, {**SMTP, 'VLADO_SMTP_HOST': ''}):  # no configuration: a failed delivery too
            with self.assertRaises(correio.FalhaDeEnvio):
                correio.enviar('convite', 'ana@exemplo.test', 'pt', DADOS)

    def test_transporte_desconhecido_e_recusado(self):
        with patch.dict(os.environ, {'VLADO_CORREIO': 'pombo'}):
            with self.assertRaises(correio.ErroDeCorreio):
                correio.transporte()
        with self.assertRaises(correio.ErroDeCorreio):
            with correio.usar('pombo'):
                pass


class PartidaTest(Base):
    def test_ambiente_editorial_so_sobe_com_envio_real(self):
        # Decision 12: with real data the service does not start showing links on the screen.
        with self.assertRaisesRegex(correio.ErroDeCorreio, 'editorial'):
            correio.conferir_partida('piloto', 'editorial')
        with patch.dict(os.environ, {'VLADO_CORREIO': 'simulado'}):
            with self.assertRaises(correio.ErroDeCorreio):
                correio.conferir_partida('piloto', 'editorial')
        with patch.dict(os.environ, SMTP):
            self.assertEqual(correio.conferir_partida('piloto', 'editorial'), 'smtp')

    def test_homologacao_e_mesa_instalada_sobem_com_o_link_na_tela(self):
        self.assertEqual(correio.conferir_partida('piloto', 'homologacao'), 'tela')
        self.assertEqual(correio.conferir_partida('local-contas', None), 'tela')

    def test_smtp_sem_as_variaveis_nao_sobe_em_ambiente_nenhum(self):
        for falta in ('VLADO_SMTP_HOST', 'VLADO_SMTP_REMETENTE'):
            with patch.dict(os.environ, {**SMTP, falta: ''}):
                with self.assertRaisesRegex(correio.ErroDeCorreio, 'VLADO_SMTP_HOST'):
                    correio.conferir_partida('piloto', 'homologacao')
        with patch.dict(os.environ, {**SMTP, 'VLADO_SMTP_PORTA': 'muitas'}):
            with self.assertRaises(correio.ErroDeCorreio):
                correio.conferir_partida('local-contas', None)


if __name__ == '__main__':
    unittest.main()
