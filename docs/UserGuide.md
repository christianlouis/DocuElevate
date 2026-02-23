# User Guide

This guide helps you get started with using DocuElevate for document management and processing.

## Getting Started

DocuElevate offers an intuitive web interface for uploading, managing, and processing your documents.

### Accessing the System

1. Navigate to your DocuElevate instance (typically at `http://your-server-address:8000`)
2. If authentication is enabled, you'll be prompted to log in using your credentials

### Authentication

DocuElevate supports two main authentication methods:

#### Basic Authentication
If basic authentication is configured:
1. You'll see a simple login form
2. Enter your username and password as configured in the system
3. Click "Log In" to access DocuElevate

#### OpenID Connect (OIDC)
If OpenID Connect authentication is configured:
1. You'll see a login button
2. Clicking this will redirect you to your identity provider (e.g., Authentik, Keycloak, Auth0)
3. Log in with your existing credentials on that platform
4. You'll be redirected back to DocuElevate after successful authentication

#### User Sessions
- Once authenticated, your session will remain active until you log out or it expires
- Click the "Logout" button in the top navigation bar to end your session
- For security, sessions automatically expire after a period of inactivity

### Main Interface

DocuElevate features a simple navigation system with the following main sections:
- **Home**: Dashboard and overview
- **Upload**: For adding new documents to the system
- **Files**: For viewing and managing processed documents
- **About**: Information about DocuElevate

## Uploading Documents

DocuElevate provides multiple convenient ways to upload documents to the system.

### Web Upload (Upload Page)

1. Navigate to the **Upload** page
2. **Drag and drop** files onto the upload area, or **click** the upload area to browse your files
3. Select files to upload (supported formats include PDF, Word documents, Excel spreadsheets, PowerPoint presentations, images, and more)
4. The system will automatically validate and upload your files
5. You'll see real-time progress for each file being uploaded
6. Your documents will be processed automatically according to the system configuration

#### Supported File Types
- **Documents**: PDF, Word (.doc, .docx), Excel (.xls, .xlsx), PowerPoint (.ppt, .pptx)
- **Images**: JPEG, PNG, GIF, BMP, TIFF, WebP, SVG
- **Text**: Plain text (.txt), CSV, RTF, HTML, XML, Markdown
- **Maximum file size**: 500MB per file

### Drag-and-Drop on Files Page

For even more convenience, you can upload files directly from the **Files** page:

1. Navigate to the **Files** page where you view your processed documents
2. **Drag files from your computer** and drop them **anywhere** on the page
3. A visual overlay will appear to confirm you're in drag mode
4. Release the files to begin uploading
5. An upload progress modal will appear in the bottom-right corner
6. The page will automatically refresh to show your newly uploaded files once complete

This feature allows you to quickly add new files without navigating away from your document management view.

### Email Attachments

If configured, DocuElevate can automatically fetch documents from email attachments:

1. Send an email with attachments to the configured email account
2. DocuElevate will poll the mailbox at the configured interval
3. Attachments will be automatically downloaded and processed
4. No further action is required

## Managing Documents

The **Files** page provides access to all processed documents:

1. Navigate to the **Files** page
2. Use the search box to find specific documents
3. Click on any file to view its details
4. Sort the list by any column by clicking on the column header

### File Detail View

When you click on a file, you'll see a comprehensive detail view with the following sections:

#### File Information
This section displays metadata about the file:
#### File Information
This section displays metadata about the file:
- File ID and original filename
- File hash (SHA-256)
- File size and MIME type
- Creation timestamp
- Original file path and status (shows if the immutable original is available)
- Processed file path and status (shows if the final processed file is available)

#### Extracted Metadata (GPT)
If metadata has been extracted by GPT, this section displays structured information including:
- **Document Type**: Classification (Invoice, Receipt, Contract, etc.)
- **Suggested Filename**: AI-recommended filename based on content
- **Document Date**: Extracted date from document
- **Sender (Absender)**: Sender or issuing party information
- **Recipient (Empfänger)**: Recipient information
- **Amount (Betrag)**: Financial amounts (for invoices, receipts)
- **Account Number**: Bank account information
- **Tags**: Document categories and labels

**Show JSON**: Click this button to toggle the full metadata in JSON format. This is useful for:
- Viewing all extracted fields at once
- Debugging metadata extraction issues
- Copying metadata for external use
- Understanding the complete data structure

#### Document Previews
View your documents side-by-side in embedded PDF viewers:
- **Original Document**: The immutable original file as first ingested, before any processing
- **Processed Document**: The final file with embedded metadata

**Features**:
- In-browser PDF rendering for immediate viewing
- Side-by-side comparison of original vs processed versions
- Full 600px height previews for detailed review
- **View Extracted Text** buttons below each preview to see the full text content

**Text Extraction Modals**: Click "View Extracted Text" to open a fullscreen modal showing:
- Complete extracted text from OCR or PDF text layer
- Dark-themed, scrollable display for easy reading
- Copy-friendly pre-formatted text
- Close by clicking the close button or clicking outside the modal

**Note**: The original file is stored in an immutable archive (`workdir/original/`) and is never modified. The processed file is stored in `workdir/processed/` with the suggested filename and embedded metadata.

#### Processing History
View the complete processing history with a timeline showing:
- Each processing step that was executed
- Status of each step (success, failure, in progress, pending)
- Error messages for failed steps
- Timestamps for each operation

**Retry Processing**: If a file's processing has failed, you can use the "Retry Processing" button to reprocess the entire file. This is useful when:
- External API services (like the configured AI provider) had temporary issues
- Network connectivity was lost during processing
- Configuration has been updated and you want to reprocess with new settings

**Force Cloud OCR**: For files with low-quality embedded text, you can use the "Reprocess with Cloud OCR" option to force high-quality Azure Document Intelligence OCR processing, even if the PDF already contains embedded text. This is useful when:
- The embedded text quality is poor or contains errors
- OCR accuracy needs to be improved
- The embedded text is corrupted or garbled
- You need the highest quality text extraction possible

#### Process Flow Visualization
The process flow visualization shows a visual representation of the document processing pipeline:
- **Green indicators**: Successful stages
- **Red indicators**: Failed stages with error messages
- **Gray indicators**: Stages that were not executed (e.g., because a previous stage failed)

This helps you understand:
- Which processing path your document took (local text extraction vs. OCR)
- Where exactly the processing failed
- Which stages were skipped and why

#### File Previews
If your file is still available on disk, you can preview it directly in the browser:
- **Original File**: The immutable original file as it was first ingested
- **Processed File**: The file after metadata has been embedded (if processing completed)

Both previews support:
- In-browser PDF viewing with embedded viewer
- Side-by-side comparison of original and processed versions
- Full text extraction viewing via modal overlays

**View Extracted Text**: Each preview includes a button to view the complete extracted text in a fullscreen modal. When you click this button:
- The system extracts text from the PDF file on-demand using pypdf
- A loading indicator shows while extraction is in progress
- The extracted text is displayed in a scrollable, copy-friendly format
- The text is cached so subsequent views load instantly

This is useful for:
- Verifying OCR accuracy
- Searching within document content
- Copying text for external use
- Reading documents without downloading them

**Note**: The original file is stored in an immutable archive (`workdir/original/`) and is never modified. This ensures you always have access to the file exactly as it was uploaded, which is valuable for:
- Auditing and compliance
- Debugging processing issues
- Reprocessing with improved algorithms

## Document Processing Features

Depending on the system configuration, DocuElevate can perform:

- **OCR** - Extract text from images and scanned PDFs
- **Metadata Extraction** - Automatically identify document types, dates, and other key information
- **PDF Conversion** - Convert various file formats to PDF
- **Document Distribution** - Store documents in Dropbox, Nextcloud, or Paperless NGX

### Paperless-ngx Integration

If Paperless-ngx is configured, DocuElevate can automatically upload processed documents and set custom fields with extracted metadata:

1. **Automatic Upload**: After processing, documents are automatically uploaded to Paperless-ngx
2. **Custom Fields Support**: DocuElevate can automatically populate custom fields in Paperless with extracted metadata
3. **Flexible Field Mapping**: Map any extracted metadata field to any custom field in Paperless

#### Setting Up Custom Fields

**Basic Setup (Single Field)**:
```bash
# In your .env file
PAPERLESS_CUSTOM_FIELD_ABSENDER=Absender
```

**Advanced Setup (Multiple Fields)**:
```bash
# Map multiple metadata fields to Paperless custom fields
PAPERLESS_CUSTOM_FIELDS_MAPPING='{"absender": "Sender", "empfaenger": "Recipient", "language": "Language", "correspondent": "Correspondent"}'
```

**Available Metadata Fields**:
- `absender` - Sender/author
- `empfaenger` - Recipient
- `correspondent` - Issuing company (short name)
- `language` - Document language (e.g., "de", "en")
- `document_type` - Classification (Invoice, Contract, etc.)
- `reference_number` - Invoice/order/reference number
- `kommunikationsart` - Communication type
- `kommunikationskategorie` - Communication category
- And more...

**Requirements**:
- Create the custom fields in Paperless-ngx first (Settings → Custom Fields)
- The field names in your configuration must exactly match the names in Paperless
- Ensure `PAPERLESS_HOST` and `PAPERLESS_NGX_API_TOKEN` are configured

**How It Works**:
1. DocuElevate extracts metadata from your documents using AI
2. The document is uploaded to Paperless-ngx
3. After successful upload, custom fields are automatically populated
4. You can view the populated fields in your Paperless-ngx document details

## API Access

For programmatic access, DocuElevate provides a comprehensive REST API:

1. Navigate to `/docs` on your DocuElevate instance
2. The interactive Swagger documentation allows you to test API endpoints directly
3. Obtain an API token if authentication is enabled

## Troubleshooting

If you encounter issues while using DocuElevate, please refer to the [Troubleshooting Guide](Troubleshooting.md).
