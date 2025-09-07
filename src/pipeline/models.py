from __future__ import annotations
from pydantic import BaseModel, Field, field_validator
from typing import List, Optional


class Company(BaseModel):
    id: str
    name: str
    ticker: Optional[str] = None
    chainIds: List[str] = Field(default_factory=list)
    voucherTypes: List[str] = Field(default_factory=list)
    notes: Optional[str] = None
    url: Optional[str] = None


class Chain(BaseModel):
    id: str
    displayName: str
    category: str
    companyIds: List[str] = Field(default_factory=list)
    voucherTypes: List[str] = Field(default_factory=list)
    tags: List[str] = Field(default_factory=list)
    url: Optional[str] = None


class Store(BaseModel):
    id: str
    chainId: str
    name: str
    address: str = ""
    lat: float
    lng: float
    tags: List[str] = Field(default_factory=list)
    updatedAt: str


class Catalog(BaseModel):
    version: str
    companies: List[Company]
    chains: List[Chain]
    stores: List[Store]
