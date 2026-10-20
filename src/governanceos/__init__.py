"""Open-source tools from GovernanceOS (Apache-2.0). https://governanceos.si"""
from .goslint import VERSION as LINTER_VERSION
from .verify import VERSION as VERIFIER_VERSION

__version__ = "0.3.0"
__all__ = ["__version__", "VERIFIER_VERSION", "LINTER_VERSION"]
