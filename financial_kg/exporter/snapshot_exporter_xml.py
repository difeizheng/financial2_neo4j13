"""Snapshot Excel export using zipfile/XML approach (preserves cached values).

This module directly manipulates Excel xlsx internal XML structure to:
1. Preserve formula cells' cached values (openpyxl loses these on save)
2. Update parameter cells' values only
3. Maintain all original formatting and structure

xlsx structure:
- xlsx file is a zip package
- xl/worksheets/sheet*.xml contains cell data
- Each cell: <c r="A1"><f>SUM(...)</f><v>123</v></c>
  * <f> = formula
  * <v> = cached value (preserved in this approach)
"""
from __future__ import annotations
import zipfile
import tempfile
import os
import shutil
from xml.etree import ElementTree as ET
from io import BytesIO
from datetime import datetime
from typing import Any

from financial_kg.models.graph import FinancialGraph
from financial_kg.engine.snapshot import Snapshot


# Excel XML namespace
NS = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
NS_MAP = {"main": NS}


def parse_cell_id(cell_id: str) -> tuple[str, int, str]:
    """Parse cell_id into (sheet_name, row, col_letter).
    
    Args:
        cell_id: Format like "Sheet1_5_A"
    
    Returns:
        (sheet_name, row_number, column_letter)
    """
    parts = cell_id.split("_")
    if len(parts) < 3:
        raise ValueError(f"Invalid cell_id format: {cell_id}")
    return parts[0], int(parts[1]), parts[2]


def convert_iso_date_to_datetime(value: Any) -> Any:
    """Convert ISO date string to datetime object for Excel.
    
    Args:
        value: Could be ISO string like "2023-02-01T00:00:00" or other types
    
    Returns:
        datetime object if ISO format detected, otherwise original value
    """
    if isinstance(value, str) and "T00:00:00" in value:
        try:
            dt_str = value.replace("T00:00:00", "")
            return datetime.fromisoformat(dt_str)
        except Exception:
            return value
    return value


def convert_value_to_excel_serial(value: Any) -> str:
    """Convert Python value to Excel serial number or string.
    
    Args:
        value: Python value (number, string, datetime, etc.)
    
    Returns:
        String representation for Excel XML <v> node
    
    Notes:
        - Numbers: keep as-is
        - Datetime: convert to Excel serial (days since 1899-12-30)
        - Strings: keep as-is (may need sharedStrings lookup in future)
    """
    if isinstance(value, datetime):
        # Excel serial: days since 1899-12-30 (Excel epoch)
        excel_epoch = datetime(1899, 12, 30)
        delta = value - excel_epoch
        serial = delta.days + delta.seconds / 86400
        return str(serial)
    elif isinstance(value, (int, float)):
        return str(value)
    elif isinstance(value, bool):
        return str(int(value))
    elif value is None:
        return ""
    else:
        # String value (may need sharedStrings in future implementation)
        return str(value)


def get_sheet_xml_path(sheet_name: str, workbook_xml_path: str, temp_dir: str) -> str | None:
    """Find the XML file path for a given sheet name.
    
    Args:
        sheet_name: Sheet name in Excel
        workbook_xml_path: Path to xl/workbook.xml
        temp_dir: Temporary directory containing extracted xlsx
    
    Returns:
        XML file path for the sheet, or None if not found
    
    Notes:
        workbook.xml contains sheet name to sheetId mapping:
        <sheet name="Sheet1" sheetId="1" r:id="rId1"/>
        workbook.xml.rels contains rId to file mapping:
        <Relationship Id="rId1" Target="worksheets/sheet1.xml"/>
    """
    # Read workbook.xml to find sheet name → rId mapping
    workbook_tree = ET.parse(workbook_xml_path)
    workbook_root = workbook_tree.getroot()
    
    sheet_rid = None
    for sheet_elem in workbook_root.findall(".//main:sheet", NS_MAP):
        if sheet_elem.get("name") == sheet_name:
            # r:id attribute (with namespace)
            # Excel uses xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"
            rid = sheet_elem.get("{http://schemas.openxmlformats.org/officeDocument/2006/relationships}id")
            if rid:
                sheet_rid = rid
                break
    
    if not sheet_rid:
        return None
    
    # Read workbook.xml.rels to find rId → file mapping
    rels_path = os.path.join(temp_dir, "xl", "_rels", "workbook.xml.rels")
    if not os.path.exists(rels_path):
        return None
    
    rels_tree = ET.parse(rels_path)
    rels_root = rels_tree.getroot()
    
    # Find the relationship with matching rId
    rels_ns = "http://schemas.openxmlformats.org/package/2006/relationships"
    for rel_elem in rels_root.findall(f".//{{{rels_ns}}}Relationship"):
        if rel_elem.get("Id") == sheet_rid:
            target = rel_elem.get("Target")
            if target:
                # Target is relative path like "worksheets/sheet1.xml"
                return os.path.join(temp_dir, "xl", target)
    
    return None


def update_cell_value_in_xml(sheet_xml_path: str, cell_id: str, new_value: Any) -> bool:
    """Update a cell's value in sheet XML (preserves formula and cached value structure).
    
    Args:
        sheet_xml_path: Path to sheet XML file
        cell_id: Cell ID like "Sheet1_5_A"
        new_value: New value to set
    
    Returns:
        True if cell found and updated, False otherwise
    
    Notes:
        - For parameter cells: updates <v> node
        - For formula cells: does NOT modify (preserves <f> and <v>)
        - This approach preserves cached values for formula cells
    """
    _, row, col_letter = parse_cell_id(cell_id)
    cell_ref = f"{col_letter}{row}"
    
    # Parse sheet XML
    tree = ET.parse(sheet_xml_path)
    root = tree.getroot()
    
    # Find the cell with matching r attribute
    cell_elem = None
    for row_elem in root.findall(".//main:row", NS_MAP):
        for c_elem in row_elem.findall("main:c", NS_MAP):
            if c_elem.get("r") == cell_ref:
                cell_elem = c_elem
                break
        if cell_elem:
            break
    
    if not cell_elem:
        return False
    
    # Check if this is a formula cell (has <f> child)
    has_formula = cell_elem.find("main:f", NS_MAP) is not None
    
    if has_formula:
        # Formula cell: DO NOT modify (preserve cached value)
        # User will see cached value when opening Excel
        return True  # Mark as "found but skipped"
    
    # Parameter cell: update <v> node
    v_elem = cell_elem.find("main:v", NS_MAP)
    
    # Convert value to Excel format
    excel_value = convert_value_to_excel_serial(convert_iso_date_to_datetime(new_value))
    
    if v_elem is None:
        # Create <v> node if missing
        v_elem = ET.SubElement(cell_elem, f"{{{NS}}}v")
    
    v_elem.text = excel_value
    
    # Write back to file
    tree.write(sheet_xml_path, encoding="UTF-8", xml_declaration=False)
    
    return True


def export_snapshot_via_xml(
    template_bytes: bytes,
    snapshot: Snapshot,
    graph: FinancialGraph,
    mode: str = "formula_preserve",
) -> tuple[bytes, dict]:
    """Export snapshot to Excel using zipfile/XML approach (preserves cached values).
    
    Optimized for batch processing: parses each sheet XML once, updates all cells, then writes once.
    
    Args:
        template_bytes: User-uploaded Excel file bytes (template)
        snapshot: Snapshot object with parameter cell values
        graph: FinancialGraph for cell metadata
        mode: Export mode
            - "formula_preserve": Update parameter cells only, preserve formulas & cached values
            - "values_only": (Future implementation) Replace all formulas with values
    
    Returns:
        (exported_bytes, stats): Excel bytes and export statistics
            stats = {
                "updated_cells": int,
                "skipped_formula": int,
                "skipped_merged": int,
                "missing_cells": int,
                "missing_sheets": int,
            }
    
    Notes:
        - Preserves formula cells' cached values (unlike openpyxl save)
        - Batch processing: parse sheet XML once → update all cells → write once
        - Only modifies parameter cells (no formula cells touched)
    """
    stats = {
        "updated_cells": 0,
        "skipped_formula": 0,
        "skipped_string": 0,  # New: track skipped string cells
        "skipped_merged": 0,
        "missing_cells": 0,
        "missing_sheets": 0,
    }
    
    temp_dir = tempfile.mkdtemp(prefix="xlsx_export_")
    
    try:
        # Extract xlsx (it's a zip file)
        template_buffer = BytesIO(template_bytes)
        with zipfile.ZipFile(template_buffer, 'r') as zf:
            zf.extractall(temp_dir)
        
        workbook_xml_path = os.path.join(temp_dir, "xl", "workbook.xml")
        
        # Group cells by sheet for batch processing
        cells_by_sheet: dict[str, dict[str, Any]] = {}
        for cell_id, new_value in snapshot.values.items():
            sheet_name, _, _ = parse_cell_id(cell_id)
            if sheet_name not in cells_by_sheet:
                cells_by_sheet[sheet_name] = {}
            cells_by_sheet[sheet_name][cell_id] = new_value
        
        # Process each sheet (parse once, update all cells, write once)
        for sheet_name, cells_dict in cells_by_sheet.items():
            # Find sheet XML path
            sheet_xml_path = get_sheet_xml_path(sheet_name, workbook_xml_path, temp_dir)
            
            if not sheet_xml_path:
                stats["missing_sheets"] += len(cells_dict)
                continue
            
            # Parse sheet XML once
            tree = ET.parse(sheet_xml_path)
            root = tree.getroot()
            
            # Build cell reference cache (r="A1" → cell_elem)
            cell_cache: dict[str, ET.Element] = {}
            for row_elem in root.findall(".//main:row", NS_MAP):
                for c_elem in row_elem.findall("main:c", NS_MAP):
                    cell_ref = c_elem.get("r")
                    if cell_ref:
                        cell_cache[cell_ref] = c_elem
            
            # Update all cells in this sheet
            for cell_id, new_value in cells_dict.items():
                _, row, col_letter = parse_cell_id(cell_id)
                cell_ref = f"{col_letter}{row}"
                
                # Check cell metadata from graph
                graph_cell = graph.cells.get(cell_id)
                
                # Skip merged child cells
                if graph_cell and graph_cell.is_merged and graph_cell.merge_parent_id:
                    stats["skipped_merged"] += 1
                    continue
                
                # Skip string cells (they use sharedStrings, cannot modify <v> directly)
                if graph_cell and graph_cell.data_type == "string":
                    stats["skipped_string"] += 1
                    continue
                
                # Find cell element in cache
                cell_elem = cell_cache.get(cell_ref)
                if not cell_elem:
                    stats["missing_cells"] += 1
                    continue
                
                # Check if this is a formula cell (has <f> child)
                has_formula = cell_elem.find("main:f", NS_MAP) is not None
                
                if has_formula:
                    # Formula cell: DO NOT modify (preserve cached value)
                    stats["skipped_formula"] += 1
                    continue
                
                # Check if cell XML has t="s" (string type in XML)
                # This is a safety check for cells not in graph
                if cell_elem.get("t") == "s":
                    stats["skipped_string"] += 1
                    continue
                
                # Parameter cell (numeric): update <v> node
                v_elem = cell_elem.find("main:v", NS_MAP)
                
                # Convert value to Excel format
                excel_value = convert_value_to_excel_serial(convert_iso_date_to_datetime(new_value))
                
                if v_elem is None:
                    # Create <v> node if missing
                    v_elem = ET.SubElement(cell_elem, f"{{{NS}}}v")
                
                v_elem.text = excel_value
                stats["updated_cells"] += 1
            
            # Write sheet XML once (after all cells updated)
            tree.write(sheet_xml_path, encoding="UTF-8", xml_declaration=False)
        
        # Repack xlsx
        output_buffer = BytesIO()
        with zipfile.ZipFile(output_buffer, 'w', zipfile.ZIP_DEFLATED) as zf:
            # Walk through all files in temp_dir and add to zip
            for root, dirs, files in os.walk(temp_dir):
                for file in files:
                    file_path = os.path.join(root, file)
                    arc_name = os.path.relpath(file_path, temp_dir)
                    zf.write(file_path, arc_name)
        
        output_buffer.seek(0)
        
    finally:
        # Clean up temporary directory
        if os.path.exists(temp_dir):
            shutil.rmtree(temp_dir)
    
    return output_buffer.getvalue(), stats