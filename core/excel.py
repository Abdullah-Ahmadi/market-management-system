"""Small dependency-free XLSX writer for MMS report exports.

The project intentionally keeps third-party dependencies limited to Django and Bootstrap.
This module writes the required Office Open XML parts using Python's standard library.
"""
from datetime import datetime
from decimal import Decimal
from io import BytesIO
from zipfile import ZIP_DEFLATED, ZipFile
from xml.sax.saxutils import escape


def _col_name(index):
    name = ''
    while index:
        index, rem = divmod(index - 1, 26)
        name = chr(65 + rem) + name
    return name


def _cell_xml(row, col, value, header=False):
    ref = f'{_col_name(col)}{row}'
    if value is None:
        value = ''
    if isinstance(value, bool):
        return f'<c r="{ref}" t="b"><v>{1 if value else 0}</v></c>'
    if isinstance(value, (int, float, Decimal)) and not isinstance(value, bool):
        style = 2 if not header else 1
        return f'<c r="{ref}" s="{style}"><v>{value}</v></c>'
    text = escape(str(value))
    style = ' s="1"' if header else ''
    preserve = ' xml:space="preserve"' if text.startswith(' ') or text.endswith(' ') else ''
    return f'<c r="{ref}" t="inlineStr"{style}><is><t{preserve}>{text}</t></is></c>'


def _sheet_xml(rows, freeze_cols=0, compact_matrix=False):
    max_cols = max((len(r) for r in rows), default=1)
    widths = []
    for col in range(max_cols):
        width = 12
        cap = 20 if compact_matrix and 5 <= col < max_cols - 3 else 42
        for row in rows[:200]:
            if col < len(row):
                width = max(width, min(cap, len(str(row[col])) + 2))
        widths.append(width)
    cols = ''.join(
        f'<col min="{i}" max="{i}" width="{w}" customWidth="1"/>'
        for i, w in enumerate(widths, 1)
    )
    row_xml = []
    for r_idx, values in enumerate(rows, 1):
        cells = ''.join(
            _cell_xml(r_idx, c_idx, value, header=(r_idx == 1))
            for c_idx, value in enumerate(values, 1)
        )
        attrs = ' ht="42" customHeight="1"' if r_idx == 1 else ''
        row_xml.append(f'<row r="{r_idx}"{attrs}>{cells}</row>')
    dimension = f'A1:{_col_name(max_cols)}{max(1, len(rows))}'
    autofilter = f'<autoFilter ref="{dimension}"/>' if rows else ''
    if freeze_cols:
        top_left = f'{_col_name(freeze_cols + 1)}2'
        pane = f'<pane xSplit="{freeze_cols}" ySplit="1" topLeftCell="{top_left}" activePane="bottomRight" state="frozen"/>'
    else:
        pane = '<pane ySplit="1" topLeftCell="A2" activePane="bottomLeft" state="frozen"/>'
    return f'''<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">
<dimension ref="{dimension}"/>
<sheetViews><sheetView workbookViewId="0">{pane}</sheetView></sheetViews>
<cols>{cols}</cols><sheetData>{''.join(row_xml)}</sheetData>{autofilter}
</worksheet>'''


def build_xlsx(sheets):
    """Return XLSX bytes. Accepts [(name, rows), ...] or an ordered mapping."""
    if hasattr(sheets, 'items'):
        sheets = sheets.items()
    safe = []
    used = set()
    for raw_name, rows in sheets:
        name = ''.join(ch for ch in str(raw_name) if ch not in r'[]:*?/\\')[:31] or 'Sheet'
        base = name
        n = 2
        while name in used:
            suffix = f' {n}'
            name = (base[: 31 - len(suffix)] + suffix)
            n += 1
        used.add(name)
        safe.append((name, rows))

    output = BytesIO()
    with ZipFile(output, 'w', ZIP_DEFLATED) as z:
        sheet_overrides = ''.join(
            f'<Override PartName="/xl/worksheets/sheet{i}.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>'
            for i in range(1, len(safe) + 1)
        )
        z.writestr(
            '[Content_Types].xml',
            f'''<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">
<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>
<Default Extension="xml" ContentType="application/xml"/>
<Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/>
<Override PartName="/xl/styles.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.styles+xml"/>
{sheet_overrides}
<Override PartName="/docProps/core.xml" ContentType="application/vnd.openxmlformats-package.core-properties+xml"/>
<Override PartName="/docProps/app.xml" ContentType="application/vnd.openxmlformats-officedocument.extended-properties+xml"/>
</Types>''',
        )
        z.writestr(
            '_rels/.rels',
            '''<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="xl/workbook.xml"/>
<Relationship Id="rId2" Type="http://schemas.openxmlformats.org/package/2006/relationships/metadata/core-properties" Target="docProps/core.xml"/>
<Relationship Id="rId3" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/extended-properties" Target="docProps/app.xml"/>
</Relationships>''',
        )
        sheets_xml = ''.join(
            f'<sheet name="{escape(name)}" sheetId="{i}" r:id="rId{i}"/>'
            for i, (name, _) in enumerate(safe, 1)
        )
        z.writestr(
            'xl/workbook.xml',
            f'''<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"><sheets>{sheets_xml}</sheets></workbook>''',
        )
        rels = ''.join(
            f'<Relationship Id="rId{i}" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet{i}.xml"/>'
            for i in range(1, len(safe) + 1)
        )
        style_id = len(safe) + 1
        z.writestr(
            'xl/_rels/workbook.xml.rels',
            f'''<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">{rels}<Relationship Id="rId{style_id}" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/styles" Target="styles.xml"/></Relationships>''',
        )
        z.writestr(
            'xl/styles.xml',
            '''<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<styleSheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">
<numFmts count="1"><numFmt numFmtId="164" formatCode="#,##0.##"/></numFmts>
<fonts count="2"><font><sz val="11"/><name val="Calibri"/></font><font><b/><color rgb="FFFFFFFF"/><sz val="11"/><name val="Calibri"/></font></fonts>
<fills count="2"><fill><patternFill patternType="none"/></fill><fill><patternFill patternType="solid"><fgColor rgb="FF005CB9"/><bgColor indexed="64"/></patternFill></fill></fills>
<borders count="1"><border><left/><right/><top/><bottom/><diagonal/></border></borders>
<cellStyleXfs count="1"><xf numFmtId="0" fontId="0" fillId="0" borderId="0"/></cellStyleXfs>
<cellXfs count="3"><xf numFmtId="0" fontId="0" fillId="0" borderId="0" xfId="0"/><xf numFmtId="0" fontId="1" fillId="1" borderId="0" xfId="0" applyFill="1" applyFont="1" applyAlignment="1"><alignment horizontal="center" vertical="center" wrapText="1"/></xf><xf numFmtId="164" fontId="0" fillId="0" borderId="0" xfId="0" applyNumberFormat="1"/></cellXfs>
<cellStyles count="1"><cellStyle name="Normal" xfId="0" builtinId="0"/></cellStyles>
</styleSheet>''',
        )
        for i, (name, rows) in enumerate(safe, 1):
            is_daily_matrix = name == 'Daily Sales Report'
            z.writestr(
                f'xl/worksheets/sheet{i}.xml',
                _sheet_xml(rows, freeze_cols=5 if is_daily_matrix else 0, compact_matrix=is_daily_matrix),
            )
        now = datetime.utcnow().replace(microsecond=0).isoformat() + 'Z'
        z.writestr(
            'docProps/core.xml',
            f'''<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<cp:coreProperties xmlns:cp="http://schemas.openxmlformats.org/package/2006/metadata/core-properties" xmlns:dc="http://purl.org/dc/elements/1.1/" xmlns:dcterms="http://purl.org/dc/terms/" xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"><dc:creator>MMS</dc:creator><dc:title>MMS Sales Report</dc:title><dcterms:created xsi:type="dcterms:W3CDTF">{now}</dcterms:created></cp:coreProperties>''',
        )
        titles = ''.join(f'<vt:lpstr>{escape(name)}</vt:lpstr>' for name, _ in safe)
        z.writestr(
            'docProps/app.xml',
            f'''<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Properties xmlns="http://schemas.openxmlformats.org/officeDocument/2006/extended-properties" xmlns:vt="http://schemas.openxmlformats.org/officeDocument/2006/docPropsVTypes"><Application>MMS</Application><TitlesOfParts><vt:vector size="{len(safe)}" baseType="lpstr">{titles}</vt:vector></TitlesOfParts></Properties>''',
        )
    return output.getvalue()
