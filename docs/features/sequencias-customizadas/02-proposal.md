# Proposta — Sequências de Acordes Customizadas

## Abordagem escolhida

### Algoritmo de matching

Fica definida uma única regra de matching, aplicada em runtime a **todas** as
sequências do catálogo (as 6 originais e as novas). Uma música é compatível com
uma sequência quando as duas condições abaixo valem:

1. **Adjacência com ordem:** a lista de acordes da sequência aparece como um
   bloco contíguo em `musica.cifra` (`musica.py:16`), respeitando ordem e
   repetições. A comparação é feita token a token, e não por substring.
2. **Vocabulário contido:** todo acorde usado na música pertence ao conjunto de
   acordes da sequência. Ou seja, `set(musica.cifra) ⊆ set(sequencia.acordes)`.

Essa é a regra **D** medida na pesquisa (`research/sequencias-customizadas.md`,
seções 1.5 e 2.2). Ela é a única das quatro regras testadas que reproduz
exatamente os conjuntos atuais das 6 sequências (0 faltantes e 0 extras em todos
os casos), o que satisfaz o critério de regressão do enunciado. Por isso o
`SEQ_FAMOSA` deixa de ser consultado na busca: as 6 sequências passam a ser
linhas semeadas no banco e o matching é sempre calculado.

Detalhes de normalização, deliberadamente mínimos:

- Tokens são aparados (`strip`) e tokens vazios são descartados.
- A comparação é **case-insensitive** (mesma decisão do gerador da tag,
  `scripts/generate_data_set.py:12`); a grafia original é preservada para
  exibição. Hoje o dicionário de requisição é case-sensitive (`main.py:194`),
  então esta é uma mudança de contrato de entrada: passamos a aceitar
  `c,g,am,f` e `C,G,Am,F`. Isso **não altera** os resultados das 6 sequências:
  a tag foi gerada com comparação em minúsculas e a regra D medida também
  compara em minúsculas, reproduzindo os mesmos conjuntos (0/0).
- A chave canônica é `','.join(acorde.lower() ...)`, o que torna a busca
  insensível a espaços e caixa.
- A entrada de `GET /similares?sequencia=...` passa a ser **somente** a forma
  canônica com vírgulas (ex.: `C,G,Am,F`). O formato antigo sem vírgulas (ex.:
  `CGAmF`) deixa de ser suportado e retorna `[]`, como qualquer sequência
  inexistente. Isso não altera os resultados das 6 no formato usado pelo
  frontend, mas é uma mudança explícita de contrato da API.
- **Fora do escopo:** equivalência enarmônica (`C#`/`Db`), normalização de
  qualidades (`7M`/`maj7`), acordes com barra e outras grafias. A pesquisa
  mostra que normalizar mudaria os conjuntos atuais e exigiria nova medição.

A implementação deve varrer `musica.cifra` (ordenada e com repetições), nunca
`musica.acordes` (`musica.py:17`), que perde ordem e repetição.

### Banco de dados

**SQLite** via `sqlite3` da stdlib.

- Zero dependência nova: a imagem `python:3.9-slim` já traz SQLite 3.46.1
  (verificado na pesquisa, seção 3.3).
- Arquivo único, com SQL, transações e restrição `UNIQUE`, o que cobre o
  catálogo aberto e a deduplicação sem lógica manual de lock/atomicidade.
- O arquivo fica em `/app/instance/sequencias.db`, **fora de `/app/data`**, para
  não sombrear o CSV copiado pela imagem (`Dockerfile:8`).
- O `Dockerfile` passa a declarar `VOLUME /app/instance`. Sem volume, o banco
  sobrevive a `docker restart`, mas não a `docker rm` + container novo
  (pesquisa, seção 3.2).
- O app continua com um único worker gunicorn por default (`Dockerfile:12`);
  ainda assim, habilitar `PRAGMA journal_mode=WAL` e usar transações curtas
  deixa a escrita segura caso o número de workers cresça.
- Schema e seed são criados de forma idempotente na inicialização, no mesmo
  momento em que o CSV é carregado.

Alternativas descartadas: TinyDB e DuckDB exigem dependência nova e rebuild;
`shelve`/`dbm` não têm SQL nem transações; JSON/CSV plano exigiria escrita
atômica e lock manuais; PostgreSQL/MySQL/MongoDB/Redis violam o container único
sem serviço adicional fixado pela ADR 0001.

### Esquema de dados (alto nível)

Uma única tabela `sequencias`:

| Campo | Tipo | Observação |
|---|---|---|
| `id` | `INTEGER PRIMARY KEY AUTOINCREMENT` | identificador interno |
| `acordes_json` | `TEXT NOT NULL` | array JSON na ordem cadastrada |
| `chave_canonica` | `TEXT NOT NULL UNIQUE` | acordes em minúsculas, separados por vírgula |
| `origem` | `TEXT NOT NULL` | `seed` para as 6, `custom` para novas |
| `criado_em` | `TEXT NOT NULL` | timestamp UTC |

O seed insere as 6 sequências de `main.py:40-45` com `origem='seed'` e
`chave_canonica` preenchida com os acordes separados por vírgula. O `UNIQUE` em
`chave_canonica` garante que não existam duplicatas; um `POST` repetido é
tratado de forma idempotente (ver API).

### API

Todos os endpoints continuam retornando `json.dumps(...)` como string, não
`jsonify` (convenção do projeto).

**`GET /sequencias`** — lista o catálogo, ordenado por `id`:

```
[
  {"id": 1, "acordes": ["Bm","G","D","A"],
   "origem": "seed", "criado_em": "..."},
  ...
]
```

**`POST /sequencias`** — cadastro anônimo, corpo JSON:

```
{"acordes": ["C","G","Am","F"]}
```

- Também aceita `"acordes": "C,G,Am,F"` para facilitar o formulário.
- Validação: lista não vazia após `strip`, no máximo 16 acordes, cada acorde
  não vazio.
- Normaliza para `chave_canonica`; se a chave já existir, devolve **200** com o
  registro existente e `"duplicada": true` (idempotente, sem criar linha nova).
- Criação nova devolve **201** com o registro criado.
- Payload inválido devolve **400** com `{"erro": "..."}`.
- O cadastro é aberto: sem login, sem autenticação.

**`GET /similares?sequencia=...`** — mantém o formato de resposta e os
parâmetros `&generos=` e `&pagina=`; a entrada de `sequencia` passa a exigir
vírgulas. As mudanças são:

- Resolve a sequência pelo catálogo usando somente a `chave_canonica`
  (acordes separados por vírgula, comparados sem diferenciar caixa). A forma
  concatenada sem vírgulas não é mais aceita e retorna `[]`.
- Aplica a regra D em `musica.cifra`, reutiliza `apply_filtro`
  (`main.py:266-272`) e `get_pagina` (`main.py:226-228`), preservando a
  paginação de `TAM_PAGINA=100` (`main.py:35`).
- Sequência inexistente continua devolvendo `[]`, como hoje (`main.py:197`).
- O formato dos objetos de resposta permanece o de `main.py:210-220`, sem
  `diferenca`/`intersecao`.

### Frontend

Em `static/assets/js/controllers/sequencia.js`:

- Remover as 4 sequências hardcoded (`sequencia.js:2-37`) e carregar
  `GET /sequencias` na inicialização do controller, convertendo cada linha para
  o formato que o template já consome (`{acorde, cor}`), com uma cor padrão
  (`#2E1C74`).
- Manter `createChordsString` (`sequencia.js:55-61`) e
  `pesquisarPorSequencia` (`sequencia.js:63`), que continuam enviando
  `similares?sequencia=...`.
- Adicionar estado do formulário (`vm.novaSequencia`) e
  `vm.cadastrarSequencia()`, que faz `POST /sequencias`, trata 201/200/400 e
  recarrega o catálogo em caso de sucesso.

Em `static/templates/sequencia.html`:

- Manter a lista com `ng-repeat` (`sequencia.html:6-8`); ela passa a refletir o
  catálogo do backend, incluindo as 6 originais e as novas.
- Adicionar formulário simples com campo de acordes separados por vírgula,
  botão de cadastro e mensagens de erro/sucesso. O texto digitado deve ser
  preto para contrastar com o fundo branco do campo.
- O clique em qualquer sequência continua disparando a mesma busca; a
  renderização dos cards (`sequencia.html:24-58`) não muda.
- O select de gêneros passa a usar `GET /generos` em vez da constante
  `GENEROS` (`app.js:6-58`). Para não repetir a chamada nos três controllers
  (`sequencia.js:43`, `acordes.js:59`, `musica.js:9`), criar um service/factory
  AngularJS que busca o catálogo uma vez e o compartilha. No backend, remover o
  `;` final do valor de gênero ao carregar o CSV (`main.py:66`): o único caso é
  `R&B;` (303 músicas), que passa a ser `R&B`. Isso corrige a divergência de
  52 × 51 e o filtro de gênero que hoje não encontra `R&B`, mantendo o catálogo
  vindo do CSV em memória.

## Alternativas consideradas e descartadas

- **Híbrido: 6 originais pela tag + novas pela regra A.** Garantiria a
  regressão pelo caminho legado e daria resultados mais intuitivos para
  sequências novas, mas criaria duas semânticas na mesma feature, mais código,
  mais testes e resultados inconsistentes entre sequências parecidas. Como a
  regra D já reproduz a tag com 0/0, o híbrido não se justifica.
- **Regra A (subsequência contígua) para todo o catálogo.** É a leitura
  intuitiva de “o trecho aparece”, mas a pesquisa mediu centenas ou milhares de
  músicas extras nas 6 sequências; isso viola o requisito de manter os mesmos
  resultados.
- **Regras B (subsequência ordenada) e C (inclusão de conjunto).** Ainda mais
  permissivas que A e mais distantes dos conjuntos atuais.
- **Manter `SEQ_FAMOSA` como fonte de verdade.** Impediria sequências novas de
  serem buscadas sem regerar o CSV a cada cadastro, contrariando o requisito de
  catálogo dinâmico.
- **TinyDB / DuckDB / LMDB / JSON plano.** Dependência nova ou ausência de
  transações/concorrência; SQLite resolve com a stdlib e já está na imagem.
- **Banco com servidor separado (PostgreSQL etc.).** Excluído pela ADR 0001
  (container único, sem serviços adicionais).

## Escopo explícito

**Dentro do escopo:**

- Matching em runtime pela regra D sobre `musica.cifra`, para todas as
  sequências.
- Catálogo de sequências persistido em SQLite, com seed idempotente das 6
  originais.
- Endpoints `GET /sequencias`, `POST /sequencias` e evolução interna de
  `GET /similares`.
- Padronização da entrada de `GET /similares?sequencia=...` no formato canônico
  com vírgulas, sem suporte ao formato concatenado antigo.
- Frontend `#/porsequencia` lendo o catálogo do backend e permitindo cadastro.
- Volume para o arquivo SQLite sobreviver à recriação do container.
- Unificação da fonte de gêneros do frontend com `GET /generos` e normalização
  do gênero `R&B;` no carregamento do CSV.
- Teste de regressão das 6 sequências e testes de API/persistência.

**Fora do escopo (e por quê):**

- Migrar músicas/gêneros para o banco: o enunciado fixa que o CSV continua
  carregado em memória.
- Login, moderação, edição e remoção de sequências: o requisito é catálogo
  aberto e anônimo; edição/remoção não foi pedida.
- Regenerar ou alterar a coluna `SEQ_FAMOSA` do CSV: ela deixa de ser usada na
  busca, mas o CSV não é migrado nesta tarefa.
- Normalização avançada de acordes (enarmônicos, qualidades, barras):
  mudaria os conjuntos atuais e exigiria nova medição.
- Rate limiting/antispam do catálogo aberto: a aplicação é local-only; fica como
  possível evolução futura.
- Deploy em nuvem ou múltiplos serviços: continua local-only via Docker.

## Pendências e definições em aberto

Os dois pontos abaixo não estão fechados na especificação e precisam de
definição antes de endurecer o contrato:

- **Validação de acordes válidos:** o cadastro hoje aceita qualquer texto não
  vazio (até 16 acordes). Falta definir, com o cliente, quais são os acordes
  possíveis (por exemplo, a lista de acordes do catálogo ou uma notação
  suportada) e passar a rejeitar acordes fora desse conjunto.
- **Semântica da busca por sequência:** a implementação atual usa a regra D —
  a sequência precisa aparecer como bloco contíguo ordenado e a música não pode
  usar nenhum acorde fora da sequência. Falta confirmar com o cliente se esse é
  o comportamento desejado (“músicas que possuem apenas aquela sequência e mais
  nenhuma”) ou se a busca deve retornar músicas em que a sequência aparece,
  mesmo que tenham outros acordes. A resposta muda o algoritmo de matching e o
  baseline de regressão das 6 sequências.
