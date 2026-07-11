import sys

# Remove the appended tests from test_embed_pdf_metadata.py and test_process_document.py
with open("tests/test_embed_pdf_metadata.py", "r") as f:
    content = f.read()

content = content.split('    @patch("app.tasks.embed_metadata_into_pdf.finalize_document_storage")')[0]

new_tests_embed = """
    @patch("app.tasks.embed_metadata_into_pdf.finalize_document_storage")
    @patch("app.tasks.embed_metadata_into_pdf.persist_metadata")
    @patch("app.tasks.embed_metadata_into_pdf.shutil.move")
    @patch("app.tasks.embed_metadata_into_pdf.os.makedirs")
    @patch("app.tasks.embed_metadata_into_pdf.get_unique_filepath_with_counter")
    @patch("app.tasks.embed_metadata_into_pdf.sanitize_filename")
    @patch("app.tasks.embed_metadata_into_pdf.SessionLocal")
    @patch("app.tasks.embed_metadata_into_pdf.log_task_progress")
    @patch("builtins.open", new_callable=mock_open, read_data=b"%PDF-1.4 content")
    @patch("app.tasks.embed_metadata_into_pdf.pypdf.PdfReader")
    @patch("app.tasks.embed_metadata_into_pdf.pypdf.PdfWriter")
    @patch("app.utils.webhook.dispatch_webhook_event")
    @patch("app.tasks.embed_metadata_into_pdf.os.path.exists", return_value=True)
    def test_webhook_dispatch_success(
        self,
        mock_exists,
        mock_webhook,
        mock_pdf_writer_class,
        mock_pdf_reader_class,
        mock_file,
        mock_log_progress,
        mock_session_local,
        mock_sanitize,
        mock_get_unique,
        mock_makedirs,
        mock_move,
        mock_persist,
        mock_finalize,
    ):
        mock_pdf_reader = MagicMock()
        mock_pdf_reader.pages = [MagicMock()]
        mock_pdf_reader_class.return_value = mock_pdf_reader
        mock_pdf_writer = MagicMock()
        mock_pdf_writer_class.return_value = mock_pdf_writer
        
        mock_sanitize.return_value = "Test_Document.pdf"
        mock_get_unique.return_value = "/workdir/processed/Test_Document.pdf"
        mock_persist.return_value = "/workdir/processed/Test_Document.json"
        
        mock_db = MagicMock()
        mock_file_record = MagicMock()
        mock_file_record.id = 42
        mock_file_record.original_filename = "upload.pdf"
        mock_file_record.user_id = 99
        mock_db.query.return_value.filter.return_value.first.return_value = mock_file_record
        mock_session_local.return_value.__enter__.return_value = mock_db
        
        metadata = {"filename": "Test Document", "document_type": "Invoice"}
        
        embed_metadata_into_pdf.__wrapped__("/tmp/upload.pdf", "Sample text", metadata, file_id=42)
        
        mock_webhook.assert_called_once()
        args = mock_webhook.call_args[0]
        assert args[0] == "document.metadata_updated"
        assert args[1]["file_id"] == 42
        assert args[1]["updated_fields"] == ["document_type", "filename"]
        
    @patch("app.tasks.embed_metadata_into_pdf.finalize_document_storage")
    @patch("app.tasks.embed_metadata_into_pdf.persist_metadata")
    @patch("app.tasks.embed_metadata_into_pdf.shutil.move")
    @patch("app.tasks.embed_metadata_into_pdf.os.makedirs")
    @patch("app.tasks.embed_metadata_into_pdf.get_unique_filepath_with_counter")
    @patch("app.tasks.embed_metadata_into_pdf.sanitize_filename")
    @patch("app.tasks.embed_metadata_into_pdf.SessionLocal")
    @patch("app.tasks.embed_metadata_into_pdf.log_task_progress")
    @patch("builtins.open", new_callable=mock_open, read_data=b"%PDF-1.4 content")
    @patch("app.tasks.embed_metadata_into_pdf.pypdf.PdfReader")
    @patch("app.tasks.embed_metadata_into_pdf.pypdf.PdfWriter")
    @patch("app.utils.webhook.dispatch_webhook_event")
    @patch("app.tasks.embed_metadata_into_pdf.os.path.exists", return_value=True)
    def test_webhook_dispatch_error(
        self,
        mock_exists,
        mock_webhook,
        mock_pdf_writer_class,
        mock_pdf_reader_class,
        mock_file,
        mock_log_progress,
        mock_session_local,
        mock_sanitize,
        mock_get_unique,
        mock_makedirs,
        mock_move,
        mock_persist,
        mock_finalize,
        caplog
    ):
        mock_pdf_reader = MagicMock()
        mock_pdf_reader.pages = [MagicMock()]
        mock_pdf_reader_class.return_value = mock_pdf_reader
        mock_pdf_writer = MagicMock()
        mock_pdf_writer_class.return_value = mock_pdf_writer
        
        mock_sanitize.return_value = "Test_Document.pdf"
        mock_get_unique.return_value = "/workdir/processed/Test_Document.pdf"
        mock_persist.return_value = "/workdir/processed/Test_Document.json"
        
        mock_db = MagicMock()
        mock_file_record = MagicMock()
        mock_file_record.id = 42
        mock_file_record.original_filename = "upload.pdf"
        mock_file_record.user_id = 99
        mock_db.query.return_value.filter.return_value.first.return_value = mock_file_record
        mock_session_local.return_value.__enter__.return_value = mock_db
        
        metadata = {"filename": "Test Document", "document_type": "Invoice"}
        
        mock_webhook.side_effect = Exception("Webhook boom")
        
        embed_metadata_into_pdf.__wrapped__("/tmp/upload.pdf", "Sample text", metadata, file_id=42)
        
        assert "Failed to dispatch document.metadata_updated webhook: Webhook boom" in caplog.text
"""
with open("tests/test_embed_pdf_metadata.py", "w") as f:
    f.write(content + new_tests_embed)


with open("tests/test_process_document.py", "r") as f:
    content = f.read()

content = content.split('\n@patch("app.tasks.process_document.SessionLocal")')[0]

new_tests_process = r"""
@patch("app.tasks.process_document.SessionLocal")
@patch("app.tasks.process_document.settings")
@patch("app.tasks.process_document.extract_metadata_with_gpt")
@patch("app.utils.webhook.dispatch_webhook_event")
@patch("app.tasks.process_document.os.path.realpath")
def test_process_document_webhook_dispatch_success(
    mock_realpath, mock_webhook, mock_extract, mock_settings, mock_session_local, db_session, tmp_path
):
    test_pdf = tmp_path / "test.pdf"
    test_pdf.write_bytes(b"%PDF-1.4\n")
    mock_settings.workdir = str(tmp_path)
    mock_session_local.return_value.__enter__.return_value = db_session
    mock_session_local.return_value.__exit__.return_value = None
    mock_realpath.side_effect = lambda path: path  # Bypass realpath check

    from app.models import Pipeline, PipelineRoutingRule
    pipeline = Pipeline(name="Test Pipeline", description="Test", is_active=True)
    db_session.add(pipeline)
    db_session.commit()
    
    rule = PipelineRoutingRule(
        name="test_rule",
        target_pipeline_id=pipeline.id,
        operator="regex",
        field="original_filename",
        value=r".*test\.pdf",
        is_active=True,
        position=10
    )
    db_session.add(rule)
    db_session.commit()

    task_run_func = process_document.run
    task_run_func(str(test_pdf))

    mock_webhook.assert_called_once()
    args = mock_webhook.call_args[0]
    assert args[0] == "document.routed"
    assert "file_id" in args[1]
    assert args[1]["pipeline_id"] == pipeline.id

@patch("app.tasks.process_document.SessionLocal")
@patch("app.tasks.process_document.settings")
@patch("app.tasks.process_document.extract_metadata_with_gpt")
@patch("app.utils.webhook.dispatch_webhook_event")
@patch("app.tasks.process_document.os.path.realpath")
def test_process_document_webhook_dispatch_error(
    mock_realpath, mock_webhook, mock_extract, mock_settings, mock_session_local, db_session, tmp_path, caplog
):
    test_pdf = tmp_path / "test.pdf"
    test_pdf.write_bytes(b"%PDF-1.4\n")
    mock_settings.workdir = str(tmp_path)
    mock_session_local.return_value.__enter__.return_value = db_session
    mock_session_local.return_value.__exit__.return_value = None
    mock_realpath.side_effect = lambda path: path  # Bypass realpath check

    from app.models import Pipeline, PipelineRoutingRule
    pipeline = Pipeline(name="Test Pipeline", description="Test", is_active=True)
    db_session.add(pipeline)
    db_session.commit()
    rule = PipelineRoutingRule(
        name="test_rule",
        target_pipeline_id=pipeline.id,
        operator="regex",
        field="original_filename",
        value=r".*test\.pdf",
        is_active=True,
        position=10
    )
    db_session.add(rule)
    db_session.commit()

    mock_webhook.side_effect = Exception("Webhook boom")
    
    task_run_func = process_document.run
    task_run_func(str(test_pdf))

    assert "Failed to dispatch document.routed webhook: Webhook boom" in caplog.text
"""
with open("tests/test_process_document.py", "w") as f:
    f.write(content + new_tests_process)
