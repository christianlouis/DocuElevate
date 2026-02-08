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
- File ID and original filename
- File hash (SHA-256)
- File size and MIME type
- Creation timestamp
- Local path and disk status

#### Processing History
View the complete processing history with a timeline showing:
- Each processing step that was executed
- Status of each step (success, failure, in progress, pending)
- Error messages for failed steps
- Timestamps for each operation

**Retry Processing**: If a file's processing has failed, you can use the "Retry Processing" button to reprocess the entire file. This is useful when:
- External API services (like OpenAI) had temporary issues
- Network connectivity was lost during processing
- Configuration has been updated and you want to reprocess with new settings

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
- **Original File**: The file as it was uploaded
- **Processed File**: The file after metadata has been embedded (if processing completed)

Both previews support:
- In-browser PDF viewing
- Opening in a new tab for full-screen viewing
- Side-by-side comparison of original and processed versions

## Document Processing Features

Depending on the system configuration, DocuElevate can perform:

- **OCR** - Extract text from images and scanned PDFs
- **Metadata Extraction** - Automatically identify document types, dates, and other key information
- **PDF Conversion** - Convert various file formats to PDF
- **Document Distribution** - Store documents in Dropbox, Nextcloud, or Paperless NGX

## API Access

For programmatic access, DocuElevate provides a comprehensive REST API:

1. Navigate to `/docs` on your DocuElevate instance
2. The interactive Swagger documentation allows you to test API endpoints directly
3. Obtain an API token if authentication is enabled

## Troubleshooting

If you encounter issues while using DocuElevate, please refer to the [Troubleshooting Guide](Troubleshooting.md).
