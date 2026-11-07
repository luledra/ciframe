# Pesquisa — Sequências de Acordes Customizadas

> Respostas às perguntas desta fase. O levantamento completo, com metodologia,
> números e referências, está em
> [`research/sequencias-customizadas.md`](../../../research/sequencias-customizadas.md).

## Perguntas que você precisa responder

### 1. Algoritmo de matching

Hoje não existe matching em tempo real. O frontend monta a lista de acordes
separada por vírgulas em `static/assets/js/controllers/sequencia.js:55-61` e a
envia como parâmetro `sequencia` em `sequencia.js:73` (ex.: `C,G,Am,F`). No
backend, `main.py:191` remove essas vírgulas com `.replace(',', '')`, gerando a
chave `CGAmF`. Essa chave é procurada no dicionário `sequencias`, definido em
`main.py:40-45`, que mapeia as 6 sequências para índices inteiros:

| Chave | Índice |
|---|---:|
| `BmGDA` | 0 |
| `CGAmF` | 1 |
| `EmG` | 2 |
| `CA7DmG7` | 3 |
| `GmF` | 4 |
| `CC7FFm` | 5 |

Se a chave existir, o índice é usado para filtrar pela tag `SEQ_FAMOSA`
(`main.py:190-197`, `main.py:203-223`). Sequência fora do dicionário retorna
`[]` imediatamente (`main.py:197`), sem tentar acordes.

A tag foi gerada por `scripts/generate_data_set.py:7-24`. A semântica efetiva é:
**a sequência aparece contiguamente na cifra E todos os acordes da música
pertencem ao vocabulário da sequência** (`scripts/generate_data_set.py:13-20`).
Portanto, na tag atual:

- **Ordem e adjacência importam** (`s in acorde`, linha 13).
- **Repetições do padrão são permitidas**; repetição de acorde dentro do padrão
  quebra a adjacência; qualquer acorde fora do vocabulário da sequência, em
  qualquer lugar da música, desqualifica (linhas 16-20).
- **Case**: a geração compara em minúsculas (linha 12); o dicionário de
  requisição é case-sensitive.
- **Não há normalização de grafia**: convivem `C#`/`Db`, `D#`/`Eb`, `F#`/`Gb`,
  acordes com barra e sufixos variados. `limpa_cifra` só trata espaços e `|`
  (`main.py:11-23`).

Para calcular em runtime é obrigatório usar `musica.cifra`, que é ordenada e
mantém repetições (`musica.py:16`); `musica.acordes` é `list(set(cifra))`, sem
ordem e sem repetições (`musica.py:17`).

Quatro definições foram medidas nos dados reais: A) subsequência contígua;
B) subsequência ordenada; C) inclusão de conjunto; D) regra do gerador
(contígua + vocabulário da música contido no da sequência). Números na tabela
da seção 2.

#### Exemplos de funcionamento do algoritmo atual

Todos os exemplos abaixo foram executados contra o app via `app.test_client()`
e usam a paginação de `TAM_PAGINA=100` (`main.py:35`, `main.py:226-228`); os
totais agregam todas as páginas:

| Entrada | Chave após `main.py:191` | Consulta em `main.py:40-45` | Saída observada |
|---|---|---|---|
| `GET /similares?sequencia=C,G,Am,F` | `CGAmF` | índice 1 | 296 músicas no total (3 páginas); página 1 com 100 itens |
| `GET /similares?sequencia=BmGDA` | `BmGDA` | índice 0 | 199 músicas no total (2 páginas); página 1 com 100 itens |
| `GET /similares?sequencia=Gm,F` | `GmF` | índice 4 | 7 músicas (1 página) |
| `GET /similares?sequencia=C,D` | `CD` | não existe | `[]` |
| `GET /similares?sequencia=c,g,am,f` | `cgamf` | não existe (chave é case-sensitive) | `[]` |

Para uma entrada válida, a resposta é uma string JSON (produzida por
`json.dumps`, não `jsonify`) com objetos no formato abaixo
(campos de `main.py:210-220`):

```
[
  {
    "id_unico_musica": "<id_artista>_<id_musica>",
    "id_artista": "...",
    "id_musica": "...",
    "nome_artista": "...",
    "nome_musica": "...",
    "popularidade": 12345,
    "acordes": ["...", "..."],
    "genero": "...",
    "url": "http://www.cifraclub.com.br/<id_artista>/<id_musica>"
  }
]
```

Exemplo real: `GET /similares?sequencia=Em,G` retorna 4 objetos; um deles tem
`id_unico_musica` igual a `marcelo-d2_mao-na-cabeca` e
`nome_musica` igual a `Mão Na Cabeça`. Já `GET /similares?sequencia=C,D`
retorna exatamente o corpo `[]`, porque `CD` não está no dicionário e o
`return` de `main.py:197` encerra o handler.

### 2. Validação da hipótese

Parsing do CSV replicando `main.py:49-98` e execução do endpoint real via
`app.test_client()` (todas as páginas, `TAM_PAGINA=100`) confirmaram:

| Idx | Sequência | Tag/endpoint | A contígua | B ordenada | C conjunto | D gerador |
|---:|---|---:|---:|---:|---:|---:|
| 0 | Bm G D A | 199 | 866 | 4.763 | 5.768 | 199 |
| 1 | C G Am F | 296 | 1.216 | 5.887 | 6.894 | 296 |
| 2 | Em G | 4 | 3.110 | 13.642 | 14.159 | 4 |
| 3 | C A7 Dm G7 | 5 | 96 | 427 | 582 | 5 |
| 4 | Gm F | 7 | 1.039 | 3.640 | 3.846 | 7 |
| 5 | C C7 F Fm | 3 | 132 | 280 | 365 | 3 |

- O endpoint real devolveu exatamente os conjuntos da tag: 0 faltantes e
  0 extras nos 6 casos.
- A regra D reproduziu exatamente os 6 conjuntos (0/0).
- A regra A contém todos os resultados atuais, mas adiciona 667, 920, 3.106,
  91, 1.032 e 129 extras, respectivamente. B e C adicionam ainda mais.
- Conclusão factual: das regras testadas, só D mantém os mesmos resultados das
  6 sequências; A/B/C produzem superconjuntos.

### 3. Banco de dados

Restrição: `Dockerfile` único e local-only (`docs/adr/0001-local-only-docker-deploy.md:9-16`;
`00-enunciado.md:60-65`). O `Dockerfile:1-12` usa `python:3.9-slim`, não declara
`VOLUME`, roda como root e mantém um único worker gunicorn por default.

Persistência testada com `python:3.9-slim`: arquivo gravado no container
sobrevive a `docker restart`, mas some após `docker rm` + container novo. Para
sobreviver à recriação é necessário volume nomeado ou bind mount.

Opções embarcadas viáveis:

- **SQLite** (`sqlite3`, stdlib): nenhuma dependência nova; imagem base
  verificada com SQLite 3.46.1; arquivo único; SQL/transações; concorrência por
  lock; schema/migração manual.
- **TinyDB**: `pip install tinydb`; arquivo JSON; exige alterar
  `requirements.txt` e rebuildar; sem SQL; concorrência fraca.
- **`shelve`/`dbm`** (stdlib): chave-valor; sem SQL; concorrência limitada.
- **DuckDB**: `pip install duckdb`; embarcado/colunar; wheel maior; arquivo
  único.
- **LMDB**: `pip install lmdb`; chave-valor memory-mapped; API de baixo nível.
- **JSON/CSV plano**: sem dependência, mas não é engine; exige escrita
  atômica/lock manual.

Bancos com processo/servidor separado (PostgreSQL, MySQL, MongoDB, Redis) ficam
fora do container único sem serviço adicional.

Implicação de caminho: o CSV está em `/app/data/top/dataset_final.csv`
(`Dockerfile:8`). Bind mount em `/app/data` cobre o CSV da imagem; volume
nomeado novo é inicializado com o conteúdo da imagem, mas atualizações
posteriores do CSV não chegam ao volume existente.

### 4. Frontend existente

Rota `#/porsequencia` em `static/assets/js/routes.js:17-21`, template
`static/templates/sequencia.html` e controller
`static/assets/js/controllers/sequencia.js`.

- O controller define **4 sequências hardcoded** em JS (`sequencia.js:2-31`) e
  as empilha em `vm.sequenciasFamosas` (`sequencia.js:33-37`).
- Mapeamento: `sequencia1` = Bm G D A (índice 0); `sequencia2` = C G Am F
  (índice 1); `sequencia3` = Gm F (índice 4); `sequencia4` = C C7 F Fm
  (índice 5). Faltam no JS as sequências 2 (Em G) e 3 (C A7 Dm G7) do backend.
- O template lista essas 4 sequências com `ng-repeat` e, no clique, chama
  `pesquisarPorSequencia(sequencia)` (`sequencia.html:6-8`).
- A busca monta `similares?sequencia=<acordes com vírgulas>`, opcionalmente com
  `&generos=...` (`sequencia.js:55-77`), e renderiza `vm.musics` com
  `orderBy:'-popularidade'` (`sequencia.html:41-58`).
- Os gêneros vêm da constante `GENEROS` (`app.js:6-58`, 51 itens), não de
  `GET /generos`. O backend tem 52 porque o CSV contém `R&B;`.
- A constante `RESTAPI` (`app.js:3-5`) aponta para `localhost:5003`, mas os
  controllers usam `apiUrl = ""` (requisições relativas); ela não é referenciada.
- **Não existe** chamada para buscar catálogo no backend, formulário de cadastro
  nem endpoint de catálogo de sequências (`main.py:101-201`).
- `ng-hide="music.diferenca.length"` (`sequencia.html:43`) não esconde os
  resultados de sequência, porque a resposta de sequência não inclui
  `diferenca` (`main.py:210-220`).

## Registro das descobertas

As referências de arquivo/linha e os números completos estão em
[`research/sequencias-customizadas.md`](../../../research/sequencias-customizadas.md).
Resumo: o matching atual é 100% baseado na tag pré-computada; a tag equivale à
regra D; sequências desconhecidas retornam `[]`; `musica.acordes` perde
ordem/repetição; o `Dockerfile` não tem volume; o frontend tem 4 sequências
hardcoded e nenhum cadastro/catálogo dinâmico.

## Trade-offs identificados

### Algoritmo

- **D (contígua + vocabulário contido)**: mantém exatamente os resultados das 6
  sequências atuais; é mais restritiva que a noção intuitiva de "o trecho
  aparece", pois uma música com acorde fora do vocabulário da sequência não
  entra.
- **A (subsequência contígua)**: leitura intuitiva de "o trecho aparece"; é
  superconjunto estrito dos resultados atuais (todos os atuais continuam, com
  extras). Usá-la para as 6 mudaria o conjunto de resultados.
- **B (subsequência ordenada)**: ignora adjacência; superconjunto maior que A.
- **C (inclusão de conjunto)**: ignora ordem; a mais permissiva e a que mais se
  afasta dos conjuntos atuais.
- **Normalização**: case-insensitive é o que a geração faz; enarmônicos,
  qualidades, barras e espaços não são normalizados hoje. Normalizar aumenta o
  alcance e precisa ser medido contra os conjuntos atuais.

### Banco

- SQLite: zero dependência nova, SQL/transações, arquivo único, schema manual.
- TinyDB: dependência nova, JSON simples, sem SQL, concorrência fraca.
- `shelve`/`dbm`: stdlib, chave-valor, sem SQL, concorrência limitada.
- DuckDB: dependência nova, colunar, mais pesado.
- LMDB: dependência nova, chave-valor de baixo nível.
- JSON/CSV plano: sem dependência, mas sem engine/atomicidade pronta.
- Em todas: `docker restart` preserva; `docker rm`/recriação só preserva com
  volume.

### Frontend

- Manter lista estática: preserva o comportamento, mas mantém 4 × 6 e não
  reflete catálogo cadastrado.
- Buscar catálogo no backend: exige endpoint novo e alteração de
  controller/template; sem build, edição direta de JS/HTML.
- Cadastro: não há precedente na página; o template atual não tem formulário
  nem campo de acordes.
- Gêneros: a página usa constante JS de 51 itens; o backend tem 52 (`R&B;`).
