"""
api/responses.py — orjson-powered FastAPI response class

Reasoning:
- FastAPI's default JSONResponse uses Python's stdlib json module,
  which cannot serialise NumPy arrays, datetime, UUID, or Decimal.
- orjson handles all of these natively and is 5-10x faster than stdlib json.
- Subclassing JSONResponse and overriding render() is the FastAPI-idiomatic
  way to swap the JSON serialiser globally.
- OPT_SERIALIZE_NUMPY: serialises np.ndarray, np.float32, np.int64, etc.
- OPT_NON_STR_KEYS: allows dict keys that are integers or other non-str types.
- OPT_UTC_Z: renders UTC datetimes as "2024-01-15T09:30:00Z" not "+00:00".
"""

import orjson
from fastapi.responses import JSONResponse


class OrjsonResponse(JSONResponse):
    """
    Drop-in replacement for FastAPI's JSONResponse using orjson.
    Usage: return OrjsonResponse(content=result_dict)
    Or set as default: app = FastAPI(default_response_class=OrjsonResponse)
    """

    media_type = "application/json"

    def render(self, content: object) -> bytes:
        return orjson.dumps(
            content,
            option=(
                orjson.OPT_SERIALIZE_NUMPY   # numpy arrays → JSON arrays natively
                | orjson.OPT_NON_STR_KEYS    # int/float dict keys allowed
                | orjson.OPT_UTC_Z           # UTC datetimes as "Z" suffix
            ),
        )
