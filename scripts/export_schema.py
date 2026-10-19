"""Write the JSON Schema of the public data models to docs/schema/."""

import json
from pathlib import Path

from bts.sim.models import Event, Match

OUT = Path(__file__).resolve().parent.parent / "docs" / "schema"


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    for model, name in ((Event, "event"), (Match, "match")):
        path = OUT / f"{name}.schema.json"
        path.write_text(json.dumps(model.model_json_schema(), indent=2) + "\n")
        print(f"wrote {path.relative_to(OUT.parent.parent)}")


if __name__ == "__main__":
    main()
