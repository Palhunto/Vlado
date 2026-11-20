import hashlib
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import empacotar_entrega as emp  # noqa: E402


class EmpacotarEntregaTest(unittest.TestCase):
    def test_lista_de_proibidos_barra_dados_e_credenciais(self):
        ruins = ['.env', 'deploy/ambientes/editorial.env', 'segredos/chaves.json', 'acesso/acesso.json',
                 'casos/x/manifesto.json', 'execucoes/x/R001/registro.json', 'conversas/a/conversa.json',
                 'banco.sqlite', 'servidor.log', 'android/saidas/app.apk', 'x/keystore.properties',
                 'assinatura.jks', 'backup.tar.gz']
        bons = ['.env.example', 'deploy/ambientes/editorial.env.example', 'casos/catalogo.json',
                'casos/README.md', 'execucoes/README.md', 'scripts/acesso.py']
        self.assertEqual(emp.proibidos(ruins), ruins)
        self.assertEqual(emp.proibidos(bons), [])

    def test_zip_reproduzivel_com_manifesto(self):
        with tempfile.TemporaryDirectory() as a, tempfile.TemporaryDirectory() as b:
            r1 = emp.empacotar('HEAD', Path(a))
            r2 = emp.empacotar('HEAD', Path(b))
            self.assertEqual(r1['sha256'], r2['sha256'])
            with zipfile.ZipFile(r1['zip']) as zf:
                nomes = zf.namelist()
                raiz = nomes[0].split('/')[0]
                self.assertIn(f'{raiz}/MANIFESTO.json', nomes)
                self.assertIn(f'{raiz}/SHA256SUMS', nomes)
                self.assertFalse(any('/segredos/' in n or n.endswith('.env') for n in nomes))
                somas = zf.read(f'{raiz}/SHA256SUMS').decode().splitlines()
                digest, caminho = somas[0].split('  ', 1)
                self.assertEqual(hashlib.sha256(zf.read(f'{raiz}/{caminho}')).hexdigest(), digest)


if __name__ == '__main__':
    unittest.main()
