"""Store formula results inside a saved .xlsx so every viewer shows them.

openpyxl writes a formula with an empty result slot and leaves calculation
to the spreadsheet program. Full Excel fills the slot when it opens the
file; anything that only displays it — Excel's Protected View for a file
that arrived by email or download, phone and mail previews — shows the
empty slot instead. A savings workbook then reads as having no savings.

This fills the slot with the value the app already computed, leaving the
formula itself in place, so the figures show everywhere and still move
when someone edits the sheet. Pure zip/XML: no openpyxl needed here.
"""

from __future__ import annotations

import math
import os
import re
import shutil
import tempfile
import zipfile
from xml.sax.saxutils import escape

XLSX_CACHE_VERSION = "1.0"

_NS_REL = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"


def _sheet_paths(archive):
    """Map each sheet's title to its XML part inside the archive."""
    book = archive.read("xl/workbook.xml").decode("utf-8")
    rels = archive.read("xl/_rels/workbook.xml.rels").decode("utf-8")
    targets = {}
    for rel in re.finditer(r"<Relationship\b([^>]*)/?>", rels):
        attrs = dict(re.findall(r'(\w+)="([^"]*)"', rel.group(1)))
        if "Id" in attrs and "Target" in attrs:
            target = attrs["Target"].lstrip("/")
            targets[attrs["Id"]] = (target if target.startswith("xl/")
                                    else "xl/" + target)
    out = {}
    for sheet in re.finditer(r"<sheet\b([^>]*)/?>", book):
        attrs = sheet.group(1)
        name = re.search(r'\bname="([^"]*)"', attrs)
        rid = re.search(r'\br:id="([^"]*)"', attrs) or re.search(
            r'\bid="([^"]*)"', attrs)
        if name and rid and rid.group(1) in targets:
            title = (name.group(1).replace("&amp;", "&").replace("&lt;", "<")
                     .replace("&gt;", ">").replace("&quot;", '"')
                     .replace("&apos;", "'"))
            out[title] = targets[rid.group(1)]
    return out


def _cached(value):
    """The <v> payload and the cell type a result is stored with."""
    if value is None or value == "":
        return "", "str"
    if isinstance(value, bool):
        return ("1" if value else "0"), "b"
    if isinstance(value, (int, float)):
        if isinstance(value, float) and not math.isfinite(value):
            return "", "str"
        return repr(float(value)) if isinstance(value, float) else str(value), None
    return escape(str(value)), "str"


def fill_sheet_xml(xml, results):
    """Return ``(xml, filled)``: each formula cell in ``results`` given its value.

    Only a formula cell whose result slot is empty is touched, so a value a
    spreadsheet program has already written is never overwritten.
    """
    filled = []

    def put(match):
        ref, attrs, formula = match.group(1), match.group(2), match.group(3)
        if ref not in results:
            return match.group(0)
        filled.append(ref)
        payload, kind = _cached(results[ref])
        attrs = re.sub(r'\s+t="[^"]*"', "", attrs)
        if kind:
            attrs += f' t="{kind}"'
        return f'<c r="{ref}"{attrs}><f>{formula}</f><v>{payload}</v></c>'

    new = re.sub(
        r'<c r="([A-Z]+[0-9]+)"([^>]*)><f>(.*?)</f>(?:<v\s*/>|<v></v>)?</c>',
        put, xml, flags=re.S)
    return new, len(filled)


def store_formula_results(path, results_by_sheet):
    """Write results into the formula cells of the workbook at ``path``.

    ``results_by_sheet`` is ``{sheet title: {"B8": value, ...}}``. Returns
    how many cells were filled. The file is rewritten through a temporary
    copy, so a failure part-way leaves the original as it was.
    """
    filled = 0
    with zipfile.ZipFile(path) as src:
        paths = _sheet_paths(src)
        parts = {paths[title]: results
                 for title, results in (results_by_sheet or {}).items()
                 if title in paths and results}
        fd, tmp = tempfile.mkstemp(suffix=".xlsx",
                                   dir=os.path.dirname(os.path.abspath(path)))
        os.close(fd)
        try:
            with zipfile.ZipFile(tmp, "w", zipfile.ZIP_DEFLATED) as dst:
                for item in src.infolist():
                    data = src.read(item.filename)
                    if item.filename in parts:
                        xml = data.decode("utf-8")
                        new, count = fill_sheet_xml(xml, parts[item.filename])
                        filled += count
                        data = new.encode("utf-8")
                    dst.writestr(item, data)
            shutil.move(tmp, path)
        except Exception:
            if os.path.exists(tmp):
                os.remove(tmp)
            raise
    return filled
