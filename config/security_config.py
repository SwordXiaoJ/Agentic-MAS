"""
Security Configuration for SLIM Transport

Prepares for future security upgrades while maintaining backward compatibility.

Security Phases:
- Phase 1 (Current): Insecure mode for development
- Phase 2: TLS + Basic Auth
- Phase 3: TLS + JWT Authentication
- Phase 4: mTLS + SPIRE (Zero Trust)

Usage:
    from config.security_config import get_security_config

    config = get_security_config()
    if config.is_secure:
        # Use secure transport settings
        pass
"""

import os
from enum import Enum
from dataclasses import dataclass, field
from typing import Optional, List


class AuthMode(Enum):
    """Authentication modes for SLIM transport"""
    INSECURE = "insecure"   # No auth (development only)
    BASIC = "basic"         # Basic username/password
    JWT = "jwt"             # JWT token authentication
    MTLS = "mtls"           # Mutual TLS with client certs
    SPIRE = "spire"         # SPIRE workload identity


@dataclass
class TLSConfig:
    """TLS configuration for secure connections"""
    enabled: bool = False
    cert_path: Optional[str] = None
    key_path: Optional[str] = None
    ca_path: Optional[str] = None
    insecure_skip_verify: bool = False

    @property
    def is_configured(self) -> bool:
        """Check if TLS is properly configured"""
        if not self.enabled:
            return True  # Not enabled is valid
        return bool(self.cert_path and self.key_path)


@dataclass
class BasicAuthConfig:
    """Basic authentication configuration"""
    username: Optional[str] = None
    password: Optional[str] = None

    @property
    def is_configured(self) -> bool:
        return bool(self.username and self.password)


@dataclass
class JWTConfig:
    """JWT authentication configuration"""
    issuer: Optional[str] = None
    audience: List[str] = field(default_factory=list)
    private_key_path: Optional[str] = None
    public_key_path: Optional[str] = None
    algorithm: str = "ES256"
    duration_hours: int = 1

    @property
    def is_configured(self) -> bool:
        return bool(self.issuer and self.private_key_path)


@dataclass
class SPIREConfig:
    """SPIRE workload identity configuration"""
    socket_path: Optional[str] = None
    trust_domain: Optional[str] = None
    target_spiffe_id: Optional[str] = None
    jwt_audiences: List[str] = field(default_factory=list)

    @property
    def is_configured(self) -> bool:
        return bool(self.socket_path)


@dataclass
class MLSConfig:
    """Message Layer Security (end-to-end encryption) configuration"""
    enabled: bool = False
    shared_secret: str = "slim-mls-secret"  # Default for development


@dataclass
class SecurityConfig:
    """
    Complete security configuration for SLIM transport.

    Attributes:
        auth_mode: Authentication mode to use
        tls: TLS configuration
        basic_auth: Basic auth credentials
        jwt: JWT configuration
        spire: SPIRE configuration
        mls: MLS end-to-end encryption
    """
    auth_mode: AuthMode = AuthMode.INSECURE
    tls: TLSConfig = field(default_factory=TLSConfig)
    basic_auth: BasicAuthConfig = field(default_factory=BasicAuthConfig)
    jwt: JWTConfig = field(default_factory=JWTConfig)
    spire: SPIREConfig = field(default_factory=SPIREConfig)
    mls: MLSConfig = field(default_factory=MLSConfig)

    @property
    def is_secure(self) -> bool:
        """Check if running in secure mode"""
        return self.auth_mode != AuthMode.INSECURE

    @property
    def is_insecure(self) -> bool:
        """Check if running in insecure mode (development)"""
        return self.auth_mode == AuthMode.INSECURE

    def get_transport_tls_config(self) -> dict:
        """
        Get TLS configuration for transport layer.

        Returns:
            Dict with TLS settings for SLIM transport
        """
        if self.is_insecure or not self.tls.enabled:
            return {"insecure": True}

        config = {"insecure": False}

        if self.tls.ca_path:
            config["ca_path"] = self.tls.ca_path
        if self.tls.insecure_skip_verify:
            config["insecure_skip_verify"] = True

        return config

    def get_slim_transport_kwargs(self) -> dict:
        """
        Get kwargs for SLIMTransport based on current security config.

        Returns kwargs compatible with SLIMTransport.__init__():
        - tls_insecure: bool (True = skip TLS verification)
        - shared_secret_identity: str (MLS shared secret)
        - jwt: str (JWT token for authentication)
        - bundle: str (SPIRE bundle path)
        - audience: list[str] (JWT audience)

        Returns:
            Dict of kwargs to pass to SLIMTransport or factory.create_transport()
        """
        kwargs = {}

        # TLS configuration
        # tls_insecure=True means skip TLS verification (insecure mode)
        # tls_insecure=False means require valid TLS certificates
        if self.tls.enabled:
            kwargs["tls_insecure"] = self.tls.insecure_skip_verify
        else:
            kwargs["tls_insecure"] = True  # Default: insecure

        # MLS shared secret for end-to-end encryption
        if self.mls.enabled or self.is_insecure:
            kwargs["shared_secret_identity"] = self.mls.shared_secret

        # JWT authentication
        if self.auth_mode == AuthMode.JWT and self.jwt.is_configured:
            # Note: JWT token needs to be generated at runtime
            # This is a placeholder - actual token generation happens elsewhere
            if self.jwt.audience:
                kwargs["audience"] = self.jwt.audience

        # SPIRE configuration
        if self.auth_mode == AuthMode.SPIRE and self.spire.is_configured:
            # bundle path would be set here if available
            pass

        return kwargs

    def get_identity_config(self) -> dict:
        """
        Get identity provider configuration based on auth mode.

        Returns:
            Dict with identity settings for SLIM
        """
        if self.auth_mode == AuthMode.INSECURE:
            return {
                "type": "shared_secret",
                "shared_secret": self.mls.shared_secret,
            }
        elif self.auth_mode == AuthMode.BASIC:
            return {
                "type": "basic",
                "username": self.basic_auth.username,
                "password": self.basic_auth.password,
            }
        elif self.auth_mode == AuthMode.JWT:
            return {
                "type": "jwt",
                "issuer": self.jwt.issuer,
                "audience": self.jwt.audience,
                "private_key_path": self.jwt.private_key_path,
                "algorithm": self.jwt.algorithm,
            }
        elif self.auth_mode == AuthMode.SPIRE:
            return {
                "type": "spire",
                "socket_path": self.spire.socket_path,
                "trust_domain": self.spire.trust_domain,
            }
        else:
            return {"type": "shared_secret", "shared_secret": self.mls.shared_secret}


def load_security_config() -> SecurityConfig:
    """
    Load security configuration from environment variables.

    Environment Variables:
        SLIM_AUTH_MODE: Authentication mode (insecure, basic, jwt, mtls, spire)
        SLIM_TLS_ENABLED: Enable TLS (true/false)
        SLIM_TLS_CERT_PATH: Path to TLS certificate
        SLIM_TLS_KEY_PATH: Path to TLS private key
        SLIM_TLS_CA_PATH: Path to CA certificate
        SLIM_BASIC_USERNAME: Basic auth username
        SLIM_BASIC_PASSWORD: Basic auth password
        SLIM_JWT_ISSUER: JWT issuer
        SLIM_JWT_AUDIENCE: JWT audience (comma-separated)
        SLIM_JWT_PRIVATE_KEY_PATH: Path to JWT private key
        SLIM_JWT_PUBLIC_KEY_PATH: Path to JWT public key
        SLIM_MLS_ENABLED: Enable MLS encryption (true/false)
        SLIM_SHARED_SECRET: Shared secret for MLS
        SPIRE_AGENT_SOCKET: SPIRE agent socket path
        SPIRE_TRUST_DOMAIN: SPIRE trust domain

    Returns:
        SecurityConfig instance
    """
    # Parse auth mode
    auth_mode_str = os.getenv("SLIM_AUTH_MODE", "insecure").lower()
    try:
        auth_mode = AuthMode(auth_mode_str)
    except ValueError:
        auth_mode = AuthMode.INSECURE

    # Parse TLS config
    tls = TLSConfig(
        enabled=os.getenv("SLIM_TLS_ENABLED", "false").lower() == "true",
        cert_path=os.getenv("SLIM_TLS_CERT_PATH"),
        key_path=os.getenv("SLIM_TLS_KEY_PATH"),
        ca_path=os.getenv("SLIM_TLS_CA_PATH"),
        insecure_skip_verify=os.getenv("SLIM_TLS_SKIP_VERIFY", "false").lower() == "true",
    )

    # Parse Basic auth
    basic_auth = BasicAuthConfig(
        username=os.getenv("SLIM_BASIC_USERNAME"),
        password=os.getenv("SLIM_BASIC_PASSWORD"),
    )

    # Parse JWT config
    jwt_audience_str = os.getenv("SLIM_JWT_AUDIENCE", "")
    jwt_audience = [a.strip() for a in jwt_audience_str.split(",") if a.strip()]

    jwt = JWTConfig(
        issuer=os.getenv("SLIM_JWT_ISSUER"),
        audience=jwt_audience,
        private_key_path=os.getenv("SLIM_JWT_PRIVATE_KEY_PATH"),
        public_key_path=os.getenv("SLIM_JWT_PUBLIC_KEY_PATH"),
        algorithm=os.getenv("SLIM_JWT_ALGORITHM", "ES256"),
        duration_hours=int(os.getenv("SLIM_JWT_DURATION_HOURS", "1")),
    )

    # Parse SPIRE config
    spire_audiences_str = os.getenv("SPIRE_JWT_AUDIENCES", "")
    spire_audiences = [a.strip() for a in spire_audiences_str.split(",") if a.strip()]

    spire = SPIREConfig(
        socket_path=os.getenv("SPIRE_AGENT_SOCKET"),
        trust_domain=os.getenv("SPIRE_TRUST_DOMAIN"),
        target_spiffe_id=os.getenv("SPIRE_TARGET_SPIFFE_ID"),
        jwt_audiences=spire_audiences,
    )

    # Parse MLS config
    mls = MLSConfig(
        enabled=os.getenv("SLIM_MLS_ENABLED", "false").lower() == "true",
        shared_secret=os.getenv("SLIM_SHARED_SECRET", "slim-mls-secret"),
    )

    return SecurityConfig(
        auth_mode=auth_mode,
        tls=tls,
        basic_auth=basic_auth,
        jwt=jwt,
        spire=spire,
        mls=mls,
    )


# Global singleton for convenience
_security_config: Optional[SecurityConfig] = None


def get_security_config() -> SecurityConfig:
    """
    Get the global security configuration (singleton).

    Returns:
        SecurityConfig instance
    """
    global _security_config
    if _security_config is None:
        _security_config = load_security_config()
    return _security_config


def reset_security_config():
    """Reset the global security config (useful for testing)"""
    global _security_config
    _security_config = None


def print_security_config():
    """Print current security configuration (for debugging)"""
    config = get_security_config()
    print()
    print("=" * 60)
    print("Security Configuration")
    print("=" * 60)
    print(f"Auth Mode: {config.auth_mode.value}")
    print(f"Is Secure: {config.is_secure}")
    print(f"TLS Enabled: {config.tls.enabled}")
    print(f"MLS Enabled: {config.mls.enabled}")
    if config.auth_mode == AuthMode.BASIC:
        print(f"Basic Auth User: {config.basic_auth.username}")
    elif config.auth_mode == AuthMode.JWT:
        print(f"JWT Issuer: {config.jwt.issuer}")
    elif config.auth_mode == AuthMode.SPIRE:
        print(f"SPIRE Socket: {config.spire.socket_path}")
    print("=" * 60)
    print()
