from pydantic import BaseModel, Field


class Config(BaseModel):
    catcake_api_base: str = Field(default="https://catcs.v6.army", description="猫猫糕 API 基础地址")
    catcake_default_server: str = Field(default="官服", description="默认服务器")
    catcake_timeout: float = Field(default=10.0, description="HTTP 请求超时时间（秒）")
