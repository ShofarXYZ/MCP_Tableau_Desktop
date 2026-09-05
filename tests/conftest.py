"""Shared pytest fixtures: temporary sandbox and minimal .twb workbooks."""

from __future__ import annotations

from pathlib import Path

import pytest

from tableau_mcp.config import Settings
from tableau_mcp.tools.context import ToolContext

# A minimal but realistic single-datasource workbook with accents and a
# multiline calculated field, plus a worksheet and a dashboard.
SINGLE_DS_TWB = """<?xml version='1.0' encoding='utf-8' ?>
<workbook source-build='2023.1' version='18.1'>
  <datasources>
    <datasource caption='Vendas' name='federated.vendas'>
      <connection class='federated' />
      <column caption='Receita' datatype='real' name='[Receita]' role='measure' type='quantitative' />
      <column caption='Pedido ID' datatype='integer' name='[Pedido ID]' role='dimension' type='ordinal' />
      <column caption='Região' datatype='string' name='[Regiao]' role='dimension' type='nominal' />
      <column caption='Desconto Total' datatype='real' name='[Calculation_abc123]' role='measure' type='quantitative'>
        <calculation class='tableau' formula='SUM([Receita])&#10;* 0.1' />
      </column>
    </datasource>
  </datasources>
  <worksheets>
    <worksheet name='Vendas por Região' />
  </worksheets>
  <dashboards>
    <dashboard name='Dashboard Vendas' />
  </dashboards>
</workbook>
"""

# A workbook with two datasources (including a duplicated field name).
MULTI_DS_TWB = """<?xml version='1.0' encoding='utf-8' ?>
<workbook version='18.1'>
  <datasources>
    <datasource caption='Vendas' name='federated.vendas'>
      <connection class='federated' />
      <column caption='Receita' datatype='real' name='[Receita]' role='measure' type='quantitative' />
      <column caption='Pedido ID' datatype='integer' name='[Pedido ID]' role='dimension' type='ordinal' />
    </datasource>
    <datasource caption='Custos' name='federated.custos'>
      <connection class='federated' />
      <column caption='Receita' datatype='real' name='[Receita]' role='measure' type='quantitative' />
      <column caption='Custo' datatype='real' name='[Custo]' role='measure' type='quantitative' />
    </datasource>
  </datasources>
</workbook>
"""

# A workbook with no datasources at all.
NO_DS_TWB = """<?xml version='1.0' encoding='utf-8' ?>
<workbook version='18.1'>
  <worksheets />
</workbook>
"""

# A federated, Relationships-based datasource with two physical tables where
# the relationship's second side deliberately points at a field that no
# longer exists on `mart_b` -- reproducing the "Este relacionamento faz
# referência a um campo desconhecido" alert after a remote schema change.
RELATIONSHIPS_TWB = """<?xml version='1.0' encoding='utf-8' ?>
<workbook version='18.1'>
  <datasources>
    <datasource caption='GA4' name='federated.ga4'>
      <connection class='federated'>
        <relation type='collection'>
          <relation connection='databricks.x' name='mart_a' table='[ga4].[gold].[mart_a]' type='table' />
          <relation connection='databricks.x' name='mart_b' table='[ga4].[gold].[mart_b]' type='table' />
        </relation>
      </connection>
      <column caption='Id' datatype='string' name='[id]' role='dimension' type='nominal' />
      <column caption='Name' datatype='string' name='[name]' role='dimension' type='nominal' />
      <column caption='Id (Mart B)' datatype='string' name='[id (mart_b)]' role='dimension' type='nominal' />
      <column caption='Value' datatype='real' name='[value]' role='measure' type='quantitative' />
      <cols>
        <map key='[id]' value='[mart_a].[id]' />
        <map key='[name]' value='[mart_a].[name]' />
        <map key='[id (mart_b)]' value='[mart_b].[id]' />
        <map key='[value]' value='[mart_b].[value]' />
      </cols>
      <object-graph>
        <objects>
          <object caption='mart_a' id='mart_a_OBJ'>
            <properties context=''>
              <relation connection='databricks.x' name='mart_a' table='[ga4].[gold].[mart_a]' type='table' />
            </properties>
          </object>
          <object caption='mart_b' id='mart_b_OBJ'>
            <properties context=''>
              <relation connection='databricks.x' name='mart_b' table='[ga4].[gold].[mart_b]' type='table' />
            </properties>
          </object>
        </objects>
        <relationships>
          <relationship>
            <expression op='='>
              <expression op='[id]' />
              <expression op='[does_not_exist]' />
            </expression>
            <first-end-point object-id='mart_a_OBJ' />
            <second-end-point object-id='mart_b_OBJ' />
          </relationship>
        </relationships>
      </object-graph>
    </datasource>
  </datasources>
</workbook>
"""

# Malformed XML (unclosed tag).
INVALID_TWB = "<workbook><datasources></workbook>"


@pytest.fixture
def sandbox(tmp_path: Path) -> Settings:
    """Return Settings pointing at isolated temp workbooks/backups/logs dirs."""
    settings = Settings(
        workbooks_dir=tmp_path / "workbooks",
        backups_dir=tmp_path / "backups",
        logs_dir=tmp_path / "logs",
    )
    settings.ensure_directories()
    return settings


@pytest.fixture
def ctx(sandbox: Settings) -> ToolContext:
    """Return a ToolContext bound to the sandbox."""
    return ToolContext(sandbox)


def _write_workbook(settings: Settings, name: str, content: str) -> Path:
    path = settings.workbooks_path / name
    path.write_text(content, encoding="utf-8")
    return path


@pytest.fixture
def single_workbook(sandbox: Settings) -> str:
    """Create 'dashboard_vendas.twb' and return its filename."""
    _write_workbook(sandbox, "dashboard_vendas.twb", SINGLE_DS_TWB)
    return "dashboard_vendas.twb"


@pytest.fixture
def multi_workbook(sandbox: Settings) -> str:
    """Create 'multi.twb' with two datasources and return its filename."""
    _write_workbook(sandbox, "multi.twb", MULTI_DS_TWB)
    return "multi.twb"


@pytest.fixture
def empty_workbook(sandbox: Settings) -> str:
    """Create 'empty.twb' with no datasources."""
    _write_workbook(sandbox, "empty.twb", NO_DS_TWB)
    return "empty.twb"


@pytest.fixture
def invalid_workbook(sandbox: Settings) -> str:
    """Create 'broken.twb' with malformed XML."""
    _write_workbook(sandbox, "broken.twb", INVALID_TWB)
    return "broken.twb"


@pytest.fixture
def relationships_workbook(sandbox: Settings) -> str:
    """Create 'ga4_relationships.twb' with one deliberately broken relationship."""
    _write_workbook(sandbox, "ga4_relationships.twb", RELATIONSHIPS_TWB)
    return "ga4_relationships.twb"
