# WAVE Report Parser

> [Read in English](README.en.md)

Script Node.js para extrair e estruturar os dados de relatórios de acessibilidade gerados pela extensão [WAVE (Web Accessibility Evaluation Tool)](https://wave.webaim.org/).

## Como funciona

A extensão WAVE injeta uma barra lateral (`sidebar_container`) na página avaliada. Este script lê o HTML dessa barra lateral — salvo como arquivo `.html` — e extrai:

- **Contagens resumidas** por categoria (Erros, Erros de Contraste, Alertas, Funcionalidades, Estrutura, ARIA)
- **Pontuação AIM** (Accessibility Improvement Measure), de 0 a 10
- **Detalhamento por tipo** dentro de cada categoria, incluindo cada instância encontrada na página e se ela estava visualmente oculta

Os resultados são exportados em **JSON** (estruturado) e **CSV** (planilha).

## Pré-requisitos

- [Node.js](https://nodejs.org/) v14 ou superior (sem dependências externas)

## Como usar

### 1. Salvar o relatório WAVE como HTML

1. Acesse a página que deseja avaliar com a extensão WAVE ativa
2. Clique com o botão direito na barra lateral do WAVE → **Inspecionar**
3. No DevTools, localize o elemento `<div id="sidebar_container">`, clique com o botão direito → **Copiar** → **Copiar elemento**
4. Cole o conteúdo em um arquivo `.html` (ex: `meu-site.html`)

### 2. Executar o parser

```bash
node wave-parser.js meu-site.html
```

Para processar múltiplos arquivos de uma vez:

```bash
node wave-parser.js site-a.html site-b.html site-c.html
```

### 3. Arquivos gerados

| Arquivo | Descrição |
|---|---|
| `<nome>.json` | Relatório completo e estruturado de cada arquivo de entrada |
| `wave-report.json` | Array combinado com todos os relatórios processados |
| `wave-summary.csv` | Uma linha por arquivo com todas as contagens e a pontuação AIM |
| `wave-details.csv` | Uma linha por instância encontrada, com todos os detalhes |

Os arquivos são gerados no mesmo diretório dos arquivos de entrada.

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
    "aim_score": 7.4
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

## Colunas do CSV de detalhes

| Coluna | Descrição |
|---|---|
| `source_file` | Nome do arquivo HTML de origem |
| `category` | ID da categoria (`error`, `alert`, `feature`, `structure`, `aria`) |
| `category_label` | Nome legível da categoria |
| `type_id` | ID do tipo de item (ex: `alt_missing`, `link_suspicious`) |
| `type_label` | Descrição do tipo de item |
| `type_count` | Total de instâncias desse tipo no relatório |
| `instance_index` | Número sequencial da instância (1, 2, 3...) |
| `hidden` | `true` se o elemento está visualmente oculto na página |
| `description` | Texto descritivo completo da instância |
| `label` | Rótulo do tipo sem o número da instância |

## Categorias do WAVE

| Categoria | Descrição |
|---|---|
| **Errors** | Problemas que certamente impactam usuários de tecnologia assistiva |
| **Contrast Errors** | Texto com contraste insuficiente em relação ao fundo |
| **Alerts** | Possíveis problemas que requerem avaliação manual |
| **Features** | Recursos de acessibilidade presentes na página |
| **Structure** | Elementos estruturais (cabeçalhos, listas, landmarks) |
| **ARIA** | Atributos e roles ARIA identificados |
