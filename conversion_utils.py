from __future__ import annotations

from pathlib import Path
from typing import Optional, Tuple, Type

from docling.backend.docling_parse_v4_backend import DoclingParseV4DocumentBackend
from docling.backend.pypdfium2_backend import PyPdfiumDocumentBackend
from docling.datamodel.accelerator_options import AcceleratorOptions
from docling.datamodel.base_models import InputFormat
from docling.datamodel.document import ConversionResult
from docling.datamodel.layout_model_specs import DOCLING_LAYOUT_EGRET_LARGE
from docling.datamodel.pipeline_options import (
    LayoutOptions,
    OcrAutoOptions,
    RapidOcrOptions,
    EasyOcrOptions,
    TesseractCliOcrOptions,
    TableFormerMode,
    TableStructureOptions,
    ThreadedPdfPipelineOptions,
)
from docling.document_converter import DocumentConverter, PdfFormatOption
from docling_core.types.doc.base import ImageRefMode
from docling_core.types.doc.document import ContentLayer, DEFAULT_EXPORT_LABELS
from docling_core.types.doc.labels import DocItemLabel
from docling_core.types.doc import TableItem

from audit_utils import (
    audit_doc_vs_markdown,
    is_spaced_text,
    needs_spacing_fix,
    needs_table_spacing_fix,
)
from pymupdf_spacing_fix import fix_spaced_items_with_pymupdf_glyphs
from spacing_fix import fix_spaced_items_with_word_cells
from table_fixes import merge_spaced_table_cells
from quality import QualityReport, format_report, score_markdown


BACKEND_MAP = {
    "docling-parse-v4": DoclingParseV4DocumentBackend,
    "pypdfium2": PyPdfiumDocumentBackend,
}

PAGE_BREAK_PLACEHOLDER = "<!-- page break -->"
SPACED_CELL_RATIO_THRESHOLD = 0.04


def parse_ocr_langs(lang: str) -> list[str]:
    raw = lang.replace("+", ",")
    return [piece.strip() for piece in raw.split(",") if piece.strip()]


def build_ocr_options(
    engine: str, lang: str, force_full_page_ocr: bool
) -> object:
    langs = parse_ocr_langs(lang)
    if engine == "tesseract":
        return TesseractCliOcrOptions(lang=langs, force_full_page_ocr=force_full_page_ocr)
    if engine == "rapidocr":
        return RapidOcrOptions(lang=langs, force_full_page_ocr=force_full_page_ocr)
    if engine == "easyocr":
        return EasyOcrOptions(lang=langs, force_full_page_ocr=force_full_page_ocr)
    return OcrAutoOptions(lang=langs, force_full_page_ocr=force_full_page_ocr)


def build_pdf_pipeline_options(
    image_mode: ImageRefMode,
    do_ocr: bool,
    device: str,
    ocr_engine: str,
    ocr_lang: str,
    force_full_page_ocr: bool,
    do_cell_matching: bool,
) -> ThreadedPdfPipelineOptions:
    ocr_options = (
        build_ocr_options(
            engine=ocr_engine,
            lang=ocr_lang,
            force_full_page_ocr=force_full_page_ocr,
        )
        if do_ocr
        else OcrAutoOptions(lang=parse_ocr_langs(ocr_lang))
    )
    return ThreadedPdfPipelineOptions(
        do_table_structure=True,
        table_structure_options=TableStructureOptions(
            mode=TableFormerMode.ACCURATE,
            do_cell_matching=do_cell_matching,
        ),
        do_ocr=do_ocr,
        accelerator_options=AcceleratorOptions(device=device),
        layout_options=LayoutOptions(
            model_spec=DOCLING_LAYOUT_EGRET_LARGE,
        ),
        ocr_options=ocr_options,
        images_scale=2.0,
        generate_picture_images=image_mode is not ImageRefMode.PLACEHOLDER,
    )


def build_export_labels() -> set[DocItemLabel]:
    labels = set(DEFAULT_EXPORT_LABELS)
    labels.discard(DocItemLabel.DOCUMENT_INDEX)
    labels.discard(DocItemLabel.PAGE_HEADER)
    labels.discard(DocItemLabel.PAGE_FOOTER)
    labels.add(DocItemLabel.CAPTION)
    labels.add(DocItemLabel.FOOTNOTE)
    return labels


def _probe_backend(
    input_path: Path,
    backend: Type,
    pipeline_options: ThreadedPdfPipelineOptions,
    export_labels: set[DocItemLabel],
) -> QualityReport:
    converter = DocumentConverter(
        format_options={
            InputFormat.PDF: PdfFormatOption(
                pipeline_options=pipeline_options,
                backend=backend,
            ),
        }
    )
    result = converter.convert(input_path, page_range=(1, 1))
    markdown = result.document.export_to_markdown(
        labels=export_labels,
        image_mode=ImageRefMode.PLACEHOLDER,
        include_annotations=False,
        escape_underscores=True,
        included_content_layers={ContentLayer.BODY},
    )
    return score_markdown(markdown)


def select_backend_auto(
    input_path: Path,
    pipeline_options: ThreadedPdfPipelineOptions,
    export_labels: set[DocItemLabel],
    *,
    quiet: bool,
) -> tuple[str, Type, dict[str, QualityReport]]:
    reports: dict[str, QualityReport] = {}
    for name, backend in BACKEND_MAP.items():
        reports[name] = _probe_backend(
            input_path=input_path,
            backend=backend,
            pipeline_options=pipeline_options,
            export_labels=export_labels,
        )

    best = max(reports.items(), key=lambda item: item[1].score)[0]
    if not quiet:
        summary = ", ".join(
            f"{name}({format_report(report)})" for name, report in reports.items()
        )
        print(f"Auto backend selection: {best}. {summary}")
    return best, BACKEND_MAP[best], reports


def convert_pdf_to_markdown(
    *,
    input_path: Path,
    output_path: Path,
    image_mode: ImageRefMode,
    images_dir: Optional[Path],
    max_pages: Optional[int],
    page_range: Optional[Tuple[int, int]],
    ocr_mode: str,
    ocr_engine: str,
    ocr_lang: str,
    force_full_page_ocr: bool,
    spacing_fix: str,
    device: str,
    pdf_backend: str,
    quiet: bool,
) -> tuple[ConversionResult, str]:
    result, backend_name, export_labels = convert_pdf_to_doc(
        input_path=input_path,
        image_mode=image_mode,
        max_pages=max_pages,
        page_range=page_range,
        ocr_mode=ocr_mode,
        ocr_engine=ocr_engine,
        ocr_lang=ocr_lang,
        force_full_page_ocr=force_full_page_ocr,
        spacing_fix=spacing_fix,
        device=device,
        pdf_backend=pdf_backend,
        quiet=quiet,
    )

    result.document.save_as_markdown(
        output_path,
        artifacts_dir=images_dir,
        image_mode=image_mode,
        labels=export_labels,
        page_break_placeholder="\n\n<!-- page break -->\n\n",
        include_annotations=False,
        escaping_underscores=True,
        included_content_layers={ContentLayer.BODY},
    )

    return result, backend_name


def convert_pdf_to_doc(
    *,
    input_path: Path,
    image_mode: ImageRefMode,
    max_pages: Optional[int],
    page_range: Optional[Tuple[int, int]],
    ocr_mode: str,
    ocr_engine: str,
    ocr_lang: str,
    force_full_page_ocr: bool,
    spacing_fix: str,
    device: str,
    pdf_backend: str,
    quiet: bool,
) -> tuple[ConversionResult, str, set[DocItemLabel]]:
    export_labels = build_export_labels()
    ocr_mode = ocr_mode.lower()

    def run_conversion(
        do_ocr: bool,
        force_full: bool,
        do_cell_matching: bool,
        backend_override: str | None = None,
    ) -> tuple[ConversionResult, str]:
        pipeline_options = build_pdf_pipeline_options(
            image_mode=image_mode,
            do_ocr=do_ocr,
            device=device,
            ocr_engine=ocr_engine,
            ocr_lang=ocr_lang,
            force_full_page_ocr=force_full,
            do_cell_matching=do_cell_matching,
        )

        if backend_override is not None:
            backend_name = backend_override
            backend_cls = BACKEND_MAP[backend_override]
        elif pdf_backend == "auto":
            backend_name, backend_cls, _reports = select_backend_auto(
                input_path=input_path,
                pipeline_options=pipeline_options,
                export_labels=export_labels,
                quiet=quiet,
            )
        else:
            backend_name = pdf_backend
            backend_cls = BACKEND_MAP[pdf_backend]

        converter = DocumentConverter(
            format_options={
                InputFormat.PDF: PdfFormatOption(
                    pipeline_options=pipeline_options,
                    backend=backend_cls,
                ),
            }
        )

        convert_kwargs: dict[str, object] = {}
        if max_pages is not None:
            convert_kwargs["max_num_pages"] = max_pages
        if page_range is not None:
            convert_kwargs["page_range"] = page_range

        result = converter.convert(input_path, **convert_kwargs)
        return result, backend_name

    if ocr_mode == "on":
        result, backend_name = run_conversion(True, force_full_page_ocr, True)
    elif ocr_mode == "off":
        result, backend_name = run_conversion(False, False, False)
    else:
        # auto: run without OCR, retry with OCR only if text is sparse
        result, backend_name = run_conversion(False, False, False)
    text = result.document.export_to_text()
    page_count = max(len(result.document.pages), 1)
    chars_per_page = len(text) / page_count
    metrics = audit_doc_vs_markdown(result.document, "")
    spaced_ratio = (
        metrics.spaced_table_cells / metrics.total_table_cells
        if metrics.total_table_cells
        else 0.0
    )

    if ocr_mode == "auto":
        if chars_per_page < 200 or spaced_ratio >= SPACED_CELL_RATIO_THRESHOLD:
            ocr_result, ocr_backend = run_conversion(
                True, True, True, backend_override=backend_name
            )
            ocr_text = ocr_result.document.export_to_text()
            ocr_metrics = audit_doc_vs_markdown(ocr_result.document, "")
            ocr_spaced_ratio = (
                ocr_metrics.spaced_table_cells / ocr_metrics.total_table_cells
                if ocr_metrics.total_table_cells
                else 0.0
            )

            if ocr_spaced_ratio < spaced_ratio * 0.5:
                result = ocr_result
                backend_name = ocr_backend
                metrics = ocr_metrics
                spaced_ratio = ocr_spaced_ratio
                text = ocr_text
                chars_per_page = len(text) / page_count
            elif len(ocr_text) > len(text) * 1.2:
                result = ocr_result
                backend_name = ocr_backend
                metrics = ocr_metrics
                spaced_ratio = ocr_spaced_ratio

    def detect_spacing_pages(doc, predicate, table_predicate=None) -> set[int] | None:
        pages: set[int] = set()
        has_unknown_page = False
        for item, _level in doc.iterate_items():
            if isinstance(item, TableItem):
                page_no = item.prov[0].page_no if item.prov else None
                if page_no is None:
                    has_unknown_page = True
                for cell in item.data.table_cells:
                    cell_predicate = table_predicate or predicate
                    if cell_predicate(cell.text):
                        if page_no is not None:
                            pages.add(page_no)
                        break
            else:
                text = getattr(item, "text", None)
                if not text or not predicate(text):
                    continue
                page_no = item.prov[0].page_no if getattr(item, "prov", None) else None
                if page_no is None:
                    has_unknown_page = True
                else:
                    pages.add(page_no)
        if has_unknown_page:
            return None
        return pages

    spacing_fix = spacing_fix.lower()
    if spacing_fix == "heuristic":
        spacing_fix = "pymupdf"
    if spacing_fix == "ocr" and metrics.total_table_cells:
        if spaced_ratio >= SPACED_CELL_RATIO_THRESHOLD:
            ocr_table_doc, _backend = run_conversion(
                True, True, True, backend_override=backend_name
            )
            replaced, total_spaced = merge_spaced_table_cells(
                result.document, ocr_table_doc.document
            )
            if not quiet:
                print(
                    f"Hybrid table fix: replaced {replaced}/{total_spaced} spaced cells."
                )

    if spacing_fix in {"pymupdf", "docling", "ocr"}:
        pages_to_fix = detect_spacing_pages(
            result.document, needs_spacing_fix, table_predicate=needs_table_spacing_fix
        )
        if spacing_fix == "docling":
            report = fix_spaced_items_with_word_cells(
                result.document, input_path, pages_to_fix=pages_to_fix
            )
            if not quiet and (report.table_cells or report.text_items):
                page_info = (
                    "all-pages"
                    if pages_to_fix is None
                    else f"{report.pages_processed} pages"
                )
                print(
                    "Docling spacing fix (word/char cells): "
                    f"table_cells={report.table_cells}, "
                    f"text_items={report.text_items}, {page_info}"
                )
        else:
            report = fix_spaced_items_with_pymupdf_glyphs(
                result.document, input_path, pages_to_fix=pages_to_fix
            )
            if not quiet and (report.table_cells or report.text_items):
                page_info = (
                    "all-pages"
                    if pages_to_fix is None
                    else f"{report.pages_processed} pages"
                )
                print(
                    "PyMuPDF spacing fix (glyph reconstruction): "
                    f"table_cells={report.table_cells}, "
                    f"text_items={report.text_items}, {page_info}"
                )

    return result, backend_name, export_labels
