"""Swagger (/docs) documentation of the restricted-list service, apart from
the code (like backend/docs/*.docs.js in NexoEDU).

Each endpoint gets a dict passed as @app.get(path, **DICT). The examples
match the restricted-list page in Docusaurus; change both together.
"""

DESCRIPTION = """
Simulated external provider of restricted lists (sanctions and PEP). It is
slow and unreliable on purpose: every call except `/health` waits a random
50 to 3000 ms and about 5 % answer `503`, so the engine has to cut by time
and fall back to its cache.

Full documentation: https://securepay-riwi.github.io/SecurePay/docs/components/restricted-list
""".strip()

# Passed as FastAPI(**APP).
APP = {
    "title": "Restricted-list provider (simulated)",
    "version": "1.0.0",
    "description": DESCRIPTION,
    "openapi_tags": [
        {"name": "Restricted list", "description": "Read the provider's list."},
        {"name": "Health", "description": "Liveness check, with no latency and no failures."},
    ],
}

_PROVIDER_DOWN = {
    503: {
        "description": "Simulated provider outage (about 5 % of calls, after the wait).",
        "content": {
            "application/json": {"example": {"detail": "Proveedor no disponible"}}
        },
    }
}

_LISTED = {"documento": "1000000016", "tipo": "sanciones", "fecha_inclusion": "2023-06-13"}

HEALTH = {
    "summary": "Check that the service is up",
    "tags": ["Health"],
    "responses": {
        200: {
            "description": "Up, with the number of people loaded.",
            "content": {"application/json": {"example": {"status": "ok", "total": 20}}},
        }
    },
}

FULL_LIST = {
    "summary": "Get the full list",
    "description": "Used by the daily task that loads the list into the engine's cache.",
    "tags": ["Restricted list"],
    "responses": {
        200: {
            "description": "Every listed person.",
            "content": {
                "application/json": {"example": {"total": 20, "registros": [_LISTED]}}
            },
        },
        **_PROVIDER_DOWN,
    },
}

CHECK_DOCUMENT = {
    "summary": "Check one document",
    "description": (
        "The engine calls it only when its cache is not available. "
        "Anything that is not a digit is ignored (`1.000.000.016` = "
        "`1000000016`). A person who is not listed is still a `200` "
        "with `listado: false`, never a `404`."
    ),
    "tags": ["Restricted list"],
    "responses": {
        200: {
            "description": "The provider answered.",
            "content": {
                "application/json": {
                    "examples": {
                        "listed": {
                            "summary": "Listed",
                            "value": {"listado": True, **_LISTED},
                        },
                        "not_listed": {
                            "summary": "Not listed",
                            "value": {"documento": "1000000099", "listado": False},
                        },
                    }
                }
            },
        },
        400: {
            "description": "The document has no digits.",
            "content": {
                "application/json": {"example": {"detail": "El documento no tiene dígitos"}}
            },
        },
        **_PROVIDER_DOWN,
    },
}

DOCUMENT_PARAM = {
    "description": "Document number, with or without dots or dashes.",
    "examples": ["1000000016"],
}


def hide_validation_error(app) -> None:
    """FastAPI adds a 422 to every endpoint with parameters, but a text path
    parameter can never fail validation here: hide it from Swagger."""
    build = app.openapi

    def openapi():
        if app.openapi_schema is None:
            schema = build()
            schema["paths"]["/lista/{documento}"]["get"]["responses"].pop("422", None)
            schema.get("components", {}).get("schemas", {}).pop("HTTPValidationError", None)
            schema.get("components", {}).get("schemas", {}).pop("ValidationError", None)
            if not schema.get("components", {}).get("schemas"):
                schema.pop("components", None)
        return app.openapi_schema

    app.openapi = openapi
