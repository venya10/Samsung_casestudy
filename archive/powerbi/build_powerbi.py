"""Generate a Power BI project (PBIP) with a TMDL semantic model.

Why generated rather than hand-built: a .pbix is an opaque binary, so it cannot be
diffed, reviewed or regenerated. PBIP is the text-based project format Power BI
Desktop reads natively — the model is TMDL, the report is JSON — so the schema,
relationships and every DAX measure live in this script and rebuild from scratch
whenever the data changes.

Report VISUALS are not generated. Power BI's report JSON is version-specific and
undocumented; a malformed one stops Desktop opening the project at all, which is a
worse outcome than an empty report. The visuals are specified in
powerbi/REPORT_BUILD_SPEC.md and are about 45 minutes of drag-and-drop. The model,
which is the part that takes real time, is complete on open.

NOTE ON TIME INTELLIGENCE: the source has no calendar dates, only an integer week
1-8. DAX time-intelligence functions (DATEADD, SAMEPERIODLASTYEAR) all require a
real date table, so the prior-week measures here use week-offset arithmetic
instead. Inventing dates to unlock those functions would let seasonality claims
into a dataset that cannot support them.
"""
from __future__ import annotations

import json
import shutil
import uuid

import pandas as pd

from common import CURRENCY, DATA_PBI, ROOT

PBI = ROOT / "powerbi"
NAME = "SamsungMENA"
MODEL_DIR = PBI / f"{NAME}.SemanticModel"
REPORT_DIR = PBI / f"{NAME}.Report"

FACTS = ["fact_market_week", "fact_channel", "fact_product", "fact_influencer",
         "fact_brand", "channel_efficiency", "market_scorecard", "product_summary",
         "product_channel", "influencer_scorecard", "reallocation", "panel_model",
         "paid_vs_earned", "alerts"]
DIMS = ["dim_week", "dim_market", "dim_channel", "dim_product", "dim_influencer"]

RELATIONSHIPS = [
    ("fact_market_week", "week", "dim_week", "week"),
    ("fact_market_week", "market", "dim_market", "market"),
    ("fact_channel", "week", "dim_week", "week"),
    ("fact_channel", "market", "dim_market", "market"),
    ("fact_channel", "channel", "dim_channel", "channel"),
    ("fact_product", "week", "dim_week", "week"),
    ("fact_product", "market", "dim_market", "market"),
    ("fact_product", "product", "dim_product", "product"),
    ("fact_influencer", "week", "dim_week", "week"),
    ("fact_influencer", "market", "dim_market", "market"),
    ("fact_influencer", "influencer", "dim_influencer", "influencer"),
    ("fact_brand", "week", "dim_week", "week"),
    ("fact_brand", "market", "dim_market", "market"),
    ("channel_efficiency", "channel", "dim_channel", "channel"),
    ("market_scorecard", "market", "dim_market", "market"),
    ("product_summary", "product", "dim_product", "product"),
    ("influencer_scorecard", "influencer", "dim_influencer", "influencer"),
    ("reallocation", "channel", "dim_channel", "channel"),
]

# (name, DAX, format string)
MEASURES: list[tuple[str, str, str]] = [
    ("Sales", "SUM(fact_market_week[sales_aed])", '"#,0,, \\m \\A\\E\\D"'),
    ("Media Spend", "SUM(fact_market_week[spend_aed])", '"#,0,, \\m \\A\\E\\D"'),
    ("Conversions", "SUM(fact_market_week[conversions])", '"#,0"'),
    ("Impressions", "SUM(fact_market_week[impressions])", '"#,0"'),
    ("Clicks", "SUM(fact_market_week[clicks])", '"#,0"'),
    ("Sessions", "SUM(fact_market_week[sessions])", '"#,0"'),
    ("Paid Spend", "SUM(fact_market_week[paid_spend_aed])", '"#,0,, \\m \\A\\E\\D"'),
    ("Earned Sales", "SUM(fact_market_week[earned_sales_aed])", '"#,0,, \\m \\A\\E\\D"'),
    ("TV Spend", "SUM(fact_market_week[tv_spend_aed])", '"#,0,, \\m \\A\\E\\D"'),
    ("TV GRPs", "SUM(fact_market_week[tv_grp])", '"#,0"'),
    # Ratios -- always DIVIDE, never "/", so a zero denominator yields blank
    ("MER", "DIVIDE([Sales], [Media Spend])", '"#,0.0\\x"'),
    ("CPA", "DIVIDE([Media Spend], [Conversions])", '"#,0 \\A\\E\\D"'),
    ("AOV", "DIVIDE([Sales], [Conversions])", '"#,0 \\A\\E\\D"'),
    ("CPM", "DIVIDE([Media Spend], [Impressions]) * 1000", '"#,0.00 \\A\\E\\D"'),
    ("CPC", "DIVIDE([Media Spend], [Clicks])", '"#,0.00 \\A\\E\\D"'),
    ("CTR", "DIVIDE([Clicks], [Impressions])", '"0.00%"'),
    ("Cost per GRP", "DIVIDE([TV Spend], [TV GRPs])", '"#,0 \\A\\E\\D"'),
    ("Earned Share of Sales", "DIVIDE([Earned Sales], [Sales])", '"0.0%"'),
    ("TV Share of Spend", "DIVIDE([TV Spend], [Media Spend])", '"0.0%"'),
    ("Spend as % of Sales", "DIVIDE([Media Spend], [Sales])", '"0.0%"'),
    # Margin -- the number a budget decision turns on
    ("Gross Margin Rate", "0.22", '"0%"'),
    ("ROI on Margin", "[MER] * [Gross Margin Rate]", '"#,0.00\\x"'),
    # Brand -- indicative, averaged
    ("Brand Awareness", "AVERAGE(fact_market_week[brand_awareness])", '"#,0.0"'),
    ("Purchase Intent", "AVERAGE(fact_market_week[purchase_intent])", '"#,0.0"'),
    ("Sentiment", "AVERAGE(fact_market_week[sentiment])", '"#,0.00"'),
    ("Share of Voice", "AVERAGE(fact_market_week[share_of_voice])", '"#,0.0"'),
    ("Competitor SOV", "AVERAGE(fact_market_week[competitor_sov])", '"#,0.0"'),
    ("SOV Gap", "[Share of Voice] - [Competitor SOV]", '"+#,0.0;-#,0.0;0.0"'),
    # Week-over-week by OFFSET, not DATEADD -- there is no date table
    ("Sales PW",
     "VAR w = SELECTEDVALUE(dim_week[week]) "
     "RETURN CALCULATE([Sales], ALL(dim_week), dim_week[week] = w - 1)",
     '"#,0,, \\m \\A\\E\\D"'),
    ("Sales WoW %",
     "VAR prev = [Sales PW] RETURN DIVIDE([Sales] - prev, prev)",
     '"+0.0%;-0.0%;0.0%"'),
    ("Spend PW",
     "VAR w = SELECTEDVALUE(dim_week[week]) "
     "RETURN CALCULATE([Media Spend], ALL(dim_week), dim_week[week] = w - 1)",
     '"#,0,, \\m \\A\\E\\D"'),
    ("Spend WoW %",
     "VAR prev = [Spend PW] RETURN DIVIDE([Media Spend] - prev, prev)",
     '"+0.0%;-0.0%;0.0%"'),
    # Peer benchmarking -- the strongest angle in an 8-market panel
    ("Peer Median MER",
     "MEDIANX(ALL(dim_market), CALCULATE([MER]))", '"#,0.0\\x"'),
    ("MER vs Peer Median",
     "DIVIDE([MER] - [Peer Median MER], [Peer Median MER])",
     '"+0.0%;-0.0%;0.0%"'),
    # Influencer
    ("Influencer Fees", "SUM(influencer_scorecard[spend_aed])", '"#,0 \\A\\E\\D"'),
    ("Influencer Conversions", "SUM(influencer_scorecard[conversions])", '"#,0"'),
    ("Influencer CPA",
     "DIVIDE([Influencer Fees], [Influencer Conversions])", '"#,0 \\A\\E\\D"'),
    ("Influencer ROI on Margin",
     "DIVIDE(SUM(influencer_scorecard[sales_aed]), [Influencer Fees]) "
     "* [Gross Margin Rate]", '"#,0.00\\x"'),
    # Alerts
    ("Open Alerts", "COUNTROWS(alerts)", '"#,0"'),
    ("Critical Alerts",
     'CALCULATE(COUNTROWS(alerts), alerts[severity] = "critical")', '"#,0"'),
]

DAX_TYPE = {"int64": "int64", "float64": "double", "bool": "boolean",
            "datetime64[ns]": "dateTime", "object": "string"}
PQ_TYPE = {"int64": "Int64.Type", "float64": "type number", "bool": "type logical",
           "datetime64[ns]": "type date", "object": "type text"}


def _esc(name: str) -> str:
    return name if name.replace("_", "").isalnum() else f"'{name}'"


def table_tmdl(name: str, df: pd.DataFrame) -> str:
    lines = [f"table {name}", ""]
    for col in df.columns:
        dt = str(df[col].dtype)
        t = DAX_TYPE.get(dt, "string")
        lines += [
            f"\tcolumn {_esc(col)}",
            f"\t\tdataType: {t}",
            "\t\tsummarizeBy: none" if t == "string" or col == "week"
            else "\t\tsummarizeBy: sum",
            f"\t\tsourceColumn: {col}",
            "",
        ]

    if name == "fact_market_week":
        for m_name, dax, fmt in MEASURES:
            dax_lines = dax.split(" RETURN ")
            if len(dax_lines) > 1:
                lines.append(f"\tmeasure '{m_name}' =")
                lines.append(f"\t\t\t{dax_lines[0]}")
                lines.append(f"\t\t\tRETURN {dax_lines[1]}")
            else:
                lines.append(f"\tmeasure '{m_name}' = {dax}")
            lines += [f"\t\tformatString: {fmt}", ""]

    transforms = ", ".join(
        f'{{"{c}", {PQ_TYPE.get(str(df[c].dtype), "type text")}}}' for c in df.columns
    )
    lines += [
        f"\tpartition {name} = m",
        "\t\tmode: import",
        "\t\tsource =",
        "\t\t\t\tlet",
        f'\t\t\t\t    Source = Csv.Document(File.Contents(DataFolder & "{name}.csv"),'
        '[Delimiter=",", Encoding=65001, QuoteStyle=QuoteStyle.Csv]),',
        "\t\t\t\t    Promoted = Table.PromoteHeaders(Source, [PromoteAllScalars=true]),",
        f"\t\t\t\t    Typed = Table.TransformColumnTypes(Promoted, {{{transforms}}})",
        "\t\t\t\tin",
        "\t\t\t\t    Typed",
        "",
        "\tannotation PBI_ResultType = Table",
        "",
    ]
    return "\n".join(lines)


def build() -> None:
    # Remove only what this script generates -- deleting powerbi/ wholesale would
    # take REPORT_BUILD_SPEC.md and any saved .pbix with it, and fails outright if
    # Desktop has the folder open.
    for path in (MODEL_DIR, REPORT_DIR):
        if path.exists():
            shutil.rmtree(path, ignore_errors=True)
    PBI.mkdir(parents=True, exist_ok=True)
    (MODEL_DIR / "definition" / "tables").mkdir(parents=True, exist_ok=True)
    REPORT_DIR.mkdir(parents=True, exist_ok=True)

    tables = [t for t in FACTS + DIMS if (DATA_PBI / f"{t}.csv").exists()]
    frames = {t: pd.read_csv(DATA_PBI / f"{t}.csv") for t in tables}

    for t, df in frames.items():
        (MODEL_DIR / "definition" / "tables" / f"{t}.tmdl").write_text(
            table_tmdl(t, df), encoding="utf-8")

    data_path = str(DATA_PBI).replace("\\", "\\\\")
    (MODEL_DIR / "definition" / "expressions.tmdl").write_text(
        "/// Absolute path to the folder holding the exported CSVs.\n"
        "/// Change this one value to repoint the model at a different export.\n"
        f'expression DataFolder = "{data_path}\\\\" meta [IsParameterQuery=true, '
        'Type="Text", IsParameterQueryRequired=true]\n'
        f"\tlineageTag: {uuid.uuid4()}\n"
        "\tannotation PBI_ResultType = Text\n",
        encoding="utf-8")

    rel_lines = []
    for ft, fc, tt, tc in RELATIONSHIPS:
        if ft not in frames or fc not in frames[ft].columns:
            continue
        if tt not in frames or tc not in frames[tt].columns:
            continue
        rel_lines += [f"relationship {uuid.uuid4()}",
                      f"\tfromColumn: {ft}.{fc}", f"\ttoColumn: {tt}.{tc}", ""]
    (MODEL_DIR / "definition" / "relationships.tmdl").write_text(
        "\n".join(rel_lines), encoding="utf-8")

    refs = "\n".join(f"ref table {t}" for t in tables)
    (MODEL_DIR / "definition" / "model.tmdl").write_text(
        "model Model\n\tculture: en-GB\n"
        "\tdefaultPowerBIDataSourceVersion: powerBI_V3\n"
        "\tsourceQueryCulture: en-GB\n\tdataAccessOptions\n"
        "\t\tlegacyRedirects\n\t\treturnErrorValuesAsNull\n\n"
        f"{refs}\n", encoding="utf-8")
    (MODEL_DIR / "definition" / "database.tmdl").write_text(
        "database\n\tcompatibilityLevel: 1567\n", encoding="utf-8")
    (MODEL_DIR / "definition.pbism").write_text(
        json.dumps({"version": "4.2", "settings": {}}, indent=2), encoding="utf-8")

    section = {"name": uuid.uuid4().hex, "displayName": "Overview", "filters": "[]",
               "ordinal": 0, "visualContainers": [], "config": "{}",
               "displayOption": 1, "height": 720.0, "width": 1280.0}
    (REPORT_DIR / "report.json").write_text(
        json.dumps({"config": json.dumps({"version": "5.55", "themeCollection": {}}),
                    "layoutOptimization": 0, "resourcePackages": [],
                    "sections": [section], "filters": "[]"}, indent=2),
        encoding="utf-8")
    (REPORT_DIR / "definition.pbir").write_text(
        json.dumps({"version": "4.0",
                    "datasetReference": {"byPath": {"path": f"../{NAME}.SemanticModel"}}},
                   indent=2), encoding="utf-8")
    (PBI / f"{NAME}.pbip").write_text(
        json.dumps({"version": "1.0",
                    "artifacts": [{"report": {"path": f"{NAME}.Report"}}],
                    "settings": {"enableAutoRecovery": True}}, indent=2),
        encoding="utf-8")

    print(f"Power BI project written to {PBI}")
    print(f"  {len(tables)} tables · {len(rel_lines)//4} relationships · "
          f"{len(MEASURES)} DAX measures ({CURRENCY})")
    print(f"  data folder parameter -> {DATA_PBI}")


if __name__ == "__main__":
    build()
