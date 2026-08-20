import ast
from pathlib import Path

APP_ROOT = Path(__file__).parents[1] / "app"


def imported_modules(directory: str) -> set[str]:
    modules: set[str] = set()
    for path in (APP_ROOT / directory).rglob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and node.module:
                modules.add(node.module)
            elif isinstance(node, ast.Import):
                modules.update(alias.name for alias in node.names)
    return modules


def assert_no_forbidden_imports(directory: str, forbidden: tuple[str, ...]) -> None:
    violations = sorted(
        module
        for module in imported_modules(directory)
        if any(module == prefix or module.startswith(f"{prefix}.") for prefix in forbidden)
    )
    assert violations == [], f"{directory} imports forbidden modules: {violations}"


def test_domain_is_framework_and_infra_independent() -> None:
    assert_no_forbidden_imports(
        "domain",
        (
            "fastapi",
            "pydantic",
            "PIL",
            "google",
            "cachetools",
            "app.api",
            "app.infra",
            "app.schemas",
            "app.services",
        ),
    )


def test_services_depend_on_ports_not_transport_or_infra() -> None:
    assert_no_forbidden_imports(
        "services",
        (
            "fastapi",
            "pydantic",
            "PIL",
            "google",
            "cachetools",
            "app.api",
            "app.infra",
            "app.schemas",
        ),
    )


def test_api_and_schemas_do_not_reach_into_infra() -> None:
    assert_no_forbidden_imports("api", ("app.infra",))
    assert_no_forbidden_imports(
        "schemas",
        ("app.api", "app.infra", "app.services"),
    )
