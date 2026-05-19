from app.agents.content_creator import ContentCreator


def test_content_creator_runs():
    text = ContentCreator().run()
    assert isinstance(text, str)
    assert len(text) >= 10
