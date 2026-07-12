"""Regression coverage for immutable per-file workflow plans."""

import json

import pytest

from app.models import FileProcessingStep, FileRecord, Pipeline, PipelineStep
from app.utils.step_manager import initialize_file_steps
from app.utils.workflow_plan import load_workflow_plan, snapshot_workflow_plan, workflow_stage_keys


@pytest.mark.integration
@pytest.mark.requires_db
class TestWorkflowPlan:
    def _file_with_pipeline(self, db_session):
        pipeline = Pipeline(name="Invoice flow", is_active=True, is_default=False)
        db_session.add(pipeline)
        db_session.flush()
        db_session.add_all(
            [
                PipelineStep(pipeline_id=pipeline.id, position=20, step_type="extract_metadata", enabled=True),
                PipelineStep(pipeline_id=pipeline.id, position=10, step_type="ocr", enabled=True),
                PipelineStep(pipeline_id=pipeline.id, position=30, step_type="embed_metadata", enabled=False),
            ]
        )
        file_record = FileRecord(
            filehash="workflow-plan-hash",
            original_filename="invoice.pdf",
            local_filename="/tmp/invoice.pdf",
            file_size=100,
            mime_type="application/pdf",
            pipeline_id=pipeline.id,
            pipeline_assignment_source="manual",
        )
        db_session.add(file_record)
        db_session.commit()
        return file_record, pipeline

    def test_snapshot_is_ordered_and_excludes_disabled_steps(self, db_session):
        file_record, _pipeline = self._file_with_pipeline(db_session)

        plan = snapshot_workflow_plan(db_session, file_record)
        db_session.commit()

        assert [step["step_type"] for step in plan["steps"]] == ["ocr", "extract_metadata"]
        assert workflow_stage_keys(file_record) == [
            "create_file_record",
            "check_text",
            "extract_text",
            "process_with_ocr",
            "extract_metadata_with_gpt",
        ]

    def test_snapshot_does_not_drift_when_pipeline_is_edited(self, db_session):
        file_record, pipeline = self._file_with_pipeline(db_session)
        snapshot_workflow_plan(db_session, file_record)
        db_session.commit()

        db_session.query(PipelineStep).filter(PipelineStep.pipeline_id == pipeline.id).delete()
        db_session.commit()

        persisted = load_workflow_plan(file_record)
        assert persisted is not None
        assert [step["step_type"] for step in persisted["steps"]] == ["ocr", "extract_metadata"]

    def test_status_rows_are_initialized_from_snapshot(self, db_session):
        file_record, _pipeline = self._file_with_pipeline(db_session)
        snapshot_workflow_plan(db_session, file_record)
        initialize_file_steps(db_session, file_record.id, workflow_stages=workflow_stage_keys(file_record))

        names = {
            row.step_name
            for row in db_session.query(FileProcessingStep).filter(FileProcessingStep.file_id == file_record.id).all()
        }
        assert "process_with_ocr" in names
        assert "extract_metadata_with_gpt" in names
        assert "embed_metadata_into_pdf" not in names
        assert file_record.workflow_plan_version == 1
        assert json.loads(file_record.workflow_plan)["pipeline_id"] == file_record.pipeline_id
