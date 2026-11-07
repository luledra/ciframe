# coding: utf-8
import json
import os
import sqlite3
from datetime import datetime, timezone
from flask import Flask, request
import sys
from musica import *
from collections import OrderedDict
import unicodedata

app = Flask(__name__)

CAMINHO_DB = os.environ.get('SEQUENCIAS_DB',
        os.path.join('instance', 'sequencias.db'))

SEQUENCIAS_SEED = [
    ['Bm', 'G', 'D', 'A'],
    ['C', 'G', 'Am', 'F'],
    ['Em', 'G'],
    ['C', 'A7', 'Dm', 'G7'],
    ['Gm', 'F'],
    ['C', 'C7', 'F', 'Fm'],
]

def abrir_db():
    conn = sqlite3.connect(CAMINHO_DB)
    conn.row_factory = sqlite3.Row
    return conn

def iniciar_db():
    diretorio = os.path.dirname(CAMINHO_DB)
    if diretorio:
        os.makedirs(diretorio, exist_ok=True)

    conn = abrir_db()
    try:
        conn.execute('PRAGMA journal_mode=WAL')
        conn.execute('''
            CREATE TABLE IF NOT EXISTS sequencias (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                acordes_json TEXT NOT NULL,
                chave_canonica TEXT NOT NULL UNIQUE,
                origem TEXT NOT NULL,
                criado_em TEXT NOT NULL
            )
        ''')
        criado_em = datetime.now(timezone.utc).isoformat()
        inseridas = 0
        for acordes in SEQUENCIAS_SEED:
            cursor = conn.execute(
                '''INSERT OR IGNORE INTO sequencias
                   (acordes_json, chave_canonica, origem, criado_em)
                   VALUES (?, ?, ?, ?)''',
                (json.dumps(acordes), chave_canonica(acordes),
                 'seed', criado_em))
            inseridas += cursor.rowcount
        conn.commit()
    finally:
        conn.close()

    app.logger.info('Banco de sequencias: %s (%d seeds inseridas)',
            CAMINHO_DB, inseridas)

def normalizar_acordes(acordes):
    if isinstance(acordes, str):
        acordes = acordes.split(',')

    if not isinstance(acordes, list):
        raise ValueError('Não foi possível cadastrar a sequência. Acordes deve ser uma lista ou um texto separado por vírgulas.')

    normalizados = []
    for acorde in acordes:
        if not isinstance(acorde, str):
            raise ValueError('Não foi possível cadastrar a sequência. Cada acorde deve ser um texto.')
        acorde = acorde.strip()
        if acorde:
            normalizados.append(acorde)

    if not normalizados:
        raise ValueError('Não foi possível cadastrar a sequência. Informe ao menos um acorde.')
    if len(normalizados) > 16:
        raise ValueError('Não foi possível cadastrar a sequência. Uma sequência pode ter no máximo 16 acordes.')

    return normalizados

def chave_canonica(acordes):
    return ','.join(acorde.lower() for acorde in acordes)

def sequencia_para_json(linha):
    return {
        'id': linha['id'],
        'acordes': json.loads(linha['acordes_json']),
        'origem': linha['origem'],
        'criado_em': linha['criado_em'],
    }

def buscar_sequencia_por_chave(chave):
    conn = abrir_db()
    try:
        linha = conn.execute(
            '''SELECT id, acordes_json, origem, criado_em
               FROM sequencias WHERE chave_canonica = ?''', (chave,)).fetchone()
    finally:
        conn.close()

    return sequencia_para_json(linha) if linha else None

def limpa_cifra(raw_cifra):
    cifra = []
    for m in raw_cifra:
        if m.strip() != '':
            # filtra tablaturas
            if '|' in m:
                acorde = m.split('|')[0].split()[0]
                cifra.append(acorde)
            # lida com acordes separados por espaço
            else:
                tokens = [token for token in m.split()]
                cifra += tokens
    return cifra

# colunas do csv
ARTISTA_ID = 0
MUSICA_ID = 1
ARTISTA = 2
MUSICA = 3
GENERO = 4
POPULARIDADE = 5
TOM = 6
SEQ_FAMOSA = 7
CIFRA = 8
TAM_PAGINA = 100

genero_musicas = {}
generos = set()
acordes = set()

musicas_dict = {}

f = open('data/top/dataset_final.csv')
f.readline()

for line in f:
    line = line.replace('"', '').replace('NA', '')[:-1]

    musica = line.split(',')
    musica[POPULARIDADE] = int(musica[POPULARIDADE].replace('.', ''))

    if musica[CIFRA] != '':
        musica[CIFRA] = limpa_cifra(musica[CIFRA].split(';'))
    else:
        musica[CIFRA] = []

    musica[SEQ_FAMOSA] = musica[SEQ_FAMOSA].split(";")

    # normaliza gêneros como 'R&B;' para 'R&B'
    musica[GENERO] = musica[GENERO].rstrip(';')

    # conjunto único de gêneros
    generos.add(musica[GENERO])

    # inclui música no dict de músicas
    musica_obj = Musica(musica[ARTISTA_ID], musica[ARTISTA],
            musica[MUSICA_ID], musica[MUSICA], musica[GENERO],
            int(musica[POPULARIDADE]), musica[SEQ_FAMOSA],
            musica[TOM], musica[CIFRA])

    musicas_dict[musica_obj.id_unico_musica] = musica_obj

    # conjunto único de acordes
    for acorde in musica_obj.acordes:
        acordes.add(acorde)

    # constrói dict mapeando gênero para músicas
    # deve ser usado para melhorar o desempenho das buscas
    if musica_obj.genero in genero_musicas:
        genero_musicas[musica_obj.genero].append(musica_obj)
    else:
        genero_musicas[musica_obj.genero] = [musica_obj]

# dicionário de músicas cujos valores são ordenados por popularidade
musicas = OrderedDict(sorted(musicas_dict.items(),
    key=lambda x: x[1].popularidade, reverse = True))

# para trabalhar melhor com json
generos = list(generos)

# ordena genero_musicas por popularidade
for k,v in genero_musicas.items():
    genero_musicas[k].sort(key = lambda x : x.popularidade, reverse = True)

f.close()

iniciar_db()


@app.route('/')
def index():
    return app.send_static_file('index.html')
''' Busca por músicas que possuem no título ou no nome do artista o argumento passado por key.
params: key e generos (opcional). Caso generos não sejam definidos, a busca não irá filtrar por gênero.
exemplo 1: /search?key=no dia em que eu saí de casa
exemplo 2: /search?key=no dia em que eu saí de casa&generos=Rock,Samba '''

@app.route('/<path:path>')
def static_proxy(path):
  # send_static_file will guess the correct MIME type
  return app.send_static_file(path)

@app.route('/search')
def busca():
    generos_tag = request.args.get('generos', [])
    pagina_tag = request.args.get('pagina','1')
    keys = request.args.get('key').lower()
    keys = remover_combinantes(keys).split(' ')

    generos_key = generos
    if generos_tag:
        generos_key = generos_tag.split(',')

    collection = apply_filtro(musicas.values(), generos_key)
    out = []

    for musica in collection:
        text = '%s %s' % (musica.nome_artista.lower(), musica.nome_musica.lower())
        text_list = remover_combinantes(text).split(' ')
        if all(key in text_list for key in keys):
            matches = {
                'id_unico_musica' : musica.id_unico_musica,
                'id_artista' : musica.id_artista,
                'id_musica' : musica.id_musica,
                'nome_artista' : musica.nome_artista,
                'nome_musica' : musica.nome_musica,
                'genero' : musica.genero,
                'url' : musica.url,
            }
            out.append(matches)
    return json.dumps(get_pagina(out, pagina_tag))

# cópia
def remover_combinantes(string):
    string = unicodedata.normalize('NFD', string)
    return u''.join(ch for ch in string if unicodedata.category(ch) != 'Mn')

''' Retorna as músicas armazenadas no sistema (ordenados por popularidade).
    O serviço é paginado. Cada página tem tamanho 100, por default.
    params: pagina. Caso não seja definida a página, o valor default é 1.
    exemplo 1: /musica?pagina=2
    exemplo 2: /musica'''
@app.route('/musicas')
def get_musicas():
    return json.dumps([v.__dict__ for v in musicas.values()])

@app.route('/generos')
def get_generos():
    return json.dumps(generos)

@app.route('/acordes')
def get_acordes():
    return json.dumps(list(acordes))

@app.route('/sequencias', methods=['GET'])
def get_sequencias():
    conn = abrir_db()
    try:
        linhas = conn.execute(
            '''SELECT id, acordes_json, origem, criado_em
               FROM sequencias ORDER BY id''').fetchall()
    finally:
        conn.close()

    return json.dumps([sequencia_para_json(linha) for linha in linhas])

@app.route('/sequencias', methods=['POST'])
def post_sequencias():
    payload = request.get_json(silent=True)
    if not isinstance(payload, dict):
        return json.dumps({'erro': 'payload deve ser um objeto JSON'}), 400

    try:
        acordes = normalizar_acordes(payload.get('acordes'))
    except ValueError as erro:
        return json.dumps({'erro': str(erro)}), 400

    chave = chave_canonica(acordes)
    conn = abrir_db()
    try:
        existente = conn.execute(
            '''SELECT id, acordes_json, origem, criado_em
               FROM sequencias WHERE chave_canonica = ?''', (chave,)).fetchone()
        if existente:
            registro = sequencia_para_json(existente)
            registro['duplicada'] = True
            return json.dumps(registro), 200

        criado_em = datetime.now(timezone.utc).isoformat()
        try:
            cursor = conn.execute(
                '''INSERT INTO sequencias
                   (acordes_json, chave_canonica, origem, criado_em)
                   VALUES (?, ?, ?, ?)''',
                (json.dumps(acordes), chave, 'custom', criado_em))
            conn.commit()
        except sqlite3.IntegrityError:
            conn.rollback()
            existente = conn.execute(
                '''SELECT id, acordes_json, origem, criado_em
                   FROM sequencias WHERE chave_canonica = ?''',
                (chave,)).fetchone()
            registro = sequencia_para_json(existente)
            registro['duplicada'] = True
            return json.dumps(registro), 200

        linha = conn.execute(
            '''SELECT id, acordes_json, origem, criado_em
               FROM sequencias WHERE id = ?''', (cursor.lastrowid,)).fetchone()
        return json.dumps(sequencia_para_json(linha)), 201
    finally:
        conn.close()

@app.route('/musica/<m_id>/')
def get_musica(m_id):
    return json.dumps(musicas[m_id].__dict__)

@app.route('/similares')
def get_similares():
    # tratando request
    acordes_tag = request.args.get('acordes')
    id_musica_tag = request.args.get('id_unico_musica')
    sequencia_tag = request.args.get('sequencia')
    pagina_tag = request.args.get('pagina','1')

    # se não existir, filtra por todos.
    generos_tag = request.args.get('generos')
    generos_key = generos
    if generos_tag:
        generos_key = generos_tag.split(',')

    acordes = []
    if acordes_tag:
        acordes = acordes_tag.split(',')
    elif id_musica_tag:
        musica = musicas[id_musica_tag]
        acordes = musica.acordes
    elif sequencia_tag:
        acordes_sequencia = [acorde.strip()
                for acorde in sequencia_tag.split(',') if acorde.strip()]
        chave = chave_canonica(acordes_sequencia)
        sequencia = buscar_sequencia_por_chave(chave)
        if sequencia is None:
            return json.dumps([])

        similares = get_similares_por_sequencia(
                sequencia['acordes'], generos_key)
        return json.dumps(get_pagina(similares, pagina_tag))

    similares = get_similares(acordes, generos_key, id_musica_tag)

    return json.dumps(get_pagina(similares, pagina_tag))

def sequencia_aparece_na_musica(cifra_musica, acordes_sequencia):
    cifra = [acorde.lower() for acorde in cifra_musica]
    sequencia = [acorde.lower() for acorde in acordes_sequencia]

    if not sequencia or not set(cifra).issubset(set(sequencia)):
        return False

    tamanho = len(sequencia)
    for i in range(len(cifra) - tamanho + 1):
        if cifra[i:i + tamanho] == sequencia:
            return True

    return False

def get_similares_por_sequencia(acordes_sequencia, generos_key):
    # filtra para melhor desempenho
    collection = apply_filtro(musicas.values(), generos_key)

    similares = []
    for musica in collection:
        if sequencia_aparece_na_musica(musica.cifra, acordes_sequencia):
            similar = {
                'id_unico_musica' : musica.id_unico_musica,
                'id_artista' : musica.id_artista,
                'id_musica' : musica.id_musica,
                'nome_artista' : musica.nome_artista,
                'nome_musica' : musica.nome_musica,
                'popularidade' : musica.popularidade,
                'acordes' : musica.acordes,
                'genero' : musica.genero,
                'url' : musica.url,
            }
            similares.append(similar)

    return similares


def get_pagina(colecao, pagina_tag):
    sl = (int(pagina_tag) - 1)*TAM_PAGINA
    return colecao[sl:sl+TAM_PAGINA]

def get_similares(acordes, generos_key, id_musica = None):

    # filtra para melhor desempenho
    collection = apply_filtro(musicas.values(), generos_key)

    similares = []
    for musica in collection:

        if musica.id_unico_musica != id_musica:

            inter = set(acordes).intersection(set(musica.acordes))
            diff = set(musica.acordes) - set(acordes)

            # somente as que tiverem interseção e as que forem
            # dos generos solicitados.
            if len(inter) > 0:
                similar = {
                        'id_unico_musica' : musica.id_unico_musica,
                        'id_artista' : musica.id_artista,
                        'id_musica' : musica.id_musica,
                        'nome_artista' : musica.nome_artista,
                        'nome_musica' : musica.nome_musica,
                        'popularidade' : musica.popularidade,
                        'acordes' : musica.acordes,
                        'genero' : musica.genero,
                        'url' : musica.url,
                        'diferenca' : list(diff),
                        'intersecao' : list(inter)
                }

                similares.append(similar)

    # ordenados por menor diferença, maior interseção e maior popularidade.
    return sorted(similares, key=lambda x: (len(x['diferenca']), -len(x['intersecao'])))

## Filtra a coleção de músicas por gênero.
def apply_filtro(musicas, generos_key):
    # filtra para melhor desempenho
    collection = []
    for genero in generos_key:
        if genero in generos:
            collection += genero_musicas[genero]
    return collection

@app.after_request
def add_header(response):
    response.headers['Access-Control-Allow-Origin'] = '*'
    return response

if __name__ == '__main__':
    app.run(debug=True)
