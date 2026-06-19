from fastapi import APIRouter

from app.pipeline.runbooks.templates import get_all_template_descriptions

router = APIRouter()


@router.get("/pipeline-templates")
def list_pipeline_templates():
    return get_all_template_descriptions()
