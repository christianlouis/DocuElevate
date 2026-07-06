"""Shared mapping between processing profile steps and status/log stages."""

from collections.abc import Iterable

PIPELINE_STEP_TO_STAGES: dict[str, list[str]] = {
    "convert_to_pdf": ["convert_to_pdf"],
    "check_duplicates": ["check_for_duplicates"],
    "ocr": ["check_text", "extract_text", "process_with_ocr"],
    "extract_metadata": ["extract_metadata_with_gpt"],
    "embed_metadata": ["embed_metadata_into_pdf"],
    "compute_embedding": ["compute_embedding"],
    "send_to_destinations": ["finalize_document_storage", "send_to_all_destinations"],
    "classify": ["classify_document"],
}

ALWAYS_SHOW_STAGES: frozenset[str] = frozenset({"create_file_record"})

LEGACY_STAGE_ALIASES: dict[str, str] = {
    "process_with_azure_document_intelligence": "process_with_ocr",
}


def normalize_stage_name(step_name: str) -> str:
    """Return the current stage key for legacy log/status names."""
    return LEGACY_STAGE_ALIASES.get(step_name, step_name)


def stage_keys_for_pipeline_steps(pipeline_steps: Iterable | None) -> set[str] | None:
    """Return expected status/log stages for enabled profile steps."""
    if pipeline_steps is None:
        return None

    stage_keys: set[str] = set(ALWAYS_SHOW_STAGES)
    for pipeline_step in pipeline_steps:
        if getattr(pipeline_step, "enabled", False):
            stage_keys.update(PIPELINE_STEP_TO_STAGES.get(pipeline_step.step_type, []))
    return stage_keys
