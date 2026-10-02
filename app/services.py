"""Model runtime, native prediction and the SystemOne adapter."""

from collections.abc import AsyncGenerator, Mapping
from contextlib import asynccontextmanager
from threading import Lock
from typing import NamedTuple, cast, get_args

from fastapi import FastAPI, HTTPException

from app.backend import LayaBackend, PredictionRouter, QuestionDefinitions
from app.config import AVAILABLE_MODELS, Settings
from app.schemas import (
    BulkItemResult,
    BulkPredictRequest,
    BulkPredictResponse,
    HealthResponse,
    ModelName,
    ModelsResponse,
    PredictRequest,
    PredictResponse,
    PresetName,
    Question,
    State,
    SystemOneRequest,
    SystemOneResponse,
)


class ModelRuntime:
    """Owns the router for the lifetime of one application."""

    def __init__(self, settings: Settings, backend: LayaBackend) -> None:
        self._settings = settings
        self._backend = backend
        self._router: PredictionRouter | None = None
        # Serializes inference across native, bulk and SystemOne requests.
        self.lock = Lock()

    @asynccontextmanager
    async def lifespan(self, app: FastAPI) -> AsyncGenerator[None]:
        """Load checkpoints at startup and drop the router on shutdown."""
        self._router = self._backend.create_router(self._settings)
        try:
            yield
        finally:
            self._router = None

    @property
    def router(self) -> PredictionRouter:
        """The loaded router; raises 503 before startup completes."""
        if self._router is None:
            raise HTTPException(status_code=503, detail="Model not loaded yet")
        return self._router

    def health(self) -> HealthResponse:
        """Readiness and configuration, available before the models load."""
        loaded = list(self._router.loaded) if self._router is not None else []
        return HealthResponse(
            status="ok",
            model_loaded=self._router is not None,
            device=self._settings.device,
            auth_enabled=self._settings.auth_enabled,
            auth_methods=self._settings.auth_methods,
            models=loaded,
            available_models=list(AVAILABLE_MODELS),
        )

    def models(self) -> ModelsResponse:
        """Available and resident checkpoints."""
        return ModelsResponse(available=list(AVAILABLE_MODELS), loaded=list(self.router.loaded))


class Job(NamedTuple):
    """One state with its resolved questions, whatever request shape it came from."""

    state: State
    questions: QuestionDefinitions
    model: ModelName | None


class PredictionService:
    """Resolves questions and runs inference under the runtime lock."""

    def __init__(self, settings: Settings, runtime: ModelRuntime, backend: LayaBackend) -> None:
        self._max_bulk_items = settings.max_bulk_items
        self._runtime = runtime
        self._backend = backend

    def predict(self, request: PredictRequest) -> PredictResponse:
        """Answer the questions for one state."""
        router = self._runtime.router
        questions = self.resolve_questions(request.questions, request.preset)
        with self._runtime.lock:
            return self._run(router, Job(request.state, questions, request.model))

    def predict_bulk(self, request: BulkPredictRequest) -> BulkPredictResponse:
        """Answer many states in order; a failing item is reported without stopping the batch."""
        jobs = self._bulk_jobs(request)
        self._check_bulk_limit(len(jobs))
        router = self._runtime.router
        # One lock for the whole batch, so other requests cannot interleave with its items.
        with self._runtime.lock:
            results = [self._run_isolated(router, job) for job in jobs]
        return BulkPredictResponse(count=len(results), results=results)

    def resolve_questions(
        self, questions: Mapping[str, Question] | None, preset: PresetName | None = None
    ) -> QuestionDefinitions:
        """A preset wins over explicit questions; unset optional fields are not sent to Laya."""
        if preset is not None:
            return self._backend.presets[preset]
        return {key: question.model_dump(exclude_none=True) for key, question in (questions or {}).items()}

    def _bulk_jobs(self, request: BulkPredictRequest) -> list[Job]:
        if not request.items:
            questions = self.resolve_questions(request.questions, request.preset)
            return [Job(state, questions, request.model) for state in request.states or []]
        return [
            Job(
                item.state,
                self.resolve_questions(item.questions or request.questions, request.preset),
                item.model or request.model,
            )
            for item in request.items
        ]

    def _check_bulk_limit(self, count: int) -> None:
        limit = self._max_bulk_items
        if limit is not None and count > limit:
            raise HTTPException(422, f"Too many states: {count} > MAX_BULK_ITEMS={limit}")

    @staticmethod
    def _run(router: PredictionRouter, job: Job) -> PredictResponse:
        result = router.predict(job.state, job.questions, model=job.model)
        return PredictResponse.model_validate(result)

    @classmethod
    def _run_isolated(cls, router: PredictionRouter, job: Job) -> BulkItemResult:
        try:
            return BulkItemResult(ok=True, result=cls._run(router, job))
        except Exception as error:  # the bulk contract reports any item failure inline
            return BulkItemResult(ok=False, error=str(error))


class SystemOneAdapter:
    """Maps SystemOne model names onto Laya checkpoints and trims the response to its shape."""

    def __init__(self, predictions: PredictionService) -> None:
        self._predictions = predictions

    @staticmethod
    def resolve_model(model_name: str) -> ModelName:
        """Accept `laya-english`, `typesafe/laya-multilingual` etc.; unknown names fall back."""
        name = model_name.lower().strip()
        for prefix in ("typesafe/", "laya/", "laya-"):
            name = name.removeprefix(prefix)
        if name in get_args(ModelName):
            return cast(ModelName, name)
        if "multi" in name:
            return "multilingual"
        if "decision" in name:
            return "typed-decisions"
        return "english"

    def predict(self, request: SystemOneRequest) -> SystemOneResponse:
        """Run a native prediction and answer with the client's own model name."""
        native = self._predictions.predict(
            PredictRequest(
                state=request.state,
                questions=request.questions,
                model=self.resolve_model(request.model),
            )
        )
        response = native.model_dump(include={"answers", "usage"})
        return SystemOneResponse.model_validate({**response, "model": request.model})
