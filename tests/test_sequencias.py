# coding: utf-8
import json
import os
import shutil
import sqlite3
import tempfile
import unittest

_TMPDIR = tempfile.mkdtemp(prefix='deciframe-tests-')
os.environ['SEQUENCIAS_DB'] = os.path.join(_TMPDIR, 'sequencias.db')

import main  # noqa: E402  (precisa do SEQUENCIAS_DB definido acima)
from main import app  # noqa: E402

DIRETORIO_TESTES = os.path.dirname(os.path.abspath(__file__))
FIXTURE_REGRESSAO = os.path.join(
        DIRETORIO_TESTES, 'fixtures', 'regressao_sequencias.json')

CHAVES_SEED = {main.chave_canonica(acordes)
        for acordes in main.SEQUENCIAS_SEED}


def json_da_resposta(resposta):
    return json.loads(resposta.get_data(as_text=True))


class SequenciasTestCase(unittest.TestCase):

    def setUp(self):
        self.client = app.test_client()

    def _todas_as_paginas(self, sequencia):
        ids = []
        pagina = 1
        while True:
            resposta = self.client.get('/similares', query_string={
                'sequencia': sequencia,
                'pagina': str(pagina),
            })
            self.assertEqual(resposta.status_code, 200)
            dados = json_da_resposta(resposta)
            if not dados:
                break
            ids.extend(musica['id_unico_musica'] for musica in dados)
            pagina += 1
        return ids

    def _criar_sequencia(self, acordes, nome=None):
        payload = {'acordes': acordes}
        if nome is not None:
            payload['nome'] = nome
        return self.client.post('/sequencias', json=payload)

    def _musica_com_cifra_curta(self):
        chaves_existentes = self._chaves_customizadas()
        for musica in main.musicas.values():
            if not (1 <= len(musica.cifra) <= 16):
                continue
            chave = main.chave_canonica(musica.cifra)
            if chave not in CHAVES_SEED and chave not in chaves_existentes:
                return musica
        self.fail('nenhuma música com cifra curta disponível para o teste')

    def test_get_sequencias_retorna_seeds_ordenadas_por_id(self):
        resposta = self.client.get('/sequencias')

        self.assertEqual(resposta.status_code, 200)
        dados = json_da_resposta(resposta)
        self.assertGreaterEqual(len(dados), 6)

        seeds = dados[:6]
        self.assertEqual([sequencia['id'] for sequencia in seeds],
                sorted(sequencia['id'] for sequencia in seeds))
        self.assertEqual([sequencia['acordes'] for sequencia in seeds],
                main.SEQUENCIAS_SEED)
        for sequencia in seeds:
            self.assertEqual(sequencia['origem'], 'seed')
            self.assertIsNone(sequencia['nome'])
            self.assertIn('criado_em', sequencia)

    def test_post_cria_sequencia_nova(self):
        resposta = self._criar_sequencia(
                ['D', 'A', 'Bm', 'G'], 'Minha sequência')

        self.assertEqual(resposta.status_code, 201)
        dados = json_da_resposta(resposta)
        self.assertIsInstance(dados['id'], int)
        self.assertEqual(dados['nome'], 'Minha sequência')
        self.assertEqual(dados['acordes'], ['D', 'A', 'Bm', 'G'])
        self.assertEqual(dados['origem'], 'custom')
        self.assertIn('criado_em', dados)

        catalogo = json_da_resposta(self.client.get('/sequencias'))
        self.assertTrue(any(item['id'] == dados['id'] for item in catalogo))

    def test_post_aceita_acordes_como_string(self):
        resposta = self._criar_sequencia(' F , Dm , Bb , C ')

        self.assertEqual(resposta.status_code, 201)
        self.assertEqual(json_da_resposta(resposta)['acordes'],
                ['F', 'Dm', 'Bb', 'C'])

    def test_post_duplicada_retorna_200_com_registro_existente(self):
        primeiro = self._criar_sequencia(['DupA', 'DupB'], 'Primeira')
        self.assertEqual(primeiro.status_code, 201)
        original = json_da_resposta(primeiro)

        segundo = self._criar_sequencia(' dupa , dupb ', 'Outra')

        self.assertEqual(segundo.status_code, 200)
        duplicada = json_da_resposta(segundo)
        self.assertTrue(duplicada['duplicada'])
        self.assertEqual(duplicada['id'], original['id'])
        self.assertEqual(duplicada['acordes'], original['acordes'])

    def test_post_payload_invalido_retorna_400(self):
        payloads = [
            {},
            {'acordes': []},
            {'acordes': '   '},
            {'acordes': ['', '  ']},
            {'acordes': [1, 2]},
            {'acordes': ','.join(['C'] * 17)},
            {'acordes': 'C', 'nome': 123},
            {'acordes': 'C', 'nome': 'x' * 101},
        ]

        for payload in payloads:
            with self.subTest(payload=payload):
                resposta = self.client.post('/sequencias', json=payload)
                self.assertEqual(resposta.status_code, 400)
                dados = json_da_resposta(resposta)
                self.assertIn('erro', dados)
                self.assertTrue(dados['erro'])

    def test_post_corpo_que_nao_e_objeto_retorna_400(self):
        resposta = self.client.post('/sequencias', json=['C', 'G'])
        self.assertEqual(resposta.status_code, 400)

        resposta = self.client.post('/sequencias', data='isto nao e json',
                content_type='application/json')
        self.assertEqual(resposta.status_code, 400)

    def test_busca_sequencia_customizada(self):
        candidata = self._musica_com_cifra_curta()

        resposta = self._criar_sequencia(candidata.cifra, 'Customizada')
        self.assertIn(resposta.status_code, (200, 201))
        sequencia = ','.join(candidata.cifra)

        ids = self._todas_as_paginas(sequencia)

        self.assertIn(candidata.id_unico_musica, ids)

    def test_busca_e_case_insensitive(self):
        musica = self._musica_com_cifra_curta()
        resposta = self._criar_sequencia(musica.cifra)
        self.assertIn(resposta.status_code, (200, 201))

        minusculas = self._todas_as_paginas(','.join(musica.cifra).lower())
        maiusculas = self._todas_as_paginas(','.join(musica.cifra).upper())

        self.assertEqual(set(minusculas), set(maiusculas))
        self.assertIn(musica.id_unico_musica, minusculas)

    def test_formato_antigo_sem_virgulas_retorna_vazio(self):
        self.assertEqual(self._todas_as_paginas('CGAmF'), [])
        self.assertEqual(self._todas_as_paginas('BmGDA'), [])

    def test_sequencia_inexistente_retorna_vazio(self):
        self.assertEqual(self._todas_as_paginas('X,Y,Z'), [])

    def test_regressao_das_seis_sequencias(self):
        with open(FIXTURE_REGRESSAO, encoding='utf-8') as arquivo:
            baseline = json.load(arquivo)

        for sequencia, esperados in baseline.items():
            with self.subTest(sequencia=sequencia):
                obtidos = self._todas_as_paginas(sequencia)
                faltantes = set(esperados) - set(obtidos)
                extras = set(obtidos) - set(esperados)
                self.assertEqual(faltantes, set(),
                        'faltantes em %s: %s' % (sequencia, sorted(faltantes)))
                self.assertEqual(extras, set(),
                        'extras em %s: %s' % (sequencia, sorted(extras)))

    def test_persistencia_em_nova_conexao(self):
        acordes = ['PersistA', 'PersistB']
        resposta = self._criar_sequencia(acordes, 'Persistente')
        self.assertEqual(resposta.status_code, 201)
        criada = json_da_resposta(resposta)

        conn = sqlite3.connect(main.CAMINHO_DB)
        try:
            linha = conn.execute(
                    '''SELECT id, nome, acordes_json, origem
                       FROM sequencias WHERE chave_canonica = ?''',
                    (main.chave_canonica(acordes),)).fetchone()
        finally:
            conn.close()

        self.assertIsNotNone(linha)
        self.assertEqual(linha[0], criada['id'])
        self.assertEqual(linha[1], 'Persistente')
        self.assertEqual(json.loads(linha[2]), acordes)
        self.assertEqual(linha[3], 'custom')

    def test_genero_rb_normalizado(self):
        self.assertIn('R&B', main.generos)
        self.assertNotIn('R&B;', main.generos)
        self.assertTrue(all(not musica.genero.endswith(';')
                for musica in main.musicas.values()))

        generos = json_da_resposta(self.client.get('/generos'))
        self.assertIn('R&B', generos)

        resposta = self.client.get('/similares', query_string={
            'acordes': 'C',
            'generos': 'R&B',
        })
        self.assertEqual(resposta.status_code, 200)
        dados = json_da_resposta(resposta)
        self.assertTrue(dados)
        self.assertTrue(all(musica['genero'] == 'R&B' for musica in dados))

    def _chaves_customizadas(self):
        conn = sqlite3.connect(main.CAMINHO_DB)
        try:
            linhas = conn.execute(
                    'SELECT chave_canonica FROM sequencias').fetchall()
        finally:
            conn.close()
        return {linha[0] for linha in linhas}


def tearDownModule():
    shutil.rmtree(_TMPDIR, ignore_errors=True)


if __name__ == '__main__':
    unittest.main()
