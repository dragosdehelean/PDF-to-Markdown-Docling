# Diagrams

## Flowchart
```mermaid
flowchart TD
    CLI[CLI parse & env load\ncli.py#L61-L217]
    Setup[Pipeline options & labels\nconversion_utils.py#L133-L178]
    Backend[Backend selection\nconversion_utils.py#L180-L229]
    Convert[Docling conversion\nconversion_utils.py#L290-L378]
    AutoOCR[Auto OCR retry?
chars/page + spacing ratio\nconversion_utils.py#L334-L378]
    SpacingDetect[Detect spacing pages\nconversion_utils.py#L400-L419]
    SpacingDocling[Docling word/char spacing fix\nspacing_fix.py#L221-L305]
    SpacingPyMuPDF[PyMuPDF glyph spacing fix\npymupdf_spacing_fix.py#L365-L509]
    SpacingOCR[OCR table merge\ntable_fixes.py#L785-L855]
    TableFix[Table cleanup\ntable_fixes.py#L415-L680]
    PictureFix[Picture cleanup + KPI OCR\ndate_cleanup.py#L73-L189\npicture_kpi_extract.py#L196-L279]
    Whitespace[Whitespace normalize\nwhitespace_fix.py#L7-L46]
    Export[Markdown export + noise clean\nconversion_utils.py#L231-L288\nexport_utils.py#L31-L355]
    Audit[Optional audit\ncli.py#L244-L271\naudit_utils.py#L272-L382]
    End

    CLI --> Setup --> Backend --> Convert --> AutoOCR --> SpacingDetect
    SpacingDetect -->|spacing-fix docling| SpacingDocling
    SpacingDetect -->|spacing-fix pymupdf| SpacingPyMuPDF
    SpacingDetect -->|spacing-fix ocr| SpacingOCR
    SpacingDocling --> TableFix
    SpacingPyMuPDF --> TableFix
    SpacingOCR --> TableFix
    TableFix --> PictureFix --> Whitespace --> Export --> Audit --> End
```

## Sequence
```mermaid
sequenceDiagram
    participant User
    participant CLI as cli.py
    participant Conv as conversion_utils.py
    participant DL as Docling backend
    participant Space as spacing_fix / pymupdf_spacing_fix / table_fixes
    participant Post as export_utils / table_fixes / whitespace_fix / date_cleanup / picture_kpi_extract
    participant Audit as audit_utils

    User->>CLI: argv (+ env)
    CLI->>CLI: parse args, resolve paths (cli.py#L61-L217)
    CLI->>Conv: convert_pdf_to_markdown(...)
    Conv->>Conv: build options/labels (conversion_utils.py#L133-L178)
    Conv->>DL: convert (maybe twice for auto OCR) (conversion_utils.py#L290-L378)
    DL-->>Conv: ConversionResult (DoclingDocument)
    Conv->>Conv: detect spacing pages (conversion_utils.py#L400-L419)
    Conv->>Space: spacing repair per mode (conversion_utils.py#L378-L457)
    Space-->>Conv: repaired DoclingDocument
    Conv->>Space: merge suspect cells (table_fixes.py#L681-L855)
    Conv->>Post: table cleanup, picture cleanup, whitespace (conversion_utils.py#L485-L506)
    Post-->>Conv: normalized DoclingDocument
    Conv->>CLI: write Markdown + noise cleanup (conversion_utils.py#L231-L288)
    CLI->>Audit: optional audit_doc_vs_markdown (cli.py#L244-L271)
    Audit-->>User: metrics/prints
    CLI-->>User: output paths
```

## Components
```mermaid
graph LR
    CLI[CLI (cli.py)] --> Conv[conversion_utils.py]
    Conv --> Docling[Docling backends\n(pypdfium2 / docling-parse-v4)]
    Conv --> Spacing[Spacing fixes\nspacing_fix.py / pymupdf_spacing_fix.py]
    Conv --> Tables[Table repairs\ntable_fixes.py]
    Conv --> Pictures[Picture/KPI cleanup\ndate_cleanup.py / picture_kpi_extract.py]
    Conv --> TextNorm[Whitespace & encoding\nwhitespace_fix.py / text_normalize.py]
    Conv --> Export[Markdown export\nexport_utils.py]
    Conv --> AuditUtil[Audit utilities\naudit_utils.py]
    CLI --> Scripts[Scripts\naudit_pdf_vs_md.py / quality_report.py]
    Export --> Output[Markdown + images]
    AuditUtil --> AuditOut[Audit metrics]
    Scripts --> AuditUtil
    Scripts --> Conv
```

Nodes correspond to the stages named in [docs/PIPELINE_OVERVIEW.md](PIPELINE_OVERVIEW.md).
