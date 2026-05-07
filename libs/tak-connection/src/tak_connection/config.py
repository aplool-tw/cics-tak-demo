from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field, field_validator


class TakConnectionConfig(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    host: str
    port: int = Field(default=8089, ge=1, le=65535)
    use_ssl: bool = True
    use_ssl_verify: bool = False
    cert_file: str | None = None
    cert_password: str | None = None
    ca_bundle: str | None = None

    @field_validator("host")
    @classmethod
    def _non_empty_host(cls, v: str) -> str:
        if not v:
            raise ValueError("host must not be empty")
        return v

    @field_validator("cert_password", mode="before")
    @classmethod
    def _empty_to_none(cls, v: object) -> object:
        if v == "":
            return None
        return v
