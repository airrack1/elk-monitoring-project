from pathlib import Path


WORKFLOW = Path(__file__).parents[2] / ".github" / "workflows" / "ci.yml"


def test_checkout_free_deploy_job_uses_existing_workspace():
    text = WORKFLOW.read_text(encoding="utf-8")
    deploy_job = text.split("\n  deploy:\n", 1)[1]

    assert "working-directory: ." in deploy_job
    assert "uses: actions/checkout" not in deploy_job
