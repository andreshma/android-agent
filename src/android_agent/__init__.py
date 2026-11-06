"""android-agent: an LLM-driven assistant for YOUR OWN Android device."""

from importlib.metadata import PackageNotFoundError, version

try:
    __version__ = version("android-agent")
except PackageNotFoundError:  # pragma: no cover - not installed as a distribution
    __version__ = "0.0.0+unknown"
