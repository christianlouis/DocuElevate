#!/usr/bin/env python3

from .database import Base
from sqlalchemy import Column, String, Integer

class DocumentMetadata(Base):
    __tablename__ = "documents"

    id = Column(Integer, primary_key=True, index=True)
    filename = Column(String, unique=True, index=True)
    sender = Column(String)
    recipient = Column(String)
    tags = Column(String)
    summary = Column(String)
