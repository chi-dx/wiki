from pydantic import BaseModel, Field, field_validator


class Document(BaseModel):
    id: str = Field(min_length=1, max_length=100, pattern=r"^[a-zA-Z0-9_-]+$")
    title: str = Field(min_length=1, max_length=200)
    category: str = Field(min_length=1, max_length=100)
    body: str = Field(min_length=1, max_length=200_000)
    tags: list[str] = Field(default_factory=list, max_length=30)
    version: str | None = None
    updated_at: str | None = None
    url: str = ""
    fictional: bool = False

    @field_validator("url")
    @classmethod
    def safe_url(cls, value):
        if value and not value.startswith(("https://", "http://")):
            raise ValueError("Source URL must be HTTP(S)")
        return value


class Evidence(BaseModel):
    evidence_id: str
    source_type: str
    source_name: str
    title: str
    url: str
    text: str = Field(min_length=1, max_length=20000)
    updated_at: str | None = None
    fictional: bool = False
    citation: int = 0
    wiki_page: str | None = None
    wiki_summary: str | None = None
    wiki_context: str | None = None

    @field_validator("url")
    @classmethod
    def safe_url(cls, value):
        if not (value.startswith(("https://", "http://")) or
                value.startswith("/documents/") or value.startswith("/reference/") or value.startswith("/compiler/pages/")):
            raise ValueError("Invalid evidence URL")
        return value


class AskRequest(BaseModel):
    question: str = Field(min_length=2, max_length=1000)
    include_external: bool = True

    @field_validator("question")
    @classmethod
    def clean_question(cls, value):
        value = value.strip()
        if len(value) < 2:
            raise ValueError("请输入至少两个字的问题")
        return value


class FeedbackRequest(BaseModel):
    request_id: str = Field(min_length=1, max_length=64)
    solved: bool
    reason: str = Field(default="", max_length=1000)
