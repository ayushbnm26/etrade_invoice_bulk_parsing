# Etrade Bulk Invoice Workbook Generator

Bulk Streamlit utility for processing supported Etrade invoice PDFs into one team-facing Excel workbook.

The app is self-contained and deployable to Streamlit Community Cloud. It does not depend on the older single-invoice app.

## Purpose

Finance users can upload one or many supported Etrade invoice PDFs in a single run and download one public/team workbook.

The team workbook contains:

- A concise `Processing Summary` sheet.
- One sheet per uploaded invoice/PDF.
- A clean `Invoice Items` table for every successfully parsed invoice.
- A safe failure sheet for every file that cannot be parsed or validated.

The app also creates a detailed/internal workbook, runtime log, attachment manifest, and original upload attachment for admin email only.

## Supported Input

Upload only Etrade invoice PDFs that follow the supported invoice layout pattern used during development.

The parser expects text/table extraction to work through `pdfplumber`. It works best when uploaded PDFs have the same or very similar:

- Table layout and column order.
- Field placement.
- Tax layout.
- Address placement.
- PDF text quality.
- Page structure.

## Unsupported Input

The app is not intended for:

- Non-PDF files.
- Empty files.
- Files without a valid PDF signature.
- Scanned-image PDFs that require OCR.
- Etrade invoices with major layout changes.
- Non-Etrade invoices.
- Documents whose table structure cannot be extracted as PDF text/tables.

OCR is not included.

## Bulk Upload Behavior

- Each uploaded file is validated and processed independently.
- One failed file does not stop the rest of the batch.
- Duplicate filenames are handled.
- Duplicate invoice or system reference sheet names are made unique.
- Excel sheet names are sanitized and kept within Excel's 31-character limit.
- Temporary directories are used for each run.
- The app does not assume durable Streamlit filesystem storage.

Default safeguards:

- `MAX_FILES_PER_RUN = 30`
- `MAX_TOTAL_UPLOAD_MB = 200`
- `.streamlit/config.toml` sets `server.maxUploadSize = 200`
- The Streamlit uploader also uses `max_upload_size` from secrets/defaults.

Streamlit's current docs state that uploaded files are limited to 200 MB by default and can be configured with `server.maxUploadSize`; the `st.file_uploader` API also supports a per-widget `max_upload_size` parameter. See:

- https://docs.streamlit.io/develop/api-reference/widgets/st.file_uploader
- https://docs.streamlit.io/knowledge-base/deploy/increase-file-uploader-limit-streamlit-cloud

## Team Workbook Behavior

The Streamlit UI exposes only the public/team workbook.

For each successful invoice sheet:

- Row 1 is a merged title: `Invoice Items`
- Row 3 is the table header.
- Row 4 onward contains item rows.
- Freeze panes are set at `A4`.
- Gridlines are hidden.
- Styling is muted and minimal.

Successful invoice sheets expose exactly these columns:

1. Invoice Number
2. System Reference Number
3. ASIN
4. Quantity
5. Price / Unit
6. Net Amount
7. CGST Rate
8. CGST Amount
9. SGST Rate
10. SGST Amount
11. IGST Rate
12. IGST Amount
13. Other Tax Type
14. Other Tax Rate
15. Other Tax Amount
16. Total Amount

No raw addresses, parser internals, validation internals, tracebacks, local paths, SMTP details, or debug fields are exposed in successful team-facing invoice sheets.

## Failure Handling

Every failed invoice/file still gets a sheet.

Failure sheets include:

- `Invoice Processing Failed`
- Source filename
- Status `FAILED`
- Safe error type
- Safe error message
- Likely reason when determinable
- Human action note

Failure sheets do not include tracebacks, secrets, server internals, SMTP credentials, or local filesystem paths.

## Admin Email Behavior

Admin notification is best-effort and never blocks workbook generation or team download.

When SMTP secrets are configured, the admin email attaches available artifacts:

- Public/team workbook.
- Detailed/internal workbook.
- Runtime log.
- Original upload attachment. Multiple uploads are zipped as `original_uploads.zip`.
- Attachment manifest.

If SMTP secrets are missing or incomplete, processing still succeeds and the UI shows an email-skipped warning.

If SMTP delivery fails, processing still succeeds and the UI shows an email-failed warning. SMTP errors are sanitized.

The internal workbook is not exposed in the team UI.

## Internal Workbook

The internal/admin workbook contains detailed diagnostics, including:

- `Run_Summary`
- `Input_Files`
- `Invoice_Header`
- `Invoice_Line_Items`
- `Invoice_Summary`
- `Validation`
- `Exceptions`
- `Attachment_Status`

The internal workbook may include raw parser fields, validation details, exception traces, source filenames, invoice numbers, system reference numbers, row counts, and totals.

## Human Verification Warning

PDF text/table extraction is not guaranteed to be 100% accurate. The generated workbook must be verified by a human before use for finance, accounting, GST, reconciliation, reporting, payment, audit, or any official business process.

## Local Run

Install dependencies:

```bash
python -m pip install -r requirements.txt
```

Create local secrets:

```bash
copy .streamlit\secrets.example.toml .streamlit\secrets.toml
```

Edit `.streamlit/secrets.toml` and replace placeholders. Never commit `.streamlit/secrets.toml`.

Run the app:

```bash
python -m streamlit run app.py
```

Optional CLI run:

```bash
python main.py --input-dir input_pdfs --output-dir output
```

## Streamlit Secrets

Use this shape in local `.streamlit/secrets.toml` or Streamlit Community Cloud secrets:

```toml
APP_PASSWORD = "replace-with-team-app-password"

[BULK]
MAX_FILES_PER_RUN = 30
MAX_TOTAL_UPLOAD_MB = 200
MAX_UPLOAD_SIZE_MB = 200

[SMTP]
HOST = "smtp.example.com"
PORT = 587
USERNAME = "sender@example.com"
APP_PASSWORD = "replace-with-smtp-app-password"
FROM_EMAIL = "sender@example.com"
ADMIN_EMAIL = "admin@example.com"
```

Use an SMTP app password when required by the email provider. Do not commit real credentials.

## Deploy on Streamlit Community Cloud

1. Push this repository to GitHub.
2. Open https://streamlit.io/cloud.
3. Create a new app from this repository.
4. Set the main file path to `app.py`.
5. Add secrets using the shape above.
6. Deploy.
7. Test with a known supported Etrade invoice PDF before sharing with the team.

The included `.streamlit/config.toml` sets:

```toml
[server]
maxUploadSize = 200

[client]
showErrorDetails = "none"
```

## Tests

Run:

```bash
python -m unittest discover -s tests
```

Tests use fake parser outputs and mocked email behavior. They do not require real SMTP credentials, network access, external PDFs, or machine-specific paths.

## Known Limitations

- The parser is layout-dependent.
- Major invoice design changes can reduce extraction accuracy.
- Scanned-image PDFs and OCR-dependent documents are unsupported.
- The app is not an accounting-certified system of record.
- Streamlit Community Cloud filesystem storage is not durable.
- Very large batches or attachments may exceed hosting or SMTP limits.
- Human verification is mandatory before official use.
