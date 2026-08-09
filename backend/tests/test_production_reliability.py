import re
from pathlib import Path


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]


def test_production_backend_has_dedicated_egress_without_exposing_app_network() -> None:
    compose = (REPOSITORY_ROOT / "docker-compose.production.yml").read_text(encoding="utf-8")
    backend = compose.split("\n  frontend:", 1)[0].split("\n  backend:", 1)[1]
    networks = compose.split("\nnetworks:\n", 1)[1]

    assert re.search(
        r"\n    networks:\n(?:      - [^\n]+\n)*      - app\n(?:      - [^\n]+\n)*      - egress\n",
        backend,
    )
    assert re.search(r"^  app:\n    internal: true$", networks, re.MULTILINE)
    assert re.search(
        r"^  egress:\n    driver: bridge\n    internal: false$",
        networks,
        re.MULTILINE,
    )
