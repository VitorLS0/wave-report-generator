# WAVE Report Parser

> [Read in English](README.en.md)

Script Node.js para extrair e estruturar os dados de relatórios de acessibilidade gerados pela extensão [WAVE (Web Accessibility Evaluation Tool)](https://wave.webaim.org/).

## Como funciona

A extensão WAVE injeta uma barra lateral (`sidebar_container`) na página avaliada. Este script lê o HTML dessa barra lateral — salvo como arquivo `.html` — e extrai:

- **Contagens resumidas** por categoria (Erros, Erros de Contraste, Alertas, Funcionalidades, Estrutura, ARIA)
- **Pontuação AIM** (Accessibility Improvement Measure), de 0 a 10
- **Detalhamento por tipo** dentro de cada categoria, incluindo cada instância encontrada na página e se ela estava visualmente oculta
- **Mapeamento WCAG** de cada tipo de problema para os critérios e nível de conformidade correspondentes (A, AA, AAA)
- **Classificação POUR** de cada tipo nas dimensões do framework WCAG (Perceptível, Operável, Compreensível, Robusto)
- **Relevância para leitores de tela** de cada tipo (`critical`, `high`, `medium`, `low`, `positive`, `informational`)
- **Resumo por POUR e relevância** no nível do relatório, contabilizando somente erros e alertas

Os resultados são exportados em **JSON** (estruturado) e **CSV** (planilha).

## Estrutura do projeto

```
wave/
├── input/          # Arquivos HTML exportados do WAVE
├── src/            # Código do parser
│   └── wave-parser.js
├── output/         # Resultados gerados (JSON e CSV)
└── README.md
```

## Pré-requisitos

- [Node.js](https://nodejs.org/) v14 ou superior (sem dependências externas)

## Como usar

### 1. Salvar o relatório WAVE como HTML

1. Acesse a página que deseja avaliar com a extensão WAVE ativa
2. Clique com o botão direito na barra lateral do WAVE → **Inspecionar**
3. No DevTools, localize o elemento `<div id="sidebar_container">`, clique com o botão direito → **Copiar** → **Copiar elemento**
4. Cole o conteúdo em um arquivo `.html` dentro da pasta `input/` (ex: `input/meu-site.html`)

### 2. Executar o parser

Processar todos os arquivos em `input/` automaticamente:

```bash
node src/wave-parser.js
```

Ou especificar arquivos individualmente:

```bash
node src/wave-parser.js input/site-a.html input/site-b.html
```

### 3. Arquivos gerados

Todos os resultados são salvos em `output/`:

| Arquivo | Descrição |
|---|---|
| `output/<nome>.json` | Relatório completo e estruturado de cada arquivo de entrada |
| `output/wave-report.json` | Array combinado com todos os relatórios processados |
| `output/wave-summary.csv` | Uma linha por arquivo com todas as contagens e a pontuação AIM |
| `output/wave-details.csv` | Uma linha por instância encontrada, com todos os detalhes |

## Estrutura do JSON

```json
{
  "source_file": "meu-site.html",
  "summary": {
    "errors": 2,
    "contrast_errors": 1,
    "alerts": 5,
    "features": 8,
    "structure": 14,
    "aria": 3,
    "aim_score": 7.4,
    "pour_breakdown": {
      "perceivable": 4,
      "operable": 2,
      "understandable": 1,
      "robust": 1
    },
    "sr_relevance_breakdown": {
      "critical": 2,
      "high": 3,
      "medium": 2,
      "low": 1
    }
  },
  "categories": [
    {
      "category": "error",
      "category_label": "Errors",
      "total": 2,
      "types": [
        {
          "type_id": "alt_missing",
          "type_label": "Missing alternative text",
          "count": 2,
          "wcag_criteria": ["1.1.1"],
          "wcag_level": "A",
          "pour_dimensions": ["Perceivable"],
          "sr_relevance": "critical",
          "instances": [
            {
              "index": 1,
              "hidden": false,
              "description": "Missing alternative text 1",
              "label": "Missing alternative text"
            }
          ]
        }
      ]
    }
  ]
}
```

### `pour_breakdown` e `sr_relevance_breakdown`

Contabilizam apenas instâncias de **Erros**, **Erros de Contraste** e **Alertas** — categorias que representam barreiras. Funcionalidades, Estrutura e ARIA são excluídas por serem indicadores positivos ou informativos.

Um mesmo tipo pode pertencer a mais de uma dimensão POUR (ex: `label_missing` pertence a Perceptível e Compreensível), sendo contado em ambas.

## Colunas do CSV de resumo (`wave-summary.csv`)

| Coluna | Descrição |
|---|---|
| `source_file` | Nome do arquivo HTML de origem |
| `errors` | Total de erros |
| `contrast_errors` | Total de erros de contraste |
| `alerts` | Total de alertas |
| `features` | Total de funcionalidades de acessibilidade |
| `structure` | Total de elementos estruturais |
| `aria` | Total de atributos/roles ARIA |
| `aim_score` | Pontuação AIM (0–10) |
| `pour_perceivable` | Instâncias de erros/alertas classificadas como Perceptível |
| `pour_operable` | Instâncias classificadas como Operável |
| `pour_understandable` | Instâncias classificadas como Compreensível |
| `pour_robust` | Instâncias classificadas como Robusto |
| `sr_critical` | Instâncias com relevância `critical` para leitores de tela |
| `sr_high` | Instâncias com relevância `high` |
| `sr_medium` | Instâncias com relevância `medium` |
| `sr_low` | Instâncias com relevância `low` |

## Colunas do CSV de detalhes (`wave-details.csv`)

| Coluna | Descrição |
|---|---|
| `source_file` | Nome do arquivo HTML de origem |
| `category` | ID da categoria (`error`, `alert`, `feature`, `structure`, `aria`) |
| `category_label` | Nome legível da categoria |
| `type_id` | ID do tipo de item (ex: `alt_missing`, `link_suspicious`) |
| `type_label` | Descrição do tipo de item |
| `type_count` | Total de instâncias desse tipo no relatório |
| `wcag_criteria` | Critérios WCAG relacionados, separados por `;` (ex: `1.3.1;2.4.1`) |
| `wcag_level` | Nível de conformidade WCAG (`A`, `AA` ou `AAA`) |
| `pour_dimensions` | Dimensões POUR, separadas por `;` (ex: `Perceivable;Operable`) |
| `sr_relevance` | Relevância para leitores de tela (`critical`, `high`, `medium`, `low`, `positive`, `informational`) |
| `instance_index` | Número sequencial da instância (1, 2, 3...) |
| `hidden` | `true` se o elemento está visualmente oculto na página |
| `description` | Texto descritivo completo da instância |
| `label` | Rótulo do tipo sem o número da instância |

### Valores de `sr_relevance`

| Valor | Significado |
|---|---|
| `critical` | Bloqueia diretamente o acesso por leitores de tela |
| `high` | Impacta significativamente a experiência com leitor de tela |
| `medium` | Impacta a experiência, mas pode ter contorno |
| `low` | Impacto menor (ex: mais relevante para usuários com baixa visão) |
| `positive` | Recurso de acessibilidade presente — beneficia usuários de leitores de tela |
| `informational` | Elemento neutro — presença registrada sem julgamento positivo ou negativo |

## Categorias do WAVE

| Categoria | Descrição |
|---|---|
| **Errors** | Problemas que certamente impactam usuários de tecnologia assistiva |
| **Contrast Errors** | Texto com contraste insuficiente em relação ao fundo |
| **Alerts** | Possíveis problemas que requerem avaliação manual |
| **Features** | Recursos de acessibilidade presentes na página |
| **Structure** | Elementos estruturais (cabeçalhos, listas, landmarks) |
| **ARIA** | Atributos e roles ARIA identificados |
