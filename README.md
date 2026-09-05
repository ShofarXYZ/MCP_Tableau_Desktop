# tableau-desktop-mcp

Local **MCP (Model Context Protocol)** server that lets Claude Desktop, Claude
Code, or Codex **inspect and safely edit Tableau Desktop workbooks** (`.twb`)
by reading and rewriting their XML. The flagship feature is creating **native
Tableau calculated fields** — conceptually similar to authoring DAX measures in
Power BI, but using **Tableau formula syntax** (never DAX).

> Example prompt:
> *"Analise o workbook dashboard_vendas.twb e crie um campo calculado chamado
> Ticket Médio usando Receita e Pedido ID."*

---

## 1. Objective

Give an LLM a small, safe toolbox to:

1. locate workbooks in an authorized folder;
2. analyze their datasources and fields;
3. verify real column names;
4. generate correct Tableau formulas;
5. create an automatic backup;
6. insert/update/delete calculated fields in the `.twb`;
7. validate the XML before and after writing;
8. return a structured change report.

## 2. Architecture

```
src/tableau_mcp/
├── server.py            FastMCP server (stdio) — registers the 12 tools
├── config.py            Centralized settings (.env), no hard-coded paths
├── models.py            Pydantic models for every input/response/metadata
├── exceptions.py        Typed exception hierarchy
├── logging_config.py    Structured JSON logging (stderr + rotating file)
│
├── workbook/            File + XML layer (I/O)
│   ├── xml_utils.py     Safe path resolution + hardened lxml parse/serialize
│   ├── reader.py        Listing + read-only loading
│   ├── inspector.py     Tree → typed metadata (datasources/fields/…)
│   ├── validator.py     XML well-formedness / structure checks
│   ├── backup.py        Timestamped, unique-id backups
│   └── writer.py        Atomic, backup-protected write flow
│
├── calculations/        Formula layer (pure, no I/O)
│   ├── dax_detector.py           Detect Power BI / DAX syntax
│   ├── field_reference_parser.py Parse & match [Field] references
│   ├── validator.py              Rule-based formula validation
│   ├── element_builder.py        Build/locate <column> calc elements (lxml)
│   └── formula_templates.py      Known functions + reusable templates
│
└── tools/               Thin MCP tool functions
    ├── context.py       Dependency container (reader/backup/writer)
    ├── workbook_tools.py
    ├── field_tools.py
    └── calculation_tools.py
```

**Design choices worth noting (deviations from the original spec):**

- Added `calculations/element_builder.py` and `tools/context.py` to keep XML
  construction and dependency wiring out of the tool functions (separation of
  concerns). Everything the spec required still exists.
- `server.py` is meant to run as a **module** (`python -m tableau_mcp.server`),
  which is more robust on Windows than invoking the file path directly. The
  example Claude config reflects this.
- Added `pydantic-settings` (needed for `.env`-based configuration).

**Write flow (safety):**

```
read original → validate → backup → mutate in memory → write temp file
→ validate temp XML → atomic replace → validate final file → log
```

If any step fails after the backup, the original is restored automatically.

## 3. Limitations (MVP)

- **`.twb` only** — packaged `.twbx` files are intentionally rejected.
- No worksheet/dashboard/chart generation.
- No visual automation (no PyAutoGUI).
- The formula validator is **rule-based**, not the real Tableau compiler; it
  catches common problems (unbalanced brackets, DAX, unknown references, naive
  division-by-zero, aggregate/non-aggregate mixing) but cannot guarantee a
  formula compiles in Tableau.
- Tableau Desktop has **no local MCP API**; this server works purely on the XML.

## 4. Requirements

- Windows 10/11, **Python 3.11+**
- The Python packages in `requirements.txt` / `pyproject.toml`
  (`mcp`, `lxml`, `pydantic`, `pydantic-settings`, `python-dotenv`).

## 5–10. Installation & running (Windows / VS Code)

```powershell
# From the project root
powershell -ExecutionPolicy Bypass -File scripts\setup.ps1
```

This creates `.venv`, installs the project (editable) with dev tools, and
copies `.env.example` → `.env`. Or do it manually:

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install --upgrade pip
.\.venv\Scripts\python.exe -m pip install -e ".[dev]"
Copy-Item .env.example .env
```

Edit **`.env`** to point at your workbook/backup/log folders:

```ini
TABLEAU_MCP_WORKBOOKS_DIR=workbooks
TABLEAU_MCP_BACKUPS_DIR=backups
TABLEAU_MCP_LOGS_DIR=logs
TABLEAU_MCP_LOG_LEVEL=INFO
```

Put your `.twb` files in the **workbooks** folder (the server never reads or
writes outside of it). Then run the server:

```powershell
powershell -ExecutionPolicy Bypass -File scripts\run_server.ps1
# or
.\.venv\Scripts\python.exe -m tableau_mcp.server
```

The server communicates over **stdio** and prints nothing to stdout; logs go to
stderr and `logs\tableau_mcp.log`.

## 11. Claude Desktop configuration

Copy `claude_desktop_config.example.json` into your Claude Desktop config
(`%APPDATA%\Claude\claude_desktop_config.json`), adjusting the paths:

```json
{
  "mcpServers": {
    "tableau-desktop": {
      "command": "C:\\tableau-mcp\\.venv\\Scripts\\python.exe",
      "args": ["-m", "tableau_mcp.server"],
      "cwd": "C:\\tableau-mcp",
      "env": {
        "TABLEAU_MCP_WORKBOOKS_DIR": "C:\\tableau-mcp\\workbooks",
        "TABLEAU_MCP_BACKUPS_DIR": "C:\\tableau-mcp\\backups",
        "TABLEAU_MCP_LOGS_DIR": "C:\\tableau-mcp\\logs"
      }
    }
  }
}
```

### `command + args` vs. a URI

This is a **local stdio server**, so Claude launches the process directly:
`command` is the Python executable and `args` tells it which module to run.
Claude then talks to the server over the process's stdin/stdout pipes.

A **URI-based** configuration (e.g. `"url": "https://…/mcp"`) is only used for
**remote** MCP servers reached over HTTP/SSE — such as Tableau Cloud/Server.
**This project deliberately needs no URI, URL, Cloud, or Server**; everything is
local. If you ever see a config asking for a URL, that is a *different*,
remote integration — not this one.

## 12. Claude Code configuration

```powershell
claude mcp add tableau-desktop -- C:\tableau-mcp\.venv\Scripts\python.exe -m tableau_mcp.server
```

Or add an entry to `.mcp.json` in your project with the same `command`/`args`
shape as the Claude Desktop example above.

## 13. Codex configuration (when applicable)

Codex-style clients that support local MCP servers use the same launch
contract. In the client's MCP config, register a server whose command is the
venv Python and whose args are `-m tableau_mcp.server`, with the
`TABLEAU_MCP_*` environment variables set as above. No URL is required.

## 14. Running the tests / quality checks

```powershell
powershell -ExecutionPolicy Bypass -File scripts\run_tests.ps1   # pytest
powershell -ExecutionPolicy Bypass -File scripts\check.ps1       # ruff + mypy
```

The unit tests use tiny in-memory `.twb` fixtures and **do not require Tableau
Desktop**.

## 15. Example prompts

```
Liste os workbooks disponíveis.
Inspecione dashboard_vendas.twb sem realizar alterações.
Liste todos os campos calculados da fonte Vendas.
Valide a fórmula SUM([Receita]) / COUNTD([Pedido ID]).
Crie o campo Ticket Médio usando Receita e Pedido ID.
Crie os KPIs Receita Total, Pedidos, Ticket Médio e Taxa de Conversão.
```

## 16. Backup flow

Every mutating tool (`create`/`update`/`delete`/`batch`/`restore`) creates a
timestamped backup **before** touching the file, e.g.:

```
backups/dashboard_vendas.20260718T130501Z.a1b2c3d4.twb
```

You can also back up manually with `backup_workbook`.

## 17. Restore

```
# List available backups (no backup_name):
restore_workbook_backup(filename="dashboard_vendas.twb")

# Restore a specific one (snapshots the current state first, requires confirm):
restore_workbook_backup(filename="dashboard_vendas.twb",
                        backup_name="dashboard_vendas.20260718T130501Z.a1b2c3d4.twb",
                        confirm=true)
```

## 18. Troubleshooting

| Symptom | Likely cause / fix |
| --- | --- |
| `workbook_not_found` | File is not in the `TABLEAU_MCP_WORKBOOKS_DIR` folder. |
| `security_error` | Path traversal / wrong extension / outside the sandbox. Use just the filename. |
| `workbook_parse_error` | The `.twb` is not valid XML (or is actually a `.twbx`). |
| `duplicate_field` | A field with that caption already exists — use `update_calculated_field`. |
| `formula_validation_error` | See the `validation.issues` list for the exact problem. |
| Server "does nothing" in a terminal | Correct — it waits for an MCP client on stdio. Use Claude, or `scripts\inspect_workbook.ps1`. |

## 19. Risks of editing `.twb` files

Editing workbook XML by hand (or via automation) can, in rare cases, corrupt a
workbook or produce a formula Tableau ultimately rejects. This project
mitigates that with mandatory backups, atomic writes, and pre/post validation —
but **you should keep your own backups of important workbooks** and review the
change report before relying on the result.

## 20. ⚠️ Close Tableau Desktop first

**Always close the workbook in Tableau Desktop before running any mutating
tool.** Tableau may hold the file open and can overwrite your changes on save,
or lock the file so the write fails. Open it again in Tableau *after* the MCP
reports success.

---

## Suggested instruction for the assistant

Add this to your Claude/Codex system or project instructions:

```
Antes de criar ou alterar qualquer campo calculado:
1. inspecione o workbook;
2. confirme a datasource correta;
3. liste os campos reais;
4. valide os campos referenciados;
5. utilize somente sintaxe nativa do Tableau;
6. nunca utilize DAX;
7. valide a fórmula;
8. crie backup;
9. aplique a alteração;
10. informe exatamente o que foi modificado.
```

## Future compatibility

The layering (workbook I/O vs. formula logic vs. tools) is designed to grow:
parameters, LOD expressions, aliases, bins/groups/sets, folders, number
formatting, descriptions, `.hyper` extracts / Tableau Hyper API, `.twbx`
support, documentation generation, BigQuery/dbt integration, dependency
inspection, and worksheet creation can each be added as new modules/tools
without rewriting the safe-write core.

## MCP tools reference

| Tool | Purpose |
| --- | --- |
| `list_workbooks` | List `.twb` files in the authorized folder. |
| `inspect_workbook` | Datasources, worksheets, dashboards, fields (read-only). |
| `list_datasources` | Datasource metadata. |
| `list_fields` | Fields of a datasource (filter: all/dimension/measure/parameter/calculated). |
| `list_calculated_fields` | All calculated fields. |
| `validate_tableau_formula` | Validate a formula without writing. |
| `create_calculated_field` | Create one calculated field. |
| `update_calculated_field` | Update a field's formula (before/after report). |
| `delete_calculated_field` | Delete a calculated field (requires `confirm=true`). |
| `create_calculated_fields_batch` | Create many fields atomically (all-or-nothing). |
| `backup_workbook` | Manual timestamped backup. |
| `restore_workbook_backup` | List/restore backups (requires `confirm=true`). |
| `analyze_dataset` | Classify fields semantically and infer the business domain. |
| `suggest_business_metrics` | Suggest KPIs with Tableau formulas + rationale. |
| `create_recommended_metrics` | Create all recommended metrics atomically (1 backup). |
| `suggest_visualizations` | Recommend chart types per analysis, with justification. |

## Analytics Copilot (semantic layer)

Beyond editing individual fields, the server can **interpret a dataset** and act
like a Tableau analytics copilot — similar in spirit to Power BI Copilot, but
producing **native Tableau** calculated fields.

Conversation flow with Claude Desktop:

```
> Analise meu dataset.               → analyze_dataset
> Quais KPIs você recomenda?         → suggest_business_metrics
> Crie todas as métricas recomendadas. → create_recommended_metrics
> Quais gráficos você recomenda?     → suggest_visualizations
```

**How it infers meaning (no fixed column names).** Field names are normalized
(accent-free, camelCase-split, PT/EN) and matched against keyword sets plus
datatype and role signals — so `ValorVenda`, `Revenue`, `Valor` → *revenue*;
`OrderID`, `PedidoID` → *identifier*; `OrderDate`, `Data` → *date*; `Lucro`,
`Profit` → *profit*; `Desconto` → *discount*; `Quantidade`, `Qty` → *quantity*;
`Estado`, `State`, `UF` → *geo*. See `semantics/field_classifier.py`.

From that classification it proposes KPIs such as **Receita Bruta/Líquida,
Lucro, Margem %, Ticket Médio, Pedidos, Clientes Únicos, Itens Vendidos,
Desconto Médio, Receita por Cliente/Produto/Categoria/Canal/Estado, Running
Total, MoM, YoY, Participação %** — each with a Portuguese rationale and a native
Tableau formula (table calcs like Running Total/MoM/YoY are flagged with
`requires_view_context`). `create_recommended_metrics` reuses
`create_calculated_fields_batch`, so it inherits the same validate-all → single
backup → atomic write guarantees and is **idempotent** (existing captions are
skipped).

The new code lives under `src/tableau_mcp/semantics/`
(`normalization`, `field_classifier`, `field_index`, `dataset_analyzer`,
`metric_catalog`, `visualization_advisor`) and `tools/analytics_tools.py`.


## License

MIT
