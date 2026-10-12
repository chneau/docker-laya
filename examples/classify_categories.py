#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.14"
# dependencies = ["httpx>=0.28", "pydantic>=2.7", "python-dotenv>=1.2", "pyyaml>=6"]
# ///
"""Classify messages into categories using this project's HTTP API."""

from pathlib import Path
from typing import Any, Literal

import httpx
import yaml
from dotenv import dotenv_values
from pydantic import BaseModel


class CategoryPrediction(BaseModel):
    """Chosen category and confidence values returned by the API."""

    type: Literal["choice"]
    choice: str
    confidence: float
    probabilities: dict[str, float]


class PredictionResponse(BaseModel):
    """Part of the response needed to read the predicted category."""

    answers: dict[str, CategoryPrediction]


class LayaCategoryClient:
    """Adapter that turns categories and descriptions into a choice question."""

    def __init__(self, client: httpx.Client, auth: httpx.BasicAuth) -> None:
        """Reuse the HTTP connection and Basic authentication across messages."""
        self._client = client
        self._auth = auth
        # Laya truncates each option to ~26 tokens when there are nine of them, so descriptions stay short
        # and lead with the words that tell categories apart.
        self.categories: dict[str, str] = {
            "Court Certificates": "Court clearance certificate confirming no criminal or civil records.",
            "Lawsuits": "Ongoing legal action: plaintiff, defendant, claim amount, petition, ruling.",
            "Bank Debt": "Bank credit agreement, loan, financing, installments, interest.",
            "Supplier Debt": "Payables to suppliers: open invoices, bills, purchase orders.",
            "Labor Debt": "Amounts owed to employees: severance, unpaid wages, pension contributions.",
            "Partner Assets": "Personal assets of the partners: real estate, vehicles held by individuals.",
            "Company Assets": "Company-owned assets: real estate, vehicles, machinery of the legal entity.",
            "Bank Statements": "Bank statement: branch, account, period, debits, credits, balance.",
            "Tax Debt": "Tax amounts owed: assessment, active debt, penalty notice, tax return.",
        }

    def classify(self, text: str, categories: dict[str, str] | None = None) -> CategoryPrediction:
        """Classify with the given dictionary, or with the client's default categories."""
        text = text.lower().strip()
        categories = categories if categories else self.categories

        response = self._client.post(
            "http://localhost:8000/predict",
            auth=self._auth,
            json=self._payload(text, categories),
            timeout=120.0,
        )
        response.raise_for_status()
        prediction = PredictionResponse.model_validate(response.json()).answers["category"]
        return prediction

    @staticmethod
    def _payload(text: str, categories: dict[str, str]) -> dict[str, Any]:
        """Send each category and its description in the question criteria map."""
        return {
            "state": text,
            "model": "english",
            "questions": {
                "category": {
                    "type": "choice",
                    "instructions": "Which category best represents the text of the document?",
                    "criteria": categories,
                }
            },
        }


class SampleDocument(BaseModel):
    """Sample document with its filename and extracted text."""

    filename: str
    content: str


class SampleDocumentRepository:
    """Repository that reads the sample documents from YAML and fills the placeholders."""

    def __init__(self, source: Path, placeholders: dict[str, str]) -> None:
        """Store the source file and the values that replace the placeholders."""
        self._source = source
        self._placeholders = placeholders

    def load(self) -> list[SampleDocument]:
        """Read every document, failing if the text uses an unknown placeholder."""
        raw = yaml.safe_load(self._source.read_text(encoding="utf-8"))
        return [self._render(SampleDocument.model_validate(item)) for item in raw["documents"]]

    def _render(self, document: SampleDocument) -> SampleDocument:
        """Replace the content placeholders with the fictional values."""
        return document.model_copy(update={"content": document.content.format_map(self._placeholders)})


class ClassificationExample:
    """Executable example using the client's document category dictionary."""

    DOCUMENTS_FILE = Path(__file__).with_name("documents.yml")
    PLACEHOLDERS: dict[str, str] = {
        "tax_id": "12-3456789",
        "company_name": "Vanguard Trading Inc.",
        "address": "123 Flower Street, Garden District, Springfield, IL 50000",
    }

    @classmethod
    def run(cls) -> None:
        """Classify the messages assuming the API is already running in Docker."""
        auth = cls._authentication(Path(__file__).resolve().parents[1] / ".env")
        documents = SampleDocumentRepository(cls.DOCUMENTS_FILE, cls.PLACEHOLDERS).load()
        with httpx.Client() as client:
            classifier = LayaCategoryClient(client, auth)
            for document in documents:
                prediction = classifier.classify(document.content)
                print(f"\nDocument: {document.filename}")
                print(f"Category: {prediction.choice}")
                print(f"Confidence: {prediction.confidence:.4f}")
                print(f"Probabilities: {prediction.probabilities}")
                print("----------------------------------------------------")

    @staticmethod
    def _authentication(env_file: Path) -> httpx.BasicAuth:
        """Read the first BASIC_AUTH pair from .env, preserving colons in the password."""
        configuration = dotenv_values(env_file, interpolate=False)
        for credentials in (configuration.get("BASIC_AUTH") or "").split(","):
            if ":" in credentials:
                username, password = credentials.split(":", 1)
                return httpx.BasicAuth(username.strip(), password.strip())
        raise ValueError(f"Configure BASIC_AUTH as user:password in {env_file}.")


if __name__ == "__main__":
    ClassificationExample.run()
