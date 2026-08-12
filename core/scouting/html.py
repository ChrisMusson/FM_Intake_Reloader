"""HTML rendering helpers for scouting report tables."""

import html
import json

import pandas as pd

# Cell styling is keyed off column names, not positions, because the exported view decides which columns exist.
# Anything not listed here renders as plain text in the body font.
NUMERIC_COLUMNS = ("Age", "Wage", "Value", "CA", "PA")  # right-aligned
MONOSPACE_COLUMNS = ("Wage", "Value", "CA", "PA")  # figures worth lining up digit by digit, as are the role scores


def _display_cell(value):
    if pd.isna(value):
        return ""
    return html.escape(str(value))


def _column_class(column):
    classes = [
        "numeric-cell" if column in NUMERIC_COLUMNS else "",
        "mono-cell" if column in MONOSPACE_COLUMNS else "",
    ]
    applied = [css_class for css_class in classes if css_class]
    return f' class="{" ".join(applied)}"' if applied else ""


def _role_toggle_html(role, column_index):
    return (
        f'<button class="role-toggle is-active" type="button" data-column-index="{column_index}" aria-pressed="true">'
        f'<span class="role-toggle-code">{html.escape(role.short_label)}</span>'
        "</button>"
    )


def _build_numeric_filters(dataframe, column_sort_values=None):
    filters = []
    column_sort_values = column_sort_values or {}

    for column_index, column_name in enumerate(dataframe.columns):
        raw_values = column_sort_values.get(column_name, dataframe[column_name].tolist())
        numeric_values = pd.to_numeric(pd.Series(raw_values), errors="coerce").dropna()
        if numeric_values.empty:
            continue

        min_value = float(numeric_values.min())
        max_value = float(numeric_values.max())
        step = "1" if (numeric_values % 1 == 0).all() else "0.1"
        default_min = 0 if min_value >= 0 else min_value
        filters.append(
            {
                "column_index": column_index,
                "column_name": str(column_name),
                "default_min": int(default_min) if step == "1" else round(default_min, 1),
                "default_max": int(max_value) if step == "1" else round(max_value, 1),
                "input_chars": max(
                    len(str(int(default_min) if step == "1" else round(default_min, 1))),
                    len(str(int(max_value) if step == "1" else round(max_value, 1))),
                ),
                "step": step,
            }
        )

    return filters


def _build_table_html(dataframe, column_sort_values=None):
    column_sort_values = column_sort_values or {}
    column_classes = {column: _column_class(column) for column in dataframe.columns}
    header_html = "".join(f"<th{column_classes[column]}>{html.escape(str(column))}</th>" for column in dataframe.columns)
    body_rows = []

    for row_index, (_, row) in enumerate(dataframe.iterrows()):
        cells = []
        for column in dataframe.columns:
            sort_values = column_sort_values.get(column)
            sort_value = sort_values[row_index] if sort_values is not None else None
            data_order = "" if sort_value is None or pd.isna(sort_value) else f' data-order="{html.escape(str(sort_value))}"'
            cells.append(f"<td{column_classes[column]}{data_order}>{_display_cell(row[column])}</td>")
        body_rows.append("<tr>" + "".join(cells) + "</tr>")

    return (
        f'<table border="0" class="report-table" id="player-table"><thead><tr>{header_html}</tr></thead><tbody>{"".join(body_rows)}</tbody></table>'
    )


def build_sortable_table_html(
    dataframe,
    *,
    title="FM Player Scan",
    subtitle="",
    roles=(),
    score_columns=(),
    default_sort_column=None,
    column_sort_values=None,
    # Scores run 0-100, but the bar covers 20-85: below 20 is unplayable and above 85 is elite either
    # way, so spending the bar's travel on those ends only flattens the differences that matter.
    score_style_min=20,
    score_style_max=85,
    # The colour ramp keeps its own tighter range, so most players sit in the part of the gradient
    # where the differences are visible. Reports scoring on another scale should set both ranges.
    score_colour_min=35,
    score_colour_max=75,
):
    if dataframe.empty:
        raise ValueError("Cannot build a player scan report from an empty dataframe")

    score_columns = [column for column in score_columns if column in dataframe.columns]
    if default_sort_column is None:
        default_sort_column = score_columns[0] if score_columns else dataframe.columns[-1]

    sort_column_index = dataframe.columns.get_loc(default_sort_column)
    score_column_indexes = [dataframe.columns.get_loc(column) for column in score_columns]
    table_html = _build_table_html(dataframe, column_sort_values=column_sort_values)
    numeric_filters = _build_numeric_filters(dataframe, column_sort_values=column_sort_values)
    role_toggles_html = "".join(
        _role_toggle_html(role, dataframe.columns.get_loc(column)) for role, column in zip(roles, score_columns, strict=False)
    )
    numeric_filter_html = "".join(
        (
            f'<div class="range-filter" data-column-index="{filter_info["column_index"]}" style="--input-width-ch: {filter_info["input_chars"]};">'
            f'<div class="range-filter-label">{html.escape(filter_info["column_name"])}</div>'
            '<div class="range-filter-inputs">'
            f'<input class="range-filter-min" type="number" value="{filter_info["default_min"]}" step="{filter_info["step"]}">'
            '<span class="range-filter-separator">to</span>'
            f'<input class="range-filter-max" type="number" value="{filter_info["default_max"]}" step="{filter_info["step"]}">'
            "</div>"
            "</div>"
        )
        for filter_info in numeric_filters
    )

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <title>{html.escape(title)}</title>
    <link rel="preconnect" href="https://fonts.googleapis.com">
    <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
    <link href="https://fonts.googleapis.com/css2?family=Space+Grotesk:wght@400;500;700&family=JetBrains+Mono:wght@500;700&display=swap" rel="stylesheet">
    <link href="https://cdn.datatables.net/1.11.5/css/jquery.dataTables.min.css" rel="stylesheet">
    <style>
        :root {{
            --bg-1: #071018;
            --bg-2: #0d1a27;
            --panel: rgba(9, 16, 24, 0.82);
            --panel-strong: rgba(13, 22, 33, 0.96);
            --line: rgba(160, 196, 220, 0.18);
            --line-strong: rgba(160, 196, 220, 0.28);
            --text: #ecf4fb;
            --muted: #98acbf;
            --accent: #7dd3fc;
            --accent-2: #f6c453;
        }}

        * {{
            box-sizing: border-box;
        }}

        body {{
            margin: 0;
            min-height: 100vh;
            color: var(--text);
            font-family: "Space Grotesk", "Segoe UI", sans-serif;
            background:
                radial-gradient(circle at top left, rgba(74, 144, 226, 0.22), transparent 34%),
                radial-gradient(circle at top right, rgba(246, 196, 83, 0.18), transparent 30%),
                linear-gradient(160deg, var(--bg-2) 0%, var(--bg-1) 72%);
        }}

        .page {{
            width: min(1960px, calc(100vw - 24px));
            margin: 0 auto;
            padding: 20px 8px 32px;
        }}

        .toolbar-card {{
            margin-bottom: 12px;
            padding: 12px;
            border-radius: 22px;
            background: rgba(10, 17, 27, 0.72);
            border: 1px solid var(--line);
            box-shadow: 0 18px 46px rgba(0, 0, 0, 0.2);
            backdrop-filter: blur(18px);
        }}

        .toolbar-copy {{
            display: flex;
            flex-wrap: wrap;
            align-items: baseline;
            justify-content: space-between;
            gap: 8px 18px;
            margin-bottom: 10px;
            padding: 2px 4px 0;
        }}

        .toolbar-title {{
            color: var(--text);
            font-size: 0.95rem;
            font-weight: 700;
            letter-spacing: 0.06em;
            text-transform: uppercase;
        }}

        .toolbar-meta {{
            color: var(--muted);
            font-size: 0.92rem;
        }}

        .role-toggle-grid {{
            display: flex;
            flex-wrap: wrap;
            gap: 10px;
        }}

        .role-toggle {{
            appearance: none;
            padding: 10px 12px;
            border-radius: 16px;
            background: rgba(125, 211, 252, 0.06);
            border: 1px solid rgba(125, 211, 252, 0.14);
            color: inherit;
            cursor: pointer;
            text-align: left;
            transition: transform 120ms ease, border-color 120ms ease, background-color 120ms ease, opacity 120ms ease;
        }}

        .role-toggle:hover {{
            transform: translateY(-1px);
            border-color: rgba(125, 211, 252, 0.35);
        }}

        .role-toggle.is-active {{
            background: rgba(125, 211, 252, 0.09);
            border-color: rgba(125, 211, 252, 0.3);
        }}

        .role-toggle:not(.is-active) {{
            opacity: 0.58;
            background: rgba(125, 211, 252, 0.03);
        }}

        .role-toggle-code {{
            color: var(--text);
            font-family: "JetBrains Mono", monospace;
            font-size: 0.93rem;
            font-weight: 700;
        }}

        .table-card {{
            padding: 16px 16px 14px;
            border-radius: 28px;
            background: var(--panel);
            border: 1px solid var(--line);
            box-shadow: 0 24px 70px rgba(0, 0, 0, 0.28);
            backdrop-filter: blur(18px);
        }}

        .filter-panel {{
            margin-bottom: 12px;
            border-radius: 22px;
            border: 1px solid var(--line);
            background: rgba(10, 17, 27, 0.72);
            box-shadow: 0 18px 46px rgba(0, 0, 0, 0.2);
            backdrop-filter: blur(18px);
        }}

        .filter-panel > summary {{
            display: flex;
            align-items: center;
            justify-content: space-between;
            gap: 12px;
            padding: 12px 14px;
            cursor: pointer;
            list-style: none;
            color: var(--text);
            font-size: 0.95rem;
            font-weight: 700;
            letter-spacing: 0.06em;
            text-transform: uppercase;
        }}

        .filter-panel > summary::-webkit-details-marker {{
            display: none;
        }}

        .filter-panel[open] > summary {{
            border-bottom: 1px solid var(--line);
        }}

        .filter-panel-body {{
            padding: 12px;
        }}

        .filter-panel-copy {{
            margin: 0 0 12px;
            color: var(--muted);
            font-size: 0.9rem;
        }}

        .filter-grid {{
            display: flex;
            flex-wrap: wrap;
            gap: 10px;
        }}

        .range-filter {{
            width: max-content;
            max-width: 100%;
            padding: 10px 12px;
            border-radius: 16px;
            background: rgba(125, 211, 252, 0.06);
            border: 1px solid rgba(125, 211, 252, 0.14);
        }}

        .range-filter-label {{
            margin-bottom: 8px;
            color: var(--text);
            font-family: "JetBrains Mono", monospace;
            font-size: 0.84rem;
            font-weight: 700;
        }}

        .range-filter-inputs {{
            display: grid;
            grid-template-columns: max-content auto max-content;
            gap: 6px;
            align-items: center;
            justify-content: start;
        }}

        .range-filter-inputs input {{
            width: calc(var(--input-width-ch, 4) * 1ch + 22px);
            padding: 8px 10px;
            border-radius: 10px;
            border: 1px solid var(--line-strong);
            background: rgba(8, 14, 22, 0.9);
            color: var(--text);
            font: inherit;
            font-family: "JetBrains Mono", monospace;
            outline: none;
            box-shadow: none;
        }}

        .range-filter-inputs input[type="number"] {{
            appearance: textfield;
            -moz-appearance: textfield;
        }}

        .range-filter-inputs input[type="number"]::-webkit-outer-spin-button,
        .range-filter-inputs input[type="number"]::-webkit-inner-spin-button {{
            -webkit-appearance: none;
            margin: 0;
        }}

        .range-filter-inputs input:focus {{
            border-color: rgba(125, 211, 252, 0.65);
            box-shadow: 0 0 0 3px rgba(125, 211, 252, 0.12);
        }}

        .range-filter-separator {{
            color: var(--muted);
            font-size: 0.82rem;
        }}

        .filter-reset {{
            appearance: none;
            padding: 8px 12px;
            border-radius: 999px;
            border: 1px solid rgba(160, 196, 220, 0.18);
            background: rgba(255, 255, 255, 0.03);
            color: var(--muted);
            cursor: pointer;
            font: inherit;
        }}

        .table-heading {{
            display: flex;
            justify-content: space-between;
            gap: 16px;
            align-items: end;
            margin-bottom: 12px;
        }}

        .table-heading h2 {{
            margin: 0;
            font-size: 1.15rem;
            letter-spacing: -0.03em;
        }}

        .table-heading p {{
            margin: 6px 0 0;
            color: var(--muted);
        }}

        .table-wrap {{
            overflow-x: auto;
            overflow-y: auto;
            border-radius: 20px;
            border: 1px solid var(--line);
            background: var(--panel-strong);
        }}

        .dataTables_wrapper {{
            color: var(--text);
        }}

        .dataTables_wrapper .table-tools {{
            padding: 12px 12px 0;
        }}

        .dataTables_wrapper .dataTables_filter {{
            float: none;
            text-align: left;
            margin-bottom: 14px;
        }}

        .dataTables_wrapper .dataTables_filter label {{
            display: block;
            color: var(--muted);
            font-size: 0.88rem;
            letter-spacing: 0.06em;
            text-transform: uppercase;
        }}

        .dataTables_wrapper .dataTables_filter input {{
            width: min(360px, 100%);
            margin-left: 0;
            margin-top: 10px;
            padding: 12px 14px;
            border-radius: 14px;
            border: 1px solid var(--line-strong);
            background: rgba(8, 14, 22, 0.9);
            color: var(--text);
            font: inherit;
            outline: none;
            box-shadow: none;
        }}

        .dataTables_wrapper .dataTables_filter input:focus {{
            border-color: rgba(125, 211, 252, 0.65);
            box-shadow: 0 0 0 4px rgba(125, 211, 252, 0.12);
        }}

        table.dataTable.report-table,
        table.dataTable.report-table thead th,
        table.dataTable.report-table tbody td {{
            border: 0;
        }}

        table.dataTable.report-table {{
            width: max-content !important;
            min-width: 100%;
            margin: 0 !important;
            border-collapse: separate !important;
            border-spacing: 0;
        }}

        table.dataTable.report-table thead th {{
            position: sticky;
            top: 0;
            z-index: 2;
            padding: 12px 10px;
            background: rgba(10, 17, 27, 0.98);
            color: #bfd3e6;
            font-size: 0.69rem;
            letter-spacing: 0.12em;
            text-transform: uppercase;
            white-space: nowrap;
            border-bottom: 1px solid var(--line-strong);
        }}

        table.dataTable.report-table thead th.sorting,
        table.dataTable.report-table thead th.sorting_asc,
        table.dataTable.report-table thead th.sorting_desc {{
            background-image: none !important;
            padding-right: 14px !important;
        }}

        table.dataTable.report-table tbody td {{
            padding: 10px 10px;
            white-space: nowrap;
            color: #dfeaf4;
            border-bottom: 1px solid rgba(160, 196, 220, 0.1);
            background-color: rgba(12, 20, 31, 0.92) !important;
            font-size: 0.94rem;
            transition: background-color 120ms ease, color 120ms ease;
        }}

        table.dataTable.report-table tbody tr.even td {{
            background-color: rgba(15, 24, 36, 0.96) !important;
        }}

        table.dataTable.report-table tbody tr.odd td {{
            background-color: rgba(11, 19, 29, 0.94) !important;
        }}

        table.dataTable.report-table tbody tr:hover td {{
            background-color: rgba(25, 41, 58, 0.98) !important;
        }}

        table.dataTable.report-table tbody td {{
            font-family: "Space Grotesk", "Segoe UI", sans-serif;
        }}

        table.dataTable.report-table tbody td.mono-cell,
        table.dataTable.report-table tbody td.score-cell {{
            font-family: "JetBrains Mono", monospace;
            font-weight: 600;
        }}

        table.dataTable.report-table thead th.numeric-cell,
        table.dataTable.report-table tbody td.numeric-cell {{
            text-align: right;
        }}

        table.dataTable.report-table tbody td.score-cell {{
            color: #f3f8fe;
        }}

        @media (max-width: 860px) {{
            .page {{
                width: calc(100vw - 16px);
                padding: 14px 4px 24px;
            }}

            .toolbar-card,
            .table-card {{
                padding-left: 12px;
                padding-right: 12px;
            }}
        }}
    </style>
</head>
<body>
    <main class="page">
        <section class="toolbar-card">
            <div class="toolbar-copy">
                <div class="toolbar-title">Role Columns</div>
                <div class="toolbar-meta">{len(dataframe):,} players | click a role to hide or show its column</div>
            </div>
            <div class="role-toggle-grid">
                {role_toggles_html}
            </div>
        </section>

        <details class="filter-panel">
            <summary>
                <span>Range Filters</span>
                <button class="filter-reset" type="button">Reset</button>
            </summary>
            <div class="filter-panel-body">
                <p class="filter-panel-copy">Set a minimum and maximum for any numeric column. Defaults are 0 and that column's current maximum.</p>
                <div class="filter-grid">
                    {numeric_filter_html}
                </div>
            </div>
        </details>

        <section class="table-card">
            <div class="table-heading">
                <div>
                    <h2>{html.escape(title)}</h2>
                    <p>{html.escape(subtitle)}</p>
                </div>
            </div>
            <div class="table-wrap">
                {table_html}
            </div>
        </section>
    </main>

    <script src="https://code.jquery.com/jquery-3.6.0.slim.min.js" integrity="sha256-u7e5khyithlIdTpu22PHhENmPcRdFiHRjhAuHcs05RI=" crossorigin="anonymous"></script>
    <script src="https://cdn.datatables.net/1.11.5/js/jquery.dataTables.min.js"></script>
    <script>
        const scoreColumnIndexes = {json.dumps(score_column_indexes)};
        const numericFilters = {json.dumps(numeric_filters)};
        const scoreStyleMin = {json.dumps(score_style_min)};
        const scoreStyleMax = {json.dumps(score_style_max)};
        const scoreColourMin = {json.dumps(score_colour_min)};
        const scoreColourMax = {json.dumps(score_colour_max)};

        function scoreIntensity(rawScore, minimum, maximum) {{
            const clamped = Math.max(minimum, Math.min(maximum, rawScore));
            return (clamped - minimum) / Math.max(1, maximum - minimum);
        }}

        function applyScoreStyling(table) {{
            scoreColumnIndexes.forEach((columnIndex) => {{
                table.column(columnIndex, {{ page: "current" }}).nodes().each((cell) => {{
                    cell.classList.add("score-cell");
                    cell.style.backgroundColor = "rgba(14, 23, 34, 0.95)";
                    cell.style.backgroundImage = "";

                    const rawScore = parseNumericCell(cell, cell.textContent.trim());
                    if (Number.isNaN(rawScore)) {{
                        return;
                    }}

                    const intensity = scoreIntensity(rawScore, scoreStyleMin, scoreStyleMax);
                    const colourIntensity = scoreIntensity(rawScore, scoreColourMin, scoreColourMax);
                    const hue = 8 + colourIntensity * 120;
                    const alpha = 0.16 + colourIntensity * 0.22;
                    const stop = intensity * 100;
                    cell.style.backgroundImage = `linear-gradient(90deg, hsla(${{hue}}, 88%, 58%, ${{alpha}}) 0%, hsla(${{hue}}, 88%, 58%, ${{alpha}}) ${{stop}}%, rgba(0, 0, 0, 0) ${{stop}}%)`;
                }});
            }});
        }}

        function parseNumericCell(cell, fallbackText) {{
            if (cell && cell.dataset.order !== undefined && cell.dataset.order !== "") {{
                const numericOrder = Number(cell.dataset.order);
                if (!Number.isNaN(numericOrder)) {{
                    return numericOrder;
                }}
            }}

            const numericText = Number(String(fallbackText).replace(/[^0-9.-]+/g, ""));
            return Number.isNaN(numericText) ? null : numericText;
        }}

        $(document).ready(function () {{
            const table = $("#player-table").DataTable({{
                paging: false,
                info: false,
                autoWidth: false,
                orderClasses: false,
                stripeClasses: [],
                order: [[{sort_column_index}, "desc"]],
                columnDefs: [
                    {{
                        targets: "_all",
                        orderSequence: ["desc", "asc"]
                    }}
                ],
                dom: '<"table-tools"f>t'
            }});

            $("#player-table_filter input").attr("placeholder", "Filter players, clubs, nations, positions...");
            document.querySelector(".filter-reset").addEventListener("click", (event) => {{
                event.preventDefault();
                numericFilters.forEach((filterInfo) => {{
                    const filterElement = document.querySelector(`.range-filter[data-column-index="${{filterInfo.column_index}}"]`);
                    filterElement.querySelector(".range-filter-min").value = filterInfo.default_min;
                    filterElement.querySelector(".range-filter-max").value = filterInfo.default_max;
                }});
                table.draw();
            }});

            document.querySelectorAll(".role-toggle").forEach((button) => {{
                button.addEventListener("click", () => {{
                    const columnIndex = Number(button.dataset.columnIndex);
                    const column = table.column(columnIndex);
                    const nextVisible = !column.visible();
                    column.visible(nextVisible, false);
                    button.classList.toggle("is-active", nextVisible);
                    button.setAttribute("aria-pressed", String(nextVisible));
                    table.columns.adjust().draw(false);
                }});
            }});

            $.fn.dataTable.ext.search.push(function (settings, rowData, dataIndex) {{
                if (settings.nTable !== table.table().node()) {{
                    return true;
                }}

                const rowNode = table.row(dataIndex).node();
                for (const filterInfo of numericFilters) {{
                    const filterElement = document.querySelector(`.range-filter[data-column-index="${{filterInfo.column_index}}"]`);
                    const minValue = Number(filterElement.querySelector(".range-filter-min").value);
                    const maxValue = Number(filterElement.querySelector(".range-filter-max").value);
                    const cell = rowNode ? rowNode.children[filterInfo.column_index] : null;
                    const numericValue = parseNumericCell(cell, rowData[filterInfo.column_index]);

                    if (numericValue === null) {{
                        continue;
                    }}
                    if (!Number.isNaN(minValue) && numericValue < minValue) {{
                        return false;
                    }}
                    if (!Number.isNaN(maxValue) && numericValue > maxValue) {{
                        return false;
                    }}
                }}

                return true;
            }});

            document.querySelectorAll(".range-filter input").forEach((input) => {{
                input.addEventListener("input", () => {{
                    table.draw();
                }});
            }});

            applyScoreStyling(table);
            table.on("draw", function () {{
                applyScoreStyling(table);
            }});
        }});
    </script>
</body>
</html>
"""
