# Pesquisa — Sequências de Acordes Customizadas

> Documento de pesquisa do código como ele está hoje. Não contém proposta de
> implementação nem decisão de projeto; as opções e trade-offs estão registrados
> no fim para alimentar a fase de proposta.

## Resumo

Hoje o endpoint `GET /similares?sequencia=...` não calcula sequência alguma em
tempo real: ele converte o parâmetro em uma chave de um dicionário de 6
sequências hardcoded (`main.py:40-45`), obtém um id inteiro e filtra músicas pela
tag pré-computada `SEQ_FAMOSA` (`main.py:190-197`, `main.py:203-223`). A tag foi
gerada por `scripts/generate_data_set.py:7-24` com uma regra mais restritiva que
"a sequência aparece na música": além de exigir a sequência contígua, exige que
**todo** acorde da música pertença ao vocabulário da sequência. Rodando essa
regra contra `data/top/dataset_final.csv`, ela reproduz exatamente os conjuntos
atuais (199, 296, 4, 5, 7 e 3 músicas); já uma busca por subsequência contígua
simples encontra todos esses mesmos resultados, mas acrescenta centenas ou
milhares de músicas extras. Sequências fora do dicionário retornam `[]`
imediatamente (`main.py:197`), e `musica.acordes` é uma lista sem ordem e sem
repetições (`musica.py:17`), enquanto a ordem original só existe em
`musica.cifra`. No frontend, `#/porsequencia` usa uma lista de 4 sequências
hardcoded no JavaScript (`static/assets/js/controllers/sequencia.js:2-37`), sem
nenhuma chamada para obter catálogo e sem formulário de cadastro. Para
persistência, o container atual não declara volume (`Dockerfile:1-12`), então
arquivos gravados sobrevivem a `docker restart`, mas somem ao remover/recriar o
container; bancos embarcados viáveis incluem SQLite (stdlib, verificado no
`python:3.9-slim`), TinyDB, `shelve`/`dbm`, DuckDB e LMDB, com implicações
distintas de dependência e volume.

## Método

- Leitura integral de `main.py`, `musica.py`, `README.md`, `AGENTS.md`,
  `Dockerfile`, `requirements.txt`, `docs/adr/0001-local-only-docker-deploy.md`,
  `docs/adr/0003-lift-frontend-freeze.md`,
  `docs/features/sequencias-customizadas/00-enunciado.md`,
  `docs/features/sequencias-customizadas/01-research.md`,
  `static/templates/sequencia.html`,
  `static/assets/js/controllers/sequencia.js`,
  `static/assets/js/app.js`, `static/assets/js/routes.js`,
  `static/index.html` e `scripts/generate_data_set.py`.
- Parsing do CSV replicando o código de `main.py:49-98`, inclusive
  `limpa_cifra` (`main.py:11-23`).
- Execução de scripts de análise sobre as 67.585 linhas de
  `data/top/dataset_final.csv`.
- Execução do app real via `app.test_client()` do Flask para consultar
  `/similares` e comparar as páginas retornadas com os conjuntos de tag.
- Teste de persistência em container Docker com `python:3.9-slim`.

## 1. Algoritmo de matching

### 1.1 Como o matching funciona hoje

O dicionário de sequências está em `main.py:40-45`:

| Chave (sem vírgulas) | Índice | Acordes |
|---|---|---|
| `BmGDA` | 0 | Bm, G, D, A |
| `CGAmF` | 1 | C, G, Am, F |
| `EmG` | 2 | Em, G |
| `CA7DmG7` | 3 | C, A7, Dm, G7 |
| `GmF` | 4 | Gm, F |
| `CC7FFm` | 5 | C, C7, F, Fm |

No handler de `/similares`, o parâmetro `sequencia` é lido, tem as vírgulas
removidas e é consultado nesse dicionário (`main.py:170-197`). Se a chave existir,
o índice é passado para `get_similares_por_sequencia` (`main.py:203-223`), que
inclui a música quando `str(id_seq)` está na lista `musica.seqs_famosas`
(`main.py:209`). A lista vem da coluna 7 do CSV, dividida por `;`
(`main.py:63`, `main.py:69-72`).

Se a chave **não** existir, o `return` de `main.py:197` encerra a função com a
lista vazia. Portanto, hoje uma sequência fora das 6 não é buscada por
interseção de acordes nem por qualquer outro critério: ela retorna `[]`
(confirmado com `GET /similares?sequencia=C,D`, `GET /similares?sequencia=Bm,G`,
`GET /similares?sequencia=c,g,am,f` e `GET /similares?sequencia=G`, todos com
corpo `[]`).

### 1.2 Proveniência da tag `SEQ_FAMOSA`

A tag não é calculada em `main.py`; ela já vem no CSV. O script que a gerou é
`scripts/generate_data_set.py` (Python 2, não executável no Python 3 atual por
usar `print` como statement) e sua regra está em:

- `scripts/generate_data_set.py:8` — mesmas 6 sequências, em minúsculas.
- `scripts/generate_data_set.py:12` — `acorde = acorde.lower()`, ou seja, a
  comparação é case-insensitive.
- `scripts/generate_data_set.py:13` — `if s in acorde`: a sequência (com `;`
  entre acordes) precisa aparecer como substring da cifra inteira, o que impõe
  **ordem e adjacência**.
- `scripts/generate_data_set.py:16-20` — segundo filtro: para **cada** acorde
  `l` da música, `l` precisa estar entre os acordes `tokens` da sequência. Ou
  seja, a música não pode ter nenhum acorde fora do vocabulário da sequência.
- `scripts/generate_data_set.py:22-23` e `86-88` — o índice é serializado; o
  `''.join(...)` concatenaria múltiplos índices, mas no dataset atual só existem
  valores `'0'`, `'1'`, `'2'`, `'3'`, `'4'` e `'5'`, sem concatenação.

Semântica efetiva da tag: **a sequência aparece contiguamente na cifra e o
conjunto de acordes usados na música é subconjunto do conjunto de acordes da
sequência**. Exemplos de músicas marcadas (obtidos do dataset):

- índice 0 (Bm G D A): `5-seconds-of-summer_independence-day` — a cifra tem 102
  acordes, começa com `Bm G Bm A G Bm G A ...` e contém `Bm G D A` contíguo
  (verificado; o trecho exibido é só o começo).
- índice 1 (C G Am F): `5-seconds-of-summer_broken-pieces` —
  `C G Am F C G Am F C G Am F C G Am F`.
- índice 2 (Em G): `marcelo-d2_mao-na-cabeca` — `Em G Em G`.
- índice 3 (C A7 Dm G7): `benito-di-paula_bendito-seja` —
  `C A7 Dm G7 C A7 Dm G7 ...`.
- índice 4 (Gm F): `asa-de-aguia_maraja` — `Gm F Gm F`.
- índice 5 (C C7 F Fm): `claudia-leitte_bem-vindo-amor` —
  `C C7 F Fm C C7 F Fm ...`.

### 1.3 Estruturas de dados disponíveis em runtime

Cada linha do CSV vira um `Musica` (`main.py:69-72`). Em `musica.py:16-18`:

- `self.cifra = cifra` — lista **ordenada** de acordes, com repetições, gerada
  por `limpa_cifra` (`main.py:11-23`).
- `self.acordes = list(set(cifra))` — lista **sem ordem e sem repetições**.
- `self.seqs_famosas = seqs_famosas` — lista de tags.

Consequência: qualquer matching que dependa de ordem/adjacência/repetição precisa
usar `musica.cifra`; `musica.acordes` só serve para comparação de conjunto.

O parsing do CSV (`main.py:49-98`) também define:

- `TAM_PAGINA = 100` (`main.py:35`), com paginação em `main.py:226-228`.
- `generos` é um `set` convertido em lista (`main.py:38`, `main.py:92`) e
  `genero_musicas` mapeia gênero para músicas ordenadas por popularidade
  (`main.py:82-85`, `main.py:95-96`).
- `musicas` é um `OrderedDict` global ordenado por popularidade
  (`main.py:88-89`), mas a busca por sequência não ordena o resultado: ela
  concatena listas por gênero em `apply_filtro` (`main.py:266-272`), na ordem de
  iteração do `set` de gêneros.

### 1.4 Repetições, ordem e normalização na tag atual

- **Ordem/adjacência importam**: a checagem é por substring da string
  `;`-separada (`scripts/generate_data_set.py:13`).
- **Repetições do padrão são permitidas**: as músicas marcadas repetem a
  sequência várias vezes (ex.: `C G Am F C G Am F ...`).
- **Repetição de acorde dentro do padrão quebra a adjacência**: por exemplo,
  `C G G Am F` não contém `C G Am F` contíguo.
- **Acorde fora do vocabulário da sequência, em qualquer lugar da música,
  desqualifica**: por causa do segundo filtro
  (`scripts/generate_data_set.py:16-20`), não basta a sequência aparecer; a
  música inteira precisa usar só acordes da sequência.
- **Case**: a geração compara tudo em minúsculas (`scripts/generate_data_set.py:12`),
  mas o dicionário de requisição é case-sensitive: `sequencia=Bm,G,D,A` encontra a
  chave `BmGDA`; `sequencia=bmgda` ou `c,g,am,f` não encontra e retorna `[]`.
- **Variações de escrita não são normalizadas**: o dataset contém grafias
  alternativas convivendo (ex.: `C#` 23.902 ocorrências e `Db` 4.084; `D#`
  12.146 e `Eb` 23.626; `F#` 49.288 e `Gb` 1.401; `A#` 10.134 e `Bb` 59.730),
  acordes com barra (3.834 tokens distintos com `/`) e sufixos variados
  (`7`, `7M`, `9`, `4/7`, `(b5 9)`, etc.). `limpa_cifra` só trata espaços e
  tablaturas com `|` (`main.py:11-23`); não faz equivalência enarmônica nem
  normalização de qualidade.

### 1.5 Candidatos de algoritmo medidos nos dados reais

Foram comparados quatro critérios, todos sobre `musica.cifra` com tokens
aparados e comparados em minúsculas:

- **A — subsequência contígua**: `seq` aparece como bloco consecutivo de
  acordes.
- **B — subsequência ordenada**: os acordes de `seq` aparecem na ordem, não
  necessariamente juntos.
- **C — inclusão de conjunto**: todos os acordes de `seq` aparecem na música,
  sem importar ordem.
- **D — regra do gerador**: A **e** todos os acordes da música pertencem ao
  vocabulário de `seq` (equivalente a `scripts/generate_data_set.py:13-20`).

Resultados (número de músicas):

| Idx | Sequência | Tag atual | A contígua | B ordenada | C conjunto | D gerador |
|---:|---|---:|---:|---:|---:|---:|
| 0 | Bm G D A | 199 | 866 | 4.763 | 5.768 | 199 |
| 1 | C G Am F | 296 | 1.216 | 5.887 | 6.894 | 296 |
| 2 | Em G | 4 | 3.110 | 13.642 | 14.159 | 4 |
| 3 | C A7 Dm G7 | 5 | 96 | 427 | 582 | 5 |
| 4 | Gm F | 7 | 1.039 | 3.640 | 3.846 | 7 |
| 5 | C C7 F Fm | 3 | 132 | 280 | 365 | 3 |

Para A, B e C, **nenhuma música marcada ficou de fora** (missing = 0 em todos
os casos), mas todas produziram extras. Para D, os conjuntos foram exatamente
iguais aos da tag (0 extras, 0 faltantes) nos 6 casos. O mesmo resultado de D vale
tanto sobre a coluna bruta `CIFRA` quanto sobre a saída de `limpa_cifra`: as 83
linhas em que os dois diferem não alteram nenhum dos 6 conjuntos.

### 1.6 Comportamento do endpoint para sequência desconhecida e bordas

- `main.py:190-197`: quando `sequencia` não está em `sequencias`, a função
  retorna `json.dumps([])` (`main.py:197`). Não há fallback para busca por
  acordes.
- `main.py:191` remove apenas vírgulas; espaços, hífens e diferenças de caixa
  permanecem e impedem o match com as chaves.
- `main.py:194-196`: mesmo para as 6 chaves, o filtro de gênero é aplicado antes
  da tag (`get_similares_por_sequencia`, `main.py:203-223`).
- A resposta de sequência contém `id_unico_musica`, `id_artista`, `id_musica`,
  `nome_artista`, `nome_musica`, `popularidade`, `acordes`, `genero` e `url`
  (`main.py:210-220`); não contém `diferenca` nem `intersecao`, diferentemente da
  busca por acordes (`main.py:246-258`).

## 2. Validação da hipótese

### 2.1 O que foi comparado

1. Conjunto atual: músicas em que `str(i) in musica.seqs_famosas`, lidas do CSV
   como `main.py:63-72` faz.
2. Conjunto do endpoint real: todas as páginas de
   `GET /similares?sequencia=<acordes>&pagina=N` via `app.test_client()`,
   agregadas até a página vazia.
3. Conjunto de cada algoritmo candidato sobre `musica.cifra`.

### 2.2 Resultado

- O endpoint real devolveu exatamente os conjuntos de tag para as 6 sequências,
  considerando todas as páginas: 199, 296, 4, 5, 7 e 3 músicas,
  respectivamente, com 0 faltantes e 0 extras em todos os casos.
- A regra D (contígua + vocabulário da música contido no vocabulário da
  sequência) reproduziu exatamente os mesmos 6 conjuntos.
- A regra A (subsequência contígua simples) **não reproduz** os mesmos
  resultados: ela contém todos os resultados atuais, mas adiciona 667, 920,
  3.106, 91, 1.032 e 129 músicas extras, respectivamente.
- As regras B e C adicionam ainda mais extras (tabela em 1.5).

Conclusão factual: se o critério for "as 6 sequências produzem exatamente os
mesmos resultados de hoje", a única das quatro regras testadas que satisfaz isso
é a regra D — a mesma que gerou a tag. Uma busca por "a sequência aparece na
música" em sentido mais intuitivo (A/B/C) produz um superconjunto dos resultados
atuais, não o mesmo conjunto.

### 2.3 Detalhes que afetam a comparação

- A paginação usa `TAM_PAGINA = 100` (`main.py:35`, `main.py:226-228`); as
  sequências 0 e 1 têm 199 e 296 resultados e exigem 2 e 3 páginas.
- O endpoint sem `generos` usa todos os gêneros (`main.py:179-182`); com
  `generos=Rock`, por exemplo, o conjunto muda.
- A ordem da lista não é globalmente por popularidade: `apply_filtro`
  (`main.py:266-272`) concatena listas por gênero. O `orderBy:'-popularidade'`
  do frontend (`static/templates/sequencia.html:42`) reordena só na exibição.
- `main.py:53` remove a substring `NA` de toda a linha antes de dividir; o
  dataset não tem tokens de acorde iguais a `NA`, mas esse comportamento existe.
- `main.py:63` transforma tag vazia em `['']`; não afeta os conjuntos acima.

## 3. Banco de dados embarcados

### 3.1 Restrição de deploy

`docs/adr/0001-local-only-docker-deploy.md:9-16` fixa um único `Dockerfile`
local, sem plataforma de nuvem, e diz que o backend mantém a arquitetura de
`main.py` com CSV em memória. O enunciado repete a restrição de container único,
sem serviços externos adicionais (`docs/features/sequencias-customizadas/00-enunciado.md:60-65`).
Isso exclui, para efeito desta pesquisa, bancos que exigem processo/serviço
separado (PostgreSQL, MySQL, MongoDB, Redis etc.) como opção "embarcada no mesmo
container".

### 3.2 `Dockerfile` atual e persistência

`Dockerfile:1-12`:

- base `python:3.9-slim`;
- `WORKDIR /app`;
- instala somente `requirements.txt` (`Flask==3.1.3`, `gunicorn==23.0.0`);
- `COPY . .` copia o código e o CSV para dentro da imagem;
- expõe 8080 e roda `gunicorn --bind 0.0.0.0:8080 main:app`;
- não declara `VOLUME`, não declara `USER` (roda como root) e não configura
  múltiplos workers (o default do gunicorn é 1 worker síncrono).

Persistência observada em teste com `python:3.9-slim`:

- arquivo criado no filesystem do container **sobrevive** a
  `docker restart` (stop/start do mesmo container);
- arquivo **desaparece** ao `docker rm` e criar um container novo.

Portanto, gravar um arquivo de banco em `/app` atende a "reiniciar o servidor"
no sentido de `docker restart`, mas não atende a remover/recriar o container. Para
isso é necessário volume nomeado ou bind mount.

### 3.3 Opções embarcadas

| Opção | Dependência | Implicação no `Dockerfile`/`requirements.txt` | Persistência | Observações |
|---|---|---|---|---|
| SQLite (`sqlite3`) | stdlib | Nenhuma dependência nova; imagem `python:3.9-slim` verificada com SQLite 3.46.1 | Arquivo no filesystem; mesma regra de restart/recreate | Relacional, SQL, transações; concorrência por lock; schema/migrações manuais |
| TinyDB | `pip install tinydb` | Adicionar em `requirements.txt` e rebuildar | Arquivo JSON; mesma regra | Document store simples; leitura/escrita do arquivo inteiro; concorrência fraca |
| `shelve`/`dbm` | stdlib | Nenhuma dependência nova | Arquivo(s) no filesystem; mesma regra | Chave-valor; sem SQL; concorrência limitada |
| DuckDB | `pip install duckdb` | Adicionar em `requirements.txt` e rebuildar | Arquivo no filesystem; mesma regra | Embarcado/colunar; wheel maior que SQLite/TinyDB; sem serviço |
| LMDB | `pip install lmdb` | Adicionar em `requirements.txt` e rebuildar | Arquivo(s) no filesystem; mesma regra | Chave-valor memory-mapped; API de mais baixo nível |
| JSON/CSV plano | nenhuma | Nenhuma dependência nova | Arquivo no filesystem; mesma regra | Não é engine de banco; exige escrita atômica/lock manual |
| PostgreSQL/MySQL/MongoDB/Redis | cliente + servidor | Serviço/processo adicional | Depende do serviço | Fora do escopo de "container único sem serviço adicional" da ADR 0001 |

### 3.4 Implicações de caminho e volume

- O CSV está em `/app/data/top/dataset_final.csv` e é copiado para a imagem por
  `COPY . .` (`Dockerfile:8`).
- Um bind mount em `/app/data` **cobre** o diretório copiado na imagem; o CSV
  deixa de ser o da imagem. Um volume nomeado novo é inicializado com o conteúdo
  da imagem, mas atualizações posteriores do CSV na imagem não chegam ao volume
  já existente.
- Um caminho de banco fora de `/app/data` não sofre esse shadowing; qualquer
  caminho dentro de `/app` é gravável hoje porque o container roda como root.
- Sem volume, recriar o container (`docker rm` + `docker run`) perde o banco,
  independentemente da tecnologia escolhida.

## 4. Frontend existente

### 4.1 Rota e ligação

- Rota `#/porsequencia` em `static/assets/js/routes.js:17-21`, com
  `templateUrl: "templates/sequencia.html"`, `SequenciaController` e
  `controllerAs: "Sequencia"`.
- `static/index.html:145` carrega `assets/js/controllers/sequencia.js`; a página
  é um SPA AngularJS 1.4.9 sem build, servida por `static_proxy`
  (`main.py:109-112`) e `index` (`main.py:101-103`).

### 4.2 Catálogo hardcoded no JavaScript

`static/assets/js/controllers/sequencia.js:2-31` define 4 objetos
(`sequencia1`..`sequencia4`), todos com `'index': 1` (valor não usado na busca),
cada um com uma lista de `{acorde, cor}`. Eles são empilhados em
`vm.sequenciasFamosas` em `sequencia.js:33-37`.

Mapeamento com o backend:

| JS | Acordes | Índice no backend |
|---|---|---:|
| `sequencia1` | Bm, G, D, A | 0 |
| `sequencia2` | C, G, Am, F | 1 |
| `sequencia3` | Gm, F | 4 |
| `sequencia4` | C, C7, F, Fm | 5 |

Não há no JS as sequências de índice 2 (`Em, G`) e 3 (`C, A7, Dm, G7`), que
existem em `main.py:40-45`.

### 4.3 Fluxo de busca da página

1. O template lista `Sequencia.sequenciasFamosas` com `ng-repeat` e, no clique,
   chama `Sequencia.pesquisarPorSequencia(sequencia)`
   (`static/templates/sequencia.html:6-8`).
2. O controller monta a string de acordes separada por vírgulas em
   `createChordsString` (`sequencia.js:55-61`) e faz
   `GET similares?sequencia=<acordes>` (`sequencia.js:72-77`).
3. Se `vm.meuGenero` estiver preenchido, acrescenta `&generos=<gênero>`
   (`sequencia.js:74-76`). O select de gênero chama a mesma função sem argumento
   (`sequencia.html:24-30`), reutilizando `vm.minhaSequencia`.
4. A resposta é atribuída a `vm.musics` (`sequencia.js:83`); o template renderiza
   os cards com `orderBy:'-popularidade'` (`sequencia.html:41-58`) e abre
   `music.url` em nova aba (`sequencia.js:97-99`).
5. `ng-hide="music.diferenca.length"` (`sequencia.html:43`) existe no template,
   mas a resposta de sequência não tem `diferenca` (`main.py:210-220`); em
   Angular, o valor é `undefined` e a expressão é falsa, então os cards não são
   escondidos por esse filtro.

### 4.4 O que a página não tem hoje

- Não existe chamada HTTP para buscar um catálogo de sequências; a lista é
  exclusivamente a constante JS (`sequencia.js:2-37`).
- Não existe formulário/campo para cadastrar sequência; o template só tem a
  lista, o select de gênero e a área de resultados
  (`static/templates/sequencia.html` inteiro, 63 linhas).
- Não existe endpoint de catálogo de sequências no backend: as rotas são `/`,
  `/<path:path>`, `/search`, `/musicas`, `/generos`, `/acordes`,
  `/musica/<m_id>/` e `/similares` (`main.py:101-201`).
- `static/assets/js/app.js:3-5` define a constante `RESTAPI` com
  `http://localhost:5003`, mas os controllers de sequência, acordes e música
  usam `var apiUrl = ""` (`sequencia.js:72`, `acordes.js:91`, `musica.js:12`), ou
  seja, requisições relativas à origem atual. A constante `RESTAPI` não é
  referenciada.
- Os gêneros do select vêm da constante `GENEROS` em `app.js:6-58` (51 itens),
  não de `GET /generos`. O backend tem 52 gêneros porque o CSV contém `R&B;`
  (com ponto e vírgula) enquanto o JS tem `"R&B"`; os demais coincidem.

## 5. Fluxos entre componentes

### 5.1 Inicialização do backend

`main.py:49-98` lê `data/top/dataset_final.csv` uma única vez no import:

1. Remove aspas, `NA` e o último caractere de cada linha (`main.py:53`).
2. Divide por vírgula usando os índices fixos `main.py:25-34`.
3. Converte `CIFRA` em lista ordenada via `limpa_cifra` (`main.py:58-61`).
4. Divide `SEQ_FAMOSA` por `;` (`main.py:63`).
5. Cria `Musica` (`main.py:69-72`), que calcula `acordes = list(set(cifra))` e
   `id_unico_musica = '<id_artista>_<id_musica>'` (`musica.py:16-22`).
6. Popula `musicas_dict`, `acordes`, `genero_musicas` (`main.py:74-85`).
7. Ordena `musicas` por popularidade (`main.py:88-89`) e converte `generos` em
   lista (`main.py:92`).

### 5.2 Busca por sequência (fluxo atual)

```
Browser (#/porsequencia)
  -> SequenciaController.pesquisarPorSequencia  (sequencia.js:63)
  -> GET similares?sequencia=Bm,G,D,A[&generos=...][&pagina=N]
  -> main.get_similares                       (main.py:170-201)
       -> remove vírgulas                     (main.py:191)
       -> sequencias[chave] -> id             (main.py:194-195)
       -> get_similares_por_sequencia         (main.py:203-223)
            -> apply_filtro por gênero        (main.py:205, 266-272)
            -> str(id) in musica.seqs_famosas (main.py:209)
       -> get_pagina                          (main.py:196, 226-228)
  <- json.dumps(lista) como string, Content-Type text/html
  -> vm.musics -> cards no template             (sequencia.js:83, sequencia.html:41-58)
```

### 5.3 Estado atual para sequência desconhecida

```
GET /similares?sequencia=<qualquer coisa fora das 6>
  -> main.get_similares
       -> chave não está em sequencias
       -> return json.dumps([])   (main.py:197)
```

## 6. Trade-offs identificados

Esta seção apenas registra opções e consequências observáveis; não escolhe uma
alternativa.

### 6.1 Definição de "a sequência aparece na música"

- **Regra D (contígua + vocabulário contido)** — única testada que mantém
  exatamente os resultados das 6 sequências atuais, porque replica a geração da
  tag. Consequência: para uma sequência nova, uma música com qualquer acorde
  fora do vocabulário da sequência não aparece, mesmo contendo o trecho.
- **Regra A (subsequência contígua)** — corresponde à leitura mais direta de
  "o trecho aparece na música"; é superconjunto estrito dos resultados atuais
  (todos os atuais continuam, com centenas/milhares de extras para as mesmas 6
  sequências). Exigiria tratar a diferença como mudança de comportamento ou
  manter as 6 originais pela tag e as novas pelo cálculo.
- **Regra B (subsequência ordenada)** — ignora adjacência; superconjunto ainda
  maior que A.
- **Regra C (inclusão de conjunto)** — ignora ordem; é a mais permissiva das
  testadas e a que mais se afasta dos conjuntos atuais.
- **Normalização**: comparar case-insensitive é o que a geração da tag faz;
  não há normalização de enarmônicos (`C#`/`Db`), qualidades (`7M`, `maj7`),
  barras (`C/E`) ou espaços. Qualquer decisão de normalizar aumenta o alcance do
  matching e precisa ser medida contra os conjuntos atuais.
- **Estrutura usada**: ordem/repetição só existem em `musica.cifra`;
  `musica.acordes` é `list(set(...))` (`musica.py:17`).

### 6.2 Banco embarcado

- **SQLite**: zero dependências novas; imagem base já tem o módulo e a lib
  (verificado); arquivo único; SQL/transações; concorrência por lock; exige
  schema/migração manual; Dockerfile só mudaria se fosse declarado volume.
- **TinyDB**: dependência Python pequena; formato JSON legível; sem SQL;
  escrita do arquivo inteiro; exige rebuild da imagem por `requirements.txt`.
- **`shelve`/`dbm`**: stdlib; chave-valor; sem SQL; arquivos múltiplos/opacos;
  concorrência limitada.
- **DuckDB**: dependência Python com wheel; colunar; mais pesado que as opções
  anteriores; arquivo único; sem serviço.
- **LMDB**: dependência Python; chave-valor memory-mapped; API de baixo nível;
  arquivo(s).
- **JSON/CSV plano**: nenhuma dependência; não é engine; exige controle manual
  de escrita atômica e concorrência.
- Em todas as opções de arquivo, a diferença entre `docker restart` e
  `docker rm`/`docker run` é a mesma: só volume nomeado/bind mount garante
  sobrevivência à recriação do container.

### 6.3 Frontend

- **Manter a lista estática** preserva o comportamento atual, mas mantém a
  divergência 4 (JS) × 6 (backend) e não reflete catálogo cadastrado.
- **Buscar o catálogo no backend** exige um endpoint novo (não existe hoje) e
  alteração no controller/template; a página continua sem build, editando
  JS/HTML diretamente.
- **Cadastro de sequência** não tem precedente na página; o template atual não
  tem formulário nem campo de entrada de acordes (só a lista de sequências, o
  select de gênero e os resultados).
- **Gêneros**: a página usa a constante `GENEROS` (`app.js:6-58`), que tem 51
  itens e não inclui `R&B;` do CSV; o backend tem 52. Alterar essa fonte é uma
  decisão separada da persistência de sequências.

## Apêndice — números do dataset usados na pesquisa

- Linhas de dados em `data/top/dataset_final.csv` (após o cabeçalho): 67.585.
- Linhas com coluna `SEQ_FAMOSA` não vazia: 514.
- Distribuição das tags: `0`=199, `1`=296, `2`=4, `3`=5, `4`=7, `5`=3.
- Gêneros distintos no CSV: 52 (inclui `R&B;`).
- Tokens de acorde brutos distintos: 6.736.
- Total de acordes nas cifras após `limpa_cifra`: 3.505.331.
- Tamanho da cifra por música (após `limpa_cifra`): mínimo 0, mediana 48,
  máximo 2.065.
- Linhas em que a coluna `CIFRA` bruta difere da saída de `limpa_cifra`: 83
  (6 com `|`, 26 com espaços internos).
- Tamanho do arquivo: 16 MB.

### Comandos de verificação executados

- Parsing e contagem do CSV com o mesmo algoritmo de `main.py:49-98`.
- Comparação de conjuntos `tag` × A/B/C/D para as 6 sequências.
- `app.test_client()` para `/similares?sequencia=...` em todas as páginas e
  comparação com `musica.seqs_famosas`.
- `docker run --rm python:3.9-slim python -c "import sqlite3; ..."` para
  confirmar a presença do SQLite na imagem base.
- Container `python:3.9-slim` com arquivo gravado, `docker restart`, leitura do
  arquivo e recriação do container para confirmar o comportamento de
  persistência.
